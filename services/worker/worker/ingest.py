"""Ingestion: chunk documents, embed with Titan V2 (or the local fallback), upsert to Chroma + Postgres.

Re-ingestion is cheap: chunks whose content hash already sits in the collection are
skipped, and Titan vectors are cached by content hash in Postgres, so an unchanged
corpus never re-bills Bedrock.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timezone

from nimbus_core import db
from nimbus_core.chunking import ChunkRecord, chunk_venue_dir, report_chunk
from nimbus_core.embeddings import choose_embedder
from nimbus_core.vectorstore import VectorStore

from .seed import load_config, venue_dirs

log = logging.getLogger("worker.ingest")


class Indexer:
    def __init__(self) -> None:
        self.embedder, self.reason = choose_embedder()
        self.store = VectorStore(self.embedder.id, self.embedder.label)
        log.info("embedder: %s (%s) -> collection %s", self.embedder.label, self.reason, self.store.name)
        self._publish(0)

    def _publish(self, embedded: int) -> None:
        db.set_setting("index", {
            "embedder_id": self.embedder.id,
            "embedder_label": self.embedder.label,
            "model_id": self.embedder.model_id,
            "dim": self.embedder.dim,
            "collection": self.store.name,
            "reason": self.reason,
            "chunks": self.store.count(),
            "last_embedded": embedded,
            "built_at": datetime.now(timezone.utc).isoformat(),
        })

    def index_chunks(self, chunks: list[ChunkRecord], force: bool = False) -> int:
        if not chunks:
            return 0
        for c in chunks:
            db.upsert_chunk(c.id, c.venue_id, c.doc_id, c.text, c.header, c.meta(), c.content_hash)
        existing = {} if force else self.store.existing_hashes([c.id for c in chunks])
        todo = [c for c in chunks if existing.get(c.id) != c.content_hash]
        if not todo:
            return 0
        vectors = self.embedder.embed_documents([c.embed_text for c in todo])
        self.store.upsert(
            ids=[c.id for c in todo],
            vectors=vectors,
            documents=[c.embed_text for c in todo],
            metadatas=[{**c.meta(), "content_hash": c.content_hash} for c in todo],
        )
        return len(todo)

    def index_all(self, force: bool = False) -> int:
        total = 0
        for vdir in venue_dirs():
            cfg = load_config(vdir)
            for doc_id, meta, chunks in chunk_venue_dir(vdir, cfg):
                doc_date = meta.get("date") or None
                doc_hash = hashlib.sha256("|".join(c.content_hash for c in chunks).encode()).hexdigest()
                db.upsert_document(f"{cfg['id']}:{doc_id}", cfg["id"], meta["title"], meta["source_type"], meta["trust"],
                                   doc_date, doc_hash)
                total += self.index_chunks(chunks, force)
            total += self.index_chunks(self._live_chunks(cfg), force)
        log.info("indexed: %d chunk(s) embedded, collection now holds %d", total, self.store.count())
        self._publish(total)
        return total

    def _live_chunks(self, cfg: dict) -> list[ChunkRecord]:
        """Report chunks added at runtime (so a new embedder collection gets them too)."""
        out = []
        for r in db.list_chunks(cfg["id"]):
            if not r["doc_id"].startswith("live_"):
                continue
            m = r["meta"]
            out.append(report_chunk(cfg["id"], cfg.get("name", cfg["id"]), r["id"], m.get("source_type", "visitor_report"),
                                    r["text"], date.fromisoformat(m.get("date")), m.get("needs", "")))
        return out

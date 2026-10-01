"""Hybrid retrieval: dense (Titan V2 -> Chroma, venue-filtered) + sparse (BM25), fused with RRF."""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from nimbus_core import db
from nimbus_core.embeddings import Embedder, embedder_by_id
from nimbus_core.sparse import BM25Index
from nimbus_core.vectorstore import VectorStore

log = logging.getLogger("api.retrieval")
RRF_K = 60
MAIN_QUERY_WEIGHT = 2.0


@dataclass
class Passage:
    chunk_id: str
    doc_id: str
    doc_title: str
    source_type: str
    trust: str
    date: str
    heading: str
    text: str
    header: str
    meta: dict[str, Any]
    scores: dict[str, float] = field(default_factory=dict)
    pid: str = ""

    def features(self) -> set[str]:
        return {k[2:] for k, v in self.meta.items() if k.startswith("f_") and v is True}

    def to_dict(self) -> dict[str, Any]:
        return {"pid": self.pid, "chunk_id": self.chunk_id, "doc_id": self.doc_id, "doc_title": self.doc_title,
                "source_type": self.source_type, "trust": self.trust, "date": self.date, "heading": self.heading,
                "text": self.text, "scores": {k: round(v, 4) for k, v in self.scores.items()}}


class HybridRetriever:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._fp: str | None = None
        self._rows: dict[str, dict[str, Any]] = {}
        self._bm25: BM25Index | None = None
        self._collection: str | None = None
        self._store: VectorStore | None = None
        self._embedder: Embedder | None = None
        self.dense_error: str | None = None
        self._canon_cache: dict[tuple[str | None, int | None], dict[str, str]] = {}

    def _refresh(self) -> None:
        fp = db.chunk_fingerprint()
        with self._lock:
            if fp != self._fp:
                rows = db.list_chunks()
                self._rows = {r["id"]: r for r in rows}
                self._bm25 = BM25Index(rows)
                self._fp = fp
            info = db.get_setting("index") or {}
            coll = info.get("collection")
            if coll and coll != self._collection:
                try:
                    self._embedder = embedder_by_id(info["embedder_id"])
                    self._store = VectorStore(info["embedder_id"], info.get("embedder_label", ""), wait_s=5)
                    self._collection = coll
                    self.dense_error = None
                except Exception as e:  # noqa: BLE001
                    self._store, self._embedder = None, None
                    self.dense_error = f"dense retrieval unavailable: {e}"[:300]
                    log.warning(self.dense_error)

    @property
    def index_info(self) -> dict[str, Any]:
        return db.get_setting("index") or {}

    def _passage(self, cid: str) -> Passage | None:
        r = self._rows.get(cid)
        if not r:
            return None
        m = r["meta"]
        return Passage(cid, r["doc_id"], m.get("doc_title", r["doc_id"]), m.get("source_type", ""), m.get("trust", "medium"),
                       m.get("date", ""), m.get("heading", ""), r["text"], r["header"], m)

    def _dense(self, venue_id: str, q: str, k: int) -> list[tuple[str, float]]:
        if not (self._store and self._embedder):
            return []
        try:
            return self._store.query(self._embedder.embed_query(q), venue_id, k)
        except Exception as e:  # noqa: BLE001
            self.dense_error = f"dense query failed: {e}"[:300]
            log.warning(self.dense_error)
            return []

    def _canonical(self, max_date: int | None) -> dict[str, str]:
        """Visible chunk id -> the id that represents its text. Documents dated after max_date are
        hidden; repeated identical entries (e.g. the same log line posted twice) collapse to the newest."""
        key_ = (self._fp, max_date)
        if key_ in self._canon_cache:
            return self._canon_cache[key_]
        if len(self._canon_cache) > 32:
            self._canon_cache.clear()
        newest: dict[tuple[str, str], tuple[int, str]] = {}
        out: dict[str, str] = {}
        for cid, r in self._rows.items():
            d = int(r["meta"].get("date_int") or 0)
            if max_date is not None and d > max_date:
                continue
            key = (r["venue_id"], " ".join(r["text"].split()).lower())
            if key not in newest or d > newest[key][0]:
                newest[key] = (d, cid)
            out[cid] = ""
        for cid in out:
            r = self._rows[cid]
            out[cid] = newest[(r["venue_id"], " ".join(r["text"].split()).lower())][1]
        self._canon_cache[key_] = out
        return out

    @staticmethod
    def _collapse(hits: list[tuple[str, float]], canon: dict[str, str]) -> list[tuple[str, float]]:
        seen: set[str] = set()
        out = []
        for cid, s in hits:
            c = canon.get(cid)
            if c and c not in seen:
                seen.add(c)
                out.append((c, s))
        return out

    def retrieve(self, venue_id: str, queries: list[str], k_each: int = 20, pool_size: int = 30,
                 max_date: int | None = None) -> tuple[list[Passage], dict[str, Any]]:
        """Returns the RRF-fused pool plus, in debug["per_query"], each query's own fused ranking
        (used by rerank to give every route feature its own best evidence).
        max_date (yyyymmdd) hides documents written after the visitor's "now"."""
        self._refresh()
        queries = [q for q in dict.fromkeys(q.strip() for q in queries) if q][:8]
        with ThreadPoolExecutor(max_workers=8) as ex:
            dense_lists = list(ex.map(lambda q: self._dense(venue_id, q, k_each), queries))
        sparse_lists = [self._bm25.search(q, venue_id, k_each) if self._bm25 else [] for q in queries]
        canon = self._canonical(max_date)
        dense_lists = [self._collapse(lst, canon) for lst in dense_lists]
        sparse_lists = [self._collapse(lst, canon) for lst in sparse_lists]

        rrf: dict[str, float] = {}
        best_dense: dict[str, float] = {}
        best_bm25: dict[str, float] = {}
        per_query: list[list[str]] = []
        for qi, (dl, sl) in enumerate(zip(dense_lists, sparse_lists)):
            weight = MAIN_QUERY_WEIGHT if qi == 0 else 1.0
            q_rrf: dict[str, float] = {}
            for rank, (cid, sim) in enumerate(dl):
                q_rrf[cid] = q_rrf.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
                best_dense[cid] = max(best_dense.get(cid, -1.0), sim)
            for rank, (cid, s) in enumerate(sl):
                q_rrf[cid] = q_rrf.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
                best_bm25[cid] = max(best_bm25.get(cid, 0.0), s)
            for cid, s in q_rrf.items():
                rrf[cid] = rrf.get(cid, 0.0) + weight * s
            per_query.append([cid for cid, _ in sorted(q_rrf.items(), key=lambda x: x[1], reverse=True)[:10]])

        keep = {cid for cid, _ in sorted(rrf.items(), key=lambda x: x[1], reverse=True)[:pool_size]}
        keep |= {cid for lst in per_query for cid in lst[:3]}
        out: list[Passage] = []
        for cid, score in sorted(rrf.items(), key=lambda x: x[1], reverse=True):
            if cid not in keep:
                continue
            p = self._passage(cid)
            if p is None:
                continue
            p.scores = {"rrf": score, "dense": best_dense.get(cid, 0.0), "bm25": best_bm25.get(cid, 0.0)}
            out.append(p)
        debug = {
            "per_query": per_query,
            "queries": queries,
            "dense_hits": sum(len(x) for x in dense_lists),
            "sparse_hits": sum(len(x) for x in sparse_lists),
            "dense_enabled": bool(self._store),
            "dense_error": self.dense_error,
            "collection": self._collection,
        }
        return out, debug

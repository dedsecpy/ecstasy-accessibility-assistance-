"""ChromaDB access. One collection per embedder version (e.g. chunks_titan_v2_1024),
so a model change never mixes incompatible vectors."""
from __future__ import annotations

import logging
import time
from typing import Any

from .config import get_settings

log = logging.getLogger("nimbus.vectorstore")


def collection_name(embedder_id: str) -> str:
    return f"chunks_{embedder_id}"


class VectorStore:
    def __init__(self, embedder_id: str, embedder_label: str = "", wait_s: int = 90):
        import chromadb

        s = get_settings()
        opts: dict[str, Any] = {"ssl": s.chroma_ssl}
        if s.chroma_api_key:
            opts["headers"] = {"x-chroma-token": s.chroma_api_key}
        if s.chroma_tenant:
            opts["tenant"] = s.chroma_tenant
        if s.chroma_database:
            opts["database"] = s.chroma_database
        deadline = time.time() + wait_s
        while True:
            try:
                self.client = chromadb.HttpClient(host=s.chroma_host, port=s.chroma_port, **opts)
                self.client.heartbeat()
                break
            except Exception as e:  # noqa: BLE001
                if time.time() > deadline:
                    raise
                log.info("waiting for chroma at %s:%s (%s)", s.chroma_host, s.chroma_port, e)
                time.sleep(2)
        self.name = collection_name(embedder_id)
        self.col = self.client.get_or_create_collection(
            name=self.name, embedding_function=None,
            metadata={"hnsw:space": "cosine", "embedder": embedder_label or embedder_id})

    def count(self) -> int:
        return self.col.count()

    def existing_hashes(self, ids: list[str]) -> dict[str, str]:
        if not ids:
            return {}
        got = self.col.get(ids=ids, include=["metadatas"])
        return {i: (m or {}).get("content_hash", "") for i, m in zip(got["ids"], got["metadatas"])}

    def upsert(self, ids: list[str], vectors: list[list[float]], documents: list[str], metadatas: list[dict[str, Any]]) -> None:
        if ids:
            self.col.upsert(ids=ids, embeddings=vectors, documents=documents, metadatas=metadatas)

    def query(self, vector: list[float], venue_id: str, k: int = 20, where_extra: dict[str, Any] | None = None) -> list[tuple[str, float]]:
        where: dict[str, Any] = {"venue_id": venue_id}
        if where_extra:
            where = {"$and": [where, where_extra]}
        res = self.col.query(query_embeddings=[vector], n_results=k, where=where, include=["distances"])
        ids = res.get("ids", [[]])[0]
        dists = res.get("distances", [[]])[0]
        return [(i, 1.0 - float(d)) for i, d in zip(ids, dists)]

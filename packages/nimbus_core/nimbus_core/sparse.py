"""BM25 index over the same chunks that live in Chroma (exact terms like "Mill Lane", "1:12", "E21")."""
from __future__ import annotations

from typing import Any

from rank_bm25 import BM25Okapi

from .text import tokenize


class BM25Index:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows
        self.ids = [r["id"] for r in rows]
        corpus = [tokenize(f"{r['header']} {r['text']}") for r in rows]
        self.bm25 = BM25Okapi(corpus) if corpus else None

    def search(self, query: str, venue_id: str, k: int = 20) -> list[tuple[str, float]]:
        if not self.bm25:
            return []
        scores = self.bm25.get_scores(tokenize(query))
        hits = [(self.ids[i], float(s)) for i, s in enumerate(scores)
                if s > 0 and self.rows[i]["venue_id"] == venue_id]
        hits.sort(key=lambda x: x[1], reverse=True)
        return hits[:k]

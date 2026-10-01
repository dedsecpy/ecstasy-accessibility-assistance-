"""BM25 retrieval with recency weighting for time-sensitive sources."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date

from rank_bm25 import BM25Okapi

from .kb import Chunk, TIME_SENSITIVE_TYPES

TOKEN_RE = re.compile(r"[a-z0-9]+")

# Light normalisation so visitor phrasing meets venue phrasing.
SYNONYMS = {
    "elevator": "lift",
    "elevators": "lift",
    "lifts": "lift",
    "stairs": "steps",
    "staircase": "steps",
    "stair": "steps",
    "entry": "entrance",
    "door": "entrance",
    "doors": "entrance",
    "wheelchairs": "wheelchair",
    "scooter": "wheelchair",
    "benches": "bench",
    "seats": "seating",
    "seat": "seating",
    "chairs": "chair",
    "sit": "seating",
    "slopes": "slope",
    "sloped": "slope",
    "incline": "slope",
    "gradient": "slope",
    "steep": "slope",
    "toilets": "toilet",
    "wc": "toilet",
    "bathroom": "toilet",
    "restroom": "toilet",
    "parking": "parking",
    "park": "parking",
    "car": "parking",
    "locked": "locked",
    "closed": "locked",
    "broken": "service",
    "working": "service",
    "works": "service",
    "tonight": "evening",
    "night": "evening",
    "late": "evening",
    "help": "assistance",
    "helper": "assistance",
    "assist": "assistance",
    "staffed": "assistance",
    "hours": "hours",
    "open": "hours",
    "opening": "hours",
}


def tokenize(text: str) -> list[str]:
    toks = TOKEN_RE.findall(text.lower())
    return [SYNONYMS.get(t, t) for t in toks]


@dataclass
class Hit:
    chunk: Chunk
    bm25: float
    recency: float
    trust: float

    @property
    def score(self) -> float:
        return self.bm25 * (1.0 + self.recency) * self.trust


TRUST_WEIGHT = {"high": 1.0, "medium": 0.95, "low": 0.85}


class Retriever:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self.corpus = [tokenize(f"{c.doc_title} {c.heading} {c.text}") for c in chunks]
        self.bm25 = BM25Okapi(self.corpus) if self.corpus else None

    def search(self, query: str, today: date, k: int = 8, half_life_days: float = 45.0) -> list[Hit]:
        if not self.bm25:
            return []
        q = tokenize(query)
        scores = self.bm25.get_scores(q)
        hits: list[Hit] = []
        for c, s in zip(self.chunks, scores):
            if s <= 0:
                continue
            recency = 0.0
            if c.source_type in TIME_SENSITIVE_TYPES:
                age = max(0, c.age_days(today))
                # Fresh operational reports get up to +60%; decays with half-life.
                recency = 0.6 * math.pow(0.5, age / half_life_days)
            hits.append(Hit(chunk=c, bm25=float(s), recency=recency, trust=TRUST_WEIGHT.get(c.trust, 0.9)))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:k]

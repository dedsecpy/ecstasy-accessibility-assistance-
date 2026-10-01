"""Tokenisation with light synonym folding, shared by BM25 and the local embedder."""
from __future__ import annotations

import re

TOKEN_RE = re.compile(r"[a-z0-9]+")

SYNONYMS = {
    "elevator": "lift", "elevators": "lift", "lifts": "lift",
    "stairs": "steps", "staircase": "steps", "stair": "steps",
    "entry": "entrance", "door": "entrance", "doors": "entrance",
    "wheelchairs": "wheelchair", "scooter": "wheelchair",
    "benches": "bench", "seats": "seating", "seat": "seating", "chairs": "chair", "sit": "seating",
    "slopes": "slope", "sloped": "slope", "incline": "slope", "gradient": "slope", "steep": "slope",
    "toilets": "toilet", "wc": "toilet", "bathroom": "toilet", "restroom": "toilet",
    "park": "parking", "car": "parking",
    "closed": "locked",
    "broken": "service", "working": "service", "works": "service",
    "tonight": "evening", "night": "evening", "late": "evening",
    "help": "assistance", "helper": "assistance", "assist": "assistance", "staffed": "assistance",
    "open": "hours", "opening": "hours",
}

STOPWORDS = {"the", "a", "an", "and", "or", "to", "of", "in", "on", "at", "for", "is", "it", "i", "my", "me", "be", "can", "with", "by", "was", "are"}


def tokenize(text: str, drop_stopwords: bool = True) -> list[str]:
    toks = [SYNONYMS.get(t, t) for t in TOKEN_RE.findall(text.lower())]
    return [t for t in toks if t not in STOPWORDS] if drop_stopwords else toks

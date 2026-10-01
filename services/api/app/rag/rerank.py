"""Rerank the fused candidates (Bedrock Rerank when available), apply recency x trust priors,
and guarantee that every required feature is covered by at least one passage."""
from __future__ import annotations

import logging
import math
from datetime import date
from typing import Any

from nimbus_core.bedrock import BedrockError, get_bedrock
from nimbus_core.config import get_settings
from nimbus_core.features import TIME_SENSITIVE_TYPES, TRUST_WEIGHT

from .retrieval import Passage

log = logging.getLogger("api.rerank")
HALF_LIFE_DAYS = 45.0
LISTING_PENALTY = 0.85


def prior(p: Passage, today: date) -> float:
    w = TRUST_WEIGHT.get(p.trust, 0.9)
    if p.source_type == "listing":
        w *= LISTING_PENALTY
    if p.source_type in TIME_SENSITIVE_TYPES and p.date:
        age = max(0, (today - date.fromisoformat(p.date)).days)
        w *= 1.0 + 0.6 * math.pow(0.5, age / HALF_LIFE_DAYS)
    return w


def _reserve(cands: list[Passage], per_query: list[list[str]], quotas: list[int], k: int) -> list[Passage]:
    """Aspect quotas: the question (query 0) gets its best passages, then each sub-query (one per
    route feature, most at-risk first) gets its own, leaving at least one slot for the global
    ranking. Among a sub-query's top 3, recency x trust decides, so the newest log entry beats
    an older one with more matching words."""
    by_id = {p.chunk_id: p for p in cands}
    picked: list[Passage] = []
    for qi, ranked in enumerate(per_query):
        quota = quotas[qi] if qi < len(quotas) else 1
        pool = [by_id[c] for c in ranked if c in by_id and by_id[c] not in picked]
        if qi == 0:
            chosen = pool[:quota]
        else:
            top = pool[:max(3, quota + 1)]
            chosen = sorted(top, key=lambda p: p.scores["prior"] / (1 + 0.1 * top.index(p)), reverse=True)[:quota]
        for p in chosen:
            if len(picked) >= k - 1:
                return picked
            picked.append(p)
    return picked


def rerank(query: str, cands: list[Passage], today: date, required: list[str], k: int = 8,
           per_query: list[list[str]] | None = None, quotas: list[int] | None = None) -> tuple[list[Passage], dict[str, Any]]:
    info: dict[str, Any] = {"method": "rrf_prior", "error": None}
    if not cands:
        return [], info
    base: dict[str, float] = {}
    s = get_settings()
    client = get_bedrock()
    if client is not None and s.rerank_enabled and client.rerank_usable:
        try:
            results = client.rerank(query, [f"{p.header}\n{p.text}" for p in cands], top_n=min(len(cands), 20))
            for idx, score in results:
                base[cands[idx].chunk_id] = score
            info["method"] = f"bedrock_rerank:{s.rerank_model}"
        except BedrockError as e:
            info["error"] = str(e)[:300]
            log.warning("rerank unavailable, using RRF x priors: %s", e)
    if not base:
        top = max(p.scores.get("rrf", 0.0) for p in cands) or 1.0
        base = {p.chunk_id: p.scores.get("rrf", 0.0) / top for p in cands}

    for p in cands:
        p.scores["rerank" if info["method"] != "rrf_prior" else "rrf_norm"] = base.get(p.chunk_id, 0.0)
        p.scores["prior"] = prior(p, today)
        p.scores["final"] = base.get(p.chunk_id, 0.0) * p.scores["prior"]
    ranked = sorted(cands, key=lambda p: p.scores["final"], reverse=True)
    reserved = _reserve(cands, per_query or [], quotas or [2], k)
    selected = reserved + [p for p in ranked if p not in reserved][:k - len(reserved)]
    selected.sort(key=lambda p: p.scores["final"], reverse=True)
    rest = [p for p in ranked if p not in selected]
    info["reserved"] = len(reserved)

    # Coverage guarantee: a required feature with evidence in the pool must have a passage in the prompt.
    swapped = []
    for fid in required:
        if any(fid in p.features() for p in selected):
            continue
        cand = next((p for p in rest if fid in p.features()), None)
        if cand is None:
            continue
        for i in range(len(selected) - 1, -1, -1):
            victim = selected[i]
            others = selected[:i] + selected[i + 1:]
            if all(any(f in o.features() for o in others) for f in victim.features() & set(required)):
                selected[i] = cand
                rest.remove(cand)
                swapped.append(fid)
                break
    info["coverage_swaps"] = swapped
    for i, p in enumerate(selected, 1):
        p.pid = f"P{i}"
    return selected, info

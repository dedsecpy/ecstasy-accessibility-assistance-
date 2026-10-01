"""Nimbus — route-level, time-aware accessibility answers for venues.

Core pipeline: venue documents + a dated fact log -> BM25 retrieval with
recency weighting -> LLM synthesis grounded in cited evidence (with a
deterministic fallback when no LLM is configured).
"""

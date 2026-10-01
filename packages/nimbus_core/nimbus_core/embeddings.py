"""Embedders. Groq (nomic-embed-text) or Titan Text Embeddings V2, depending on the provider; a local
hashing embedder is the offline fallback. Each embedder has an id that names its own Chroma collection,
so vectors from different models never mix."""
from __future__ import annotations

import hashlib
import logging
import math
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Protocol

from . import db
from .bedrock import Bedrock, BedrockError, get_bedrock
from .config import get_settings

log = logging.getLogger("nimbus.embeddings")


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Embedder(Protocol):
    id: str
    model_id: str
    dim: int
    label: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class TitanEmbedder:
    """amazon.titan-embed-text-v2:0, normalized, with a Postgres content-hash cache.
    Titan V2 accepts one input per call, so batches fan out over a bounded thread pool."""

    def __init__(self, client: Bedrock, dim: int, workers: int = 4, use_cache: bool = True):
        self.client = client
        self.model_id = client.s.embed_model
        self.dim = dim
        self.id = f"titan_v2_{dim}"
        self.label = f"AWS Titan Text Embeddings V2 ({dim}d)"
        self.workers = max(1, workers)
        self.use_cache = use_cache

    def _one(self, text: str) -> list[float]:
        h = content_hash(text)
        if self.use_cache:
            cached = db.get_cached_embedding(h, self.model_id, self.dim)
            if cached is not None:
                return cached
        vec = self.client.embed(text, self.dim)
        if self.use_cache:
            db.put_cached_embedding(h, self.model_id, self.dim, vec)
        return vec

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            return list(ex.map(self._one, texts))

    def embed_query(self, text: str) -> list[float]:
        return self.client.embed(text, self.dim)


class GroqEmbedder:
    """Groq embeddings (nomic-embed-text-v1_5 by default), batched, with the Postgres content-hash cache.
    Nomic models are trained with task prefixes, so documents and queries are prefixed accordingly."""

    def __init__(self, client: Any, dim: int, use_cache: bool = True):
        self.client = client
        self.model_id = client.s.groq_embed_model
        self.dim = dim
        slug = re.sub(r"[^a-z0-9]+", "_", self.model_id.lower()).strip("_")[:40]
        self.id = f"groq_{slug}_{dim}"
        self.label = f"Groq {self.model_id} ({dim}d)"
        self.use_cache = use_cache
        nomic = "nomic" in self.model_id.lower()
        self._doc_prefix = "search_document: " if nomic else ""
        self._query_prefix = "search_query: " if nomic else ""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        hashes = [content_hash(t) for t in texts]
        out: list[list[float] | None] = [None] * len(texts)
        if self.use_cache:
            for i, h in enumerate(hashes):
                out[i] = db.get_cached_embedding(h, self.model_id, self.dim)
        missing = [i for i, v in enumerate(out) if v is None]
        if missing:
            vecs = self.client.embed_many([self._doc_prefix + texts[i] for i in missing])
            for i, v in zip(missing, vecs):
                out[i] = v
                if self.use_cache:
                    db.put_cached_embedding(hashes[i], self.model_id, self.dim, v)
        return [v for v in out if v is not None]

    def embed_query(self, text: str) -> list[float]:
        return self.client.embed_many([self._query_prefix + text])[0]


_TOKEN = re.compile(r"[a-z0-9]+")


class HashEmbedder:
    """Deterministic feature-hashing embedder (unigrams + bigrams + char trigrams).
    Needs no network and no model download; weaker than Titan, clearly labelled as fallback."""

    def __init__(self, dim: int = 512):
        self.dim = dim
        self.id = f"local_hash_{dim}"
        self.model_id = "local-hash"
        self.label = f"Local hashing embeddings ({dim}d, offline fallback)"

    def _vec(self, text: str) -> list[float]:
        from .text import tokenize

        toks = tokenize(text)
        feats = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]
        for t in toks:
            if len(t) > 4:
                feats += [t[i:i + 3] for i in range(len(t) - 2)]
        v = [0.0] * self.dim
        for f in feats:
            h = int.from_bytes(hashlib.md5(f.encode()).digest()[:8], "little")
            v[h % self.dim] += 1.0 if (h >> 63) & 1 else -1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


def choose_embedder() -> tuple[Embedder, str]:
    """Probe the provider's embedding model once; fall back to the local embedder with a reason the UI can show."""
    s = get_settings()
    client = get_bedrock()
    if client is None:
        why = ("NIMBUS_AI_MODE=local" if s.ai_mode == "local"
               else "no GROQ_API_KEY, AWS credentials or Bedrock API key in environment")
        return HashEmbedder(), why
    if s.provider == "groq":
        try:
            dim = len(client.embed("Ecstasy embedding probe"))
            return GroqEmbedder(client, dim), "ok"
        except BedrockError as e:
            log.warning("Groq embedding probe failed, using local embeddings: %s", e)
            msg = str(e)
            if "404" in msg or "model_not_found" in msg:
                return HashEmbedder(), f"Groq embedding model {s.groq_embed_model} is not available to this API key"
            if "401" in msg or "403" in msg:
                return HashEmbedder(), "Groq rejected the API key for embeddings"
            return HashEmbedder(), f"Groq embedding probe failed: {msg}"[:300]
    try:
        client.embed("Ecstasy embedding probe", s.embed_dim)
        return TitanEmbedder(client, s.embed_dim, s.embed_workers), "ok"
    except BedrockError as e:
        log.warning("Titan probe failed, using local embeddings: %s", e)
        return HashEmbedder(), f"Titan probe failed: {e}"[:300]


def embedder_by_id(embedder_id: str) -> Embedder:
    s = get_settings()
    if embedder_id.startswith("titan_v2_"):
        client = get_bedrock()
        if client is None:
            raise BedrockError("Index was built with Titan but Bedrock is not available in this process")
        return TitanEmbedder(client, int(embedder_id.rsplit("_", 1)[1]), s.embed_workers)
    if embedder_id.startswith("groq_"):
        client = get_bedrock()
        if client is None or s.provider != "groq":
            raise BedrockError("Index was built with Groq embeddings but Groq is not configured in this process")
        emb = GroqEmbedder(client, int(embedder_id.rsplit("_", 1)[1]))
        if emb.id != embedder_id:
            raise BedrockError(f"Index was built with {embedder_id} but GROQ_EMBED_MODEL_ID gives {emb.id}")
        return emb
    if embedder_id.startswith("local_hash_"):
        return HashEmbedder(int(embedder_id.rsplit("_", 1)[1]))
    raise ValueError(f"unknown embedder id {embedder_id}")

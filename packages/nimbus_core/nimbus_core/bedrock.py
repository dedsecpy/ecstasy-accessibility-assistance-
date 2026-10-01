"""AWS Bedrock access through boto3. Credentials come from the environment (.env):
AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, optional AWS_SESSION_TOKEN, AWS_REGION - or a Bedrock API key
in AWS_BEARER_TOKEN_BEDROCK, which botocore uses for bedrock-runtime (embeddings, Converse) but not for
bedrock-agent-runtime (Rerank), so Rerank needs IAM keys.

Three capabilities:
- Titan Text Embeddings V2 (bedrock-runtime.invoke_model)
- Rerank (bedrock-agent-runtime.rerank, Amazon or Cohere rerank models)
- Claude via the Converse API with a forced tool call, so output is schema-shaped JSON

get_bedrock() returns the Groq client instead when NIMBUS_LLM_PROVIDER resolves to groq (see groq.py).
"""
from __future__ import annotations

import json
import logging
import threading
import time
from functools import lru_cache
from typing import Any

from .config import Settings, get_settings

log = logging.getLogger("nimbus.bedrock")


class AIError(RuntimeError):
    """Any failed call to the configured AI provider (Bedrock or Groq)."""


BedrockError = AIError


class Bedrock:
    def __init__(self, settings: Settings | None = None):
        import boto3
        from botocore.config import Config

        self.s = settings or get_settings()
        self._session = boto3.Session(region_name=self.s.aws_region)
        cfg = Config(retries={"max_attempts": 4, "mode": "adaptive"}, read_timeout=90, connect_timeout=10)
        self.runtime = self._session.client("bedrock-runtime", config=cfg)
        rr_region = self.s.rerank_region or self.s.aws_region
        self.rerank_region = rr_region
        self.agent_runtime = self._session.client("bedrock-agent-runtime", region_name=rr_region, config=cfg)
        self.rerank_usable = self._session.get_credentials() is not None
        self._lock = threading.Lock()
        self.stats = {"embed_calls": 0, "llm_calls": 0, "rerank_calls": 0}

    # ------------------------------------------------------------ embeddings
    def embed(self, text: str, dim: int | None = None) -> list[float]:
        dim = dim or self.s.embed_dim
        body = json.dumps({"inputText": text[:40000], "dimensions": dim, "normalize": True})
        try:
            resp = self.runtime.invoke_model(modelId=self.s.embed_model, body=body,
                                             contentType="application/json", accept="application/json")
            data = json.loads(resp["body"].read())
        except Exception as e:  # noqa: BLE001
            raise BedrockError(f"Titan embedding failed: {e}") from e
        with self._lock:
            self.stats["embed_calls"] += 1
        vec = data.get("embedding")
        if not vec:
            raise BedrockError("Titan returned no embedding")
        return vec

    # ------------------------------------------------------------ rerank
    def rerank(self, query: str, documents: list[str], top_n: int) -> list[tuple[int, float]]:
        if not documents:
            return []
        model = self.s.rerank_model
        arn = model if model.startswith("arn:") else f"arn:aws:bedrock:{self.rerank_region}::foundation-model/{model}"
        try:
            resp = self.agent_runtime.rerank(
                queries=[{"type": "TEXT", "textQuery": {"text": query[:2000]}}],
                sources=[{"type": "INLINE", "inlineDocumentSource": {"type": "TEXT", "textDocument": {"text": d[:4000]}}}
                         for d in documents],
                rerankingConfiguration={
                    "type": "BEDROCK_RERANKING_MODEL",
                    "bedrockRerankingConfiguration": {"numberOfResults": min(top_n, len(documents)),
                                                      "modelConfiguration": {"modelArn": arn}},
                },
            )
        except Exception as e:  # noqa: BLE001
            raise BedrockError(f"Rerank failed: {e}") from e
        with self._lock:
            self.stats["rerank_calls"] += 1
        return [(int(r["index"]), float(r["relevanceScore"])) for r in resp.get("results", [])]

    # ------------------------------------------------------------ Claude (Converse + tool schema)
    def converse_json(self, *, model: str, system: str, user: str, tool_name: str, tool_description: str,
                      schema: dict[str, Any], max_tokens: int = 1500, temperature: float = 0.0) -> dict[str, Any]:
        t0 = time.time()
        try:
            resp = self.runtime.converse(
                modelId=model,
                system=[{"text": system}],
                messages=[{"role": "user", "content": [{"text": user}]}],
                inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
                toolConfig={
                    "tools": [{"toolSpec": {"name": tool_name, "description": tool_description,
                                            "inputSchema": {"json": schema}}}],
                    "toolChoice": {"tool": {"name": tool_name}},
                },
            )
        except Exception as e:  # noqa: BLE001
            raise BedrockError(f"Converse ({model}) failed: {e}") from e
        with self._lock:
            self.stats["llm_calls"] += 1
        for block in resp.get("output", {}).get("message", {}).get("content", []):
            if "toolUse" in block:
                log.info("converse %s ok in %.0f ms", model, (time.time() - t0) * 1000)
                return block["toolUse"]["input"]
        for block in resp.get("output", {}).get("message", {}).get("content", []):
            if "text" in block:
                try:
                    return json.loads(block["text"])
                except json.JSONDecodeError:
                    pass
        raise BedrockError("Model did not return the structured tool output")


@lru_cache(maxsize=1)
def get_bedrock() -> Any:
    """Shared AI client for the configured provider (Bedrock or Groq; both expose embed, rerank,
    converse_json and rerank_usable), or None when AI is not wanted or the client cannot be built."""
    s = get_settings()
    if not s.ai_wanted:
        return None
    try:
        if s.provider == "groq":
            from .groq import Groq
            return Groq(s)
        return Bedrock(s)
    except Exception as e:  # noqa: BLE001
        log.warning("%s client unavailable: %s", s.provider_label, e)
        return None

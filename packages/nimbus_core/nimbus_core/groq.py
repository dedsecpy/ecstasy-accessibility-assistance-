"""Groq access over its OpenAI-compatible REST API. The key comes from the environment (GROQ_API_KEY).

Same surface as the Bedrock client, so the rest of Ecstasy does not care which provider is active:
- embed / embed_many: /embeddings (nomic-embed-text-v1_5 by default)
- converse_json: /chat/completions with a forced function call, so output is schema-shaped JSON
- rerank: not offered by Groq; rerank_usable is False and retrieval keeps its local ranking
"""
from __future__ import annotations

import json
import logging
import math
import threading
import time
from typing import Any

from .bedrock import AIError
from .config import Settings, get_settings

log = logging.getLogger("nimbus.groq")

EMBED_BATCH = 64


class Groq:
    def __init__(self, settings: Settings | None = None):
        import httpx

        self.s = settings or get_settings()
        if not self.s.groq_api_key:
            raise AIError("GROQ_API_KEY is not set")
        self._http = httpx.Client(
            base_url=self.s.groq_base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {self.s.groq_api_key}", "Content-Type": "application/json"},
            timeout=httpx.Timeout(90.0, connect=10.0),
        )
        self.rerank_usable = False
        self._lock = threading.Lock()
        self.stats = {"embed_calls": 0, "llm_calls": 0, "rerank_calls": 0}

    def _post(self, path: str, payload: dict[str, Any], attempts: int = 3) -> dict[str, Any]:
        import httpx

        last = ""
        for attempt in range(attempts):
            try:
                r = self._http.post(path, json=payload)
            except httpx.HTTPError as e:
                last = f"{type(e).__name__}: {e}"
                time.sleep(1 + attempt)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                last = f"HTTP {r.status_code}: {r.text[:300]}"
                try:
                    wait = float(r.headers.get("retry-after", 2 ** attempt))
                except ValueError:
                    wait = 2.0 ** attempt
                if attempt + 1 < attempts and wait <= self.s.groq_max_retry_wait_s:
                    log.info("groq %s %s, retrying in %.1fs", path, r.status_code, wait)
                    time.sleep(wait)
                    continue
                break
            if r.status_code >= 400:
                raise AIError(f"Groq {path} HTTP {r.status_code}: {r.text[:400]}")
            return r.json()
        raise AIError(f"Groq {path} failed: {last}")

    # ------------------------------------------------------------ embeddings
    def embed_many(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), EMBED_BATCH):
            batch = [t[:20000] or " " for t in texts[i:i + EMBED_BATCH]]
            data = self._post("/embeddings", {"model": self.s.groq_embed_model, "input": batch, "encoding_format": "float"})
            rows = sorted(data.get("data", []), key=lambda d: d.get("index", 0))
            if len(rows) != len(batch):
                raise AIError(f"Groq returned {len(rows)} embeddings for {len(batch)} inputs")
            for row in rows:
                v = row.get("embedding") or []
                n = math.sqrt(sum(x * x for x in v)) or 1.0
                out.append([x / n for x in v])
            with self._lock:
                self.stats["embed_calls"] += 1
        return out

    def embed(self, text: str, dim: int | None = None) -> list[float]:
        return self.embed_many([text])[0]

    # ------------------------------------------------------------ rerank
    def rerank(self, query: str, documents: list[str], top_n: int) -> list[tuple[int, float]]:
        raise AIError("Groq has no rerank API")

    # ------------------------------------------------------------ chat (forced function call)
    def converse_json(self, *, model: str, system: str, user: str, tool_name: str, tool_description: str,
                      schema: dict[str, Any], max_tokens: int = 1500, temperature: float = 0.0) -> dict[str, Any]:
        t0 = time.time()
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
            "max_completion_tokens": max_tokens + 1500,
        }
        if model.startswith("openai/gpt-oss") and self.s.groq_reasoning_effort:
            payload["reasoning_effort"] = self.s.groq_reasoning_effort
        tooled = {**payload,
                  "tools": [{"type": "function", "function": {"name": tool_name, "description": tool_description,
                                                              "parameters": schema}}],
                  "tool_choice": {"type": "function", "function": {"name": tool_name}}}
        try:
            data = self._post("/chat/completions", tooled)
        except AIError as e:
            # Groq rejects calls whose arguments fail schema validation (tool_use_failed); retry in JSON mode.
            if "tool_use_failed" not in str(e):
                raise AIError(f"Groq chat ({model}) failed: {e}") from e
            log.info("groq %s tool call failed validation, retrying in JSON mode", model)
            data = self._post("/chat/completions", {
                **payload,
                "messages": [{"role": "system", "content": f"{system}\n\nRespond with only a JSON object that matches "
                                                           f"this JSON schema:\n{json.dumps(schema)}"},
                             {"role": "user", "content": user}],
                "response_format": {"type": "json_object"},
            })
        with self._lock:
            self.stats["llm_calls"] += 1
        msg = (data.get("choices") or [{}])[0].get("message") or {}
        for call in msg.get("tool_calls") or []:
            fn = call.get("function") or {}
            if fn.get("name") == tool_name:
                try:
                    out = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError as e:
                    raise AIError(f"Groq returned malformed tool arguments: {e}") from e
                log.info("groq %s ok in %.0f ms", model, (time.time() - t0) * 1000)
                return out
        content = (msg.get("content") or "").strip()
        if content:
            start, end = content.find("{"), content.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(content[start:end + 1])
                except json.JSONDecodeError:
                    pass
        raise AIError("Model did not return the structured tool output")

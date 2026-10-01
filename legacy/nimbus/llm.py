"""Thin OpenAI-compatible chat client (OpenAI, Groq, Ollama, LM Studio...).

Configured via environment variables (see .env.example):
  NIMBUS_LLM_API_KEY   - required to enable the LLM
  NIMBUS_LLM_BASE_URL  - optional, e.g. https://api.groq.com/openai/v1 or http://localhost:11434/v1
  NIMBUS_LLM_MODEL     - optional, default gpt-4o-mini
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any


class LLMError(RuntimeError):
    pass


@dataclass
class LLMConfig:
    api_key: str | None
    base_url: str | None
    model: str

    @classmethod
    def from_env(cls) -> "LLMConfig":
        return cls(
            api_key=os.getenv("NIMBUS_LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or None,
            base_url=os.getenv("NIMBUS_LLM_BASE_URL") or None,
            model=os.getenv("NIMBUS_LLM_MODEL", "gpt-4o-mini"),
        )

    @property
    def available(self) -> bool:
        # Local servers (Ollama) accept any key; a base_url alone is enough.
        return bool(self.api_key) or bool(self.base_url)

    @property
    def describe(self) -> str:
        if not self.available:
            return "no LLM configured - deterministic fallback"
        host = self.base_url or "api.openai.com"
        return f"{self.model} @ {host}"


class LLMClient:
    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig.from_env()
        self._client = None

    @property
    def available(self) -> bool:
        return self.config.available

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI  # imported lazily so the app runs without the SDK installed

            self._client = OpenAI(api_key=self.config.api_key or "not-needed", base_url=self.config.base_url)
        return self._client

    def complete(self, system: str, user: str, temperature: float = 0.1, max_tokens: int = 1400) -> str:
        if not self.available:
            raise LLMError("LLM not configured")
        try:
            client = self._get_client()
            resp = client.chat.completions.create(
                model=self.config.model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:  # noqa: BLE001 - surface any provider error to the UI
            raise LLMError(str(e)) from e

    def complete_json(self, system: str, user: str, **kw) -> dict[str, Any]:
        raw = self.complete(system, user, **kw)
        return parse_json_block(raw)


def parse_json_block(raw: str) -> dict[str, Any]:
    """Extract the first JSON object from a model response, tolerating code fences."""
    s = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", s, re.DOTALL)
    if fence:
        s = fence.group(1)
    else:
        start, end = s.find("{"), s.rfind("}")
        if start != -1 and end != -1:
            s = s[start : end + 1]
    try:
        return json.loads(s)
    except json.JSONDecodeError as e:
        raise LLMError(f"Model did not return valid JSON: {e}\n---\n{raw[:500]}") from e

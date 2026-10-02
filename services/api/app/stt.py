"""Speech to text through Deepgram's pre-recorded API. The key stays on the server (DEEPGRAM_API_KEY)."""
from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from typing import Any

import httpx

from nimbus_core.config import get_settings

log = logging.getLogger("api.stt")

DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"
MAX_BYTES = 8 * 1024 * 1024
# Deepgram bills per audio minute; the endpoint is public, so each client gets a small budget.
RATE_LIMIT = 20
RATE_WINDOW_S = 60.0
ENGLISH_VARIANTS = {"en-us", "en-gb", "en-au", "en-in", "en-nz"}


class STTError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


_hits: dict[str, deque[float]] = defaultdict(deque)
_hits_lock = threading.Lock()


def enabled() -> bool:
    return bool(get_settings().deepgram_api_key)


def status() -> dict[str, Any]:
    s = get_settings()
    on = bool(s.deepgram_api_key)
    return {"enabled": on, "provider": "deepgram" if on else None, "model": s.deepgram_model if on else None,
            "max_seconds": 60}


def check_rate(client: str) -> None:
    now = time.monotonic()
    with _hits_lock:
        q = _hits[client]
        while q and now - q[0] > RATE_WINDOW_S:
            q.popleft()
        if len(q) >= RATE_LIMIT:
            raise STTError(429, "Too many voice requests. Please wait a minute and try again.")
        q.append(now)


def _language(requested: str | None) -> str:
    default = get_settings().deepgram_language or "en"
    if not requested:
        return default
    tag = requested.strip().lower()
    if tag in ENGLISH_VARIANTS and default.lower().startswith("en"):
        return tag
    return default


async def transcribe(audio: bytes, content_type: str, language: str | None = None) -> dict[str, Any]:
    s = get_settings()
    if not s.deepgram_api_key:
        raise STTError(503, "Voice input is not configured on this server.")
    if not audio:
        raise STTError(400, "No audio was received.")
    if len(audio) > MAX_BYTES:
        raise STTError(413, "That recording is too long. Please keep it under a minute.")
    ctype = (content_type or "").split(";")[0].strip() or "application/octet-stream"
    if not (ctype.startswith("audio/") or ctype in ("video/webm", "application/octet-stream")):
        raise STTError(415, f"Unsupported audio type '{ctype}'.")

    params = {"model": s.deepgram_model, "language": _language(language), "smart_format": "true", "punctuate": "true"}
    headers = {"Authorization": f"Token {s.deepgram_api_key}", "Content-Type": ctype}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=10.0)) as http:
            r = await http.post(DEEPGRAM_URL, params=params, headers=headers, content=audio)
    except httpx.HTTPError as e:
        log.warning("deepgram request failed: %s", type(e).__name__)
        raise STTError(502, "Could not reach the speech service. Please try again.") from e
    if r.status_code in (401, 403):
        log.error("deepgram rejected the API key (HTTP %s)", r.status_code)
        raise STTError(502, "The speech service rejected this server's key.")
    if r.status_code == 429:
        raise STTError(429, "The speech service is busy. Please try again in a moment.")
    if r.status_code >= 400:
        log.warning("deepgram HTTP %s: %s", r.status_code, r.text[:300])
        raise STTError(502, "The speech service could not read that recording.")

    data = r.json()
    try:
        alt = data["results"]["channels"][0]["alternatives"][0]
    except (KeyError, IndexError, TypeError):
        alt = {}
    return {
        "text": str(alt.get("transcript") or "").strip(),
        "confidence": alt.get("confidence"),
        "duration_s": (data.get("metadata") or {}).get("duration"),
        "provider": "deepgram",
        "model": s.deepgram_model,
    }

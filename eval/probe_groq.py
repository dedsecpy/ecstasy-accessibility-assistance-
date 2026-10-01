"""Check the Groq setup from .env: key, chat models (forced tool call) and the embedding model.

  docker run --rm --env-file .env -v "${PWD}/eval:/app/eval" nimbus-python:latest python /app/eval/probe_groq.py
"""
from __future__ import annotations

import sys
import time

import httpx

from nimbus_core.bedrock import AIError
from nimbus_core.config import get_settings
from nimbus_core.groq import Groq

SCHEMA = {"type": "object", "properties": {"verdict": {"type": "string", "enum": ["go", "caution", "no_go"]},
                                           "reason": {"type": "string"}}, "required": ["verdict", "reason"]}


def main() -> int:
    s = get_settings()
    print(f"provider={s.provider}  GROQ_API_KEY={'<set>' if s.groq_api_key else '<empty>'}")
    if not s.groq_api_key:
        print("Set GROQ_API_KEY in .env (console.groq.com > API Keys).")
        return 2
    r = httpx.get(f"{s.groq_base_url}/models", headers={"Authorization": f"Bearer {s.groq_api_key}"}, timeout=20)
    if r.status_code != 200:
        print(f"models: HTTP {r.status_code} {r.text[:200]}")
        return 1
    ids = sorted(m["id"] for m in r.json().get("data", []))
    print(f"models available ({len(ids)}): {', '.join(ids)}")
    for want in (s.groq_llm_model, s.groq_fast_llm_model, s.groq_embed_model):
        print(f"  {want}: {'listed' if want in ids else 'NOT LISTED'}")

    g, ok = Groq(s), True
    for model in (s.groq_fast_llm_model, s.groq_llm_model):
        t0 = time.time()
        try:
            out = g.converse_json(model=model, system="You assess step-free access.",
                                  user="The only lift is out of service and the seat is upstairs. Verdict?",
                                  tool_name="give_verdict", tool_description="Return a verdict", schema=SCHEMA,
                                  max_tokens=200)
            print(f"chat {model}: ok in {(time.time() - t0) * 1000:.0f} ms -> {out}")
        except AIError as e:
            ok = False
            print(f"chat {model}: FAILED {e}")
    t0 = time.time()
    try:
        vecs = g.embed_many(["search_document: Lift to the gallery", "search_query: is the lift working"])
        print(f"embed {s.groq_embed_model}: ok in {(time.time() - t0) * 1000:.0f} ms, dim {len(vecs[0])}")
    except AIError as e:
        ok = False
        print(f"embed {s.groq_embed_model}: FAILED {e}")
        print("  Ecstasy will still use Groq for answers and fall back to local embeddings.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

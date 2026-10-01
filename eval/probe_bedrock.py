"""Check Bedrock access with the credentials in the environment: python eval/probe_bedrock.py"""
from __future__ import annotations

import sys
import time

from nimbus_core.bedrock import BedrockError, get_bedrock
from nimbus_core.config import get_settings

s = get_settings()
print(f"region={s.aws_region} iam_keys={s.iam_credentials_present} api_key={s.aws_credentials_present and not s.iam_credentials_present}")
client = get_bedrock()
if client is None:
    print("Bedrock client not created (no credentials, or NIMBUS_AI_MODE=local)")
    sys.exit(1)

ok = True


def check(name, fn):
    global ok
    t0 = time.time()
    try:
        out = fn()
        print(f"  OK   {name} ({(time.time() - t0) * 1000:.0f} ms): {out}")
    except BedrockError as e:
        ok = False
        print(f"  FAIL {name}: {str(e)[:300]}")


check(f"Titan embed {s.embed_model}", lambda: f"{len(client.embed('step-free entrance via Side Gate'))} dims")
schema = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}
for model in (s.fast_llm_model, s.llm_model):
    check(f"Converse {model}", lambda m=model: client.converse_json(
        model=m, system="Reply briefly.", user="Say hello in three words.", tool_name="reply",
        tool_description="Return the reply", schema=schema, max_tokens=50))
if s.rerank_enabled and client.rerank_usable:
    check(f"Rerank {s.rerank_model}", lambda: client.rerank("lift out of service", ["The lift is broken.", "Seats in foyer."], 2))
else:
    print("  SKIP Rerank (needs IAM access keys or is disabled)")
sys.exit(0 if ok else 1)

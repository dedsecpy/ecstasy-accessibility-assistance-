"""Try a list of Bedrock model ids with one tiny call each: python eval/probe_models.py [model ...]"""
from __future__ import annotations

import sys
import time

import boto3
from botocore.config import Config

from nimbus_core.config import get_settings

s = get_settings()
rt = boto3.client("bedrock-runtime", region_name=s.aws_region, config=Config(retries={"max_attempts": 1}))
DEFAULT = [
    "amazon.titan-embed-text-v2:0",
    "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "us.anthropic.claude-sonnet-4-20250514-v1:0",
    "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    "us.amazon.nova-pro-v1:0",
    "us.amazon.nova-lite-v1:0",
    "us.amazon.nova-micro-v1:0",
]

try:
    ctl = boto3.client("bedrock", region_name=s.aws_region)
    ids = [m["modelId"] for m in ctl.list_foundation_models(byOutputModality="TEXT")["modelSummaries"]
           if "anthropic" in m["modelId"] or "nova" in m["modelId"]]
    print("listed text models:", ", ".join(sorted(ids)))
except Exception as e:  # noqa: BLE001
    print("list_foundation_models unavailable:", str(e)[:160])

for mid in sys.argv[1:] or DEFAULT:
    t0 = time.time()
    try:
        if "embed" in mid:
            rt.invoke_model(modelId=mid, body='{"inputText":"hello","dimensions":256}')
        else:
            rt.converse(modelId=mid, messages=[{"role": "user", "content": [{"text": "Say OK."}]}],
                        inferenceConfig={"maxTokens": 5})
        print(f"OK   {mid} ({(time.time() - t0) * 1000:.0f} ms)")
    except Exception as e:  # noqa: BLE001
        msg = str(e).split(":", 1)[-1].strip()
        print(f"FAIL {mid}: {type(e).__name__}: {msg[:140]}")
    time.sleep(1)

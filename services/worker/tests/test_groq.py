import json

import httpx
import pytest

from nimbus_core.bedrock import AIError
from nimbus_core.config import Settings
from nimbus_core.embeddings import GroqEmbedder
from nimbus_core.groq import Groq

SCHEMA = {"type": "object", "properties": {"verdict": {"type": "string"}}, "required": ["verdict"]}


def settings(monkeypatch, **env):
    for k in ("GROQ_API_KEY", "NIMBUS_LLM_PROVIDER", "NIMBUS_AI_MODE", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
              "AWS_PROFILE", "AWS_BEARER_TOKEN_BEDROCK"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return Settings()


def client(monkeypatch, handler):
    g = Groq(settings(monkeypatch, GROQ_API_KEY="test-key"))
    g._http = httpx.Client(base_url="https://groq.test/v1", transport=httpx.MockTransport(handler))
    return g


def test_provider_resolution(monkeypatch):
    assert settings(monkeypatch).provider == "local"
    s = settings(monkeypatch, GROQ_API_KEY="k")
    assert (s.provider, s.ai_wanted, s.llm_model) == ("groq", True, "openai/gpt-oss-120b")
    s = settings(monkeypatch, AWS_BEARER_TOKEN_BEDROCK="t")
    assert (s.provider, s.bedrock_wanted) == ("bedrock", True)
    assert settings(monkeypatch, GROQ_API_KEY="k", AWS_BEARER_TOKEN_BEDROCK="t").provider == "groq"
    s = settings(monkeypatch, NIMBUS_LLM_PROVIDER="groq")
    assert (s.provider, s.ai_wanted) == ("groq", False)
    assert settings(monkeypatch, GROQ_API_KEY="k", NIMBUS_AI_MODE="local").provider == "local"


def test_settings_repr_hides_key(monkeypatch):
    assert "secret-value" not in repr(settings(monkeypatch, GROQ_API_KEY="secret-value"))


def test_converse_json_reads_forced_tool_call(monkeypatch):
    seen = {}

    def handler(req):
        seen.update(json.loads(req.content))
        call = {"type": "function", "function": {"name": "give", "arguments": '{"verdict": "no_go"}'}}
        return httpx.Response(200, json={"choices": [{"message": {"tool_calls": [call]}}]})

    g = client(monkeypatch, handler)
    out = g.converse_json(model="openai/gpt-oss-20b", system="s", user="u", tool_name="give",
                          tool_description="d", schema=SCHEMA)
    assert out == {"verdict": "no_go"}
    assert seen["tool_choice"] == {"type": "function", "function": {"name": "give"}}
    assert seen["reasoning_effort"] == "low"


def test_tool_validation_failure_retries_in_json_mode(monkeypatch):
    calls = []

    def handler(req):
        body = json.loads(req.content)
        calls.append(body)
        if "tools" in body:
            return httpx.Response(400, json={"error": {"code": "tool_use_failed", "message": "bad args"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": 'Here: {"verdict": "go"}'}}]})

    g = client(monkeypatch, handler)
    out = g.converse_json(model="llama-3.3-70b-versatile", system="s", user="u", tool_name="give",
                          tool_description="d", schema=SCHEMA)
    assert out == {"verdict": "go"}
    assert calls[1]["response_format"] == {"type": "json_object"} and "reasoning_effort" not in calls[1]


def test_rate_limit_beyond_wait_budget_raises(monkeypatch):
    g = client(monkeypatch, lambda req: httpx.Response(429, headers={"retry-after": "120"}, text="slow down"))
    with pytest.raises(AIError, match="429"):
        g.converse_json(model="m", system="s", user="u", tool_name="give", tool_description="d", schema=SCHEMA)


def test_embedder_prefixes_and_normalises(monkeypatch):
    inputs = []

    def handler(req):
        body = json.loads(req.content)
        inputs.extend(body["input"])
        return httpx.Response(200, json={"data": [{"index": i, "embedding": [3.0, 4.0]} for i in range(len(body["input"]))]})

    emb = GroqEmbedder(client(monkeypatch, handler), dim=2, use_cache=False)
    assert emb.id == "groq_nomic_embed_text_v1_5_2"
    assert emb.embed_documents(["a", "b"]) == [[0.6, 0.8], [0.6, 0.8]]
    emb.embed_query("q")
    assert inputs == ["search_document: a", "search_document: b", "search_query: q"]

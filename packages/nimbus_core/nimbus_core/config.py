"""Runtime settings, read once from the environment (.env is passed in by Docker Compose)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    v = os.getenv(name)
    return v.strip() if v and v.strip() else default


def _int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _bool(name: str, default: bool = False) -> bool:
    return _env(name, "true" if default else "false").lower() in ("1", "true", "yes")


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", "postgresql://nimbus:nimbus@localhost:5432/nimbus"), repr=False)
    mqtt_host: str = field(default_factory=lambda: _env("MQTT_HOST", "localhost"))
    mqtt_port: int = field(default_factory=lambda: _int("MQTT_PORT", 1883))
    # Hosted brokers (HiveMQ Cloud, EMQX Cloud) need a login and TLS, usually on port 8883.
    mqtt_username: str = field(default_factory=lambda: _env("MQTT_USERNAME"))
    mqtt_password: str = field(default_factory=lambda: _env("MQTT_PASSWORD"), repr=False)
    mqtt_tls: bool = field(default_factory=lambda: _bool("MQTT_TLS"))
    chroma_host: str = field(default_factory=lambda: _env("CHROMA_HOST", "localhost"))
    chroma_port: int = field(default_factory=lambda: _int("CHROMA_PORT", 8000))
    # Chroma Cloud: CHROMA_HOST=api.trychroma.com, CHROMA_PORT=443, CHROMA_SSL=true, plus key, tenant and database.
    chroma_ssl: bool = field(default_factory=lambda: _bool("CHROMA_SSL"))
    chroma_api_key: str = field(default_factory=lambda: _env("CHROMA_API_KEY"), repr=False)
    chroma_tenant: str = field(default_factory=lambda: _env("CHROMA_TENANT"))
    chroma_database: str = field(default_factory=lambda: _env("CHROMA_DATABASE"))
    data_dir: Path = field(default_factory=lambda: Path(_env("NIMBUS_DATA_DIR", "data")))

    # auto: use the AI provider when its credentials are present and a probe call succeeds; else local fallback.
    ai_mode: str = field(default_factory=lambda: _env("NIMBUS_AI_MODE", "auto").lower())
    # auto: Groq when GROQ_API_KEY is set, else AWS Bedrock | groq | bedrock
    llm_provider: str = field(default_factory=lambda: _env("NIMBUS_LLM_PROVIDER", "auto").lower())

    groq_api_key: str = field(default_factory=lambda: _env("GROQ_API_KEY"), repr=False)
    groq_base_url: str = field(default_factory=lambda: _env("GROQ_BASE_URL", "https://api.groq.com/openai/v1"))
    groq_llm_model: str = field(default_factory=lambda: _env("GROQ_LLM_MODEL_ID", "openai/gpt-oss-120b"))
    groq_fast_llm_model: str = field(default_factory=lambda: _env("GROQ_FAST_LLM_MODEL_ID", "openai/gpt-oss-20b"))
    groq_embed_model: str = field(default_factory=lambda: _env("GROQ_EMBED_MODEL_ID", "nomic-embed-text-v1_5"))
    # gpt-oss models spend completion tokens on reasoning; low keeps answers fast and inside free-tier TPM.
    groq_reasoning_effort: str = field(default_factory=lambda: _env("GROQ_REASONING_EFFORT", "low"))
    groq_max_retry_wait_s: int = field(default_factory=lambda: _int("GROQ_MAX_RETRY_WAIT_S", 30))

    aws_region: str = field(default_factory=lambda: _env("AWS_REGION", _env("AWS_DEFAULT_REGION", "us-east-1")))
    embed_model: str = field(default_factory=lambda: _env("BEDROCK_EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0"))
    embed_dim: int = field(default_factory=lambda: _int("BEDROCK_EMBED_DIM", 1024))
    bedrock_llm_model: str = field(default_factory=lambda: _env("BEDROCK_LLM_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0"))
    bedrock_fast_llm_model: str = field(default_factory=lambda: _env("BEDROCK_FAST_LLM_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0"))
    rerank_model: str = field(default_factory=lambda: _env("BEDROCK_RERANK_MODEL_ID", "amazon.rerank-v1:0"))
    # Rerank models are only offered in some regions (e.g. us-west-2); defaults to AWS_REGION.
    rerank_region: str = field(default_factory=lambda: _env("BEDROCK_RERANK_REGION", ""))
    rerank_enabled: bool = field(default_factory=lambda: _env("BEDROCK_RERANK_ENABLED", "true").lower() in ("1", "true", "yes"))
    embed_workers: int = field(default_factory=lambda: _int("BEDROCK_EMBED_WORKERS", 4))

    # Fusion TTLs (seconds). Demo compose shortens the sensor/camera TTLs to match faster publishing.
    sensor_ttl_s: int = field(default_factory=lambda: _int("SENSOR_TTL_S", 90))
    cctv_ttl_s: int = field(default_factory=lambda: _int("CCTV_TTL_S", 300))
    venue_tz: str = field(default_factory=lambda: _env("NIMBUS_VENUE_TZ", ""))

    @property
    def aws_credentials_present(self) -> bool:
        return self.iam_credentials_present or bool(_env("AWS_BEARER_TOKEN_BEDROCK"))

    @property
    def iam_credentials_present(self) -> bool:
        return bool(_env("AWS_ACCESS_KEY_ID") and _env("AWS_SECRET_ACCESS_KEY")) or bool(_env("AWS_PROFILE"))

    @property
    def provider(self) -> str:
        """Resolved AI provider: groq | bedrock | local."""
        if self.ai_mode == "local":
            return "local"
        if self.llm_provider in ("groq", "bedrock"):
            return self.llm_provider
        if self.groq_api_key:
            return "groq"
        if self.ai_mode == "bedrock" or self.aws_credentials_present:
            return "bedrock"
        return "local"

    @property
    def provider_label(self) -> str:
        return {"groq": "Groq", "bedrock": "AWS Bedrock"}.get(self.provider, "local fallback")

    @property
    def credentials_present(self) -> bool:
        return bool(self.groq_api_key) if self.provider == "groq" else self.aws_credentials_present

    @property
    def ai_wanted(self) -> bool:
        if self.provider == "local":
            return False
        return self.ai_mode in ("bedrock", "groq") or self.credentials_present

    @property
    def bedrock_wanted(self) -> bool:
        return self.provider == "bedrock" and self.ai_wanted

    @property
    def llm_model(self) -> str:
        return self.groq_llm_model if self.provider == "groq" else self.bedrock_llm_model

    @property
    def fast_llm_model(self) -> str:
        return self.groq_fast_llm_model if self.provider == "groq" else self.bedrock_fast_llm_model


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

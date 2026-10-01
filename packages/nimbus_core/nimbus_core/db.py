"""Thin Postgres access layer shared by the worker and the API (psycopg 3, sync pool)."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from importlib import resources
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from .config import get_settings
from .fusion import FusedState, Observation

log = logging.getLogger("nimbus.db")
_pool: ConnectionPool | None = None

EVENTS_CHANNEL = "nimbus_events"


def wait_for_db(timeout_s: int = 90) -> None:
    url = get_settings().database_url
    deadline = time.time() + timeout_s
    while True:
        try:
            with psycopg.connect(url, connect_timeout=3) as c:
                c.execute("SELECT 1")
            return
        except Exception as e:  # noqa: BLE001
            if time.time() > deadline:
                raise
            log.info("waiting for postgres: %s", e)
            time.sleep(2)


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(get_settings().database_url, min_size=1, max_size=10,
                               kwargs={"row_factory": dict_row, "autocommit": True}, open=True)
    return _pool


def apply_schema() -> None:
    sql = resources.files("nimbus_core").joinpath("schema.sql").read_text(encoding="utf-8")
    with pool().connection() as c:
        c.execute(sql)


def notify(event: dict[str, Any]) -> None:
    payload = json.dumps(event, default=str)
    if len(payload) > 7000:  # NOTIFY payload limit is 8000 bytes
        payload = json.dumps({k: v for k, v in event.items() if k in ("type", "venue_id", "feature", "id")}, default=str)
    with pool().connection() as c:
        c.execute("SELECT pg_notify(%s, %s)", (EVENTS_CHANNEL, payload))


# ---------------------------------------------------------------- settings

def set_setting(key: str, value: Any) -> None:
    with pool().connection() as c:
        c.execute(
            "INSERT INTO settings(key, value, updated_at) VALUES (%s, %s, now()) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
            (key, Jsonb(value)),
        )


def get_setting(key: str, default: Any = None) -> Any:
    with pool().connection() as c:
        row = c.execute("SELECT value FROM settings WHERE key = %s", (key,)).fetchone()
    return row["value"] if row else default


# ---------------------------------------------------------------- venues

def upsert_venue(config: dict[str, Any]) -> None:
    with pool().connection() as c:
        c.execute(
            "INSERT INTO venues(id, name, config, updated_at) VALUES (%s, %s, %s, now()) "
            "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, config = EXCLUDED.config, updated_at = now()",
            (config["id"], config["name"], Jsonb(config)),
        )
        for ev in config.get("events", []):
            c.execute(
                "INSERT INTO events(id, venue_id, name, start_at, doors_at, location) VALUES (%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, start_at=EXCLUDED.start_at, "
                "doors_at=EXCLUDED.doors_at, location=EXCLUDED.location",
                (ev["id"], config["id"], ev["name"], ev["start"], ev.get("doors"), ev["location"]),
            )


def list_venues() -> list[dict[str, Any]]:
    with pool().connection() as c:
        return c.execute("SELECT id, name, config FROM venues ORDER BY name").fetchall()


def get_venue(venue_id: str) -> dict[str, Any] | None:
    with pool().connection() as c:
        row = c.execute("SELECT config FROM venues WHERE id = %s", (venue_id,)).fetchone()
    return row["config"] if row else None


# ---------------------------------------------------------------- observations / fusion

def insert_observation(venue_id: str, feature: str, status: str, source_kind: str, note: str = "",
                       payload: dict[str, Any] | None = None, confidence: float | None = None,
                       source_ref: str = "", observed_at: datetime | None = None) -> int:
    observed_at = observed_at or datetime.now(timezone.utc)
    with pool().connection() as c:
        row = c.execute(
            "INSERT INTO observations(venue_id, feature, status, source_kind, note, payload, confidence, source_ref, observed_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (venue_id, feature, status, source_kind, note, Jsonb(payload or {}), confidence, source_ref, observed_at),
        ).fetchone()
    return int(row["id"])


def has_observations(venue_id: str, source_ref_prefix: str) -> bool:
    with pool().connection() as c:
        row = c.execute("SELECT 1 FROM observations WHERE venue_id=%s AND source_ref LIKE %s LIMIT 1",
                        (venue_id, source_ref_prefix + "%")).fetchone()
    return row is not None


def latest_observations(venue_id: str) -> list[Observation]:
    """Latest observation per (feature, source kind): all the fusion engine needs."""
    with pool().connection() as c:
        rows = c.execute(
            "SELECT DISTINCT ON (feature, source_kind) id, feature, status, source_kind, note, confidence, source_ref, observed_at "
            "FROM observations WHERE venue_id = %s ORDER BY feature, source_kind, observed_at DESC, id DESC",
            (venue_id,),
        ).fetchall()
    return [Observation(feature=r["feature"], status=r["status"], source_kind=r["source_kind"], observed_at=r["observed_at"],
                        note=r["note"], confidence=r["confidence"], id=r["id"], source_ref=r["source_ref"]) for r in rows]


def observation_history(venue_id: str, feature: str, limit: int = 30) -> list[dict[str, Any]]:
    with pool().connection() as c:
        return c.execute(
            "SELECT id, feature, status, source_kind, note, confidence, source_ref, payload, observed_at FROM observations "
            "WHERE venue_id=%s AND feature=%s ORDER BY observed_at DESC, id DESC LIMIT %s",
            (venue_id, feature, limit),
        ).fetchall()


def get_feature_states(venue_id: str) -> dict[str, FusedState]:
    with pool().connection() as c:
        rows = c.execute("SELECT feature, state FROM feature_status WHERE venue_id = %s", (venue_id,)).fetchall()
    return {r["feature"]: FusedState.from_dict(r["state"]) for r in rows}


def put_feature_state(venue_id: str, state: FusedState) -> None:
    with pool().connection() as c:
        c.execute(
            "INSERT INTO feature_status(venue_id, feature, state, updated_at) VALUES (%s,%s,%s,now()) "
            "ON CONFLICT (venue_id, feature) DO UPDATE SET state = EXCLUDED.state, updated_at = now()",
            (venue_id, state.feature, Jsonb(state.to_dict())),
        )


# ---------------------------------------------------------------- alerts

def insert_alert(venue_id: str, feature: str, kind: str, severity: str, message: str) -> dict[str, Any]:
    with pool().connection() as c:
        return c.execute(
            "INSERT INTO alerts(venue_id, feature, kind, severity, message) VALUES (%s,%s,%s,%s,%s) "
            "RETURNING id, venue_id, feature, kind, severity, message, acked, created_at",
            (venue_id, feature, kind, severity, message),
        ).fetchone()


def list_alerts(venue_id: str, limit: int = 50) -> list[dict[str, Any]]:
    with pool().connection() as c:
        return c.execute(
            "SELECT id, venue_id, feature, kind, severity, message, acked, created_at FROM alerts "
            "WHERE venue_id=%s ORDER BY created_at DESC, id DESC LIMIT %s", (venue_id, limit)).fetchall()


def ack_alert(venue_id: str, alert_id: int) -> None:
    with pool().connection() as c:
        c.execute("UPDATE alerts SET acked = true WHERE venue_id=%s AND id=%s", (venue_id, alert_id))


# ---------------------------------------------------------------- reports

def insert_report(venue_id: str, kind: str, reporter: str, needs: str, text: str) -> int:
    with pool().connection() as c:
        row = c.execute(
            "INSERT INTO reports(venue_id, kind, reporter, needs, text) VALUES (%s,%s,%s,%s,%s) RETURNING id",
            (venue_id, kind, reporter, needs, text),
        ).fetchone()
    return int(row["id"])


def get_report(report_id: int) -> dict[str, Any] | None:
    with pool().connection() as c:
        return c.execute("SELECT * FROM reports WHERE id=%s", (report_id,)).fetchone()


def claim_pending_report() -> dict[str, Any] | None:
    with pool().connection() as c:
        with c.transaction():
            row = c.execute(
                "SELECT * FROM reports WHERE status='pending' ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1").fetchone()
            if row:
                c.execute("UPDATE reports SET status='processing' WHERE id=%s", (row["id"],))
    return row


def finish_report(report_id: int, status: str, extraction: dict[str, Any] | None, error: str | None = None) -> None:
    with pool().connection() as c:
        c.execute("UPDATE reports SET status=%s, extraction=%s, error=%s, processed_at=now() WHERE id=%s",
                  (status, Jsonb(extraction) if extraction is not None else None, error, report_id))


def insert_staff_check(venue_id: str, staff_name: str, items: list[dict[str, Any]]) -> int:
    with pool().connection() as c:
        row = c.execute("INSERT INTO staff_checks(venue_id, staff_name, items) VALUES (%s,%s,%s) RETURNING id",
                        (venue_id, staff_name, Jsonb(items))).fetchone()
    return int(row["id"])


# ---------------------------------------------------------------- chunks / embeddings

def upsert_chunk(chunk_id: str, venue_id: str, doc_id: str, text: str, header: str, meta: dict[str, Any], content_hash: str) -> None:
    with pool().connection() as c:
        c.execute(
            "INSERT INTO chunks(id, venue_id, doc_id, text, header, meta, content_hash) VALUES (%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (id) DO UPDATE SET text=EXCLUDED.text, header=EXCLUDED.header, meta=EXCLUDED.meta, content_hash=EXCLUDED.content_hash",
            (chunk_id, venue_id, doc_id, text, header, Jsonb(meta), content_hash),
        )


def list_chunks(venue_id: str | None = None) -> list[dict[str, Any]]:
    with pool().connection() as c:
        if venue_id:
            return c.execute("SELECT id, venue_id, doc_id, text, header, meta FROM chunks WHERE venue_id=%s ORDER BY id", (venue_id,)).fetchall()
        return c.execute("SELECT id, venue_id, doc_id, text, header, meta FROM chunks ORDER BY id").fetchall()


def chunk_fingerprint() -> str:
    with pool().connection() as c:
        row = c.execute("SELECT count(*) AS n, coalesce(max(created_at)::text, '') AS m FROM chunks").fetchone()
    return f"{row['n']}:{row['m']}"


def upsert_document(doc_id: str, venue_id: str, title: str, source_type: str, trust: str, doc_date: Any, content_hash: str) -> bool:
    """Returns True when the document is new or changed."""
    with pool().connection() as c:
        row = c.execute("SELECT content_hash FROM documents WHERE id=%s", (doc_id,)).fetchone()
        if row and row["content_hash"] == content_hash:
            return False
        c.execute(
            "INSERT INTO documents(id, venue_id, title, source_type, trust, doc_date, content_hash, updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,now()) "
            "ON CONFLICT (id) DO UPDATE SET title=EXCLUDED.title, source_type=EXCLUDED.source_type, trust=EXCLUDED.trust, "
            "doc_date=EXCLUDED.doc_date, content_hash=EXCLUDED.content_hash, updated_at=now()",
            (doc_id, venue_id, title, source_type, trust, doc_date, content_hash),
        )
    return True


def get_cached_embedding(content_hash: str, model_id: str, dim: int) -> list[float] | None:
    with pool().connection() as c:
        row = c.execute("SELECT vector FROM embedding_cache WHERE content_hash=%s AND model_id=%s AND dim=%s",
                        (content_hash, model_id, dim)).fetchone()
    return list(row["vector"]) if row else None


def put_cached_embedding(content_hash: str, model_id: str, dim: int, vector: list[float]) -> None:
    with pool().connection() as c:
        c.execute("INSERT INTO embedding_cache(content_hash, model_id, dim, vector) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                  (content_hash, model_id, dim, vector))


def insert_trace(venue_id: str, question: str, profile: dict, plan: dict, retrieved: list, live_context: list,
                 answer: dict, validation: dict, mode: str, prompt_version: str, latency_ms: int) -> int:
    with pool().connection() as c:
        row = c.execute(
            "INSERT INTO answer_traces(venue_id, question, profile, plan, retrieved, live_context, answer, validation, mode, prompt_version, latency_ms) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (venue_id, question, Jsonb(profile), Jsonb(plan), Jsonb(retrieved), Jsonb(live_context), Jsonb(answer),
             Jsonb(validation), mode, prompt_version, latency_ms),
        ).fetchone()
    return int(row["id"])

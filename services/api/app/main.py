"""Ecstasy API: REST + Server-Sent Events. Docs at /docs."""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from nimbus_core import db, topics
from nimbus_core.config import get_settings
from nimbus_core.features import FEATURES, MOBILITY_LABELS, SOURCE_KINDS, STATUS_LABELS
from nimbus_core.mqtt import publish_once
from nimbus_core.schemas import AskRequest, ReportIn, ScenarioIn, StaffCheckIn
from nimbus_core.visit import hours_text, venue_now

from .events import broadcaster
from .rag.context import refresh_ages
from .rag.listing import listing_health
from .rag.pipeline import AnswerPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("api")
pipeline = AnswerPipeline()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await run_in_threadpool(db.wait_for_db)
    try:
        await run_in_threadpool(db.apply_schema)
    except Exception as e:  # noqa: BLE001  (the worker applies it too; a race here is harmless)
        log.info("schema apply skipped: %s", e)
    broadcaster.start()
    yield
    await broadcaster.stop()


app = FastAPI(
    title="Ecstasy API",
    version="0.2.0",
    lifespan=lifespan,
    # Only /api/* reaches this service on the shared Vercel domain; everything else goes to the web app.
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _venue(venue_id: str) -> dict[str, Any]:
    cfg = db.get_venue(venue_id)
    if cfg is None:
        raise HTTPException(404, f"Unknown venue '{venue_id}'")
    return cfg


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(jsonable_encoder(data))}\n\n"


SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"}


# ------------------------------------------------------------------ meta

@app.get("/api/health")
def health() -> dict[str, Any]:
    s = get_settings()
    index = db.get_setting("index") or {}
    emb = str(index.get("embedder_id", ""))
    if not s.ai_wanted:
        label = "Local fallback (no AI provider)"
    elif s.provider == "groq":
        label = "Groq (embeddings + LLM)" if emb.startswith("groq_") else "Groq LLM (local embeddings)"
    else:
        label = "AWS Bedrock (Titan V2 + Claude)" if emb.startswith("titan") else "Bedrock partially available"
    rerank_on = s.provider == "bedrock" and s.rerank_enabled and s.iam_credentials_present
    return {
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat(),
        "ai": {
            "mode_setting": s.ai_mode,
            "provider": s.provider,
            "provider_label": s.provider_label,
            "credentials_present": s.credentials_present,
            "aws_credentials_present": s.aws_credentials_present,
            "bedrock_enabled": s.ai_wanted,
            "region": s.aws_region if s.provider == "bedrock" else None,
            "llm_model": s.llm_model,
            "fast_llm_model": s.fast_llm_model,
            "embed_model": s.groq_embed_model if s.provider == "groq" else s.embed_model,
            "rerank_model": s.rerank_model if rerank_on else None,
            "index": index,
            "label": label,
        },
    }


@app.get("/api/meta")
def meta() -> dict[str, Any]:
    return {
        "features": {k: {"label": f.label, "stale_after_days": f.stale_after_days} for k, f in FEATURES.items()},
        "statuses": STATUS_LABELS,
        "source_kinds": SOURCE_KINDS,
        "mobility": MOBILITY_LABELS,
        "scenarios": topics.SCENARIOS,
    }


# ------------------------------------------------------------------ venues

@app.get("/api/venues")
def venues() -> list[dict[str, Any]]:
    return [{"id": v["id"], "name": v["name"], "events": v["config"].get("events", [])} for v in db.list_venues()]


@app.get("/api/venues/{venue_id}")
def venue(venue_id: str) -> dict[str, Any]:
    cfg = _venue(venue_id)
    now = venue_now(cfg)
    return {**cfg, "hours_text": hours_text(cfg), "local_time": now.isoformat(),
            "scenario": db.get_setting(f"scenario:{venue_id}", "normal")}


# ------------------------------------------------------------------ ask

@app.post("/api/venues/{venue_id}/ask")
async def ask(venue_id: str, req: AskRequest) -> dict[str, Any]:
    _venue(venue_id)
    return jsonable_encoder(await run_in_threadpool(pipeline.answer, venue_id, req))


async def _ask_stream(venue_id: str, req: AskRequest) -> AsyncIterator[str]:
    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()

    def progress(stage: str, message: str) -> None:
        loop.call_soon_threadsafe(q.put_nowait, ("progress", {"stage": stage, "message": message}))

    async def run() -> None:
        try:
            res = await run_in_threadpool(pipeline.answer, venue_id, req, progress)
            await q.put(("result", res))
        except Exception as e:  # noqa: BLE001
            log.exception("ask failed")
            await q.put(("error", {"message": str(e)[:300]}))
        await q.put(None)

    task = asyncio.create_task(run())
    try:
        while True:
            item = await q.get()
            if item is None:
                break
            yield _sse(*item)
    finally:
        task.cancel()


@app.post("/api/venues/{venue_id}/ask/stream")
async def ask_stream_post(venue_id: str, req: AskRequest) -> StreamingResponse:
    _venue(venue_id)
    return StreamingResponse(_ask_stream(venue_id, req), media_type="text/event-stream", headers=SSE_HEADERS)


@app.get("/api/venues/{venue_id}/ask/stream")
async def ask_stream_get(venue_id: str, body: str = Query(..., description="AskRequest as JSON")) -> StreamingResponse:
    _venue(venue_id)
    try:
        req = AskRequest.model_validate_json(body)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return StreamingResponse(_ask_stream(venue_id, req), media_type="text/event-stream", headers=SSE_HEADERS)


# ------------------------------------------------------------------ live status

def _status_payload(venue_id: str) -> dict[str, Any]:
    states = refresh_ages(db.get_feature_states(venue_id), datetime.now(timezone.utc))
    order = list(FEATURES)
    feats = [states[f].to_dict() for f in order if f in states]
    return {"venue_id": venue_id, "features": feats, "generated_at": datetime.now(timezone.utc).isoformat(),
            "scenario": db.get_setting(f"scenario:{venue_id}", "normal")}


@app.get("/api/venues/{venue_id}/status")
def status(venue_id: str) -> dict[str, Any]:
    _venue(venue_id)
    return jsonable_encoder(_status_payload(venue_id))


@app.get("/api/venues/{venue_id}/features/{feature}/history")
def feature_history(venue_id: str, feature: str, limit: int = 30) -> list[dict[str, Any]]:
    _venue(venue_id)
    if feature not in FEATURES:
        raise HTTPException(404, "Unknown feature")
    return jsonable_encoder(db.observation_history(venue_id, feature, min(limit, 200)))


@app.get("/api/venues/{venue_id}/stream")
async def stream(venue_id: str) -> StreamingResponse:
    _venue(venue_id)

    async def gen() -> AsyncIterator[str]:
        q = broadcaster.subscribe(venue_id)
        try:
            yield "retry: 3000\n\n"
            yield _sse("snapshot", await run_in_threadpool(_status_payload, venue_id))
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                    yield _sse(ev.get("type", "message"), ev)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            broadcaster.unsubscribe(venue_id, q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers=SSE_HEADERS)


# ------------------------------------------------------------------ reports and staff checks

@app.post("/api/venues/{venue_id}/reports", status_code=202)
def submit_report(venue_id: str, body: ReportIn) -> dict[str, Any]:
    _venue(venue_id)
    kind = body.kind or ("staff_note" if body.reporter == "staff" else "visitor_report")
    rid = db.insert_report(venue_id, kind, body.reporter, body.needs, body.text.strip())
    return {"id": rid, "status": "pending", "kind": kind}


@app.get("/api/reports/{report_id}")
def report_status(report_id: int) -> dict[str, Any]:
    row = db.get_report(report_id)
    if row is None:
        raise HTTPException(404, "Unknown report")
    return jsonable_encoder(row)


@app.post("/api/venues/{venue_id}/staff-checks", status_code=201)
def staff_check(venue_id: str, body: StaffCheckIn) -> dict[str, Any]:
    _venue(venue_id)
    bad = [i.model_dump() for i in body.items if not i.valid()]
    if bad:
        raise HTTPException(422, {"invalid_items": bad})
    if not body.items:
        raise HTTPException(422, "No items")
    items = [i.model_dump() for i in body.items]
    cid = db.insert_staff_check(venue_id, body.staff_name, items)
    now = datetime.now(timezone.utc)
    for i in body.items:
        note = i.note or f"Staff check: {STATUS_LABELS[i.status].lower()}."
        db.insert_observation(venue_id, i.feature, i.status, "staff", note, {"staff_name": body.staff_name, "check_id": cid},
                              None, f"staffcheck:{cid}", now)
    return {"id": cid, "items": len(items)}


# ------------------------------------------------------------------ staff tools

@app.get("/api/venues/{venue_id}/listing-health")
async def get_listing_health(venue_id: str) -> dict[str, Any]:
    _venue(venue_id)
    return jsonable_encoder(await run_in_threadpool(listing_health, venue_id))


@app.get("/api/venues/{venue_id}/alerts")
def alerts(venue_id: str, limit: int = 50) -> list[dict[str, Any]]:
    _venue(venue_id)
    return jsonable_encoder(db.list_alerts(venue_id, min(limit, 200)))


@app.post("/api/venues/{venue_id}/alerts/{alert_id}/ack")
def ack(venue_id: str, alert_id: int) -> dict[str, Any]:
    db.ack_alert(venue_id, alert_id)
    return {"ok": True}


@app.get("/api/venues/{venue_id}/traces")
def traces(venue_id: str, limit: int = 20) -> list[dict[str, Any]]:
    with db.pool().connection() as c:
        rows = c.execute("SELECT id, question, mode, prompt_version, latency_ms, answer->>'verdict' AS verdict, validation, created_at "
                         "FROM answer_traces WHERE venue_id=%s ORDER BY id DESC LIMIT %s", (venue_id, min(limit, 100))).fetchall()
    return jsonable_encoder(rows)


@app.get("/api/sim/scenarios")
def scenarios() -> dict[str, str]:
    return topics.SCENARIOS


@app.post("/api/sim/scenario")
def set_scenario(body: ScenarioIn) -> dict[str, Any]:
    _venue(body.venue_id)
    if body.scenario not in topics.SCENARIOS:
        raise HTTPException(422, f"Unknown scenario. Choose one of: {', '.join(topics.SCENARIOS)}")
    payload = {"scenario": body.scenario, "ts": datetime.now(timezone.utc).isoformat()}
    publish_once(topics.control(body.venue_id), payload, retain=True)
    db.set_setting(f"scenario:{body.venue_id}", body.scenario)
    db.notify({"type": "scenario", "venue_id": body.venue_id, "scenario": body.scenario})
    return {"ok": True, **payload}


@app.post("/api/admin/reindex", status_code=202)
def reindex(force: bool = False) -> dict[str, Any]:
    req = {"ts": datetime.now(timezone.utc).isoformat(), "force": force}
    db.set_setting("reindex_requested", req)
    return {"ok": True, "requested": req}

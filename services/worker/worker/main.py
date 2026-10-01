"""Worker entry point: seed, index, consume MQTT, fuse, alert, process text reports."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from nimbus_core import db, topics
from nimbus_core.mqtt import make_client

from .fusion_service import recompute
from .ingest import Indexer
from .reports import process_report
from .seed import seed_venue, venue_dirs
from .translate import cctv_to_obs, lift_telemetry_to_obs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("worker")

FUSION_TICK_S = 2.0
PRUNE_EVERY_S = 3600


def on_device_message(topic: str, payload: dict) -> None:
    parts = topics.parse(topic)
    venue = parts.get("venue")
    if not venue or db.get_venue(venue) is None:
        return
    if parts.get("kind") == "lift" and parts.get("stream") == "telemetry":
        d = lift_telemetry_to_obs(parts["device"], payload)
    elif parts.get("kind") == "cctv" and parts.get("stream") == "detections":
        d = cctv_to_obs(parts["device"], payload)
    else:
        return
    if d is None:
        return
    db.insert_observation(venue, d.feature, d.status, d.source_kind, d.note, d.payload, d.confidence, d.source_ref, d.observed_at)
    recompute(venue)


def prune_machine_observations() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    with db.pool().connection() as c:
        c.execute("DELETE FROM observations WHERE source_kind IN ('sensor','cctv') AND observed_at < %s", (cutoff,))


def main() -> None:
    db.wait_for_db()
    db.apply_schema()
    venues = [seed_venue(d)["id"] for d in venue_dirs()]
    for v in venues:
        recompute(v, quiet_alerts=True)

    indexer = Indexer()
    indexer.index_all()

    client = make_client("worker", on_device_message, [topics.SUB_LIFT, topics.SUB_CCTV])
    client.loop_start()
    log.info("worker running for venues %s", venues)

    last_tick = last_prune = 0.0
    while True:
        try:
            row = db.claim_pending_report()
            while row:
                process_report(row, indexer)
                recompute(row["venue_id"])
                row = db.claim_pending_report()

            req = db.get_setting("reindex_requested")
            if req and req != db.get_setting("reindex_done"):
                indexer.index_all(force=bool(req.get("force")) if isinstance(req, dict) else False)
                db.set_setting("reindex_done", req)

            now = time.time()
            if now - last_tick >= FUSION_TICK_S:
                for v in venues:
                    recompute(v)  # also catches TTL expiry, e.g. a silent lift sensor
                last_tick = now
            if now - last_prune >= PRUNE_EVERY_S:
                prune_machine_observations()
                last_prune = now
        except Exception:  # noqa: BLE001
            log.exception("worker loop error")
            time.sleep(2)
        time.sleep(0.5)


if __name__ == "__main__":
    main()

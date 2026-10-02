"""Runs the fusion engine against Postgres, persists changes, raises alerts, notifies the API."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from nimbus_core import db
from nimbus_core.config import get_settings
from nimbus_core.features import use_venue
from nimbus_core.fusion import derive_alerts, fuse_all, source_rules, state_changed

log = logging.getLogger("worker.fusion")
_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


def _lock(venue_id: str) -> threading.Lock:
    with _guard:
        return _locks.setdefault(venue_id, threading.Lock())


def rules():
    s = get_settings()
    return source_rules(s.sensor_ttl_s, s.cctv_ttl_s)


def recompute(venue_id: str, now: datetime | None = None, quiet_alerts: bool = False) -> int:
    """Fuse the latest observations; returns the number of features whose state changed."""
    now = now or datetime.now(timezone.utc)
    with _lock(venue_id):
        use_venue(db.get_venue(venue_id))
        states = fuse_all(db.latest_observations(venue_id), now, rules())
        prev = db.get_feature_states(venue_id)
        changed = 0
        for fid, st in states.items():
            p = prev.get(fid)
            if not state_changed(p, st):
                continue
            changed += 1
            db.put_feature_state(venue_id, st)
            db.notify({"type": "status", "venue_id": venue_id, "feature": fid, "state": st.to_dict()})
            if quiet_alerts:
                continue
            for a in derive_alerts(p, st):
                row = db.insert_alert(venue_id, a.feature, a.kind, a.severity, a.message)
                log.info("ALERT %s %s: %s", a.severity, a.feature, a.message)
                db.notify({"type": "alert", "venue_id": venue_id, "alert": row})
        return changed

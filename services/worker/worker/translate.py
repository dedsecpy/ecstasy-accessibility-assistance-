"""Device messages -> observations. Pure functions so they are easy to test.

Thresholds: 900 mm is a common minimum clear width for wheelchair routes; below
750 mm many manual chairs cannot pass at all.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

MIN_CLEAR_MM = 900
BLOCKED_MM = 750
UNANSWERED_WAIT_S = 120


@dataclass
class ObsDraft:
    feature: str
    status: str
    source_kind: str
    note: str
    confidence: float
    observed_at: datetime
    payload: dict[str, Any]
    source_ref: str


def _ts(payload: dict[str, Any]) -> datetime:
    try:
        dt = datetime.fromisoformat(str(payload.get("ts")))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def lift_telemetry_to_obs(lift_id: str, p: dict[str, Any]) -> ObsDraft:
    fault = p.get("fault_code")
    power = p.get("power", "on")
    door = p.get("door", "closed")
    floor = p.get("floor")
    if power != "on":
        status, note = "out_of_service", "Lift has no power."
    elif fault and "BETWEEN" in str(fault).upper():
        status, note = "out_of_service", f"Lift stopped between floors (fault {fault})."
    elif fault or door == "fault":
        status, note = "out_of_service", f"Lift fault reported by controller ({fault or 'door fault'})."
    else:
        status, note = "ok", "Lift responding normally to calls."
    return ObsDraft("lift", status, "sensor", note, 0.95, _ts(p),
                    {"lift_id": lift_id, "floor": floor, "moving": p.get("moving"), "door": door, "fault_code": fault, "seq": p.get("seq")},
                    f"mqtt:lift:{lift_id}")


def cctv_to_obs(camera_id: str, p: dict[str, Any]) -> ObsDraft | None:
    feature = p.get("feature")
    conf = float(p.get("confidence") or 0.9)
    ref = f"mqtt:cctv:{camera_id}"
    if feature == "side_gate":
        if p.get("gate_open"):
            return ObsDraft("side_gate", "ok", "cctv", "Side gate seen open.", conf, _ts(p), p, ref)
        waiting = int(p.get("person_waiting_s") or 0)
        if waiting >= UNANSWERED_WAIT_S and not p.get("staff_present"):
            return ObsDraft("side_gate", "locked_unanswered", "cctv",
                            f"Gate closed; a visitor has been waiting about {waiting // 60} min with no staff seen.", conf, _ts(p), p, ref)
        return ObsDraft("side_gate", "locked_on_request", "cctv", "Gate closed as usual (opened on request via intercom).", conf, _ts(p), p, ref)
    if feature == "courtyard_path":
        width = p.get("path_clear_width_mm")
        obstruction = p.get("obstruction")
        if width is None:
            return None
        what = f" ({obstruction})" if obstruction else ""
        if width < BLOCKED_MM:
            return ObsDraft("courtyard_path", "out_of_service", "cctv", f"Path blocked: about {width} mm clear{what}.", conf, _ts(p), p, ref)
        if width < MIN_CLEAR_MM:
            rounded = int(round(width, -1))
            return ObsDraft("courtyard_path", "degraded", "cctv",
                            f"Path narrowed to about {rounded} mm{what}; larger powered chairs and scooters may not pass.", conf, _ts(p), p, ref)
        return ObsDraft("courtyard_path", "ok", "cctv", "Path clear at full width (over 1.4 m).", conf, _ts(p), p, ref)
    if feature == "seating":
        free = p.get("seats_free")
        total = p.get("seats_total") or 4
        if free is None:
            return None
        if free == 0:
            return ObsDraft("seating", "degraded", "cctv", f"All {total} foyer chairs taken.", conf, _ts(p), p, ref)
        return ObsDraft("seating", "ok", "cctv", f"{free} of {total} foyer chairs free.", conf, _ts(p), p, ref)
    return None

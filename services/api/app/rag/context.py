"""Structured live context: the fused status board as citable items S1..Sn."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from nimbus_core.features import FEATURES, SOURCE_KINDS
from nimbus_core.fusion import FusedState, age_text

from .retrieval import Passage


def refresh_ages(states: dict[str, FusedState], now: datetime | None = None) -> dict[str, FusedState]:
    now = now or datetime.now(timezone.utc)
    for s in states.values():
        try:
            s.age_s = max(0, int((now - datetime.fromisoformat(s.observed_at)).total_seconds()))
        except ValueError:
            pass
    return states


def live_items(states: dict[str, FusedState], required: list[str], context_features: list[str]) -> list[dict[str, Any]]:
    order = list(required) + [f for f in context_features if f not in required]
    order += [f for f in FEATURES if f not in order]
    items = []
    for fid in order:
        s = states.get(fid)
        if s is None:
            continue
        items.append({
            "sid": f"S{len(items) + 1}",
            "feature": fid,
            "label": s.label,
            "status": s.status,
            "status_label": s.status_label,
            "source_kind": s.source_kind,
            "source_label": SOURCE_KINDS.get(s.source_kind, s.source_kind),
            "observed_at": s.observed_at,
            "age_s": s.age_s,
            "age_text": age_text(s.age_s),
            "stale": s.stale,
            "conflict": s.conflict,
            "sensor_offline": s.sensor_offline,
            "blocking": s.blocking,
            "note": s.note,
            "required": fid in required,
        })
    return items


def live_text(items: list[dict[str, Any]]) -> str:
    lines = []
    for it in items:
        flags = []
        if it["required"]:
            flags.append("REQUIRED")
        if it["stale"]:
            flags.append("STALE")
        if it["conflict"]:
            flags.append("SOURCES DISAGREE")
        if it["sensor_offline"]:
            flags.append("SENSOR OFFLINE")
        lines.append(f"{it['sid']} [{it['feature']}] {it['label']}: {it['status_label']} ({it['status']}) - "
                     f"{it['source_label']}, {it['age_text']}{' - ' + ', '.join(flags) if flags else ''}. {it['note']}")
    return "\n".join(lines)


def passages_text(passages: list[Passage], today: date) -> str:
    out = []
    for p in passages:
        age = (today - date.fromisoformat(p.date)).days if p.date else "?"
        out.append(f"{p.pid} [{p.header} | trust {p.trust} | {age} days old]\n{p.text}")
    return "\n\n".join(out)

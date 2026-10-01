"""Feature vocabulary and the dated fact log that sits beside the documents.

Each access feature has a stable id, a human label, and a staleness window:
how long a status report can be trusted before the answer should say
"last confirmed N days ago - verify". Permanent features (a staircase, a
ramp gradient) never go stale.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class Feature:
    id: str
    label: str
    stale_after_days: int | None  # None = permanent, never stale
    keywords: tuple[str, ...]


FEATURES: dict[str, Feature] = {
    f.id: f
    for f in [
        Feature("lift", "Lift", 7, ("lift", "elevator", "floors", "upstairs", "first floor")),
        Feature("side_gate", "Side Gate (Mill Lane)", 7, ("side gate", "gate", "mill lane", "locked")),
        Feature("intercom", "Side Gate intercom", 30, ("intercom", "buzzer", "bell")),
        Feature("main_entrance", "Main entrance", None, ("main entrance", "front door", "steps", "stairs", "staircase")),
        Feature("ramp", "Courtyard ramp", 60, ("ramp", "slope", "gradient", "handrail", "steep")),
        Feature("courtyard_path", "Courtyard path", 14, ("courtyard", "path", "scaffolding", "narrow", "works", "obstacle")),
        Feature("seating", "Seating and rest points", 30, ("seat", "seating", "bench", "chair", "rest", "sit")),
        Feature("toilet", "Accessible toilet", None, ("toilet", "wc", "bathroom", "restroom")),
        Feature("parking", "Blue badge parking", None, ("parking", "blue badge", "car park", "drop-off", "drop off")),
        Feature("assistance_desk", "Assistance desk", 90, ("assistance", "staff", "help", "pre-book", "prebook", "desk")),
        Feature("hearing_loop", "Hearing loop", None, ("hearing loop", "induction loop", "loop")),
    ]
}

STATUS_LABELS = {
    "ok": "Working / available",
    "degraded": "Usable with limitations",
    "out_of_service": "Out of service",
    "not_step_free": "Not step-free",
    "locked_on_request": "Locked - opened on request",
    "locked_unanswered": "Locked - intercom unanswered",
    "unknown": "Unknown / untested",
}

# Statuses that mean "do not rely on this feature right now".
BLOCKING_STATUSES = {"out_of_service", "not_step_free", "locked_unanswered"}


@dataclass
class FeatureStatus:
    feature: Feature
    status: str
    date: date
    note: str
    source: str
    source_type: str
    age_days: int
    stale: bool
    history: list[dict[str, Any]]

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status)

    @property
    def freshness_text(self) -> str:
        if self.feature.stale_after_days is None:
            return f"permanent feature, recorded {self.date.isoformat()}"
        if self.age_days == 0:
            return "confirmed today"
        base = f"last confirmed {self.age_days} day{'s' if self.age_days != 1 else ''} ago ({self.date.isoformat()})"
        return base + (" - may be out of date" if self.stale else "")


def latest_statuses(facts: list[dict[str, Any]], today: date) -> dict[str, FeatureStatus]:
    """Collapse the fact log to the most recent status per feature."""
    by_feature: dict[str, list[dict[str, Any]]] = {}
    for f in facts:
        if f.get("feature") in FEATURES:
            by_feature.setdefault(f["feature"], []).append(f)
    out: dict[str, FeatureStatus] = {}
    for fid, items in by_feature.items():
        items.sort(key=lambda x: x.get("date", ""))
        latest = items[-1]
        d = date.fromisoformat(latest["date"][:10])
        feat = FEATURES[fid]
        age = (today - d).days
        stale = feat.stale_after_days is not None and age > feat.stale_after_days
        out[fid] = FeatureStatus(
            feature=feat,
            status=latest.get("status", "unknown"),
            date=d,
            note=latest.get("note", ""),
            source=latest.get("source", ""),
            source_type=latest.get("source_type", ""),
            age_days=age,
            stale=stale,
            history=items,
        )
    return out


def status_board_text(statuses: dict[str, FeatureStatus]) -> str:
    """Render the status board as compact text for an LLM prompt."""
    lines = []
    for fid in FEATURES:
        s = statuses.get(fid)
        if not s:
            continue
        lines.append(
            f"- {s.feature.label}: {s.status_label} [{s.status}] - {s.freshness_text}; "
            f"source: {s.source}. {s.note}"
        )
    return "\n".join(lines)

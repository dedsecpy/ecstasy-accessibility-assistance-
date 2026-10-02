"""Feature vocabulary, status labels and the profile model.

Each access feature has a stable id, a label and a staleness window (how long a
human-sourced status can be trusted before the answer must say "verify").
Permanent features (a staircase, a ramp gradient) never go stale.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Feature:
    id: str
    label: str
    stale_after_days: int | None
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
    "locked_unanswered": "Locked - nobody answering",
    "verify": "Sources disagree - verify",
    "unknown": "Unknown / untested",
}

# Statuses that mean "do not rely on this feature right now".
BLOCKING_STATUSES = {"out_of_service", "not_step_free", "locked_unanswered"}
# Statuses that count as "fine" when checking for disagreement between sources.
OK_STATUSES = {"ok", "locked_on_request"}

SOURCE_KINDS = {
    "sensor": "Lift sensor (live)",
    "cctv": "Camera detection (live)",
    "staff": "Staff check",
    "maintenance_log": "Maintenance log",
    "report": "Visitor report",
    "audit": "Access audit",
    "policy": "Visitor services policy",
}

# Mapping from document source_type (frontmatter) to observation source kind.
SOURCE_TYPE_TO_KIND = {
    "maintenance_log": "maintenance_log",
    "staff_note": "staff",
    "visitor_report": "report",
    "audit": "audit",
    "policy": "policy",
}

SOURCE_TYPE_LABELS = {
    "listing": "Public listing",
    "audit": "Access audit",
    "maintenance_log": "Maintenance log",
    "staff_note": "Staff note",
    "policy": "Visitor services",
    "events": "Event programme",
    "visitor_report": "Visitor report",
}

TIME_SENSITIVE_TYPES = {"maintenance_log", "staff_note", "visitor_report"}
TRUST_WEIGHT = {"high": 1.0, "medium": 0.95, "low": 0.85}

MOBILITY_LABELS = {
    "manual_wheelchair": "Manual wheelchair user",
    "powered_wheelchair": "Powered wheelchair user",
    "mobility_scooter": "Mobility scooter user",
    "walks_short_distances": "Walks short distances only (may use a stick or frame)",
    "other": "Other / prefer not to say",
}
WHEELED = {"manual_wheelchair", "powered_wheelchair", "mobility_scooter"}
WIDE = {"powered_wheelchair", "mobility_scooter"}

MOBILITY_QUERY_TERMS = {
    "manual_wheelchair": "wheelchair step-free steps lift ramp slope gate entrance path width",
    "powered_wheelchair": "wheelchair step-free steps lift ramp gate entrance path width narrow",
    "mobility_scooter": "wheelchair step-free steps lift ramp gate entrance path width narrow",
    "walks_short_distances": "seating bench chair rest distance slope ramp steps lift walk",
    "other": "accessible entrance lift seating",
}


# Place names used in route wording. Each venue.json can override them under "terms" (and feature
# labels under "feature_labels"); these defaults describe Riverside Hall.
DEFAULT_TERMS = {
    "gate": "the Side Gate",
    "gate_where": "the Side Gate on Mill Lane",
    "path": "the courtyard path",
    "path_area": "the courtyard",
    "bypass": "the delivery-entrance bypass",
    "bypass_long": "the portable-ramp bypass via the delivery entrance",
    "ramp_to": "the ground floor foyer",
    "lift_from": "the foyer",
    "seat_reserve": "a foyer chair and an end-of-row seat",
    "seating_short": "seating on the route is scarce and the foyer chairs are taken",
}

_venue_names: ContextVar[tuple[dict[str, str], dict[str, str]]] = ContextVar("venue_names", default=({}, {}))


def use_venue(config: dict[str, Any] | None) -> None:
    """Make feature_label() and term() speak about this venue for the rest of the current request or task."""
    cfg = config or {}
    _venue_names.set((dict(cfg.get("feature_labels") or {}), dict(cfg.get("terms") or {})))


def term(key: str, capital: bool = False) -> str:
    s = _venue_names.get()[1].get(key) or DEFAULT_TERMS[key]
    return s[:1].upper() + s[1:] if capital else s


def terms() -> dict[str, str]:
    """All place terms for the current venue, plus capitalised variants (gate_cap, path_cap, ...)."""
    out = {k: term(k) for k in DEFAULT_TERMS}
    out.update({f"{k}_cap": term(k, capital=True) for k in DEFAULT_TERMS})
    return out


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def feature_label(fid: str) -> str:
    override = _venue_names.get()[0].get(fid)
    if override:
        return override
    f = FEATURES.get(fid)
    return f.label if f else fid

"""Deterministic fusion engine: many observations in, one trusted status per feature out.

Rules (safety first, no LLM involved):
- Each feature has a source table: (source kind, TTL, confidence) in priority order.
- A live machine source (lift sensor, camera) that is within its TTL wins.
- Otherwise the freshest non-expired human source wins (ties broken by priority).
- If nothing is within its TTL, the most recent record is used and marked stale.
- A machine that says "fine" while a strong human record says "blocked" -> status "verify".
  (A machine reporting a fault always wins: a fresh fault is never argued away.)
- A sensor past its TTL is "offline": we fall back to the next source and, if that
  source says the lift works, the status becomes "unknown". It never assumes the lift is working.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from .features import BLOCKING_STATUSES, FEATURES, OK_STATUSES, SOURCE_KINDS, feature_label, status_label

DAY = 86400
MACHINE_KINDS = {"sensor", "cctv"}
STRONG_CONFIDENCE = 0.8


@dataclass(frozen=True)
class SourceRule:
    kind: str
    ttl_s: int | None  # None = permanent record (structural fact)
    confidence: float


def source_rules(sensor_ttl_s: int = 90, cctv_ttl_s: int = 300) -> dict[str, list[SourceRule]]:
    R = SourceRule
    return {
        "lift": [R("sensor", sensor_ttl_s, 0.95), R("staff", 1 * DAY, 0.9), R("maintenance_log", 7 * DAY, 0.85), R("report", 3 * DAY, 0.6)],
        "side_gate": [R("cctv", cctv_ttl_s, 0.9), R("staff", 7 * DAY, 0.9), R("report", 3 * DAY, 0.6), R("audit", None, 0.7)],
        "intercom": [R("staff", 30 * DAY, 0.9), R("report", 3 * DAY, 0.6), R("audit", 30 * DAY, 0.5)],
        "courtyard_path": [R("cctv", cctv_ttl_s, 0.85), R("staff", 14 * DAY, 0.9), R("report", 3 * DAY, 0.6)],
        "seating": [R("cctv", cctv_ttl_s, 0.85), R("staff", 30 * DAY, 0.9), R("report", 7 * DAY, 0.6), R("audit", None, 0.5)],
        "main_entrance": [R("audit", None, 0.95), R("staff", None, 0.9), R("report", 30 * DAY, 0.6)],
        "ramp": [R("staff", 60 * DAY, 0.9), R("audit", None, 0.85), R("report", 7 * DAY, 0.6)],
        "toilet": [R("audit", None, 0.9), R("staff", 30 * DAY, 0.9), R("report", 7 * DAY, 0.6)],
        "parking": [R("audit", None, 0.9), R("staff", 90 * DAY, 0.9), R("report", 30 * DAY, 0.6)],
        "assistance_desk": [R("policy", 365 * DAY, 0.9), R("staff", 90 * DAY, 0.9), R("report", 7 * DAY, 0.6)],
        "hearing_loop": [R("audit", None, 0.8), R("staff", 90 * DAY, 0.9), R("report", 30 * DAY, 0.6)],
    }


@dataclass
class Observation:
    feature: str
    status: str
    source_kind: str
    observed_at: datetime
    note: str = ""
    confidence: float | None = None
    id: int | None = None
    source_ref: str = ""


@dataclass
class Evidence:
    obs_id: int | None
    source_kind: str
    status: str
    note: str
    observed_at: str
    age_s: int
    expired: bool
    confidence: float
    source_ref: str = ""


@dataclass
class FusedState:
    feature: str
    status: str
    confidence: float
    source_kind: str
    note: str
    observed_at: str
    age_s: int
    stale: bool = False
    conflict: bool = False
    sensor_offline: bool = False
    evidence: list[Evidence] = field(default_factory=list)

    @property
    def label(self) -> str:
        return feature_label(self.feature)

    @property
    def status_label(self) -> str:
        return status_label(self.status)

    @property
    def blocking(self) -> bool:
        return self.status in BLOCKING_STATUSES

    def freshness_text(self) -> str:
        return f"{age_text(self.age_s)} via {SOURCE_KINDS.get(self.source_kind, self.source_kind).lower()}" + (
            " - may be out of date" if self.stale else ""
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["label"] = self.label
        d["status_label"] = self.status_label
        d["blocking"] = self.blocking
        d["freshness"] = self.freshness_text()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "FusedState":
        ev = [Evidence(**e) for e in d.get("evidence", [])]
        keys = {k: d[k] for k in ("feature", "status", "confidence", "source_kind", "note", "observed_at", "age_s", "stale", "conflict", "sensor_offline") if k in d}
        return cls(**keys, evidence=ev)


def age_text(age_s: int) -> str:
    if age_s < 0:
        age_s = 0
    if age_s < 90:
        return f"{age_s} s ago"
    if age_s < 5400:
        return f"{age_s // 60} min ago"
    if age_s < 2 * DAY:
        return f"{age_s // 3600} h ago"
    return f"{age_s // DAY} days ago"


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _disagree_machine_ok_human_blocked(machine_status: str, human_status: str) -> bool:
    return machine_status in OK_STATUSES and human_status in BLOCKING_STATUSES


def fuse_feature(feature: str, observations: Iterable[Observation], now: datetime,
                 rules: dict[str, list[SourceRule]] | None = None) -> FusedState | None:
    rules = rules or source_rules()
    now = _aware(now)
    table = list(rules.get(feature, []))
    obs = [o for o in observations if o.feature == feature]
    if not obs:
        return None
    known = {r.kind for r in table}
    stale_days = FEATURES[feature].stale_after_days if feature in FEATURES else 7
    for kind in sorted({o.source_kind for o in obs} - known):
        table.append(SourceRule(kind, None if stale_days is None else stale_days * DAY, 0.5))

    latest: dict[str, Observation] = {}
    for o in obs:
        cur = latest.get(o.source_kind)
        if cur is None or _aware(o.observed_at) >= _aware(cur.observed_at):
            latest[o.source_kind] = o

    cands: list[tuple[int, SourceRule, Observation, int, bool]] = []
    for prio, rule in enumerate(table):
        o = latest.get(rule.kind)
        if o is None:
            continue
        age = int((now - _aware(o.observed_at)).total_seconds())
        expired = rule.ttl_s is not None and age > rule.ttl_s
        cands.append((prio, rule, o, age, expired))
    if not cands:
        return None

    def conf(rule: SourceRule, o: Observation) -> float:
        return float(o.confidence) if o.confidence is not None else rule.confidence

    active = [c for c in cands if not c[4]]
    machine_active = [c for c in active if c[1].kind in MACHINE_KINDS]
    human_active = [c for c in active if c[1].kind not in MACHINE_KINDS]
    stale = False
    if machine_active:
        winner = machine_active[0]
    elif human_active:
        winner = max(human_active, key=lambda c: (_aware(c[2].observed_at), -c[0]))
    else:
        winner = max(cands, key=lambda c: (_aware(c[2].observed_at), -c[0]))
        stale = True

    _, w_rule, w_obs, w_age, _ = winner
    status = w_obs.status
    note = w_obs.note
    confidence = conf(w_rule, w_obs) * (0.5 if stale else 1.0)

    sensor_offline = any(c[1].kind == "sensor" and c[4] for c in cands)
    if sensor_offline and status in OK_STATUSES:
        status = "unknown"
        note = (f"Lift sensor silent (last reading {age_text(next(c[3] for c in cands if c[1].kind == 'sensor'))}). "
                f"Last {SOURCE_KINDS.get(w_rule.kind, w_rule.kind).lower()} said working: {w_obs.note}")

    conflict = False
    if w_rule.kind in MACHINE_KINDS:
        for _, rule, o, _, _ in human_active:
            if conf(rule, o) >= STRONG_CONFIDENCE and _disagree_machine_ok_human_blocked(w_obs.status, o.status):
                conflict = True
                note = (f"{SOURCE_KINDS[w_rule.kind]} says {status_label(w_obs.status).lower()}, but "
                        f"{SOURCE_KINDS.get(rule.kind, rule.kind).lower()} says {status_label(o.status).lower()}: {o.note}")
                break
    if conflict:
        status = "verify"

    evidence = [
        Evidence(o.id, rule.kind, o.status, o.note, _aware(o.observed_at).isoformat(), age, expired, conf(rule, o), o.source_ref)
        for _, rule, o, age, expired in cands
    ]
    return FusedState(
        feature=feature, status=status, confidence=round(confidence, 3), source_kind=w_rule.kind, note=note,
        observed_at=_aware(w_obs.observed_at).isoformat(), age_s=w_age, stale=stale, conflict=conflict,
        sensor_offline=sensor_offline, evidence=evidence,
    )


def fuse_all(observations: Iterable[Observation], now: datetime,
             rules: dict[str, list[SourceRule]] | None = None) -> dict[str, FusedState]:
    obs = list(observations)
    out: dict[str, FusedState] = {}
    for fid in FEATURES:
        st = fuse_feature(fid, obs, now, rules)
        if st:
            out[fid] = st
    return out


@dataclass
class AlertDraft:
    feature: str
    kind: str  # blocking | conflict | sensor_offline | resolved | stale
    severity: str  # high | medium | info
    message: str


def derive_alerts(prev: FusedState | None, new: FusedState) -> list[AlertDraft]:
    """Alerts fire on transitions only, so a steady state never spams staff."""
    out: list[AlertDraft] = []
    label = new.label
    was_blocking = bool(prev and prev.status in BLOCKING_STATUSES)
    if new.status in BLOCKING_STATUSES and (not was_blocking or (prev and prev.status != new.status)):
        out.append(AlertDraft(new.feature, "blocking", "high",
                              f"{label}: {new.status_label.lower()} ({SOURCE_KINDS.get(new.source_kind, new.source_kind).lower()}). {new.note}"))
    if new.conflict and not (prev and prev.conflict):
        out.append(AlertDraft(new.feature, "conflict", "high", f"{label}: sources disagree. {new.note} Please check in person and record a staff check."))
    if new.sensor_offline and not (prev and prev.sensor_offline):
        out.append(AlertDraft(new.feature, "sensor_offline", "medium",
                              f"{label}: live sensor has gone silent. Falling back to {SOURCE_KINDS.get(new.source_kind, new.source_kind).lower()}; status shown as {new.status_label.lower()}."))
    if prev and (prev.status in BLOCKING_STATUSES or prev.status == "verify") and new.status in OK_STATUSES:
        out.append(AlertDraft(new.feature, "resolved", "info", f"{label}: back to {new.status_label.lower()} ({SOURCE_KINDS.get(new.source_kind, new.source_kind).lower()})."))
    return out


def state_changed(prev: FusedState | None, new: FusedState) -> bool:
    if prev is None:
        return True
    # observed_at is included so a steady live sensor still refreshes "updated N s ago".
    return (prev.status, prev.source_kind, prev.conflict, prev.sensor_offline, prev.stale, prev.note, prev.observed_at) != (
        new.status, new.source_kind, new.conflict, new.sensor_offline, new.stale, new.note, new.observed_at)

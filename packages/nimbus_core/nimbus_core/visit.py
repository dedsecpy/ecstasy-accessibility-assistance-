"""Visit context: deterministic facts about WHEN and WHERE the visit happens."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from .config import get_settings


def venue_tz(config: dict[str, Any]) -> ZoneInfo:
    name = get_settings().venue_tz or config.get("timezone") or "UTC"
    try:
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001
        return ZoneInfo("UTC")


def venue_now(config: dict[str, Any], override: str | None = None) -> datetime:
    tz = venue_tz(config)
    if override:
        dt = datetime.fromisoformat(override)
        return dt if dt.tzinfo else dt.replace(tzinfo=tz)
    return datetime.now(tz)


def find_event(config: dict[str, Any], event_id: str | None) -> dict[str, Any] | None:
    if not event_id:
        return None
    return next((e for e in config.get("events", []) if e.get("id") == event_id), None)


@dataclass
class VisitContext:
    destination: str | None
    floor: int | None
    needs_lift: bool
    visit_at: str | None
    staffed: bool | None
    staffed_window: str
    prebook_possible: bool | None
    hours_until_visit: float | None
    event_name: str | None
    phone: str

    def describe(self) -> str:
        lines = []
        if self.event_name:
            lines.append(f"Event: {self.event_name}")
        if self.destination:
            where = "upstairs - requires the lift" if self.needs_lift else "ground floor - no lift needed"
            lines.append(f"Destination: {self.destination} ({where})")
        else:
            lines.append("Destination: not specified (assume any public area, including upstairs rooms)")
        if self.visit_at:
            dt = datetime.fromisoformat(self.visit_at)
            lines.append(f"Visit time: {dt.strftime('%A %d %B %Y, %H:%M')} (venue local time)")
            lines.append(f"Assistance desk at that time: {'STAFFED' if self.staffed else 'NOT STAFFED'} ({self.staffed_window})")
            if self.prebook_possible is not None:
                lines.append("Pre-booking assistance: still possible" if self.prebook_possible
                             else "Pre-booking assistance: TOO LATE for the notice period")
        else:
            lines.append("Visit time: not specified - the visitor must check assistance desk hours")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_visit_context(config: dict[str, Any], event: dict[str, Any] | None, visit_at: str | None,
                        now: datetime) -> VisitContext:
    tz = venue_tz(config)
    destination = event["location"] if event else None
    loc = config.get("locations", {}).get(destination, {}) if destination else {}
    needs_lift = bool(loc.get("needs_lift", False)) if destination else True
    when: datetime | None = None
    if visit_at:
        when = datetime.fromisoformat(visit_at)
    elif event:
        when = datetime.fromisoformat(event.get("doors") or event["start"])
    if when is not None and when.tzinfo is None:
        when = when.replace(tzinfo=tz)

    staffed: bool | None = None
    window = "hours unknown"
    prebook: bool | None = None
    hours_until: float | None = None
    if when:
        key = when.strftime("%a").lower()
        span = config.get("assistance_hours", {}).get(key)
        if span is None:
            staffed = False
            window = f"desk closed on {when.strftime('%A')}s"
        else:
            staffed = time.fromisoformat(span[0]) <= when.time() < time.fromisoformat(span[1])
            window = f"desk hours {span[0]}-{span[1]} on {when.strftime('%A')}s"
        hours_until = round((when - now).total_seconds() / 3600, 1)
        prebook = hours_until >= config.get("prebook_hours", 48)
    return VisitContext(
        destination=destination, floor=loc.get("floor") if destination else None, needs_lift=needs_lift,
        visit_at=when.isoformat() if when else None, staffed=staffed, staffed_window=window,
        prebook_possible=prebook, hours_until_visit=hours_until, event_name=event["name"] if event else None,
        phone=config.get("assistance_phone", "the venue"),
    )


def hours_text(config: dict[str, Any]) -> str:
    parts = []
    for d, span in config.get("assistance_hours", {}).items():
        parts.append(f"{d.capitalize()}: {'closed' if span is None else span[0] + '-' + span[1]}")
    return ", ".join(parts) + f". Phone {config.get('assistance_phone', '')}. Pre-book {config.get('prebook_hours', 48)} h ahead."

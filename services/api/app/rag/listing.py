"""Listing health: audit each public listing claim against live status, flag affected events,
and draft an honest replacement listing (Claude when available, template otherwise)."""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from nimbus_core import db, prompts
from nimbus_core.bedrock import BedrockError, get_bedrock
from nimbus_core.config import get_settings
from nimbus_core.features import BLOCKING_STATUSES, feature_label, term, terms, use_venue
from nimbus_core.fusion import FusedState
from nimbus_core.visit import build_visit_context, hours_text, venue_now

from .context import refresh_ages

log = logging.getLogger("api.listing")
RANK = {"supported": 0, "unverified": 1, "qualified": 2, "contradicted": 3}


def audit_claims(config: dict[str, Any], states: dict[str, FusedState]) -> list[dict[str, Any]]:
    out = []
    for c in config.get("listing_claims", []):
        verdicts, reasons = ["supported"], []
        for fid in c["features"]:
            s = states.get(fid)
            if s is None:
                verdicts.append("unverified")
                reasons.append(f"No evidence recorded for {feature_label(fid)}.")
            elif s.status in BLOCKING_STATUSES:
                verdicts.append("contradicted")
                reasons.append(f"{s.label}: {s.status_label} - {s.note} ({s.freshness_text()})")
            elif s.status == "degraded":
                verdicts.append("qualified")
                reasons.append(f"{s.label}: {s.status_label} - {s.note} ({s.freshness_text()})")
            elif s.status in ("unknown", "verify") or s.stale:
                verdicts.append("unverified")
                reasons.append(f"{s.label}: {s.status_label} ({s.freshness_text()}) - {s.note}")
        verdict = max(verdicts, key=lambda v: RANK[v])
        if c["id"] == "step_free" and verdict == "supported":
            verdict = "qualified"
            main = states.get("main_entrance")
            if main is not None and main.status == "not_step_free":
                reasons.append(f"Step-free entry exists only via {term('gate')}, not the main entrance.")
        out.append({"claim": c["text"], "verdict": verdict, "reasons": reasons})
    return out


def affected_events(config: dict[str, Any], states: dict[str, FusedState], now: datetime) -> list[dict[str, Any]]:
    out = []
    lift = states.get("lift")
    cp = states.get("courtyard_path")
    for ev in config.get("events", []):
        ctx = build_visit_context(config, ev, None, now)
        if ctx.hours_until_visit is not None and ctx.hours_until_visit < 0:
            continue
        issues = []
        if ctx.needs_lift and lift and lift.status in BLOCKING_STATUSES:
            issues.append("upstairs and the lift is out of service")
        elif ctx.needs_lift and lift and lift.status in ("verify", "unknown"):
            issues.append("upstairs and the lift status is unconfirmed")
        if ctx.staffed is False:
            issues.append(f"outside assistance desk hours ({ctx.staffed_window})")
        if cp and cp.status in ("degraded", "out_of_service"):
            issues.append(f"{term('path')} narrowed or blocked")
        if issues:
            out.append({**ev, "issues": issues})
    return out


def template_listing(config: dict[str, Any], states: dict[str, FusedState], today: date) -> str:
    def line(fid: str) -> str:
        s = states.get(fid)
        return f"{s.note} ({s.status_label.lower()}, {s.freshness_text()})" if s else "No information recorded."

    t = terms()
    lift = states.get("lift")
    upstairs = [name for name, loc in config.get("locations", {}).items() if loc.get("needs_lift")]
    if upstairs:
        lift_text = (f"{', '.join(upstairs)} {'is' if len(upstairs) == 1 else 'are'} upstairs. If the lift is out of service there is "
                     "no step-free way to reach them. Check live status on Ecstasy or call us before travelling to any upstairs event.")
    else:
        lift_text = "All visitor areas are on the ground floor."
    entry = config.get("entry_text") or (f"Step-free entry is only via {t['gate_where']}, which is kept locked. "
                                         "Press the intercom; it is answered during assistance desk hours.")
    return f"""# {config['name']} - Access information (updated {today.isoformat()})

## Getting in step-free
{line('main_entrance')}
{entry} {line('side_gate')}
Then cross {t['path_area']} ({line('courtyard_path')}) and take the ramp to {t['ramp_to']} ({line('ramp')}).

## Lift - {lift.status_label if lift else 'unknown'}
{line('lift')}
{lift_text}

## Seating and rest points
{line('seating')}

## Toilets
{line('toilet')}

## Parking
{line('parking')}

## Assistance
{hours_text(config)} Outside these hours security can open {t['gate']} but cannot provide mobility assistance.
"""


DEFAULT_ACTIONS = [
    "Confirm lift status every morning in the Ecstasy daily check; human checks expire after 24 hours.",
    "Publish assistance desk hours next to every evening event and offer 48 h pre-booking.",
    "Set an end date for temporary works and record a staff check when they change.",
    "Replace 'Wheelchair accessible' on the public listing with the route description below.",
]


def listing_health(venue_id: str) -> dict[str, Any]:
    config = db.get_venue(venue_id)
    if config is None:
        raise KeyError(venue_id)
    use_venue(config)
    now = venue_now(config)
    states = refresh_ages(db.get_feature_states(venue_id), datetime.now(timezone.utc))
    claims = audit_claims(config, states)
    events = affected_events(config, states, now)
    stale = [s.to_dict() for s in states.values() if s.stale or s.status in ("unknown", "verify")]
    listing_age = (now.date() - date.fromisoformat(config["listing_updated"])).days if config.get("listing_updated") else None

    draft, actions, mode, error = "", [], "template", None
    client = get_bedrock()
    if client is not None:
        audit_chunks = [r for r in db.list_chunks(venue_id) if r["meta"].get("source_type") == "audit"][:6]
        listing_chunks = [r for r in db.list_chunks(venue_id) if r["meta"].get("source_type") == "listing"]
        try:
            data = client.converse_json(
                model=get_settings().llm_model, system=prompts.LISTING_SYSTEM,
                user=prompts.LISTING_USER.format(
                    today=now.date().isoformat(), venue=config["name"], assistance=hours_text(config),
                    current_listing="\n".join(r["text"] for r in listing_chunks),
                    claim_audit="\n".join(f"- {c['claim']}: {c['verdict'].upper()}. " + " ".join(c["reasons"]) for c in claims),
                    status="\n".join(f"- {s.label}: {s.status_label} - {s.note} ({s.freshness_text()})" for s in states.values()),
                    audit_excerpts="\n\n".join(f"{r['meta'].get('heading', '')}: {r['text']}" for r in audit_chunks)),
                tool_name="draft_listing", tool_description="Return the drafted listing and staff actions",
                schema=prompts.LISTING_SCHEMA, max_tokens=1800)
            draft, actions, mode = data.get("listing_markdown", ""), list(data.get("staff_actions", [])), "llm"
        except BedrockError as e:
            error = f"{get_settings().provider_label} drafting failed; showing the template. ({e})"[:300]
    if not draft:
        draft = template_listing(config, states, now.date())
        actions = actions or DEFAULT_ACTIONS
    return {"claims": claims, "affected_events": events, "unconfirmed_features": stale, "listing_age_days": listing_age,
            "listing_updated": config.get("listing_updated"), "draft_listing": draft, "staff_actions": actions,
            "mode": mode, "ai_label": f"{get_settings().llm_model} on {get_settings().provider_label}" if mode == "llm" else None,
            "error": error}

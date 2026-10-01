"""End-to-end flows: answer a visitor, ingest a report, audit the listing."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

from . import prompts
from .features import (
    BLOCKING_STATUSES,
    FEATURES,
    FeatureStatus,
    latest_statuses,
    status_board_text,
)
from .kb import Chunk, VenueKB
from .llm import LLMClient, LLMError
from .retriever import Hit, Retriever

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


@dataclass
class NeedsProfile:
    mobility: str = "manual_wheelchair"
    needs_seating: bool = False
    avoid_slopes: bool = False
    needs_assistance: bool = False
    event: dict[str, Any] | None = None
    visit_at: datetime | None = None
    free_text: str = ""

    def describe(self) -> str:
        parts = [MOBILITY_LABELS.get(self.mobility, self.mobility)]
        if self.needs_seating:
            parts.append("needs seating and rest points along the route and at the destination")
        if self.avoid_slopes:
            parts.append("cannot manage steep slopes")
        if self.needs_assistance:
            parts.append("would like staff assistance on arrival")
        if self.free_text.strip():
            parts.append(f"in their own words: {self.free_text.strip()}")
        return "; ".join(parts)

    def query_terms(self) -> str:
        t = [MOBILITY_QUERY_TERMS.get(self.mobility, "")]
        if self.needs_seating:
            t.append("seating bench chair rest")
        if self.avoid_slopes:
            t.append("ramp slope gradient steep")
        if self.needs_assistance:
            t.append("assistance desk hours pre-book intercom")
        return " ".join(t)


@dataclass
class VisitContext:
    destination: str | None
    needs_lift: bool
    visit_at: datetime | None
    staffed: bool | None  # None when visit time unknown
    staffed_window: str
    prebook_possible: bool | None
    hours_until_visit: float | None

    def describe(self) -> str:
        lines = []
        if self.destination:
            lines.append(
                f"Destination: {self.destination} ({'upstairs - requires the lift' if self.needs_lift else 'ground floor - no lift needed'})"
            )
        else:
            lines.append("Destination: not specified (assume the visitor may need any public area, including the Main Hall upstairs)")
        if self.visit_at:
            lines.append(f"Visit time: {self.visit_at.strftime('%A %d %B %Y, %H:%M')}")
            lines.append(f"Assistance desk at that time: {'STAFFED' if self.staffed else 'NOT STAFFED'} ({self.staffed_window})")
            if self.prebook_possible is not None:
                lines.append(
                    "Pre-booking assistance: still possible (48 h notice)" if self.prebook_possible
                    else "Pre-booking assistance: TOO LATE for the 48 h notice period"
                )
        else:
            lines.append("Visit time: not specified - assistance desk hours must be checked by the visitor")
        return "\n".join(lines)


def build_visit_context(profile: NeedsProfile, config: dict[str, Any], now: datetime) -> VisitContext:
    destination = profile.event["location"] if profile.event else None
    needs_lift = bool(config["locations"].get(destination, {}).get("needs_lift", False)) if destination else True
    visit_at = profile.visit_at
    if visit_at is None and profile.event:
        visit_at = datetime.fromisoformat(profile.event.get("doors") or profile.event["start"])

    staffed: bool | None = None
    window = "hours unknown"
    prebook: bool | None = None
    hours_until: float | None = None
    if visit_at:
        key = visit_at.strftime("%a").lower()
        span = config["assistance_hours"].get(key)
        if span is None:
            staffed = False
            window = f"desk closed on {visit_at.strftime('%A')}s"
        else:
            start = time.fromisoformat(span[0])
            end = time.fromisoformat(span[1])
            staffed = start <= visit_at.time() < end
            window = f"desk hours {span[0]}-{span[1]} on {visit_at.strftime('%A')}s"
        hours_until = (visit_at - now).total_seconds() / 3600
        prebook = hours_until >= config.get("prebook_hours", 48)
    return VisitContext(destination, needs_lift, visit_at, staffed, window, prebook, hours_until)


@dataclass
class Answer:
    verdict: str
    headline: str
    summary: str
    route: list[str]
    warnings: list[str]
    verify: list[str]
    discrepancies: list[str]
    hits: list[Hit]
    statuses: dict[str, FeatureStatus]
    visit: VisitContext
    mode: str  # "llm" or "fallback"
    error: str | None = None
    raw: str | None = None


def _format_passages(hits: list[Hit], today: date) -> str:
    out = []
    for i, h in enumerate(hits, 1):
        c = h.chunk
        age = c.age_days(today)
        out.append(
            f"[{i}] {c.label} - \"{c.doc_title}\" / {c.heading or 'general'} - dated {c.date.isoformat()} "
            f"({age} days ago, trust: {c.trust})\n{c.text}"
        )
    return "\n\n".join(out)


def _listing_claims_text(config: dict[str, Any]) -> str:
    return "\n".join(f"- {c['text']}" for c in config["listing_claims"])


def answer_question(
    question: str,
    profile: NeedsProfile,
    kb: VenueKB,
    llm: LLMClient,
    now: datetime | None = None,
    k: int = 8,
) -> Answer:
    now = now or datetime.now()
    today = now.date()
    visit = build_visit_context(profile, kb.config, now)
    statuses = latest_statuses(kb.facts, today)

    retriever = Retriever(kb.chunks)
    query = f"{question} {profile.query_terms()} {visit.destination or ''}"
    hits = retriever.search(query, today, k=k)

    if llm.available:
        user = prompts.ANSWER_USER.format(
            today=today.isoformat(),
            venue=kb.name,
            profile=profile.describe(),
            visit=visit.describe(),
            listing_updated=kb.config.get("listing_updated", "unknown"),
            listing_claims=_listing_claims_text(kb.config),
            status_board=status_board_text(statuses),
            passages=_format_passages(hits, today),
            question=question or "Can I get in and to my seat for this visit?",
        )
        try:
            data = llm.complete_json(prompts.ANSWER_SYSTEM, user)
            return Answer(
                verdict=str(data.get("verdict", "caution")).lower(),
                headline=data.get("headline", ""),
                summary=data.get("summary", ""),
                route=list(data.get("route", [])),
                warnings=list(data.get("warnings", [])),
                verify=list(data.get("verify_before_travel", [])),
                discrepancies=list(data.get("listing_discrepancies", [])),
                hits=hits,
                statuses=statuses,
                visit=visit,
                mode="llm",
            )
        except LLMError as e:
            fb = fallback_answer(profile, visit, statuses, hits, kb, today)
            fb.error = f"LLM call failed, showing rule-based answer instead: {e}"
            return fb
    return fallback_answer(profile, visit, statuses, hits, kb, today)


def _cite(hits: list[Hit], *needles: str) -> str:
    """Return citation markers for passages whose text mentions any needle."""
    idx = []
    for i, h in enumerate(hits, 1):
        blob = (h.chunk.text + " " + h.chunk.heading).lower()
        if any(n.lower() in blob for n in needles):
            idx.append(i)
    return " " + "".join(f"[{i}]" for i in idx[:3]) if idx else ""


def fallback_answer(
    profile: NeedsProfile,
    visit: VisitContext,
    statuses: dict[str, FeatureStatus],
    hits: list[Hit],
    kb: VenueKB,
    today: date,
) -> Answer:
    """Deterministic composition from the status board - used when no LLM is configured."""
    warnings: list[str] = []
    route: list[str] = []
    verify: list[str] = []
    discrepancies: list[str] = []
    blockers: list[str] = []
    cautions: list[str] = []
    wheeled = profile.mobility in WHEELED
    phone = kb.config.get("assistance_phone", "the venue")

    def st(fid: str) -> FeatureStatus | None:
        return statuses.get(fid)

    # Entrance
    me = st("main_entrance")
    if me and me.status == "not_step_free":
        msg = f"The main entrance is not step-free ({me.note}){_cite(hits, 'main entrance', 'steps')}"
        if wheeled:
            route.append("Do not use the main entrance - it has steps. Head to the Side Gate on Mill Lane instead." + _cite(hits, "side gate", "mill lane"))
        else:
            route.append(f"The main entrance has six steps with one handrail; the step-free alternative is the Side Gate on Mill Lane.{_cite(hits, 'main entrance')}")
        discrepancies.append("Listing says 'Step-free access' but the main entrance and drop-off point have steps; step-free entry is only via a locked side gate." + _cite(hits, "main entrance", "side gate"))
        warnings.append(msg)

    # Side gate / intercom / staffing
    sg = st("side_gate")
    ic = st("intercom")
    gate_note = f"The Side Gate is kept locked and opened on request{_cite(hits, 'side gate')}"
    if visit.staffed is False:
        blockers_or_caution = "Your visit is outside assistance desk hours (" + visit.staffed_window + "). The intercom is not answered then; a visitor on 2026-09-27 found the gate locked and the intercom unanswered at 18:30." if (sg and sg.status == "locked_unanswered") else f"Your visit is outside assistance desk hours ({visit.staffed_window}); the intercom is not answered then."
        warnings.append(blockers_or_caution + _cite(hits, "intercom", "locked", "not staffed"))
        if visit.prebook_possible:
            verify.append(f"Pre-book assistance now on {phone} (48 h notice) so the desk is staffed and the gate is opened for your arrival.")
            cautions.append("gate_out_of_hours")
        else:
            verify.append(f"Call {phone} during desk hours and ask security to meet you at the Side Gate at your arrival time - the 48 h pre-booking window has passed.")
            cautions.append("gate_out_of_hours_late")
    elif visit.staffed is None:
        warnings.append(gate_note + ". The intercom is only answered during assistance desk hours (Mon-Fri 10:00-17:00, Sat 10:00-14:00)." + _cite(hits, "intercom", "hours"))
        verify.append(f"Confirm your arrival time falls within desk hours, or pre-book on {phone}.")
    route.append("Enter via the Side Gate on Mill Lane: press the intercom and wait to be let in." + _cite(hits, "intercom", "side gate"))
    if ic and ic.status == "ok" and ic.stale:
        warnings.append(f"Intercom {ic.freshness_text}.")

    # Courtyard path
    cp = st("courtyard_path")
    if cp and cp.status == "degraded":
        route.append(f"Cross the courtyard. {cp.note}{_cite(hits, 'scaffolding', 'courtyard')}")
        if profile.mobility in WIDE:
            cautions.append("narrow_path")
            warnings.append("The courtyard path is narrowed to about 800 mm by scaffolding; larger powered chairs and scooters may not pass. A portable ramp bypass exists but only during staffed hours." + _cite(hits, "scaffolding"))
            verify.append("Ask the desk to confirm your chair width fits 800 mm, or arrange the portable-ramp bypass via the delivery entrance.")
        if cp.stale:
            warnings.append(f"Courtyard works status {cp.freshness_text}.")

    # Ramp
    rp = st("ramp")
    if rp:
        route.append(f"Take the external ramp to the ground floor foyer: {rp.note}{_cite(hits, 'ramp')}")
        if profile.mobility == "manual_wheelchair" or profile.avoid_slopes or profile.mobility == "walks_short_distances":
            cautions.append("steep_ramp")
            warnings.append("The ramp is about 1:12 over 14 m with no landings or seating - steeper than recommended; manual wheelchair users and people with limited stamina may need help." + _cite(hits, "ramp", "gradient"))

    # Seating
    se = st("seating")
    if profile.needs_seating or profile.mobility == "walks_short_distances":
        if se and se.status == "degraded":
            cautions.append("seating")
            warnings.append(f"Seating is limited: {se.note} ({se.freshness_text}).{_cite(hits, 'bench', 'chairs', 'seating')}")
            verify.append(f"Ask the desk ({phone}) to reserve a foyer chair and an end-of-row seat near the lift.")
        pk = st("parking")
        if pk:
            warnings.append(f"From the blue badge bays it is ~120 m to the Side Gate with no seating on the way.{_cite(hits, 'blue badge', '120')}")

    # Lift
    lf = st("lift")
    if visit.needs_lift:
        if lf and lf.status in BLOCKING_STATUSES:
            blockers.append("lift")
            warnings.append(f"The lift is OUT OF SERVICE ({lf.freshness_text}): {lf.note} The destination is upstairs and there is no step-free alternative.{_cite(hits, 'lift')}")
            discrepancies.append("Listing says 'Lift to all floors' but the lift is currently out of service with no repair date." + _cite(hits, "out of service", "engineer"))
            verify.append(f"Call {phone} on the day and ask: 'Is the lift back in service, and has it been tested today?' Do not travel on the listing alone.")
            if wheeled:
                verify.append("Ask whether the event can be relocated to the Ground Floor Gallery or streamed to the foyer.")
        elif lf and lf.stale:
            cautions.append("lift_stale")
            warnings.append(f"Lift {lf.freshness_text}. It has failed twice since August.{_cite(hits, 'lift')}")
            verify.append(f"Call {phone} on the day to confirm the lift is running.")
            route.append("Take the lift from the foyer to the First floor Main Hall." + _cite(hits, "lift"))
        else:
            route.append("Take the lift from the foyer to the First floor Main Hall." + _cite(hits, "lift"))
    else:
        route.append("Your destination is on the ground floor - no lift needed." + _cite(hits, "ground floor"))
        if lf and lf.status in BLOCKING_STATUSES:
            warnings.append(f"The lift is out of service ({lf.freshness_text}), but your destination is on the ground floor so this does not block you.{_cite(hits, 'lift')}")

    # Toilet
    tl = st("toilet")
    if tl:
        route.append(f"Accessible toilet: {tl.note}{_cite(hits, 'toilet')}")

    # Verdict
    if blockers:
        verdict = "no_go"
        headline = "Do not travel on the strength of the listing: the lift is out of service and your destination is upstairs."
    elif cautions:
        verdict = "caution"
        headlines = {
            "lift_stale": "The route works on paper, but the lift has not been confirmed recently and has failed twice since August - check on the day.",
            "narrow_path": "Entry is possible, but a temporary 800 mm pinch point in the courtyard and the gate arrangements need confirming first.",
            "gate_out_of_hours": "You can get in step-free, but only via the Side Gate and only if assistance is pre-booked for your arrival time.",
            "gate_out_of_hours_late": "You can get in step-free via the Side Gate, but the desk will be closed when you arrive - phone ahead so security meets you.",
            "steep_ramp": "The step-free route works, but it includes a steep 14 m ramp with nowhere to rest - allow time or ask for help.",
            "seating": "You can get in, but plan rest stops: seating on the route is scarce and the foyer chairs fill up.",
        }
        if profile.mobility == "walks_short_distances":
            order = ["gate_out_of_hours", "gate_out_of_hours_late", "seating", "steep_ramp", "lift_stale", "narrow_path"]
        else:
            order = ["lift_stale", "narrow_path", "gate_out_of_hours", "gate_out_of_hours_late", "steep_ramp", "seating"]
        headline = next(headlines[c] for c in order if c in cautions)
    else:
        verdict = "go"
        headline = "The step-free route via the Side Gate works for you, provided you arrive during staffed hours."

    summary_bits = [f"Nimbus checked {len(hits)} evidence passages and the latest status of {len(statuses)} access features."]
    if lf:
        summary_bits.append(f"Lift: {lf.status_label.lower()}, {lf.freshness_text}.")
    if cp and cp.status == "degraded":
        summary_bits.append("Temporary courtyard works narrow the only step-free path.")
    summary_bits.append("The public listing (2024) does not reflect any of this.")

    if not verify:
        verify.append(f"Call {phone} during desk hours to confirm the current lift and gate arrangements.")

    return Answer(
        verdict=verdict,
        headline=headline,
        summary=" ".join(summary_bits),
        route=route,
        warnings=warnings,
        verify=_dedupe(verify),
        discrepancies=_dedupe(discrepancies),
        hits=hits,
        statuses=statuses,
        visit=visit,
        mode="fallback",
    )


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for i in items:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


# --------------------------------------------------------------------------- reports

@dataclass
class IngestResult:
    report_chunk: Chunk
    facts: list[dict[str, Any]]
    summary: str
    mode: str
    error: str | None = None


STATUS_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("out_of_service", ("out of order", "out of service", "not working", "broken", "stopped", "isn't working", "wasn't working", "no lift", "closed")),
    ("locked_unanswered", ("nobody answered", "no answer", "no one answered", "didn't answer", "unanswered", "nobody came", "no one came")),
    ("locked_on_request", ("let me in", "let us in", "opened the gate", "came and opened", "opened quickly", "answered quickly")),
    ("degraded", ("narrow", "scaffolding", "blocked", "partly", "full", "taken", "occupied", "steep", "loose", "cordon", "no bench", "nowhere to sit", "no seating")),
    ("ok", ("working", "worked", "fine", "ok", "okay", "open", "available", "no problem", "clean", "repaired", "fixed", "back in service")),
]


def _rule_extract(text: str) -> list[dict[str, Any]]:
    lower = text.lower()
    facts = []
    sentences = re.split(r"(?<=[.!?])\s+", lower)
    for fid, feat in FEATURES.items():
        pats = [re.compile(r"\b" + re.escape(k) + r"s?\b") for k in feat.keywords]
        relevant = [s for s in sentences if any(p.search(s) for p in pats)]
        if not relevant:
            continue
        blob = " ".join(relevant)
        status = "unknown"
        for st_name, pats in STATUS_PATTERNS:
            if any(p in blob for p in pats):
                status = st_name
                break
        if fid == "main_entrance" and ("steps" in blob or "stairs" in blob):
            status = "not_step_free"
        if fid in ("side_gate", "intercom") and status == "degraded":
            status = "unknown"
        if fid == "intercom" and status == "locked_on_request":
            status = "ok"
        if fid == "side_gate" and status == "ok":
            status = "locked_on_request"  # the gate is always kept locked; "working" means it was opened
        facts.append({"feature": fid, "status": status, "note": relevant[0].strip().capitalize()[:200], "confidence": 0.5})
    return facts


def ingest_report(
    text: str,
    reporter: str,
    needs: str,
    kb: VenueKB,
    llm: LLMClient,
    when: date | None = None,
) -> IngestResult:
    when = when or date.today()
    chunk = kb.append_report(text, reporter, needs, when)
    mode, summary, error = "fallback", "", None
    facts: list[dict[str, Any]] = []
    if llm.available:
        system = prompts.EXTRACT_SYSTEM.format(
            features="\n".join(f"- {f.id}: {f.label}" for f in FEATURES.values())
        )
        user = prompts.EXTRACT_USER.format(date=when.isoformat(), reporter=reporter, needs=needs or "not stated", text=text)
        try:
            data = llm.complete_json(system, user, max_tokens=800)
            facts = [f for f in data.get("facts", []) if f.get("feature") in FEATURES]
            summary = data.get("summary", "")
            mode = "llm"
        except LLMError as e:
            error = f"LLM extraction failed, used rule-based extraction: {e}"
            facts = _rule_extract(text)
    else:
        facts = _rule_extract(text)
    if not summary:
        summary = f"{len(facts)} feature update(s) extracted from a {reporter} report."

    stored = []
    for f in facts:
        stored.append(
            {
                "date": when.isoformat(),
                "feature": f["feature"],
                "status": f.get("status", "unknown"),
                "note": f.get("note", ""),
                "confidence": f.get("confidence", 0.5),
                "source": f"{'Staff' if reporter == 'staff' else 'Visitor'} report ({when.isoformat()})",
                "source_type": "staff_note" if reporter == "staff" else "visitor_report",
                "report_chunk": chunk.id,
            }
        )
    kb.append_facts(stored)
    return IngestResult(report_chunk=chunk, facts=stored, summary=summary, mode=mode, error=error)


# --------------------------------------------------------------------------- listing audit

@dataclass
class ClaimAudit:
    claim: str
    verdict: str  # supported | qualified | contradicted | unverified
    reasons: list[str]


@dataclass
class ListingAudit:
    claims: list[ClaimAudit]
    affected_events: list[dict[str, Any]]
    stale_features: list[FeatureStatus]
    draft_listing: str
    staff_actions: list[str]
    mode: str
    listing_age_days: int
    error: str | None = None


def audit_listing(kb: VenueKB, llm: LLMClient, now: datetime | None = None) -> ListingAudit:
    now = now or datetime.now()
    today = now.date()
    statuses = latest_statuses(kb.facts, today)
    claims: list[ClaimAudit] = []
    rank = {"supported": 0, "unverified": 1, "qualified": 2, "contradicted": 3}
    for c in kb.config["listing_claims"]:
        verdicts = ["supported"]
        reasons = []
        for fid in c["features"]:
            s = statuses.get(fid)
            if not s:
                verdicts.append("unverified")
                reasons.append(f"No evidence recorded for {FEATURES[fid].label}.")
                continue
            if s.status in BLOCKING_STATUSES:
                verdicts.append("contradicted")
                reasons.append(f"{s.feature.label}: {s.status_label} - {s.note} ({s.freshness_text}; source: {s.source})")
            elif s.status == "degraded":
                verdicts.append("qualified")
                reasons.append(f"{s.feature.label}: {s.status_label} - {s.note} ({s.freshness_text})")
            elif s.status == "unknown":
                verdicts.append("unverified")
                reasons.append(f"{s.feature.label}: {s.note} ({s.freshness_text})")
            elif s.stale:
                verdicts.append("unverified")
                reasons.append(f"{s.feature.label}: {s.status_label} but {s.freshness_text}")
        verdict = max(verdicts, key=lambda v: rank[v])
        if c["id"] == "step_free" and verdict == "supported":
            verdict = "qualified"  # step-free only via a locked gate
            reasons.append("Step-free entry exists only via the locked Side Gate on Mill Lane, not the main entrance.")
        claims.append(ClaimAudit(c["text"], verdict, reasons))

    lift = statuses.get("lift")
    affected = []
    for ev in kb.config.get("events", []):
        start = datetime.fromisoformat(ev["start"])
        if start < now:
            continue
        loc = kb.config["locations"].get(ev["location"], {})
        issues = []
        if loc.get("needs_lift") and lift and lift.status in BLOCKING_STATUSES:
            issues.append("upstairs; lift out of service")
        ctx = build_visit_context(NeedsProfile(event=ev), kb.config, now)
        if ctx.staffed is False:
            issues.append(f"outside assistance desk hours ({ctx.staffed_window})")
        cp = statuses.get("courtyard_path")
        if cp and cp.status == "degraded":
            issues.append("courtyard path narrowed by works")
        if issues:
            affected.append({**ev, "issues": issues})

    stale = [s for s in statuses.values() if s.stale]
    listing_age = (today - date.fromisoformat(kb.config["listing_updated"])).days

    draft, actions, mode, error = "", [], "fallback", None
    if llm.available:
        audit_chunks = [c for c in kb.chunks if c.source_type == "audit"][:6]
        user = prompts.LISTING_USER.format(
            today=today.isoformat(),
            venue=kb.name,
            assistance=_hours_text(kb.config),
            current_listing="\n".join(c.text for c in kb.listing_chunks()),
            claim_audit="\n".join(f"- {c.claim}: {c.verdict.upper()}. " + " ".join(c.reasons) for c in claims),
            status_board=status_board_text(statuses),
            audit_excerpts="\n\n".join(f"{c.heading}: {c.text}" for c in audit_chunks),
        )
        try:
            data = llm.complete_json(prompts.LISTING_SYSTEM, user, max_tokens=1600)
            draft = data.get("listing_markdown", "")
            actions = list(data.get("staff_actions", []))
            mode = "llm"
        except LLMError as e:
            error = f"LLM drafting failed, showing template draft: {e}"
    if not draft:
        draft = _template_listing(kb, statuses, today)
        actions = actions or [
            "Confirm lift status every morning and after any fault; the status board goes stale after 7 days.",
            "Publish assistance desk hours next to every evening event and enable 48 h pre-booking links.",
            "Set an end date for the courtyard works and remove the notice when the scaffolding comes down.",
            "Replace 'Wheelchair accessible' with the route description below on the public listing.",
        ]
    return ListingAudit(claims, affected, stale, draft, actions, mode, listing_age, error)


def _hours_text(config: dict[str, Any]) -> str:
    parts = []
    for d, span in config["assistance_hours"].items():
        parts.append(f"{d.capitalize()}: {'closed' if span is None else span[0] + '-' + span[1]}")
    return ", ".join(parts) + f". Phone {config.get('assistance_phone', '')}. Pre-book {config.get('prebook_hours', 48)} h ahead."


def _template_listing(kb: VenueKB, statuses: dict[str, FeatureStatus], today: date) -> str:
    def line(fid: str) -> str:
        s = statuses.get(fid)
        return f"{s.note} ({s.freshness_text})" if s else "No information recorded."

    return f"""# {kb.name} - Access information (updated {today.isoformat()})

## Getting in step-free
The main entrance on Riverside Walk has six steps. Step-free entry is **only** via the Side Gate on Mill Lane, which is kept locked. Press the intercom; it is answered during assistance desk hours only. Then cross the courtyard and take a 14 m ramp (about 1:12, steeper than standard, handrail on one side, no resting places) to the ground floor foyer.

## Lift - {statuses['lift'].status_label if 'lift' in statuses else 'unknown'}
{line('lift')}
The Main Hall is on the First floor. If the lift is out of service there is no step-free way to reach it. Call us before travelling to any upstairs event.

## Temporary obstacles
{line('courtyard_path')}

## Seating and rest points
{line('seating')} It is about 120 m from the blue badge bays to the Side Gate with no seating on the way. Ask us to reserve a foyer chair or an end-of-row seat.

## Toilets
{line('toilet')}

## Parking
{line('parking')}

## Assistance
{_hours_text(kb.config)} Outside these hours security can open the Side Gate but cannot provide mobility assistance.
"""

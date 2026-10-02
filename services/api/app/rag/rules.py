"""Deterministic rule checks: which features this visitor needs, and which statuses block
or caution them. The fallback answer is built from these, and the validators use them to
override any LLM verdict that is more optimistic than the rules allow."""
from __future__ import annotations

from dataclasses import dataclass, field

from nimbus_core.features import BLOCKING_STATUSES, WHEELED, WIDE, feature_label, terms
from nimbus_core.fusion import FusedState
from nimbus_core.schemas import Profile
from nimbus_core.visit import VisitContext

IMMINENT_HOURS = 3.0
UNCERTAIN = {"verify", "unknown"}


@dataclass
class Finding:
    feature: str
    code: str
    text: str
    severity: str  # blocker | caution | info
    verify: str | None = None


@dataclass
class RuleResult:
    required: list[str]
    context_features: list[str]
    findings: list[Finding] = field(default_factory=list)

    @property
    def blockers(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "blocker"]

    @property
    def cautions(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "caution"]

    @property
    def min_verdict(self) -> str:
        return "no_go" if self.blockers else "caution" if self.cautions else "go"

    @property
    def verify_items(self) -> list[str]:
        out: list[str] = []
        for f in self.findings:
            if f.verify and f.verify not in out:
                out.append(f.verify)
        return out

    def summary_lines(self) -> str:
        if not self.findings:
            return "- No blockers or cautions found by the rules."
        return "\n".join(f"- {f.severity.upper()} [{f.feature}] {f.text}" for f in self.findings)


def required_features(profile: Profile, visit: VisitContext) -> tuple[list[str], list[str]]:
    req: list[str] = []
    m = profile.mobility
    if m in WHEELED:
        req += ["side_gate", "intercom", "courtyard_path", "ramp", "main_entrance"]
    elif m == "walks_short_distances":
        req += ["main_entrance", "side_gate", "courtyard_path", "ramp", "seating", "parking"]
    else:
        req += ["main_entrance", "side_gate"]
    if visit.needs_lift:
        req.append("lift")
    if (profile.needs_seating or profile.walk_range == "short") and "seating" not in req:
        req.append("seating")
    if profile.avoid_slopes and "ramp" not in req:
        req.append("ramp")
    if profile.needs_assistance:
        req += [f for f in ("assistance_desk", "intercom") if f not in req]
    if profile.hearing_support and "hearing_loop" not in req:
        req.append("hearing_loop")
    if profile.needs_toilet and "toilet" not in req:
        req.append("toilet")
    if profile.arrival in ("blue_badge", "car") and "parking" not in req:
        req.append("parking")
    ctx = [f for f in ("lift", "toilet", "assistance_desk", "parking", "hearing_loop") if f not in req]
    return req, ctx


def assess(profile: Profile, visit: VisitContext, states: dict[str, FusedState]) -> RuleResult:
    req, ctx = required_features(profile, visit)
    r = RuleResult(req, ctx)
    add = r.findings.append
    wheeled = profile.mobility in WHEELED
    phone = visit.phone
    t = terms()
    imminent = visit.hours_until_visit is None or visit.hours_until_visit <= IMMINENT_HOURS

    def st(fid: str) -> FusedState | None:
        return states.get(fid)

    # Lift
    lf = st("lift")
    if visit.needs_lift:
        if lf is None:
            add(Finding("lift", "lift_no_data", "No record of the lift's status.", "caution",
                        f"Call {phone} and ask whether the lift is in service today."))
        elif lf.status in BLOCKING_STATUSES:
            add(Finding("lift", "lift_out", f"The lift is out of service ({lf.freshness_text()}): {lf.note} "
                        "The destination is upstairs and there is no step-free alternative.", "blocker",
                        f"Call {phone} on the day and ask: 'Is the lift back in service and tested today?' Do not travel on the listing alone."))
        elif lf.status == "verify":
            add(Finding("lift", "lift_verify", f"Lift sources disagree: {lf.note}", "caution",
                        f"Call {phone} before travelling and ask staff to physically confirm the lift is running."))
        elif lf.status == "unknown":
            add(Finding("lift", "lift_unknown", f"Lift status cannot be confirmed: {lf.note}", "caution",
                        f"Call {phone} before travelling to confirm the lift is running."))
        elif lf.stale:
            add(Finding("lift", "lift_stale", f"Lift last confirmed {lf.freshness_text()}.", "caution",
                        f"Call {phone} on the day to confirm the lift is running."))
        elif visit.hours_until_visit is not None and visit.hours_until_visit > 24:
            add(Finding("lift", "lift_ok_future", f"The lift is working now ({lf.freshness_text()}). Live status can change before your visit; "
                        "check this page on the day.", "info"))
    elif lf is not None and lf.status in BLOCKING_STATUSES:
        add(Finding("lift", "lift_out_not_needed", f"The lift is out of service ({lf.freshness_text()}), but your destination is on the "
                    "ground floor so this does not block you.", "info"))

    # Entrance and side gate
    me = st("main_entrance")
    if me is not None and me.status == "not_step_free" and (wheeled or profile.mobility == "walks_short_distances"):
        add(Finding("main_entrance", "main_steps", f"The main entrance is not step-free: {me.note}", "info"))
    sg = st("side_gate")
    if wheeled:
        if sg is not None and sg.status == "locked_unanswered":
            if imminent:
                add(Finding("side_gate", "gate_unanswered_now", f"The only step-free entrance is locked and nobody is answering right now: {sg.note}",
                            "blocker", f"Call {phone} and ask security to open {t['gate_where']} before you set off."))
            else:
                add(Finding("side_gate", "gate_unanswered_earlier", f"{t['gate_cap']} was recently locked with nobody answering: {sg.note}",
                            "caution", f"Pre-book assistance on {phone} so someone is at {t['gate']} when you arrive."))
        elif sg is not None and (sg.status in UNCERTAIN or sg.stale):
            add(Finding("side_gate", "gate_unconfirmed", f"{feature_label('side_gate')} status is not confirmed: {sg.note}", "caution",
                        f"Call {phone} to confirm {t['gate']} will be opened for you."))
        elif sg is not None and sg.status == "out_of_service":
            add(Finding("side_gate", "gate_out", f"{t['gate_cap']} (only step-free entrance) is out of use: {sg.note}", "blocker",
                        f"Call {phone} to ask about another step-free entrance."))
        if visit.staffed is False:
            if visit.prebook_possible:
                add(Finding("assistance_desk", "out_of_hours", f"Your visit is outside assistance desk hours ({visit.staffed_window}); "
                            f"the intercom is not answered then and {t['gate']} stays locked.", "caution",
                            f"Pre-book assistance now on {phone} so {t['gate']} is opened for your arrival."))
            else:
                add(Finding("assistance_desk", "out_of_hours_late", f"Your visit is outside assistance desk hours ({visit.staffed_window}) "
                            "and the pre-booking window has passed.", "caution",
                            f"Call {phone} during desk hours and ask security to meet you at {t['gate']} at your arrival time."))
        elif visit.staffed is None:
            add(Finding("assistance_desk", "hours_unknown", f"The intercom at {t['gate']} is only answered during assistance desk hours.", "info",
                        f"Check your arrival falls within desk hours, or pre-book on {phone}."))
        ic = st("intercom")
        if ic is not None and ic.status == "out_of_service":
            add(Finding("intercom", "intercom_down", f"The {feature_label('intercom')} is not working: {ic.note}", "caution",
                        f"Call {phone} when you arrive at {t['gate']}."))

    # Step-free path (the courtyard at Riverside)
    cp = st("courtyard_path")
    if cp is not None and (wheeled or profile.mobility == "walks_short_distances"):
        if cp.status in BLOCKING_STATUSES:
            add(Finding("courtyard_path", "path_blocked", f"{t['path_cap']} (the only step-free route) is blocked: {cp.note}",
                        "blocker" if wheeled else "caution", f"Call {phone} to ask whether {t['bypass']} is available."))
        elif cp.status == "degraded":
            if profile.mobility in WIDE or profile.wide_chair:
                add(Finding("courtyard_path", "path_narrow", f"{t['path_cap']} is narrowed: {cp.note}", "caution",
                            f"Ask the desk ({phone}) whether your chair width fits, or arrange {t['bypass_long']}."))
            else:
                add(Finding("courtyard_path", "path_narrow_info", f"{t['path_cap']} is narrowed: {cp.note}", "info"))
        elif cp.status in UNCERTAIN or cp.stale:
            add(Finding("courtyard_path", "path_unconfirmed", f"{feature_label('courtyard_path')} status is not confirmed ({cp.freshness_text()}).", "caution",
                        f"Call {phone} to confirm {t['path']} is clear."))

    # Ramp
    rp = st("ramp")
    if rp is not None and "ramp" in req:
        if rp.status in BLOCKING_STATUSES and wheeled:
            add(Finding("ramp", "ramp_out", f"The ramp is out of use: {rp.note}", "blocker", f"Call {phone} about alternative access."))
        elif rp.status == "degraded" and (profile.mobility in ("manual_wheelchair", "walks_short_distances") or profile.avoid_slopes):
            add(Finding("ramp", "steep_ramp", f"The ramp is steeper than recommended with nowhere to rest: {rp.note}", "caution",
                        f"Ask the desk ({phone}) for someone to help on the ramp if you need it."))

    # Seating
    drives = profile.arrival in ("blue_badge", "car")
    if profile.needs_seating or profile.short_range:
        se = st("seating")
        if se is not None and se.status == "degraded":
            add(Finding("seating", "seating", f"Seating is limited: {se.note}", "caution",
                        f"Ask the desk ({phone}) to reserve {t['seat_reserve']}."))
    if profile.needs_seating or profile.short_range or drives:
        pk = st("parking")
        if pk is not None and pk.status == "degraded":
            if drives and profile.short_range:
                add(Finding("parking", "parking_far_short_range", f"Parking may be too far for you: {pk.note}", "caution",
                            f"Ask the desk ({phone}) about a drop-off at {t['gate']} before parking."))
            else:
                add(Finding("parking", "parking_far", f"Parking: {pk.note}", "info"))
        elif pk is not None and pk.status in BLOCKING_STATUSES and drives:
            add(Finding("parking", "parking_out", f"Blue badge parking is unavailable: {pk.note}", "caution",
                        f"Ask the desk ({phone}) where to park or be dropped off."))

    # Hearing loop
    hl = st("hearing_loop")
    if profile.hearing_support and hl is not None:
        if hl.status in BLOCKING_STATUSES:
            add(Finding("hearing_loop", "loop_out", f"The hearing loop is not working: {hl.note}", "caution",
                        f"Ask the venue ({phone}) for a portable loop or reserved seat near the speaker."))
        elif hl.status in UNCERTAIN or hl.stale:
            add(Finding("hearing_loop", "loop_untested", f"The hearing loop has not been confirmed working: {hl.note}", "caution",
                        f"Ask the venue ({phone}) to test the hearing loop before your visit."))

    # Accessible toilet
    wc = st("toilet")
    if profile.needs_toilet and wc is not None and wc.status in BLOCKING_STATUSES:
        add(Finding("toilet", "toilet_out", f"The accessible toilet is out of order: {wc.note}", "caution",
                    f"Ask the venue ({phone}) where the nearest accessible toilet is."))

    # Uncertain required features not covered above must still reach the verify list.
    covered = {f.feature for f in r.findings}
    for fid in req:
        s = st(fid)
        if s is not None and fid not in covered and (s.status in UNCERTAIN or s.stale) and s.status not in BLOCKING_STATUSES:
            add(Finding(fid, f"{fid}_unconfirmed", f"{feature_label(fid)} is not confirmed ({s.status_label.lower()}, {s.freshness_text()}).",
                        "caution" if s.status == "verify" else "info", f"Ask the venue ({phone}) to confirm the {feature_label(fid).lower()}."))
    return r

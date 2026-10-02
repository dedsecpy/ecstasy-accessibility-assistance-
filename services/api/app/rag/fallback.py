"""Rule-based answer composer: used when no LLM is available, or when the LLM answer
fails validation twice. Every sentence is built from the live status board and cites it."""
from __future__ import annotations

from typing import Any

from nimbus_core.features import BLOCKING_STATUSES, FEATURES, WHEELED, feature_label, terms
from nimbus_core.fusion import FusedState
from nimbus_core.schemas import AnswerBody, Cited, Profile
from nimbus_core.visit import VisitContext

from .retrieval import Passage
from .rules import RuleResult

BLOCKER_HEADLINES = {
    "lift_out": "Do not travel on the strength of the listing: the lift is out of service and your destination is upstairs.",
    "gate_unanswered_now": "Not right now: the only step-free entrance is locked and nobody is answering.",
    "gate_out": "Not right now: the only step-free entrance is out of use.",
    "path_blocked": "Not right now: the only step-free path through {path_area} is blocked.",
    "ramp_out": "Not right now: the ramp on the step-free route is out of use.",
}
CAUTION_HEADLINES = {
    "lift_verify": "Check before you travel: the lift sensor and the maintenance log disagree about whether the lift is working.",
    "lift_unknown": "Check before you travel: the lift's live sensor is silent, so Ecstasy cannot confirm the lift is working.",
    "lift_stale": "The route works on paper, but the lift has not been confirmed recently - check on the day.",
    "lift_no_data": "Check before you travel: there is no record of the lift's status.",
    "gate_unanswered_earlier": "You can get in step-free, but {gate} was recently left unanswered - pre-book assistance.",
    "gate_unconfirmed": "Check before you travel: the arrangements at {gate} are not confirmed.",
    "path_narrow": "Entry is possible, but {path} is narrowed - confirm your chair fits first.",
    "path_unconfirmed": "Check before you travel: {path} has not been confirmed clear recently.",
    "out_of_hours": "You can get in step-free, but only via {gate} and only if assistance is pre-booked for your arrival time.",
    "out_of_hours_late": "You can get in step-free via {gate}, but the desk will be closed when you arrive - phone ahead so security meets you.",
    "intercom_down": "You can get in step-free, but the intercom at {gate} is not working - phone when you arrive.",
    "steep_ramp": "The step-free route works, but it includes a steep ramp with nowhere to rest - allow time or ask for help.",
    "seating": "You can get in, but plan rest stops: {seating_short}.",
    "loop_untested": "You can get in, but the hearing loop has not been confirmed working - ask the venue to test it first.",
    "loop_out": "You can get in, but the hearing loop is not working - ask for a portable loop or a seat near the speaker.",
    "toilet_out": "You can get in, but the accessible toilet is out of order - ask where the nearest one is.",
    "parking_far_short_range": "The route works, but the blue badge parking may be too far for you - ask about a drop-off at {gate}.",
    "parking_out": "The route works, but blue badge parking is unavailable - ask the desk where to park or be dropped off.",
}
CAUTION_ORDER_WHEELED = ["lift_verify", "lift_unknown", "lift_no_data", "lift_stale", "gate_unconfirmed", "gate_unanswered_earlier",
                         "path_unconfirmed", "path_narrow", "out_of_hours", "out_of_hours_late", "intercom_down", "steep_ramp", "seating",
                         "parking_far_short_range", "parking_out", "toilet_out", "loop_out", "loop_untested"]
CAUTION_ORDER_WALKING = ["lift_verify", "lift_unknown", "lift_no_data", "lift_stale", "seating", "parking_far_short_range", "steep_ramp",
                         "path_unconfirmed", "out_of_hours", "out_of_hours_late", "gate_unconfirmed", "gate_unanswered_earlier", "path_narrow",
                         "intercom_down", "parking_out", "toilet_out", "loop_out", "loop_untested"]


class Citer:
    def __init__(self, live: list[dict[str, Any]], passages: list[Passage]):
        self.sid = {it["feature"]: it["sid"] for it in live}
        self.passages = passages

    @staticmethod
    def _relevance(p: Passage, feature: str) -> int:
        kws = FEATURES[feature].keywords if feature in FEATURES else (feature,)
        head, body = p.heading.lower(), p.text.lower()
        return sum(3 * head.count(k) + body.count(k) for k in kws)

    def __call__(self, feature: str, n_passages: int = 2, source_type: str | None = None) -> list[str]:
        out = [self.sid[feature]] if feature in self.sid else []
        scored = [(self._relevance(p, feature), -i, p) for i, p in enumerate(self.passages)
                  if feature in p.features() and (source_type is None or p.source_type == source_type)]
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        out += [p.pid for score, _, p in scored[:n_passages] if score > 0]
        return out

    def listing(self) -> list[str]:
        return [p.pid for p in self.passages if p.source_type == "listing"][:1]


def compose(profile: Profile, visit: VisitContext, rules: RuleResult, states: dict[str, FusedState],
            live: list[dict[str, Any]], passages: list[Passage], config: dict[str, Any]) -> AnswerBody:
    cite = Citer(live, passages)
    t = terms()
    wheeled = profile.mobility in WHEELED
    st = states.get
    route: list[Cited] = []

    pk = st("parking")
    if pk is not None and (profile.short_range or profile.needs_seating or profile.arrival in ("blue_badge", "car")):
        route.append(Cited(text=f"Arrive at the blue badge parking: {pk.note}", citations=cite("parking")))
    me = st("main_entrance")
    if me is not None and me.status == "not_step_free":
        if wheeled:
            route.append(Cited(text=f"Do not use the main entrance ({me.note.rstrip('.')}). Go to the {feature_label('side_gate')} instead.",
                               citations=cite("main_entrance")))
        else:
            route.append(Cited(text=f"The main entrance is not step-free ({me.note.rstrip('.')}); the step-free alternative is the {feature_label('side_gate')}.",
                               citations=cite("main_entrance")))
    sg = st("side_gate")
    if sg is not None:
        route.append(Cited(text=f"Enter via the {feature_label('side_gate')}: press the intercom and wait to be let in. Now: {sg.note}",
                           citations=cite("side_gate")))
    cp = st("courtyard_path")
    if cp is not None:
        route.append(Cited(text=f"Cross {t['path_area']}. {cp.note}", citations=cite("courtyard_path")))
    rp = st("ramp")
    if rp is not None:
        route.append(Cited(text=f"Take the ramp up to {t['ramp_to']}: {rp.note}", citations=cite("ramp")))
    lf = st("lift")
    dest = visit.destination or "your destination"
    if visit.needs_lift:
        if lf is not None and lf.status in BLOCKING_STATUSES:
            route.append(Cited(text=f"The lift to the {dest} is out of service - there is no step-free way up. Do not travel until it is confirmed working.",
                               citations=cite("lift")))
        elif lf is not None:
            route.append(Cited(text=f"Take the lift from {t['lift_from']} to the {dest} (floor {visit.floor if visit.floor is not None else 1}). Live status: {lf.status_label.lower()}, {lf.freshness_text()}.",
                               citations=cite("lift")))
    else:
        route.append(Cited(text=f"The {dest} is on the ground floor - no lift needed.", citations=cite("lift") or cite("ramp")))
    tl = st("toilet")
    if tl is not None:
        route.append(Cited(text=f"Accessible toilet: {tl.note}", citations=cite("toilet")))
    route = [r for r in route if r.citations] or route

    warnings = [Cited(text=f.text, citations=cite(f.feature)) for f in rules.findings]
    verify = rules.verify_items or [f"Call {visit.phone} during desk hours to confirm the current lift and gate arrangements."]

    discrepancies: list[Cited] = []
    for claim in config.get("listing_claims", []):
        bad = []
        for fid in claim.get("features", []):
            s = st(fid)
            if s is None or fid not in rules.required + rules.context_features:
                continue
            if s.status in BLOCKING_STATUSES or s.status in ("degraded", "verify"):
                bad.append((fid, s))
        if bad:
            fid, s = bad[0]
            discrepancies.append(Cited(
                text=f"The listing says '{claim['text']}', but the {s.label.lower()} is {s.status_label.lower()}: {s.note}",
                citations=list(dict.fromkeys(cite.listing() + cite(fid, 1)))))

    codes = [f.code for f in rules.findings]
    if rules.blockers:
        verdict = "no_go"
        code = rules.blockers[0].code
        headline = BLOCKER_HEADLINES[code].format(**t) if code in BLOCKER_HEADLINES else "Do not travel yet: " + rules.blockers[0].text
    elif rules.cautions:
        verdict = "caution"
        order = CAUTION_ORDER_WALKING if profile.mobility == "walks_short_distances" else CAUTION_ORDER_WHEELED
        code = next((c for c in order if c in codes), rules.cautions[0].code)
        headline = CAUTION_HEADLINES[code].format(**t) if code in CAUTION_HEADLINES else "Possible, but check first: " + rules.cautions[0].text
    else:
        verdict = "go"
        headline = (f"Yes - the step-free route via the {feature_label('side_gate')} works for you"
                    + (f", and the lift to the {dest} is working." if visit.needs_lift else ".")) if wheeled \
            else "Yes - your route works for this visit."

    n_live = sum(1 for it in live if it["required"])
    bits = [f"Ecstasy checked {n_live} live status items for your route and {len(passages)} venue records."]
    if lf is not None:
        bits.append(f"Lift: {lf.status_label.lower()} ({lf.freshness_text()}).")
    if config.get("listing_updated"):
        bits.append(f"The public listing was last updated {config['listing_updated']} and does not reflect live conditions.")
    return AnswerBody(verdict=verdict, headline=headline, summary=" ".join(bits), route=route, warnings=warnings,
                      verify=verify, discrepancies=discrepancies)

"""Query planner: which features to check, and which sub-queries to run.
Claude (fast model) proposes; the rule-based plan is always merged in, so the plan can
only grow, never drop a feature the visitor physically needs."""
from __future__ import annotations

import logging
import re
from typing import Any

from nimbus_core import prompts
from nimbus_core.bedrock import BedrockError, get_bedrock
from nimbus_core.config import get_settings
from nimbus_core.features import FEATURES
from nimbus_core.schemas import Profile
from nimbus_core.visit import VisitContext

log = logging.getLogger("api.planner")

FEATURE_QUERIES = {
    "lift": "lift out of service fault engineer returned to service",
    "side_gate": "side gate Mill Lane locked intercom opened on request",
    "intercom": "intercom answered staffed hours side gate",
    "main_entrance": "main entrance steps step-free",
    "ramp": "ramp gradient 1:12 handrail rest points",
    "courtyard_path": "courtyard path scaffolding narrow width",
    "seating": "seating bench chairs foyer rest",
    "toilet": "accessible toilet transfer",
    "parking": "blue badge parking distance Mill Lane",
    "assistance_desk": "assistance desk hours outside staffed hours security pre-book 48 hours",
    "hearing_loop": "hearing loop induction Main Hall",
}

# A rule finding sharpens its feature's search to the situation at hand. {window} is the visit's
# desk-hours text, e.g. "desk closed on Sundays".
_HOURS_Q = "assistance desk hours outside staffed hours security open Side Gate pre-book 48 hours {window}"
_LIFT_CONFIRM_Q = "lift status confirm tested returned to service engineer"
_GATE_Q = "side gate locked intercom unanswered security opens gate on request"
FINDING_QUERIES = {
    "lift_out": "lift stopped between floors out of service engineer no alternative step-free route",
    "lift_verify": _LIFT_CONFIRM_Q,
    "lift_unknown": _LIFT_CONFIRM_Q,
    "lift_stale": _LIFT_CONFIRM_Q,
    "lift_no_data": _LIFT_CONFIRM_Q,
    "out_of_hours": _HOURS_Q,
    "out_of_hours_late": _HOURS_Q,
    "hours_unknown": _HOURS_Q,
    "gate_unanswered_now": _GATE_Q,
    "gate_unanswered_earlier": _GATE_Q,
    "gate_unconfirmed": _GATE_Q,
    "gate_out": "side gate only step-free route entrance",
    "intercom_down": "side gate intercom not working replaced",
    "path_blocked": "courtyard path blocked scaffolding portable ramp delivery entrance",
    "path_narrow": "courtyard scaffolding path narrow width powered chairs scooters portable ramp delivery entrance",
    "steep_ramp": "ramp gradient 1:12 steep handrail no resting places",
    "ramp_out": "ramp closed handrail gradient alternative access",
    "seating": "seating rest points benches foyer chairs 120 metres",
}


def mentioned_features(question: str) -> list[str]:
    """Features the visitor names in their own words ("elevator" -> lift, "loop" -> hearing_loop)."""
    def words(text: str) -> set[str]:
        return {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in re.findall(r"[a-z0-9]+", text.lower())}

    toks = words(question)
    return [fid for fid, feat in FEATURES.items() if any(words(k) and words(k) <= toks for k in feat.keywords)]


def rule_plan(question: str, profile: Profile, visit: VisitContext, required: list[str]) -> dict[str, Any]:
    # The question stays unpadded so its own ranking is sharp; profile needs are covered by the
    # per-feature sub-queries.
    main = question.strip() or f"step-free route from arrival to seat {profile.query_terms()}"
    if visit.destination:
        main = f"{main} {visit.destination}"
    mentioned = mentioned_features(question)
    feats = list(dict.fromkeys(required + mentioned))
    subs = [FEATURE_QUERIES[f] for f in feats if f in FEATURE_QUERIES]
    return {"features": feats, "sub_queries": subs, "main_query": main, "mentioned": mentioned, "method": "rules"}


def plan(question: str, profile: Profile, visit: VisitContext, required: list[str]) -> dict[str, Any]:
    base = rule_plan(question, profile, visit, required)
    client = get_bedrock()
    if client is None:
        return base
    try:
        data = client.converse_json(
            model=get_settings().fast_llm_model,
            system=prompts.PLANNER_SYSTEM.format(features=prompts.features_block()),
            user=f"PROFILE: {profile.describe()}\nVISIT:\n{visit.describe()}\nQUESTION: {question or 'Can I get in and to my seat?'}",
            tool_name="plan_retrieval", tool_description="Plan which features to check and what to search for",
            schema=prompts.PLANNER_SCHEMA, max_tokens=400,
        )
    except BedrockError as e:
        base["error"] = str(e)[:300]
        return base
    feats = list(dict.fromkeys(base["features"] + [f for f in data.get("features", []) if f in FEATURES]))
    llm_subs = [s for s in data.get("sub_queries", []) if isinstance(s, str) and s.strip()][:5]
    subs = list(dict.fromkeys(llm_subs + base["sub_queries"]))
    return {"features": feats, "sub_queries": subs, "main_query": base["main_query"], "mentioned": base["mentioned"],
            "method": f"llm:{get_settings().fast_llm_model}"}

"""Report -> structured facts. Claude (fast model, enum-constrained tool schema) when Bedrock
is available; a keyword rule extractor otherwise."""
from __future__ import annotations

import logging
import re
from typing import Any

from . import prompts
from .bedrock import BedrockError, get_bedrock
from .config import get_settings
from .features import FEATURES, STATUS_LABELS

log = logging.getLogger("nimbus.extraction")

STATUS_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("out_of_service", ("out of order", "out of service", "not working", "broken", "stopped", "isn't working", "wasn't working",
                        "no lift", "doors not closing", "fault")),
    ("locked_unanswered", ("nobody answered", "no answer", "no one answered", "didn't answer", "unanswered", "nobody came",
                           "no one came", "nobody has answered")),
    ("locked_on_request", ("let me in", "let us in", "opened the gate", "came and opened", "opened quickly", "answered quickly",
                           "answered the intercom", "routes to the desk")),
    ("degraded", ("narrow", "scaffolding", "blocked", "partly", "full", "taken", "occupied", "steep", "loose", "cordon",
                  "no bench", "nowhere to sit", "no seating", "needed a push")),
    ("ok", ("working", "worked", "fine", "ok", "okay", "open", "available", "no problem", "clean", "repaired", "fixed",
            "back in service", "returned to service", "clear at full width", "found a chair", "tested")),
]


def rule_extract(text: str) -> list[dict[str, Any]]:
    originals = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    facts = []
    for fid, feat in FEATURES.items():
        pats = [re.compile(r"\b" + re.escape(k) + r"s?\b") for k in feat.keywords]
        relevant = [s for s in originals if any(p.search(s.lower()) for p in pats)]
        if not relevant:
            continue
        blob = " ".join(relevant).lower()
        status = "unknown"
        for name, needles in STATUS_PATTERNS:
            if any(n in blob for n in needles):
                status = name
                break
        if fid == "main_entrance" and ("steps" in blob or "stairs" in blob):
            status = "not_step_free"
        if fid in ("side_gate", "intercom") and status == "degraded":
            status = "unknown"
        if fid == "intercom" and status == "locked_on_request":
            status = "ok"
        if fid == "intercom" and status == "locked_unanswered":
            status = "unknown"  # unanswered says nothing about whether the intercom itself works
        if fid == "side_gate" and status == "ok":
            status = "locked_on_request"
        if fid == "lift" and ("returned to service" in blob or ("repaired" in blob and "tested" in blob)):
            status = "ok"
        if fid == "courtyard_path" and ("full width" in blob or "cleared" in blob):
            status = "ok"
        if status == "unknown":
            continue
        note = relevant[0].strip()
        facts.append({"feature": fid, "status": status, "note": (note[:1].upper() + note[1:])[:220], "confidence": 0.55})
    return facts


def extract_facts(text: str, kind: str, needs: str, when: str) -> tuple[list[dict[str, Any]], str, str, str | None]:
    """Returns (facts, summary, mode, error)."""
    client = get_bedrock()
    if client is not None:
        try:
            data = client.converse_json(
                model=get_settings().fast_llm_model,
                system=prompts.EXTRACT_SYSTEM.format(features=prompts.features_block(), statuses=prompts.statuses_block()),
                user=prompts.EXTRACT_USER.format(date=when, kind=kind, needs=needs or "not stated", text=text),
                tool_name="record_facts", tool_description="Record the accessibility facts stated in the report",
                schema=prompts.EXTRACT_SCHEMA, max_tokens=800,
            )
            facts = [f for f in data.get("facts", [])
                     if f.get("feature") in FEATURES and f.get("status") in STATUS_LABELS and f.get("status") != "verify"]
            return facts, data.get("summary", ""), "llm", None
        except BedrockError as e:
            log.warning("LLM extraction failed, using rules: %s", e)
            return rule_extract(text), "", "rules", str(e)[:300]
    return rule_extract(text), "", "rules", None

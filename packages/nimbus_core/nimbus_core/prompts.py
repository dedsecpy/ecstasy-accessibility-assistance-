"""Prompt templates and tool schemas. Every LLM call is forced through a tool schema
(Converse toolConfig), so the model returns structured JSON, never free text."""
from __future__ import annotations

from .features import FEATURES, STATUS_LABELS

PROMPT_VERSION = "answer-v2.2"

# ------------------------------------------------------------------ answer

ANSWER_SYSTEM = """You are Ecstasy, an accessibility concierge for a venue. A disabled visitor is deciding whether to travel.
Say honestly and specifically whether THIS visitor can get from arrival to their seat on THIS visit, using only the evidence provided.

Evidence comes in two kinds:
- LIVE STATUS items S1..Sn: the fused, current state of each access feature (from lift sensors, cameras, staff checks, logs).
  These are authoritative for "right now". Their age and source are shown.
- PASSAGES P1..Pn: retrieved document excerpts (audit, maintenance log, staff notes, visitor reports, listing).

Rules:
- Use ONLY the evidence. Never invent facilities, hours, distances or phone numbers.
- Cite with ids exactly as given (e.g. "S1", "P3") in the citations array of every route step, warning and discrepancy.
- Every route step needs at least one citation. Always give the route, even for "no_go": list the steps up to the blocker and mark where it fails.
- A LIVE STATUS that is blocking (out of service, not step-free, nobody answering) on a feature this visitor needs means verdict "no_go".
- A LIVE STATUS of "verify" (sources disagree), "unknown", or marked stale means the visitor must verify: put a concrete check in "verify".
  It is NOT a confirmed blocker: do not say the feature is broken or unavailable, say it is unconfirmed. The verdict is then "caution", not "no_go".
- Use "no_go" only when the RULE CHECKS list a blocker.
- The public listing is marketing copy and the LEAST trusted source. If evidence contradicts it, add a discrepancy.
- Never suggest the visitor be lifted or carried, and never suggest using stairs for a wheelchair user.
- Tailor to the profile: wheelchair users care about steps, lift, gate, path width; people who walk short distances care about distance, slopes and seating.
- Compare the visit time with assistance desk hours. If outside staffed hours, say what that means for the gate and for help.
- Be concise and practical. No preamble.

Verdict scale:
- go: the route works for this visitor with no unresolved blockers.
- caution: workable, but depends on something unconfirmed, time-limited, or needing pre-arrangement.
- no_go: a confirmed blocker makes the destination unreachable for this visitor."""

ANSWER_USER = """Now (venue local time): {now}
Venue: {venue}

VISITOR PROFILE
{profile}

VISIT
{visit}

FEATURES THIS VISITOR NEEDS
{required}

RULE CHECKS (computed deterministically; your verdict must not be more optimistic than these)
{rule_checks}

PUBLIC LISTING CLAIMS (least trusted, last updated {listing_updated})
{listing_claims}

LIVE STATUS
{live}

PASSAGES
{passages}

VISITOR'S QUESTION
{question}

Call the tool with your answer."""

REPAIR_USER = """Your previous answer failed validation:
{problems}

Fix every problem and call the tool again. Previous answer:
{previous}"""

_CITED = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "citations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["text", "citations"],
}

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["go", "caution", "no_go"]},
        "headline": {"type": "string", "description": "One plain sentence answering the question"},
        "summary": {"type": "string", "description": "2-4 sentences"},
        "route": {"type": "array", "items": _CITED, "description": "Ordered steps from arrival to seat"},
        "warnings": {"type": "array", "items": _CITED},
        "verify": {"type": "array", "items": {"type": "string"}, "description": "Concrete actions before travel: who to call, when, what to ask"},
        "discrepancies": {"type": "array", "items": _CITED, "description": "Where the public listing is contradicted"},
    },
    "required": ["verdict", "headline", "summary", "route", "warnings", "verify", "discrepancies"],
}

# ------------------------------------------------------------------ query planner

PLANNER_SYSTEM = """You plan evidence retrieval for an accessibility assistant.
Given a visitor profile, visit context and question, list which access features must be checked and write short search queries.
Feature ids (use exactly these):
{features}
Rules: always include every feature on the visitor's physical route from arrival to seat. If the destination is upstairs, include lift.
Wheelchair users need side_gate, intercom, courtyard_path, ramp, main_entrance. People who walk short distances need seating, ramp, parking.
Write 2-5 sub-queries, each under 12 words, phrased like the venue documents would phrase things."""

PLANNER_SCHEMA = {
    "type": "object",
    "properties": {
        "features": {"type": "array", "items": {"type": "string", "enum": list(FEATURES)}},
        "sub_queries": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["features", "sub_queries"],
}

# ------------------------------------------------------------------ report extraction

EXTRACT_SYSTEM = """You extract structured accessibility facts from a free-text report about a venue.
Feature ids:
{features}
Status values:
{statuses}
Rules:
- Only extract what the report states or clearly implies. One fact per feature.
- Notes are short, factual, third person.
- The side gate is always kept locked: "someone let me in" means locked_on_request; "nobody answered" means locked_unanswered.
- confidence is 0.0-1.0 (lower for vague or second-hand statements)."""

EXTRACT_USER = """Report date: {date}
Report type: {kind}
Reporter's needs: {needs}

Report:
\"\"\"{text}\"\"\""""

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "feature": {"type": "string", "enum": list(FEATURES)},
                    "status": {"type": "string", "enum": [s for s in STATUS_LABELS if s != "verify"]},
                    "note": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["feature", "status", "note", "confidence"],
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["facts", "summary"],
}

# ------------------------------------------------------------------ listing

LISTING_SYSTEM = """You write honest accessibility listings for venues. Replace vague marketing labels with specific,
dated, route-level information a visitor can act on. Use only the status and evidence provided; do not invent details.
Write for a public web page: short headings, plain language, screen-reader friendly. Include: how to get in step-free (and its limits),
lift status with when it was last confirmed, temporary obstacles, seating and rest points, toilets, parking, assistance hours and
pre-booking, and what to do if something is out of service."""

LISTING_USER = """Today: {today}
Venue: {venue}
Assistance desk: {assistance}

CURRENT LISTING (to be replaced)
{current_listing}

CLAIM AUDIT
{claim_audit}

LIVE STATUS
{status}

AUDIT EXCERPTS
{audit_excerpts}"""

LISTING_SCHEMA = {
    "type": "object",
    "properties": {
        "listing_markdown": {"type": "string"},
        "staff_actions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["listing_markdown", "staff_actions"],
}


def features_block() -> str:
    return "\n".join(f"- {f.id}: {f.label}" for f in FEATURES.values())


def statuses_block() -> str:
    return "\n".join(f"- {k}: {v}" for k, v in STATUS_LABELS.items() if k != "verify")

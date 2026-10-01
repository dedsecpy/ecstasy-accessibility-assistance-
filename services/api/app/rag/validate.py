"""Post-generation validators. Hard problems trigger one repair attempt, then the rule-based
fallback. Soft problems are fixed deterministically (verdict floor, missing verify items)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from nimbus_core.features import WHEELED
from nimbus_core.schemas import AnswerBody, Profile

from .rules import RuleResult

VERDICT_RANK = {"go": 0, "caution": 1, "no_go": 2}

BANNED_ALL = re.compile(
    r"\b(carr(y|ied|ying)\s+(you|them|him|her|the visitor|your chair)|be\s+carried|piggy-?back|"
    r"lift(ed)?\s+(you|them|him|her)\s+(up|over)|bump(ed)?\s+(you|the chair|your chair)\s+up)\b", re.I)
BANNED_WHEELED = re.compile(r"\b(use|take|climb)\s+the\s+(stairs|steps|staircase)\b", re.I)
CITATION_RE = re.compile(r"^[SP]\d+$")


@dataclass
class Validation:
    hard: list[str] = field(default_factory=list)
    fixes: list[str] = field(default_factory=list)
    body: AnswerBody | None = None

    @property
    def ok(self) -> bool:
        return not self.hard and self.body is not None

    def to_dict(self) -> dict[str, Any]:
        return {"hard_problems": self.hard, "fixes": self.fixes, "ok": self.ok}


def _texts(body: AnswerBody) -> list[str]:
    return [body.headline, body.summary, *[r.text for r in body.route], *[w.text for w in body.warnings], *body.verify,
            *[d.text for d in body.discrepancies]]


def check(raw: dict[str, Any], valid_ids: set[str], profile: Profile, rules: RuleResult | None = None) -> Validation:
    v = Validation()
    try:
        body = AnswerBody.model_validate(raw)
    except ValidationError as e:
        v.hard.append(f"Output does not match the schema: {e.errors()[:3]}")
        return v
    v.body = body
    if rules is not None and body.verdict == "no_go" and not rules.blockers:
        unsure = list(dict.fromkeys(f.feature for f in rules.cautions))
        v.hard.append("Verdict no_go needs a confirmed blocker, and the rule checks list none"
                      + (f"; unconfirmed (not broken): {', '.join(unsure)}" if unsure else "")
                      + ". Use caution, describe unconfirmed features as unconfirmed, and put the check in verify.")
    if not body.route:
        if body.verdict == "no_go" and rules is not None and rules.blockers:
            v.fixes.append("route empty on a confirmed no_go; accepted")
        else:
            v.hard.append("The route is empty; give ordered steps from arrival to seat.")
    for i, step in enumerate(body.route, 1):
        if not step.citations:
            v.hard.append(f"Route step {i} has no citation.")
    for item in [*body.route, *body.warnings, *body.discrepancies]:
        for c in item.citations:
            if not CITATION_RE.match(c) or c not in valid_ids:
                v.hard.append(f"Citation '{c}' does not exist. Valid ids: {', '.join(sorted(valid_ids))}.")
    for t in _texts(body):
        if BANNED_ALL.search(t):
            v.hard.append(f"Unsafe advice (carrying or lifting a person) in: '{t[:120]}'. Remove it.")
        if profile.mobility in WHEELED and BANNED_WHEELED.search(t):
            v.hard.append(f"Stairs suggested to a wheelchair user in: '{t[:120]}'. Remove it.")
    v.hard = list(dict.fromkeys(v.hard))
    return v


def enforce(body: AnswerBody, rules: RuleResult, v: Validation) -> AnswerBody:
    """Safety overrides that never depend on the model behaving."""
    if VERDICT_RANK[body.verdict] < VERDICT_RANK[rules.min_verdict]:
        v.fixes.append(f"verdict raised from {body.verdict} to {rules.min_verdict} by rule checks: "
                       + "; ".join(f.code for f in (rules.blockers or rules.cautions)))
        body.verdict = rules.min_verdict  # type: ignore[assignment]
        if rules.blockers and not body.headline.lower().startswith(("do not", "not ")):
            body.headline = "Do not travel yet: " + rules.blockers[0].text.split(":")[0] + "."
    blob = " ".join(body.verify).lower()
    for f in rules.findings:
        if not f.verify or f.severity == "info":
            continue
        key = f.feature.replace("_", " ").split()[0]
        if key not in blob and f.verify not in body.verify:
            body.verify.append(f.verify)
            v.fixes.append(f"added verify item for {f.feature}")
    return body


def strip_invalid_citations(body: AnswerBody, valid_ids: set[str]) -> None:
    for item in [*body.route, *body.warnings, *body.discrepancies]:
        item.citations = [c for c in item.citations if c in valid_ids]

"""The full answer pipeline:

1 visit context (rules) -> 2 query planner -> 3 hybrid retrieval (Titan dense + BM25)
-> 4 RRF -> 5 rerank + priors -> 6 structured live context -> 7 Claude (Converse, tool schema)
-> 8 validators + safety overrides -> 9 one repair, else rule fallback -> trace.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable

from nimbus_core import db, prompts
from nimbus_core.bedrock import BedrockError, get_bedrock
from nimbus_core.config import get_settings
from nimbus_core.fusion import FusedState
from nimbus_core.schemas import AnswerBody, AskRequest
from nimbus_core.visit import build_visit_context, find_event, venue_now

from . import fallback, planner
from .context import live_items, live_text, passages_text, refresh_ages
from .rerank import rerank
from .retrieval import HybridRetriever
from .rules import assess
from .validate import Validation, check, enforce, strip_invalid_citations

log = logging.getLogger("api.pipeline")
Progress = Callable[[str, str], None]


def _noop(_stage: str, _msg: str) -> None:
    pass


SEVERITY_RANK = {"blocker": 0, "caution": 1, "info": 2}


def _sub_queries(plan: dict, rules, visit, states: dict[str, FusedState]) -> list[tuple[str, str | None]]:
    """(query, feature) pairs. Retrieval keeps at most 8 queries, so order matters: features the
    visitor asked about or that have blockers/cautions first (searched with their finding's
    specific query plus the live note), then free-form (LLM) sub-queries, then the rest."""
    feature_of = {q: f for f, q in planner.FEATURE_QUERIES.items()}
    sev = {f: -1 for f in plan.get("mentioned", [])}
    sharpened: dict[str, str] = {}
    for f in sorted(rules.findings, key=lambda f: SEVERITY_RANK.get(f.severity, 3)):
        sev[f.feature] = min(sev.get(f.feature, 3), SEVERITY_RANK.get(f.severity, 3))
        if f.severity != "info" and f.code in planner.FINDING_QUERIES and f.feature not in sharpened:
            q = planner.FINDING_QUERIES[f.code].format(window=visit.staffed_window)
            st = states.get(f.feature)
            if f.severity == "blocker" and st is not None and st.note:
                q = f"{q} {st.note[:160]}"
            sharpened[f.feature] = q
    llm = [(q, None) for q in plan["sub_queries"] if q not in feature_of]
    feats = list(dict.fromkeys([feature_of[q] for q in plan["sub_queries"] if q in feature_of] + list(sharpened)))
    feats.sort(key=lambda f: sev.get(f, 3))
    ruled = [(sharpened.get(f) or planner.FEATURE_QUERIES[f], f) for f in feats if f in planner.FEATURE_QUERIES]
    risky = [x for x in ruled if sev.get(x[1], 3) <= 1]
    return risky + llm + [x for x in ruled if x not in risky]


class AnswerPipeline:
    def __init__(self) -> None:
        self.retriever = HybridRetriever()

    def answer(self, venue_id: str, req: AskRequest, progress: Progress | None = None,
               states: dict[str, FusedState] | None = None, persist: bool = True) -> dict[str, Any]:
        progress = progress or _noop
        t0 = time.time()
        config = db.get_venue(venue_id)
        if config is None:
            raise KeyError(venue_id)
        now = venue_now(config, req.now)
        event = find_event(config, req.event_id)

        progress("context", "Checking your visit time against assistance desk hours")
        visit = build_visit_context(config, event, req.visit_at, now)

        progress("live", "Reading the live lift sensor, cameras and staff checks")
        if states is None:
            states = refresh_ages(db.get_feature_states(venue_id), datetime.now(timezone.utc))
        rules = assess(req.profile, visit, states)

        progress("plan", "Working out which access features your route depends on")
        plan = planner.plan(req.question, req.profile, visit, rules.required)
        required = plan["features"]
        live = live_items(states, required, rules.context_features)

        progress("retrieve", "Searching the venue's records")
        subs = _sub_queries(plan, rules, visit, states)
        cands, rdebug = self.retriever.retrieve(venue_id, [plan["main_query"], *(q for q, _ in subs)],
                                                max_date=int(now.strftime("%Y%m%d")))
        per_query = rdebug.pop("per_query", None)
        blocking = {f.feature for f in rules.blockers}
        quota_of = {q: 2 if f in blocking else 1 for q, f in subs}
        quotas = [2] + [quota_of.get(q, 1) for q in rdebug["queries"][1:]]
        progress("rerank", "Ranking evidence by relevance, recency and trust")
        passages, rinfo = rerank(plan["main_query"], cands, now.date(), required, per_query=per_query, quotas=quotas)
        valid_ids = {it["sid"] for it in live} | {p.pid for p in passages}

        mode, error = "fallback", None
        validation = Validation()
        body: AnswerBody | None = None
        client = get_bedrock()
        s = get_settings()
        if client is not None:
            progress("generate", "Writing your answer")
            user = prompts.ANSWER_USER.format(
                now=now.strftime("%A %d %B %Y, %H:%M"), venue=config["name"], profile=req.profile.describe(),
                visit=visit.describe(), required=", ".join(required), rule_checks=rules.summary_lines(),
                listing_updated=config.get("listing_updated", "unknown"),
                listing_claims="\n".join(f"- {c['text']}" for c in config.get("listing_claims", [])),
                live=live_text(live), passages=passages_text(passages, now.date()),
                question=req.question or "Can I get in and to my seat for this visit?")
            try:
                raw = self._generate(client, user)
                validation = check(raw, valid_ids, req.profile, rules)
                if not validation.ok:
                    progress("repair", "Answer failed a safety check - asking the model to fix it")
                    repair_user = user + "\n\n" + prompts.REPAIR_USER.format(
                        problems="\n".join(f"- {p}" for p in validation.hard), previous=json.dumps(raw)[:6000])
                    first_problems = validation.hard
                    raw = self._generate(client, repair_user)
                    validation = check(raw, valid_ids, req.profile, rules)
                    validation.fixes.append(f"repaired after: {first_problems}")
                if validation.ok:
                    body, mode = validation.body, "llm"
                else:
                    error = "Model answer failed validation twice; showing the rule-based answer."
            except BedrockError as e:
                error = f"{s.provider_label} generation failed; showing the rule-based answer. ({e})"[:400]
                log.warning(error)

        progress("validate", "Safety-checking the answer against live status")
        if body is None:
            body = fallback.compose(req.profile, visit, rules, states, live, passages, config)
            fb_check = check(body.model_dump(), valid_ids, req.profile)
            if fb_check.hard:
                validation.fixes.append(f"fallback issues: {fb_check.hard}")
            if mode == "fallback" and client is not None:
                validation.fixes.append("model answer discarded: " + "; ".join(validation.hard)[:500])
            validation.hard, validation.body = fb_check.hard, body
        cited = [c for item in [*body.route, *body.warnings, *body.discrepancies] for c in item.citations]
        citation_stats = {"total": len(cited), "invalid": sum(c not in valid_ids for c in cited),
                          "uncited_steps": sum(not s.citations for s in body.route)}
        strip_invalid_citations(body, valid_ids)
        body = enforce(body, rules, validation)

        latency_ms = int((time.time() - t0) * 1000)
        ai = {
            "mode": mode,
            "provider": s.provider_label if client is not None else None,
            "bedrock_enabled": client is not None,
            "llm_model": s.llm_model if mode == "llm" else None,
            "embedder": self.retriever.index_info.get("embedder_label"),
            "embedder_reason": self.retriever.index_info.get("reason"),
            "rerank": rinfo.get("method"),
            "planner": plan.get("method"),
            "error": error,
        }
        result = {
            "answer": body.model_dump(),
            "mode": mode,
            "ai": ai,
            "visit": visit.to_dict(),
            "required_features": required,
            "rule_findings": [f.__dict__ for f in rules.findings],
            "live": live,
            "passages": [p.to_dict() for p in passages],
            "plan": plan,
            "retrieval": {**rdebug, **rinfo, "candidates": len(cands)},
            "validation": {**validation.to_dict(), "citations": citation_stats},
            "latency_ms": latency_ms,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "prompt_version": prompts.PROMPT_VERSION,
        }
        if persist:
            result["trace_id"] = db.insert_trace(
                venue_id, req.question, req.model_dump(), plan,
                [{"pid": p.pid, "chunk_id": p.chunk_id, "scores": p.scores} for p in passages],
                live, result["answer"], {**validation.to_dict(), "ai": ai}, mode, prompts.PROMPT_VERSION, latency_ms)
        return result

    @staticmethod
    def _generate(client, user: str) -> dict[str, Any]:
        return client.converse_json(
            model=get_settings().llm_model, system=prompts.ANSWER_SYSTEM, user=user,
            tool_name="give_answer", tool_description="Return the visitor's accessibility answer",
            schema=prompts.ANSWER_SCHEMA, max_tokens=2000)

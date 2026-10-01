"""Golden-set evaluation for the Ecstasy answer pipeline.

Runs every case in eval/golden.yaml through the real pipeline (hybrid retrieval, rerank, generation,
validators) with statuses fused from the case's synthetic observations, then reports:
verdict accuracy, fused-status accuracy, retrieval recall@8, citation validity, safety violations
(must be 0), verify-list coverage and p95 latency - in LLM mode (Groq or Bedrock, whichever is
configured) and/or fallback mode. On Groq's free tier pass --pause-s 45 so answers stay under the
per-minute token limit.

Run inside the stack (needs Postgres + Chroma with the corpus indexed):
  docker compose -f infra/docker-compose.yml run --rm --no-deps -v "${PWD}/eval:/app/eval" \
      api python /app/eval/run_eval.py --mode both
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

from nimbus_core import db  # noqa: E402
from nimbus_core.bedrock import get_bedrock  # noqa: E402
from nimbus_core.config import get_settings  # noqa: E402
from nimbus_core.features import SOURCE_TYPE_TO_KIND, WHEELED  # noqa: E402
from nimbus_core.fusion import Observation, fuse_all, source_rules  # noqa: E402
from nimbus_core.schemas import AskRequest, Profile  # noqa: E402
from nimbus_core.visit import venue_tz  # noqa: E402

from app.rag import pipeline as pipeline_mod  # noqa: E402
from app.rag import planner as planner_mod  # noqa: E402
from app.rag import rerank as rerank_mod  # noqa: E402
from app.rag.validate import BANNED_ALL, BANNED_WHEELED, VERDICT_RANK  # noqa: E402

AGE_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*([smhd])$")
AGE_UNIT = {"s": 1, "m": 60, "h": 3600, "d": 86400}
AI_MODULES = (pipeline_mod, planner_mod, rerank_mod)


def parse_age(text: str) -> timedelta:
    m = AGE_RE.match(str(text).strip())
    if not m:
        raise ValueError(f"bad age '{text}' (use 15s, 10m, 2h, 3d)")
    return timedelta(seconds=float(m.group(1)) * AGE_UNIT[m.group(2)])


def seed_observations(venue_dir: Path, tz) -> list[Observation]:
    out: list[Observation] = []
    path = venue_dir / "facts.jsonl"
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        f = json.loads(line)
        day = datetime.fromisoformat(f["date"][:10]).date()
        out.append(Observation(
            feature=f["feature"], status=f.get("status", "unknown"),
            source_kind=SOURCE_TYPE_TO_KIND.get(f.get("source_type", ""), "report"),
            observed_at=datetime(day.year, day.month, day.day, 9, 0, tzinfo=tz),
            note=f.get("note", ""), confidence=f.get("confidence"), source_ref=f"seed:facts:{i}"))
    return out


def case_states(case: dict[str, Any], baseline: list[Observation], now: datetime, rules) -> dict:
    obs = list(baseline)
    for j, o in enumerate(case.get("observations", [])):
        obs.append(Observation(
            feature=o["feature"], status=o["status"], source_kind=o["kind"],
            observed_at=now - parse_age(o.get("age", "0s")), note=o.get("note", ""),
            confidence=o.get("confidence"), source_ref=f"eval:{case['id']}:{j}"))
    return fuse_all(obs, now.astimezone(timezone.utc), rules)


def source_hit(expected: str, passages: list[dict[str, Any]]) -> bool:
    """expected: "doc_id", "doc_id#heading substring", or alternatives joined by "|"."""
    for alt in expected.split("|"):
        doc, _, heading = alt.strip().partition("#")
        for p in passages:
            if p["doc_id"] == doc and (not heading or heading.lower() in (p.get("heading") or "").lower()):
                return True
    return False


def answer_texts(a: dict[str, Any]) -> list[str]:
    return [a["headline"], a["summary"], *[r["text"] for r in a["route"]], *[w["text"] for w in a["warnings"]],
            *a["verify"], *[d["text"] for d in a["discrepancies"]]]


def p95(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return float(s[min(len(s) - 1, math.ceil(0.95 * len(s)) - 1)])


def set_mode(mode: str, real_get_bedrock) -> bool:
    """fallback: planner, rerank and generation run without the AI provider. Returns False if it is unavailable."""
    fn = (lambda: None) if mode == "fallback" else real_get_bedrock
    for m in AI_MODULES:
        m.get_bedrock = fn
    return mode == "fallback" or real_get_bedrock() is not None


def run_case(pipe, case: dict[str, Any], golden: dict[str, Any], baseline, rules, venue_id: str, tz) -> dict[str, Any]:
    d = golden.get("defaults", {})
    now_s = case.get("now", d.get("now"))
    now = datetime.fromisoformat(now_s).replace(tzinfo=tz)
    profile = Profile(**{**d.get("profile", {}), **case.get("profile", {})})
    req = AskRequest(question=case.get("question", ""), profile=profile, event_id=case.get("event"),
                     visit_at=case.get("visit_at"), now=now_s)
    states = case_states(case, baseline, now, rules)
    exp = case.get("expect", {})

    t0 = time.time()
    try:
        res = pipe.answer(venue_id, req, states=states, persist=False)
    except Exception as e:  # noqa: BLE001
        return {"id": case["id"], "group": case.get("group"), "error": f"{type(e).__name__}: {e}"[:400],
                "latency_ms": int((time.time() - t0) * 1000)}
    a = res["answer"]

    status_checks = {f: (states[f].status if f in states else None, want) for f, want in exp.get("status", {}).items()}
    sources = exp.get("sources", [])
    hits = [s for s in sources if source_hit(s, res["passages"])]
    verify_blob = " ".join(a["verify"]).lower()
    verify_missing = [w for w in exp.get("verify_mentions", []) if w.lower() not in verify_blob]

    safety: list[str] = []
    for t in answer_texts(a):
        if BANNED_ALL.search(t):
            safety.append(f"carry/lift advice: {t[:100]}")
        if profile.mobility in WHEELED and BANNED_WHEELED.search(t):
            safety.append(f"stairs advice to a wheelchair user: {t[:100]}")
    want = exp.get("verdict")
    if want and VERDICT_RANK[a["verdict"]] < VERDICT_RANK[want]:
        safety.append(f"verdict more optimistic than expected: {a['verdict']} < {want}")
    cstats = res["validation"].get("citations", {})
    if cstats.get("uncited_steps"):
        safety.append(f"{cstats['uncited_steps']} uncited route step(s)")

    return {
        "id": case["id"],
        "group": case.get("group"),
        "mode": res["mode"],
        "verdict": a["verdict"],
        "expected_verdict": want,
        "verdict_ok": (a["verdict"] == want) if want else None,
        "status_checks": {f: {"got": g, "want": w, "ok": g == w} for f, (g, w) in status_checks.items()},
        "recall": (len(hits) / len(sources)) if sources else None,
        "sources_expected": sources,
        "sources_hit": hits,
        "top_passages": [f"{p['doc_id']}#{p.get('heading', '')}" for p in res["passages"]],
        "citations": cstats,
        "verify_expected": exp.get("verify_mentions", []),
        "verify_missing": verify_missing,
        "safety_violations": safety,
        "repaired": any("repaired after" in f for f in res["validation"].get("fixes", [])),
        "fixes": res["validation"].get("fixes", []),
        "headline": a["headline"],
        "latency_ms": res["latency_ms"],
        "ai": res["ai"],
    }


def summarise(mode: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in rows if "error" not in r]
    verdicts = [r["verdict_ok"] for r in ok if r["verdict_ok"] is not None]
    statuses = [c["ok"] for r in ok for c in r["status_checks"].values()]
    recalls = [r["recall"] for r in ok if r["recall"] is not None]
    cit_total = sum(r["citations"].get("total", 0) for r in ok)
    cit_bad = sum(r["citations"].get("invalid", 0) for r in ok)
    verify_cases = [r for r in ok if r["verify_expected"]]
    return {
        "mode": mode,
        "cases": len(rows),
        "errors": len(rows) - len(ok),
        "answered_by": {m: sum(r["mode"] == m for r in ok) for m in sorted({r["mode"] for r in ok})},
        "verdict_accuracy": round(sum(verdicts) / len(verdicts), 3) if verdicts else None,
        "status_accuracy": round(sum(statuses) / len(statuses), 3) if statuses else None,
        "recall_at_8": round(sum(recalls) / len(recalls), 3) if recalls else None,
        "citation_validity": round(1 - cit_bad / cit_total, 3) if cit_total else None,
        "citations_checked": cit_total,
        "safety_violations": sum(len(r["safety_violations"]) for r in ok),
        "verify_coverage": round(sum(not r["verify_missing"] for r in verify_cases) / len(verify_cases), 3) if verify_cases else None,
        "repaired_answers": sum(r["repaired"] for r in ok),
        "p50_latency_ms": int(sorted(r["latency_ms"] for r in ok)[len(ok) // 2]) if ok else 0,
        "p95_latency_ms": int(p95([r["latency_ms"] for r in ok])),
    }


def markdown(summaries: list[dict[str, Any]], results: dict[str, list[dict[str, Any]]]) -> str:
    keys = [("verdict_accuracy", "Verdict accuracy"), ("status_accuracy", "Fused status accuracy"),
            ("recall_at_8", "Retrieval recall@8"), ("citation_validity", "Citation validity"),
            ("safety_violations", "Safety violations (must be 0)"), ("verify_coverage", "Verify-list coverage"),
            ("repaired_answers", "Answers repaired once"), ("p50_latency_ms", "p50 latency (ms)"),
            ("p95_latency_ms", "p95 latency (ms)"), ("errors", "Errors")]
    lines = ["# Ecstasy eval results", "", f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}", "",
             "| Metric | " + " | ".join(s["mode"] for s in summaries) + " |",
             "|---|" + "---|" * len(summaries)]
    for k, label in keys:
        lines.append(f"| {label} | " + " | ".join(str(s.get(k)) for s in summaries) + " |")
    lines.append(f"| Cases | " + " | ".join(str(s["cases"]) for s in summaries) + " |")
    for mode, rows in results.items():
        lines += ["", f"## {mode}: per case", "", "| Case | Verdict | Expected | Recall | Notes |", "|---|---|---|---|---|"]
        for r in rows:
            if "error" in r:
                lines.append(f"| {r['id']} | error | | | {r['error'][:80]} |")
                continue
            notes = []
            notes += [f"status {f}: {c['got']} (want {c['want']})" for f, c in r["status_checks"].items() if not c["ok"]]
            notes += [f"verify missing '{w}'" for w in r["verify_missing"]]
            notes += r["safety_violations"]
            mark = "" if r["verdict_ok"] in (True, None) else " (wrong)"
            rec = "-" if r["recall"] is None else f"{r['recall']:.2f}"
            lines.append(f"| {r['id']} | {r['verdict']}{mark} | {r['expected_verdict']} | {rec} | {'; '.join(notes)} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mode", choices=["fallback", "llm", "bedrock", "both"], default="both",
                    help="llm uses the configured provider (bedrock is accepted as an alias)")
    ap.add_argument("--pause-s", type=float, default=0.0, help="sleep between cases in llm mode (rate limits)")
    ap.add_argument("--golden", default=str(ROOT / "eval" / "golden.yaml"))
    ap.add_argument("--out", default=str(ROOT / "eval" / "results"))
    ap.add_argument("--only", help="comma-separated case ids")
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    golden = yaml.safe_load(Path(args.golden).read_text(encoding="utf-8"))
    venue_id = golden["venue"]
    db.wait_for_db()
    config = db.get_venue(venue_id)
    if config is None:
        print(f"venue {venue_id} not found - start the stack so the worker seeds it", file=sys.stderr)
        return 2
    tz = venue_tz(config)
    ttl = golden.get("ttl", {})
    rules = source_rules(ttl.get("sensor_s", 90), ttl.get("cctv_s", 300))
    baseline = seed_observations(get_settings().data_dir / "venues" / venue_id, tz)
    cases = golden["cases"]
    if args.only:
        wanted = set(args.only.split(","))
        cases = [c for c in cases if c["id"] in wanted]

    real_get_bedrock = get_bedrock
    s = get_settings()
    modes = ["llm", "fallback"] if args.mode == "both" else ["llm" if args.mode == "bedrock" else args.mode]
    pipe = pipeline_mod.AnswerPipeline()
    results: dict[str, list[dict[str, Any]]] = {}
    summaries: list[dict[str, Any]] = []
    for mode in modes:
        if not set_mode(mode, real_get_bedrock):
            print(f"[{mode}] skipped: no AI provider available (no GROQ_API_KEY / AWS credentials, or NIMBUS_AI_MODE=local)")
            continue
        print(f"[{mode}] running {len(cases)} cases" + (f" with {s.llm_model} on {s.provider_label}" if mode == "llm" else ""))
        rows = []
        for i, case in enumerate(cases):
            if mode == "llm" and args.pause_s and i:
                time.sleep(args.pause_s)
            r = run_case(pipe, case, golden, baseline, rules, venue_id, tz)
            rows.append(r)
            if "error" in r:
                print(f"  ERROR {r['id']}: {r['error']}")
                continue
            flag = "ok " if r["verdict_ok"] else "BAD"
            rec = "-" if r["recall"] is None else f"{r['recall']:.2f}"
            extra = "; ".join(r["safety_violations"] + [f"verify missing {w}" for w in r["verify_missing"]]
                              + [f"{f}={c['got']}" for f, c in r["status_checks"].items() if not c["ok"]])
            print(f"  {flag} {r['id']:<40} {r['verdict']:<8} want {r['expected_verdict']:<8} recall {rec}  {r['latency_ms']:>5} ms  {extra}")
        results[mode] = rows
        summaries.append(summarise(mode, rows))
    set_mode("llm", real_get_bedrock)
    if not summaries:
        return 1

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    payload = {"summaries": summaries, "results": results, "golden": args.golden,
               "index": db.get_setting("index"), "settings": {"provider": s.provider, "llm_model": s.llm_model, "fast_llm_model": s.fast_llm_model}}
    (out / f"eval-{stamp}.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    md = markdown(summaries, results)
    (out / "latest.md").write_text(md, encoding="utf-8")
    print()
    print(md.split("\n## ")[0])
    print(f"wrote {out / f'eval-{stamp}.json'} and {out / 'latest.md'}")
    return 0 if all(s["safety_violations"] == 0 and s["errors"] == 0 for s in summaries) else 1


if __name__ == "__main__":
    sys.exit(main())

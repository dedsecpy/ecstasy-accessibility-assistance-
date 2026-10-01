"""End-to-end smoke test against a running stack: python eval/smoke_api.py [API_URL]

Walks the complaint scenario: baseline answer, trigger lift_stuck, answer flips to NO-GO,
a staff alert fires, then recovery."""
from __future__ import annotations

import json
import sys
import time

import httpx

API = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
V = "riverside_hall"
ASK = {"question": "Can I get to the lecture in my wheelchair?", "event_id": "autumn_lecture",
       "profile": {"mobility": "manual_wheelchair", "needs_assistance": True}}


def lift_status() -> str:
    feats = httpx.get(f"{API}/api/venues/{V}/status", timeout=10).json()["features"]
    return next(f["status"] for f in feats if f["feature"] == "lift")


def ask() -> dict:
    r = httpx.post(f"{API}/api/venues/{V}/ask", json=ASK, timeout=120)
    r.raise_for_status()
    return r.json()


def scenario(name: str) -> None:
    httpx.post(f"{API}/api/sim/scenario", json={"venue_id": V, "scenario": name}, timeout=10).raise_for_status()


def wait_for(pred, timeout=40) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(2)
    return False


def main() -> int:
    ok = True
    print("health:", json.dumps(httpx.get(f"{API}/api/health", timeout=10).json()["ai"]["label"]))
    scenario("normal")
    wait_for(lambda: lift_status() == "ok")
    a = ask()
    print(f"baseline: lift={lift_status()} verdict={a['answer']['verdict']} mode={a['mode']} ({a['latency_ms']} ms)")
    print("  headline:", a["answer"]["headline"])
    n_alerts = len(httpx.get(f"{API}/api/venues/{V}/alerts").json())

    scenario("lift_stuck")
    if not wait_for(lambda: lift_status() == "out_of_service"):
        print("FAIL: lift did not go out of service"); ok = False
    a = ask()
    print(f"lift_stuck: lift={lift_status()} verdict={a['answer']['verdict']}")
    print("  headline:", a["answer"]["headline"])
    ok &= a["answer"]["verdict"] == "no_go"
    alerts = httpx.get(f"{API}/api/venues/{V}/alerts").json()
    print(f"  new alerts: {len(alerts) - n_alerts}; latest: {alerts[0]['message'][:90] if alerts else '-'}")
    ok &= len(alerts) > n_alerts

    ground = {**ASK, "event_id": "history_talk", "question": "Can I get to the history talk?"}
    g = httpx.post(f"{API}/api/venues/{V}/ask", json=ground, timeout=120).json()
    print(f"ground-floor event while lift stuck: verdict={g['answer']['verdict']}")
    ok &= g["answer"]["verdict"] != "no_go"

    scenario("normal")
    wait_for(lambda: lift_status() in ("ok", "verify"))
    print("recovered: lift =", lift_status())
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

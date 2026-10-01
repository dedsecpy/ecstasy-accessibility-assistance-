"""sim-ops: emulates the people side of the venue over the public REST API.

- Facilities team: maintenance log entries (on start, and when a lift scenario fires)
- Front-of-house: a morning staff check
- Visitors: occasional plain-language reports, plus scenario-specific ones
"""
from __future__ import annotations

import logging
import os
import random
import threading
import time
from datetime import datetime, timezone

import httpx

from nimbus_core import topics
from nimbus_core.mqtt import make_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s sim-ops %(message)s")
log = logging.getLogger("sim-ops")

API = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
VENUE = os.getenv("SIM_VENUE", "riverside_hall")
PERIODIC_S = float(os.getenv("SIM_OPS_INTERVAL_S", "240"))
TRIGGER_DELAY_S = float(os.getenv("SIM_OPS_TRIGGER_DELAY_S", "4"))
STARTED = datetime.now(timezone.utc)

BENIGN_REPORTS = [
    ("Came for the gallery this morning. Someone answered the intercom at the side gate straight away and let me in.", "manual wheelchair"),
    ("Accessible toilet on the ground floor was clean and the door was easy to open.", "powered wheelchair"),
    ("Found a chair in the foyer without trouble today.", "walks short distances"),
    ("The ramp is still steep, I needed a push near the top.", "manual wheelchair"),
    ("Lift was working fine, took it up to the Main Hall for a rehearsal.", "mobility scooter"),
]

SCENARIO_POSTS = {
    "lift_stuck": [("maintenance_log", "staff", "Lift stopped between Ground and First floors. Taken out of service, engineer called, no repair time yet.")],
    "lift_door_fault": [("maintenance_log", "staff", "Lift doors not closing on the First floor. Out of order signs placed, engineer called.")],
    "conflict": [("maintenance_log", "staff", "Lift out of service as a precaution pending an engineer inspection.")],
    "scaffolding_narrow": [("staff_note", "staff", "Scaffolding has been moved closer to the courtyard path. Clear width now about 780 mm; larger powered chairs and scooters may not pass.")],
    "gate_locked_after_hours": [("visitor_report", "visitor", "I am at the side gate on Mill Lane. It is locked and nobody has answered the intercom for several minutes.")],
    "seats_full": [("visitor_report", "visitor", "All the chairs in the foyer are taken and there is nowhere to sit while waiting.")],
}
RECOVERY_POSTS = {
    "lift_stuck": ("maintenance_log", "staff", "Engineer attended. Lift repaired, tested on both floors and returned to service."),
    "lift_door_fault": ("maintenance_log", "staff", "Door sensor replaced. Lift tested and returned to service."),
    "conflict": ("maintenance_log", "staff", "Engineer inspection complete. Lift tested and returned to service."),
    "scaffolding_narrow": ("staff_note", "staff", "Scaffolding moved back. Courtyard path clear at full width again."),
}


def wait_for_api() -> None:
    while True:
        try:
            if httpx.get(f"{API}/api/health", timeout=3).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        log.info("waiting for API at %s", API)
        time.sleep(3)


def post_report(kind: str, reporter: str, text: str, needs: str = "") -> None:
    try:
        r = httpx.post(f"{API}/api/venues/{VENUE}/reports", json={"text": text, "reporter": reporter, "kind": kind, "needs": needs}, timeout=10)
        log.info("posted %s (%s): %s", kind, r.status_code, text[:60])
    except httpx.HTTPError as e:
        log.warning("report failed: %s", e)


def post_staff_check() -> None:
    items = [
        {"feature": "lift", "status": "ok", "note": "Morning check: lift called to both floors, doors and alarm tested."},
        {"feature": "side_gate", "status": "locked_on_request", "note": "Side gate locked as usual; intercom routes to the desk."},
        {"feature": "intercom", "status": "ok", "note": "Intercom tested from Mill Lane, answered by the desk."},
    ]
    try:
        r = httpx.post(f"{API}/api/venues/{VENUE}/staff-checks", json={"staff_name": "Front of house (sim)", "items": items}, timeout=10)
        log.info("posted morning staff check (%s)", r.status_code)
    except httpx.HTTPError as e:
        log.warning("staff check failed: %s", e)


def main() -> None:
    wait_for_api()
    post_report("maintenance_log", "staff", "Engineer attended the 26 Sept fault. Levelling sensor replaced; lift tested on both floors and returned to service.")
    post_staff_check()

    state = {"scenario": "normal"}

    def on_control(topic: str, payload: dict) -> None:
        if topics.parse(topic).get("venue") != VENUE:
            return
        try:
            ts = datetime.fromisoformat(payload.get("ts", ""))
        except ValueError:
            ts = STARTED
        if ts < STARTED:
            return  # retained message from before this process started; already handled
        new, old = payload.get("scenario", "normal"), state["scenario"]
        state["scenario"] = new

        def fire() -> None:
            time.sleep(TRIGGER_DELAY_S)
            if new == "normal" and old in RECOVERY_POSTS:
                post_report(*RECOVERY_POSTS[old])
            for kind, reporter, text in SCENARIO_POSTS.get(new, []):
                post_report(kind, reporter, text)

        threading.Thread(target=fire, daemon=True).start()

    client = make_client("sim-ops", on_control, [topics.SUB_CONTROL_ALL])
    client.loop_start()
    while True:
        time.sleep(PERIODIC_S)
        if state["scenario"] == "normal" and random.random() < 0.5:
            text, needs = random.choice(BENIGN_REPORTS)
            post_report("visitor_report", "visitor", text, needs)


if __name__ == "__main__":
    main()

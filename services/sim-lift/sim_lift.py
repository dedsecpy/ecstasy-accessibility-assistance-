"""sim-lift: emulates the NodeMCU (ESP8266) box inside the lift car.

A real unit reads the lift controller's floor/door/fault outputs through an
opto-isolated interface (installed by a certified lift contractor) and publishes
the same JSON over MQTT. Telemetry doubles as the heartbeat: if it stops, the
fusion engine marks the sensor offline after SENSOR_TTL_S.
"""
from __future__ import annotations

import json
import logging
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path

from nimbus_core import topics
from nimbus_core.mqtt import make_client, publish_json

logging.basicConfig(level=logging.INFO, format="%(asctime)s sim-lift %(message)s")
log = logging.getLogger("sim-lift")

INTERVAL = float(os.getenv("SIM_INTERVAL_S", "30"))
DATA_DIR = Path(os.getenv("NIMBUS_DATA_DIR", "/app/data"))


def load_lifts() -> list[tuple[str, str]]:
    out = []
    for vj in sorted((DATA_DIR / "venues").glob("*/venue.json")):
        cfg = json.loads(vj.read_text(encoding="utf-8"))
        for lift in cfg.get("devices", {}).get("lifts", []):
            out.append((cfg["id"], lift["id"]))
    return out


class LiftModel:
    def __init__(self, venue: str, lift_id: str):
        self.venue, self.lift_id = venue, lift_id
        self.scenario = "normal"
        self.floor = 0
        self.target = 0
        self.moving = False
        self.door = "closed"
        self.seq = 0
        self.boot = time.time()

    def step(self) -> dict | None:
        if self.scenario == "sensor_offline":
            return None
        self.seq += 1
        fault = None
        power = "on"
        if self.scenario == "lift_stuck":
            self.moving, self.door, floor = False, "closed", 0.5
            fault = "E21_STOPPED_BETWEEN_FLOORS"
        elif self.scenario == "lift_door_fault":
            self.moving, self.door, floor = False, "fault", self.floor
            fault = "E07_DOOR_NOT_CLOSING"
        else:
            # Normal service: random calls between Ground (0) and First (1).
            if self.moving:
                self.floor, self.moving, self.door = self.target, False, "open"
            elif self.door == "open":
                self.door = "closed"
            elif random.random() < 0.5:
                self.target = 1 - self.floor
                self.moving = True
            floor = self.floor
        return {
            "lift_id": self.lift_id,
            "floor": floor,
            "moving": self.moving,
            "door": self.door,
            "power": power,
            "fault_code": fault,
            "seq": self.seq,
            "uptime_s": int(time.time() - self.boot),
            "rssi_dbm": random.randint(-72, -55),
            "ts": datetime.now(timezone.utc).isoformat(),
        }


def main() -> None:
    lifts = {(v, lid): LiftModel(v, lid) for v, lid in load_lifts()}
    log.info("simulating %d lift(s), every %.0fs", len(lifts), INTERVAL)

    def on_control(topic: str, payload: dict) -> None:
        venue = topics.parse(topic).get("venue")
        sc = payload.get("scenario", "normal")
        for (v, _), m in lifts.items():
            if v == venue:
                m.scenario = sc if sc in topics.SCENARIOS else "normal"
                log.info("%s scenario -> %s", venue, m.scenario)

    client = make_client("sim-lift", on_control, [topics.SUB_CONTROL_ALL])
    client.loop_start()
    while True:
        for (venue, lid), model in lifts.items():
            msg = model.step()
            if msg is not None:
                publish_json(client, topics.lift_telemetry(venue, lid), msg)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()

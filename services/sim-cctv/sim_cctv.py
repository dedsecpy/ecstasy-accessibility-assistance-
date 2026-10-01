"""sim-cctv: emulates edge computer-vision boxes attached to existing CCTV cameras.

The real edge box runs a detector (gate state, path clear width, free seats) next to
the camera and publishes LABELS ONLY. No images or faces ever leave the box.
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s sim-cctv %(message)s")
log = logging.getLogger("sim-cctv")

INTERVAL = float(os.getenv("SIM_INTERVAL_S", "30"))
DATA_DIR = Path(os.getenv("NIMBUS_DATA_DIR", "/app/data"))
SEATS_TOTAL = 4


def load_cameras() -> list[tuple[str, dict]]:
    out = []
    for vj in sorted((DATA_DIR / "venues").glob("*/venue.json")):
        cfg = json.loads(vj.read_text(encoding="utf-8"))
        for cam in cfg.get("devices", {}).get("cameras", []):
            out.append((cfg["id"], cam))
    return out


class CameraModel:
    def __init__(self, venue: str, cam: dict):
        self.venue, self.cam = venue, cam
        self.scenario = "normal"
        self.seats_free = 3
        self.wait_started: float | None = None

    def detect(self) -> dict:
        base = {
            "camera_id": self.cam["id"],
            "feature": self.cam["feature"],
            "model": "edge-cv-sim-1.0",
            "gate_open": None,
            "person_waiting_s": None,
            "staff_present": None,
            "path_clear_width_mm": None,
            "obstruction": None,
            "seats_free": None,
            "seats_total": None,
            "crowd_level": None,
            "confidence": round(random.uniform(0.86, 0.97), 2),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        f = self.cam["feature"]
        if f == "side_gate":
            if self.scenario == "gate_locked_after_hours":
                if self.wait_started is None:
                    self.wait_started = time.time() - 150  # visitor already waiting when the camera flags it
                base.update(gate_open=False, person_waiting_s=int(time.time() - self.wait_started), staff_present=False)
            else:
                self.wait_started = None
                base.update(gate_open=False, person_waiting_s=0, staff_present=random.random() < 0.3)
        elif f == "courtyard_path":
            if self.scenario == "scaffolding_narrow":
                base.update(path_clear_width_mm=random.randint(760, 800), obstruction="scaffolding")
            else:
                base.update(path_clear_width_mm=random.randint(1450, 1550), obstruction=None)
        elif f == "seating":
            if self.scenario == "seats_full":
                self.seats_free = 0
                crowd = "high"
            else:
                self.seats_free = max(1, min(SEATS_TOTAL, self.seats_free + random.choice([-1, 0, 0, 1])))
                crowd = "low" if self.seats_free >= 3 else "medium"
            base.update(seats_free=self.seats_free, seats_total=SEATS_TOTAL, crowd_level=crowd)
        return base


def main() -> None:
    cams = [CameraModel(v, c) for v, c in load_cameras()]
    log.info("simulating %d camera(s), every %.0fs", len(cams), INTERVAL)

    def on_control(topic: str, payload: dict) -> None:
        venue = topics.parse(topic).get("venue")
        sc = payload.get("scenario", "normal")
        for m in cams:
            if m.venue == venue:
                m.scenario = sc if sc in topics.SCENARIOS else "normal"
        log.info("%s scenario -> %s", venue, sc)

    client = make_client("sim-cctv", on_control, [topics.SUB_CONTROL_ALL])
    client.loop_start()
    while True:
        for m in cams:
            publish_json(client, topics.cctv_detections(m.venue, m.cam["id"]), m.detect())
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()

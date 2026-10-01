"""MQTT topic layout shared by the simulators (publishers) and the worker (subscriber)."""
from __future__ import annotations

SCENARIOS = {
    "normal": "Everything working",
    "lift_stuck": "Lift stops between floors",
    "lift_door_fault": "Lift doors fail to close",
    "sensor_offline": "Lift sensor goes silent",
    "gate_locked_after_hours": "Side gate locked, nobody answering",
    "scaffolding_narrow": "Scaffolding narrows the courtyard path",
    "seats_full": "All foyer seats taken",
    "conflict": "Sensor says running, maintenance log says out of service",
}


def lift_telemetry(venue: str, lift_id: str) -> str:
    return f"nimbus/{venue}/lift/{lift_id}/telemetry"


def cctv_detections(venue: str, camera_id: str) -> str:
    return f"nimbus/{venue}/cctv/{camera_id}/detections"


def control(venue: str) -> str:
    return f"nimbus/{venue}/control/scenario"


SUB_LIFT = "nimbus/+/lift/+/telemetry"
SUB_CCTV = "nimbus/+/cctv/+/detections"
SUB_CONTROL_ALL = "nimbus/+/control/scenario"


def parse(topic: str) -> dict[str, str]:
    parts = topic.split("/")
    if len(parts) == 5 and parts[0] == "nimbus":
        return {"venue": parts[1], "kind": parts[2], "device": parts[3], "stream": parts[4]}
    if len(parts) == 4 and parts[0] == "nimbus":
        return {"venue": parts[1], "kind": parts[2], "stream": parts[3]}
    return {}

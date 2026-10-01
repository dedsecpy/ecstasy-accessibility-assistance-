from worker.translate import cctv_to_obs, lift_telemetry_to_obs


def test_lift_normal_and_faults():
    assert lift_telemetry_to_obs("l1", {"floor": 1, "door": "closed", "power": "on", "fault_code": None}).status == "ok"
    assert lift_telemetry_to_obs("l1", {"floor": 0.5, "fault_code": "E21_STOPPED_BETWEEN_FLOORS"}).status == "out_of_service"
    assert lift_telemetry_to_obs("l1", {"door": "fault", "fault_code": "E07_DOOR_NOT_CLOSING"}).status == "out_of_service"
    assert lift_telemetry_to_obs("l1", {"power": "off"}).status == "out_of_service"


def test_gate_detection():
    base = {"feature": "side_gate", "confidence": 0.9}
    assert cctv_to_obs("g", {**base, "gate_open": True}).status == "ok"
    assert cctv_to_obs("g", {**base, "gate_open": False, "person_waiting_s": 0}).status == "locked_on_request"
    assert cctv_to_obs("g", {**base, "gate_open": False, "person_waiting_s": 300, "staff_present": False}).status == "locked_unanswered"


def test_path_width_thresholds():
    base = {"feature": "courtyard_path"}
    assert cctv_to_obs("c", {**base, "path_clear_width_mm": 1500}).status == "ok"
    assert cctv_to_obs("c", {**base, "path_clear_width_mm": 790, "obstruction": "scaffolding"}).status == "degraded"
    assert cctv_to_obs("c", {**base, "path_clear_width_mm": 600}).status == "out_of_service"


def test_seats():
    assert cctv_to_obs("f", {"feature": "seating", "seats_free": 0, "seats_total": 4}).status == "degraded"
    assert cctv_to_obs("f", {"feature": "seating", "seats_free": 2, "seats_total": 4}).status == "ok"

"""Unit tests for the safety-critical fusion rules. Run: pytest services/worker/tests"""
from datetime import datetime, timedelta, timezone

from nimbus_core.fusion import Observation, derive_alerts, fuse_feature, source_rules

NOW = datetime(2026, 10, 8, 18, 0, tzinfo=timezone.utc)
RULES = source_rules(sensor_ttl_s=90, cctv_ttl_s=300)


def obs(feature, status, kind, age_s, note="", conf=None):
    return Observation(feature, status, kind, NOW - timedelta(seconds=age_s), note, conf)


def fuse(*o, feature="lift"):
    return fuse_feature(feature, list(o), NOW, RULES)


def test_live_sensor_beats_older_human_record():
    st = fuse(obs("lift", "ok", "maintenance_log", 3 * 86400), obs("lift", "out_of_service", "sensor", 10))
    assert st.status == "out_of_service" and st.source_kind == "sensor" and not st.conflict


def test_sensor_fault_is_never_argued_away_by_older_ok_log():
    st = fuse(obs("lift", "ok", "staff", 3600), obs("lift", "out_of_service", "sensor", 5))
    assert st.status == "out_of_service" and not st.conflict


def test_sensor_ok_but_log_says_out_of_service_is_verify():
    st = fuse(obs("lift", "out_of_service", "maintenance_log", 3600), obs("lift", "ok", "sensor", 5))
    assert st.status == "verify" and st.conflict


def test_weak_visitor_report_does_not_create_conflict():
    st = fuse(obs("lift", "out_of_service", "report", 3600), obs("lift", "ok", "sensor", 5))
    assert st.status == "ok" and not st.conflict


def test_silent_sensor_falls_back_and_never_assumes_working():
    st = fuse(obs("lift", "ok", "sensor", 600), obs("lift", "ok", "staff", 3600))
    assert st.sensor_offline
    assert st.status == "unknown"
    assert st.source_kind == "staff"


def test_silent_sensor_falls_back_to_blocking_record():
    st = fuse(obs("lift", "ok", "sensor", 600), obs("lift", "out_of_service", "maintenance_log", 86400))
    assert st.sensor_offline and st.status == "out_of_service"


def test_freshest_human_source_wins_without_machine():
    st = fuse(obs("lift", "out_of_service", "maintenance_log", 2 * 86400), obs("lift", "ok", "staff", 3600))
    assert st.status == "ok" and st.source_kind == "staff"


def test_everything_expired_uses_latest_and_marks_stale():
    st = fuse(obs("lift", "ok", "maintenance_log", 20 * 86400), obs("lift", "out_of_service", "report", 10 * 86400))
    assert st.stale and st.status == "out_of_service"
    assert st.confidence < 0.5


def test_permanent_audit_fact_never_expires():
    st = fuse(obs("main_entrance", "not_step_free", "audit", 400 * 86400), feature="main_entrance")
    assert st.status == "not_step_free" and not st.stale


def test_camera_gate_reading_beats_old_report():
    st = fuse(obs("side_gate", "locked_unanswered", "report", 3600), obs("side_gate", "locked_on_request", "cctv", 20),
              feature="side_gate")
    assert st.status == "locked_on_request" and st.source_kind == "cctv"


def test_expired_camera_falls_back_to_staff_note():
    st = fuse(obs("courtyard_path", "ok", "cctv", 900), obs("courtyard_path", "degraded", "staff", 86400, "800 mm"),
              feature="courtyard_path")
    assert st.status == "degraded" and st.source_kind == "staff"


def test_alerts_fire_on_transitions_only():
    ok = fuse(obs("lift", "ok", "sensor", 5))
    down = fuse(obs("lift", "out_of_service", "sensor", 5))
    kinds = [a.kind for a in derive_alerts(ok, down)]
    assert kinds == ["blocking"]
    assert derive_alerts(down, down) == []
    assert [a.kind for a in derive_alerts(down, ok)] == ["resolved"]


def test_fresh_reading_with_same_status_counts_as_change():
    from nimbus_core.fusion import state_changed

    a = fuse(obs("lift", "ok", "sensor", 10))
    b = fuse(obs("lift", "ok", "sensor", 5))
    assert state_changed(a, b)
    assert not state_changed(b, b)


def test_conflict_and_offline_alerts():
    ok = fuse(obs("lift", "ok", "sensor", 5))
    conflict = fuse(obs("lift", "out_of_service", "maintenance_log", 3600), obs("lift", "ok", "sensor", 5))
    assert "conflict" in [a.kind for a in derive_alerts(ok, conflict)]
    offline = fuse(obs("lift", "ok", "sensor", 600), obs("lift", "ok", "staff", 3600))
    assert "sensor_offline" in [a.kind for a in derive_alerts(ok, offline)]

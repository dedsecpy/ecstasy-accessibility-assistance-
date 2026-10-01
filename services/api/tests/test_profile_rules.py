"""Travel-profile questionnaire answers change which features are required and how they are judged."""
from app.rag.rules import assess, required_features
from nimbus_core.fusion import FusedState
from nimbus_core.schemas import Profile
from nimbus_core.visit import VisitContext


def visit(needs_lift: bool = False) -> VisitContext:
    return VisitContext(destination="Courtyard", floor=0, needs_lift=needs_lift, visit_at=None, staffed=True,
                        staffed_window="10:00-17:00", prebook_possible=True, hours_until_visit=1.0,
                        event_name=None, phone="0100 000 000")


def state(feature: str, status: str, note: str = "note") -> FusedState:
    return FusedState(feature=feature, status=status, confidence=0.9, source_kind="audit", note=note,
                      observed_at="2026-10-01T10:00:00+00:00", age_s=60)


def codes(profile: Profile, states: dict[str, FusedState]) -> dict[str, str]:
    return {f.code: f.severity for f in assess(profile, visit(), states).findings}


def test_defaults_require_nothing_new():
    req, _ = required_features(Profile(), visit())
    assert not {"hearing_loop", "toilet", "parking"} & set(req)


def test_questionnaire_adds_required_features():
    p = Profile(hearing_support=True, needs_toilet=True, arrival="blue_badge", walk_range="short")
    req, _ = required_features(p, visit())
    assert {"hearing_loop", "toilet", "parking", "seating"} <= set(req)


def test_untested_loop_is_caution_for_hearing_aid_users_only():
    states = {"hearing_loop": state("hearing_loop", "unknown")}
    assert codes(Profile(hearing_support=True), states).get("loop_untested") == "caution"
    assert "loop_untested" not in codes(Profile(), states)


def test_toilet_out_of_order_is_caution():
    states = {"toilet": state("toilet", "out_of_service")}
    assert codes(Profile(needs_toilet=True), states).get("toilet_out") == "caution"


def test_far_parking_is_caution_for_short_range_drivers():
    states = {"parking": state("parking", "degraded", "~120 m from Side Gate")}
    assert codes(Profile(arrival="blue_badge", walk_range="short"), states).get("parking_far_short_range") == "caution"
    assert codes(Profile(arrival="car"), states).get("parking_far") == "info"


def test_wide_chair_width_counts_as_wide():
    states = {"courtyard_path": state("courtyard_path", "degraded", "narrowed to ~800 mm")}
    assert codes(Profile(mobility="manual_wheelchair", chair_width_mm=740), states).get("path_narrow") == "caution"
    assert "path_narrow" not in codes(Profile(mobility="manual_wheelchair"), states)


def test_describe_mentions_questionnaire():
    text = Profile(hearing_support=True, arrival="taxi", steps="none", companion=True).describe()
    assert "hearing loop" in text and "taxi" in text and "steps" in text and "companion" in text

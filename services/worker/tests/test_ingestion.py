import json
from pathlib import Path

from nimbus_core.chunking import chunk_venue_dir
from nimbus_core.extraction import rule_extract

VENUE = Path(__file__).resolve().parents[3] / "data" / "venues" / "riverside_hall"


def test_chunks_have_context_headers_and_dates():
    cfg = json.loads((VENUE / "venue.json").read_text(encoding="utf-8"))
    docs = chunk_venue_dir(VENUE, cfg)
    chunks = [c for _, _, cs in docs for c in cs]
    assert len(chunks) > 10
    lift = [c for c in chunks if c.doc_id == "lift_log"]
    assert any(c.date.isoformat() == "2026-09-26" for c in lift)
    c = lift[-1]
    assert c.header.startswith("Riverside Hall | ") and "Maintenance log" in c.header
    m = c.meta()
    assert m["f_lift"] is True and m["date_int"] == int(c.date.strftime("%Y%m%d"))
    assert len({c.id for c in chunks}) == len(chunks)


def test_rule_extraction_examples():
    f = {x["feature"]: x["status"] for x in rule_extract(
        "I am at the side gate on Mill Lane. It is locked and nobody has answered the intercom for several minutes.")}
    assert f["side_gate"] == "locked_unanswered" and "intercom" not in f
    f = {x["feature"]: x["status"] for x in rule_extract(
        "Engineer attended. Lift repaired, tested on both floors and returned to service.")}
    assert f["lift"] == "ok"
    f = {x["feature"]: x["status"] for x in rule_extract(
        "Lift stopped between Ground and First floors. Taken out of service, engineer called.")}
    assert f["lift"] == "out_of_service"
    f = {x["feature"]: x["status"] for x in rule_extract("Scaffolding moved back. Courtyard path clear at full width again.")}
    assert f["courtyard_path"] == "ok"

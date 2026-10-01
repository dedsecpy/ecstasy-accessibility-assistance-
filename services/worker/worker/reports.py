"""Process a submitted text report: extract facts -> observations, and index the text for RAG."""
from __future__ import annotations

import logging

from nimbus_core import db
from nimbus_core.chunking import report_chunk
from nimbus_core.extraction import extract_facts
from nimbus_core.visit import venue_tz

from .ingest import Indexer

log = logging.getLogger("worker.reports")

KIND_TO_SOURCE = {"visitor_report": "report", "staff_note": "staff", "maintenance_log": "maintenance_log"}


def process_report(row: dict, indexer: Indexer) -> None:
    rid, vid, kind = row["id"], row["venue_id"], row["kind"]
    try:
        cfg = db.get_venue(vid) or {"id": vid, "name": vid}
        when = row["submitted_at"].astimezone(venue_tz(cfg))
        facts, summary, mode, err = extract_facts(row["text"], kind, row.get("needs", ""), when.date().isoformat())
        source_kind = KIND_TO_SOURCE.get(kind, "report")
        for f in facts:
            # Staff and maintenance entries carry the source's own trust; visitor reports keep the model's confidence.
            conf = f.get("confidence") if source_kind == "report" else None
            db.insert_observation(vid, f["feature"], f["status"], source_kind, f.get("note", ""),
                                  {"report_id": rid, "extraction": mode}, conf, f"report:{rid}", row["submitted_at"])
        chunk = report_chunk(vid, cfg.get("name", vid), f"{vid}:report:{rid}", kind, row["text"], when.date(), row.get("needs", ""))
        indexer.index_chunks([chunk])
        result = {"facts": facts, "summary": summary or f"{len(facts)} fact(s) extracted.", "mode": mode, "error": err, "chunk_id": chunk.id}
        db.finish_report(rid, "done", result)
        db.notify({"type": "report_processed", "venue_id": vid, "id": rid, "facts": len(facts), "mode": mode})
        log.info("report %s (%s): %d fact(s) via %s", rid, kind, len(facts), mode)
    except Exception as e:  # noqa: BLE001
        log.exception("report %s failed", rid)
        db.finish_report(rid, "error", None, str(e)[:500])

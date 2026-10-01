"""Load venues from data/venues/*/venue.json and seed historical observations from facts.jsonl."""
from __future__ import annotations

import json
import logging
from datetime import datetime, time
from pathlib import Path
from typing import Any

from nimbus_core import db
from nimbus_core.config import get_settings
from nimbus_core.features import FEATURES, SOURCE_TYPE_TO_KIND
from nimbus_core.visit import venue_tz

log = logging.getLogger("worker.seed")


def venue_dirs() -> list[Path]:
    root = get_settings().data_dir / "venues"
    return sorted(p for p in root.iterdir() if (p / "venue.json").exists())


def load_config(venue_dir: Path) -> dict[str, Any]:
    return json.loads((venue_dir / "venue.json").read_text(encoding="utf-8"))


def seed_venue(venue_dir: Path) -> dict[str, Any]:
    cfg = load_config(venue_dir)
    db.upsert_venue(cfg)
    vid = cfg["id"]
    if db.has_observations(vid, "seed:"):
        return cfg
    tz = venue_tz(cfg)
    facts = venue_dir / "facts.jsonl"
    n = 0
    if facts.exists():
        for i, line in enumerate(facts.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            f = json.loads(line)
            if f.get("feature") not in FEATURES:
                continue
            kind = SOURCE_TYPE_TO_KIND.get(f.get("source_type", ""), "report")
            observed = datetime.combine(datetime.fromisoformat(f["date"][:10]).date(), time(9, 0), tzinfo=tz)
            db.insert_observation(vid, f["feature"], f.get("status", "unknown"), kind, f.get("note", ""),
                                  {"source": f.get("source", "")}, f.get("confidence"), f"seed:facts:{i}", observed)
            n += 1
    log.info("seeded %d historical observations for %s", n, vid)
    return cfg

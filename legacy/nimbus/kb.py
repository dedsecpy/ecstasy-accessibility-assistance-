"""Knowledge base: load venue documents into dated, typed chunks."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
HEADING_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\s*[—-]\s*(.*)$")

SOURCE_TYPE_LABELS = {
    "listing": "Public listing",
    "audit": "Access audit",
    "maintenance_log": "Maintenance log",
    "staff_note": "Staff note",
    "policy": "Visitor services",
    "events": "Event programme",
    "visitor_report": "Visitor report",
}

# Source types whose content describes a state that changes over time.
TIME_SENSITIVE_TYPES = {"maintenance_log", "staff_note", "visitor_report"}


@dataclass
class Chunk:
    id: str
    venue: str
    doc_title: str
    source_type: str
    date: date
    trust: str
    heading: str
    text: str
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return SOURCE_TYPE_LABELS.get(self.source_type, self.source_type)

    def age_days(self, today: date) -> int:
        return (today - self.date).days

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["date"] = self.date.isoformat()
        return d


def _parse_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    m = FRONTMATTER_RE.match(raw)
    if not m:
        return {}, raw
    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, raw[m.end():]


def _parse_date(s: str | None, fallback: date) -> date:
    if not s:
        return fallback
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return fallback


def _split_sections(body: str) -> list[tuple[str, str]]:
    """Split markdown body on '## ' headings. Returns (heading, text) pairs."""
    sections: list[tuple[str, str]] = []
    current_heading = ""
    buf: list[str] = []
    for line in body.splitlines():
        if line.startswith("## "):
            if buf and "".join(buf).strip():
                sections.append((current_heading, "\n".join(buf).strip()))
            current_heading = line[3:].strip()
            buf = []
        elif line.startswith("# "):
            continue
        else:
            buf.append(line)
    if buf and "".join(buf).strip():
        sections.append((current_heading, "\n".join(buf).strip()))
    return sections


def load_markdown_doc(path: Path, venue: str) -> list[Chunk]:
    raw = path.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(raw)
    doc_date = _parse_date(meta.get("date"), date.today())
    title = meta.get("title", path.stem)
    source_type = meta.get("source_type", "document")
    trust = meta.get("trust", "medium")
    chunks: list[Chunk] = []
    for i, (heading, text) in enumerate(_split_sections(body)):
        chunk_date = doc_date
        clean_heading = heading
        m = HEADING_DATE_RE.match(heading)
        if m:
            chunk_date = _parse_date(m.group(1), doc_date)
            clean_heading = m.group(2).strip() or heading
        chunks.append(
            Chunk(
                id=f"{path.stem}#{i}",
                venue=venue,
                doc_title=title,
                source_type=source_type,
                date=chunk_date,
                trust=trust,
                heading=clean_heading,
                text=text,
                meta={"author": meta.get("author", "")},
            )
        )
    return chunks


def load_reports(path: Path, venue: str, prefix: str) -> list[Chunk]:
    if not path.exists():
        return []
    chunks: list[Chunk] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        d = _parse_date(rec.get("date"), date.today())
        reporter = rec.get("reporter", "visitor")
        needs = rec.get("needs", "")
        heading = f"{reporter.capitalize()} report" + (f" ({needs})" if needs else "")
        chunks.append(
            Chunk(
                id=f"{prefix}#{i}",
                venue=venue,
                doc_title="Visitor and staff reports",
                source_type="staff_note" if reporter == "staff" else "visitor_report",
                date=d,
                trust="medium" if reporter == "staff" else "low",
                heading=heading,
                text=rec.get("text", ""),
                meta={"reporter": reporter, "needs": needs},
            )
        )
    return chunks


class VenueKB:
    """All knowledge for one venue: config, chunks, and dated facts."""

    def __init__(self, venue_dir: Path):
        self.dir = Path(venue_dir)
        self.config: dict[str, Any] = json.loads((self.dir / "venue.json").read_text(encoding="utf-8"))
        self.id: str = self.config["id"]
        self.name: str = self.config["name"]
        self.reload()

    # Files that hold user-submitted content during a session.
    @property
    def live_reports_path(self) -> Path:
        return self.dir / "live_reports.jsonl"

    @property
    def live_facts_path(self) -> Path:
        return self.dir / "live_facts.jsonl"

    def reload(self) -> None:
        chunks: list[Chunk] = []
        for md in sorted(self.dir.glob("*.md")):
            chunks.extend(load_markdown_doc(md, self.id))
        chunks.extend(load_reports(self.dir / "visitor_reports.jsonl", self.id, "visitor_reports"))
        chunks.extend(load_reports(self.live_reports_path, self.id, "live_reports"))
        self.chunks = chunks
        self.by_id = {c.id: c for c in chunks}

        facts: list[dict[str, Any]] = []
        for p in (self.dir / "facts.jsonl", self.live_facts_path):
            if p.exists():
                for line in p.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        facts.append(json.loads(line))
        self.facts = facts

    def append_report(self, text: str, reporter: str, needs: str, when: date) -> Chunk:
        rec = {"date": when.isoformat(), "reporter": reporter, "needs": needs, "text": text,
               "submitted_at": datetime.now().isoformat(timespec="seconds")}
        with self.live_reports_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        self.reload()
        return self.chunks[-1]

    def append_facts(self, facts: list[dict[str, Any]]) -> None:
        if not facts:
            return
        with self.live_facts_path.open("a", encoding="utf-8") as f:
            for fact in facts:
                f.write(json.dumps(fact) + "\n")
        self.reload()

    def reset_live_data(self) -> None:
        for p in (self.live_reports_path, self.live_facts_path):
            if p.exists():
                p.unlink()
        self.reload()

    def listing_chunks(self) -> list[Chunk]:
        return [c for c in self.chunks if c.source_type == "listing"]


def discover_venues(data_dir: Path) -> list[Path]:
    return sorted(p for p in (data_dir / "venues").iterdir() if (p / "venue.json").exists())

"""Contextual chunking: venue documents -> dated, typed chunks with a context header.

Each chunk is embedded as "<header>\\n<text>", where the header is
`venue | document title | section | date | source type`. Short sections such as
"Lift" then still carry enough context to be retrieved for the right venue and era.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from .features import FEATURES, SOURCE_TYPE_LABELS

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
HEADING_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\s*(?:\u2014|-|\u2013)\s*(.*)$")
MAX_CHARS = 1200
WINDOW_CHARS = 900


@dataclass
class ChunkRecord:
    id: str
    venue_id: str
    doc_id: str
    doc_title: str
    source_type: str
    trust: str
    date: date
    heading: str
    text: str
    venue_name: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def header(self) -> str:
        label = SOURCE_TYPE_LABELS.get(self.source_type, self.source_type)
        return f"{self.venue_name or self.venue_id} | {self.doc_title} | {self.heading or 'General'} | {self.date.isoformat()} | {label}"

    @property
    def embed_text(self) -> str:
        return f"{self.header}\n{self.text}"

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.embed_text.encode("utf-8")).hexdigest()

    def meta(self) -> dict[str, Any]:
        blob = f"{self.heading} {self.text}".lower()
        m: dict[str, Any] = {
            "venue_id": self.venue_id,
            "doc_id": self.doc_id,
            "doc_title": self.doc_title,
            "source_type": self.source_type,
            "trust": self.trust,
            "date": self.date.isoformat(),
            "date_int": int(self.date.strftime("%Y%m%d")),
            "heading": self.heading,
        }
        for fid, feat in FEATURES.items():
            m[f"f_{fid}"] = any(re.search(r"\b" + re.escape(k) + r"s?\b", blob) for k in feat.keywords)
        m.update({k: v for k, v in self.extra.items() if isinstance(v, (str, int, float, bool))})
        return m


def _frontmatter(raw: str) -> tuple[dict[str, str], str]:
    m = FRONTMATTER_RE.match(raw)
    if not m:
        return {}, raw
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, raw[m.end():]


def _date(s: str | None, fallback: date) -> date:
    try:
        return date.fromisoformat((s or "")[:10])
    except ValueError:
        return fallback


def _sections(body: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    heading, buf = "", []
    for line in body.splitlines():
        if line.startswith("## "):
            if "".join(buf).strip():
                out.append((heading, "\n".join(buf).strip()))
            heading, buf = line[3:].strip(), []
        elif line.startswith("# "):
            continue
        else:
            buf.append(line)
    if "".join(buf).strip():
        out.append((heading, "\n".join(buf).strip()))
    return out


def _windows(text: str) -> list[str]:
    if len(text) <= MAX_CHARS:
        return [text]
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out, cur = [], ""
    for p in paras:
        if cur and len(cur) + len(p) > WINDOW_CHARS:
            out.append(cur)
            cur = cur.split("\n\n")[-1] if len(cur.split("\n\n")[-1]) < 300 else ""  # small overlap
        cur = f"{cur}\n\n{p}".strip()
    if cur:
        out.append(cur)
    return out


def chunk_markdown(path: Path, venue_id: str, venue_name: str) -> tuple[dict[str, str], list[ChunkRecord]]:
    raw = path.read_text(encoding="utf-8")
    meta, body = _frontmatter(raw)
    doc_date = _date(meta.get("date"), date.today())
    title = meta.get("title", path.stem).replace("\u2014", "-")
    stype = meta.get("source_type", "document")
    trust = meta.get("trust", "medium")
    chunks: list[ChunkRecord] = []
    for i, (heading, text) in enumerate(_sections(body)):
        cdate, clean = doc_date, heading
        m = HEADING_DATE_RE.match(heading)
        if m:
            cdate, clean = _date(m.group(1), doc_date), (m.group(2).strip() or heading)
        for j, win in enumerate(_windows(text)):
            cid = f"{venue_id}:{path.stem}#{i}" + (f".{j}" if j else "")
            chunks.append(ChunkRecord(cid, venue_id, path.stem, title, stype, trust, cdate, clean, win, venue_name))
    return {"title": title, "source_type": stype, "trust": trust, "date": doc_date.isoformat()}, chunks


def report_chunk(venue_id: str, venue_name: str, chunk_id: str, kind: str, text: str, when: date, needs: str = "") -> ChunkRecord:
    titles = {"maintenance_log": "Lift maintenance log (live entries)", "staff_note": "Staff notes (live entries)",
              "visitor_report": "Visitor reports"}
    trust = {"maintenance_log": "high", "staff_note": "medium", "visitor_report": "low"}.get(kind, "low")
    heading = {"maintenance_log": "Maintenance entry", "staff_note": "Staff note"}.get(kind, "Visitor report" + (f" ({needs})" if needs else ""))
    return ChunkRecord(chunk_id, venue_id, f"live_{kind}", titles.get(kind, "Reports"), kind, trust, when, heading, text, venue_name,
                       {"needs": needs})


def chunk_report_file(path: Path, venue_id: str, venue_name: str) -> list[ChunkRecord]:
    out = []
    if not path.exists():
        return out
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        rec = json.loads(line)
        kind = "staff_note" if rec.get("reporter") == "staff" else "visitor_report"
        c = report_chunk(venue_id, venue_name, f"{venue_id}:{path.stem}#{i}", kind, rec.get("text", ""),
                         _date(rec.get("date"), date.today()), rec.get("needs", ""))
        c.doc_id = path.stem
        out.append(c)
    return out


def chunk_venue_dir(venue_dir: Path, config: dict[str, Any]) -> list[tuple[str, dict[str, str], list[ChunkRecord]]]:
    """Returns (doc_id, doc_meta, chunks) per document."""
    vid, name = config["id"], config.get("name", config["id"])
    docs = []
    for md in sorted(venue_dir.glob("*.md")):
        meta, chunks = chunk_markdown(md, vid, name)
        docs.append((md.stem, meta, chunks))
    rep = venue_dir / "visitor_reports.jsonl"
    if rep.exists():
        docs.append((rep.stem, {"title": "Visitor reports", "source_type": "visitor_report", "trust": "low", "date": ""},
                     chunk_report_file(rep, vid, name)))
    return docs

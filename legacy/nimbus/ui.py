"""Shared Streamlit helpers: cached resources, demo clock, status board rendering."""
from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from .features import FEATURES, FeatureStatus, latest_statuses
from .kb import VenueKB, discover_venues
from .llm import LLMClient
from .retriever import Hit

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT.parent / "data"

load_dotenv(ROOT / ".env")


@st.cache_resource
def get_kb(venue_id: str) -> VenueKB:
    for p in discover_venues(DATA_DIR):
        if p.name == venue_id:
            return VenueKB(p)
    raise FileNotFoundError(venue_id)


@st.cache_resource
def get_llm() -> LLMClient:
    return LLMClient()


def venue_ids() -> list[str]:
    return [p.name for p in discover_venues(DATA_DIR)]


def init_state() -> None:
    st.session_state.setdefault("venue_id", venue_ids()[0])
    st.session_state.setdefault("demo_date", date.today())
    st.session_state.setdefault("demo_time", time(hour=datetime.now().hour, minute=0))
    st.session_state.setdefault("last_answer", None)
    st.session_state.setdefault("last_ingest", None)
    st.session_state.setdefault("report_text", "")
    st.session_state.setdefault("report_needs", "")


def demo_now() -> datetime:
    return datetime.combine(st.session_state.demo_date, st.session_state.demo_time)


def sidebar() -> None:
    kb = get_kb(st.session_state.venue_id)
    llm = get_llm()
    with st.sidebar:
        st.subheader("Nimbus", icon=":material/accessible_forward:")
        st.caption("Accessible until the last staircase")
        st.selectbox("Venue", venue_ids(), key="venue_id", format_func=lambda v: get_kb(v).name)

        st.markdown("**Demo clock**")
        st.caption("Freshness warnings are computed relative to this date.")
        st.date_input("Today", key="demo_date")
        st.time_input("Time now", key="demo_time", step=1800)

        st.markdown("**AI backend**")
        if llm.available:
            st.badge(llm.config.describe, icon=":material/smart_toy:", color="green")
        else:
            st.badge("Rule-based fallback", icon=":material/rule:", color="orange")
            st.caption(
                "No LLM key found. Set `NIMBUS_LLM_API_KEY` (and optionally `NIMBUS_LLM_BASE_URL`, "
                "`NIMBUS_LLM_MODEL`) in `.env` to enable grounded LLM answers. Retrieval, the status "
                "board, and listing audit work without it."
            )

        st.markdown("**Knowledge base**")
        st.caption(f"{len(kb.chunks)} passages across {len({c.doc_title for c in kb.chunks})} documents; {len(kb.facts)} dated facts.")
        if kb.live_reports_path.exists() or kb.live_facts_path.exists():
            if st.button("Reset demo data", icon=":material/restart_alt:", help="Remove reports and facts added during this session."):
                kb.reset_live_data()
                st.session_state.last_answer = None
                st.session_state.last_ingest = None
                st.toast("Live reports and facts cleared.")
                st.rerun()


def status_frame(statuses: dict[str, FeatureStatus]) -> pd.DataFrame:
    rows = []
    for fid in FEATURES:
        s = statuses.get(fid)
        if not s:
            continue
        rows.append(
            {
                "Feature": s.feature.label,
                "Status": s.status_label,
                "Last confirmed": s.date,
                "Age (days)": s.age_days,
                "Stale": s.stale,
                "Latest note": s.note,
                "Source": s.source,
            }
        )
    return pd.DataFrame(rows)


def render_status_board(statuses: dict[str, FeatureStatus], key: str) -> None:
    df = status_frame(statuses)
    st.dataframe(
        df,
        hide_index=True,
        key=key,
        column_config={
            "Last confirmed": st.column_config.DateColumn(format="YYYY-MM-DD"),
            "Stale": st.column_config.CheckboxColumn(help="Older than the trust window for this feature"),
            "Latest note": st.column_config.TextColumn(width="large"),
        },
    )


def render_evidence(hits: list[Hit], today: date) -> None:
    for i, h in enumerate(hits, 1):
        c = h.chunk
        age = c.age_days(today)
        title = f"[{i}] {c.label}: {c.heading or c.doc_title} ({c.date.isoformat()}, {age} d ago)"
        with st.expander(title, icon=_icon_for(c.source_type)):
            st.markdown(c.text)
            st.caption(
                f"Document: {c.doc_title} | trust: {c.trust} | relevance {h.bm25:.1f}"
                + (f" | recency boost +{h.recency * 100:.0f}%" if h.recency else "")
            )


def _icon_for(source_type: str) -> str:
    return {
        "listing": ":material/campaign:",
        "audit": ":material/fact_check:",
        "maintenance_log": ":material/build:",
        "staff_note": ":material/badge:",
        "policy": ":material/support_agent:",
        "events": ":material/event:",
        "visitor_report": ":material/person:",
    }.get(source_type, ":material/description:")


def current_statuses(kb: VenueKB) -> dict[str, FeatureStatus]:
    return latest_statuses(kb.facts, demo_now().date())

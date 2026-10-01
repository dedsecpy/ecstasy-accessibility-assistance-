import streamlit as st

from nimbus.features import FEATURES, STATUS_LABELS, latest_statuses
from nimbus.pipeline import ingest_report
from nimbus.ui import demo_now, get_kb, get_llm, render_status_board

kb = get_kb(st.session_state.venue_id)
llm = get_llm()
now = demo_now()

st.title("Report what you found", icon=":material/rate_review:")
st.caption(
    "Visitors and staff describe what actually happened. Nimbus extracts dated, feature-level facts, "
    "adds them to the evidence base, and the next visitor's answer changes immediately."
)

EXAMPLES = {
    "The complaint (visitor, wheelchair)": (
        "visitor",
        "manual wheelchair",
        "I checked before travelling and the website said accessible. Arrived 18:30 for the evening lecture. "
        "The main entrance had stairs. The side gate on Mill Lane was locked and nobody answered the intercom. "
        "A guard eventually came and said the lift was out of service and suggested my friends carry me. "
        "I missed the event and paid for accessible transport twice.",
    ),
    "Second visitor (walks short distances)": (
        "visitor",
        "walks short distances, needs seating",
        "I can walk short distances but I need seating and a route without steep slopes. The ramp was steep and "
        "there was no bench on it. All the foyer chairs were taken when I arrived.",
    ),
    "Venue response (staff)": (
        "staff",
        "",
        "The building normally has a lift. The lift is out of service since 26 September; the engineer is now booked "
        "for 6 October. We did not know the listing needed changing.",
    ),
    "Good news (staff): lift repaired": (
        "staff",
        "",
        "Lift repaired and tested this morning, back in service. Side gate intercom working and answered. "
        "Scaffolding still narrows the courtyard path until mid-October.",
    ),
}


def _load_example() -> None:
    reporter, needs, text = EXAMPLES[st.session_state.example_choice]
    st.session_state.report_reporter = reporter
    st.session_state.report_needs = needs
    st.session_state.report_text = text


st.selectbox(
    "Load an example report",
    list(EXAMPLES),
    index=None,
    placeholder="Choose an example or write your own below",
    key="example_choice",
    on_change=_load_example,
)

st.session_state.setdefault("report_reporter", "visitor")

with st.form("report_form", border=True):
    c1, c2, c3 = st.columns([1, 2, 1])
    with c1:
        reporter = st.segmented_control("Who is reporting?", ["visitor", "staff"], key="report_reporter", format_func=str.capitalize)
    with c2:
        needs = st.text_input("Your access needs (optional)", key="report_needs", placeholder="e.g. powered wheelchair, 700 mm wide")
    with c3:
        when = st.date_input("Date of visit", value=now.date(), max_value=now.date())
    text = st.text_area("What did you find?", key="report_text", height=160, placeholder="Describe entrances, gates, lift, obstacles, seating, staff help...")
    submitted = st.form_submit_button("Submit report", type="primary", icon=":material/send:")

if submitted:
    if not text.strip():
        st.error("Please describe what you found.", icon=":material/error:")
    else:
        before = latest_statuses(kb.facts, now.date())
        with st.spinner("Extracting facts..."):
            result = ingest_report(text, reporter or "visitor", needs, kb, llm, when=when)
        after = latest_statuses(kb.facts, now.date())
        st.session_state.last_ingest = (result, before, after)
        st.toast("Report added to the evidence base.", icon=":material/check_circle:")

if st.session_state.last_ingest:
    result, before, after = st.session_state.last_ingest
    if result.error:
        st.warning(result.error, icon=":material/warning:")
    st.success(result.summary, icon=":material/check_circle:")
    with st.container(horizontal=True):
        st.badge(
            "LLM extraction" if result.mode == "llm" else "Rule-based extraction (no LLM key)",
            icon=":material/smart_toy:" if result.mode == "llm" else ":material/rule:",
            color="green" if result.mode == "llm" else "orange",
        )
        st.badge(f"{len(result.facts)} fact(s) extracted", icon=":material/data_object:", color="blue")

    left, right = st.columns([1, 1])
    with left:
        with st.container(border=True):
            st.subheader("Extracted facts", icon=":material/data_object:")
            if not result.facts:
                st.caption("Nothing feature-specific could be extracted from this report.")
            for f in result.facts:
                label = FEATURES[f["feature"]].label
                st.markdown(f"**{label}** - {STATUS_LABELS.get(f['status'], f['status'])}  \n{f['note']}")
    with right:
        with st.container(border=True):
            st.subheader("What changed on the status board", icon=":material/difference:")
            changes = []
            for fid, s in after.items():
                b = before.get(fid)
                if b is None or b.status != s.status or b.date != s.date:
                    changes.append((s.feature.label, b.status_label if b else "none", s.status_label, s.freshness_text))
            if not changes:
                st.caption("No status changed; the report confirmed existing information.")
            for label, old, new, fresh in changes:
                st.markdown(f"**{label}**: {old} -> **{new}** ({fresh})")
    st.page_link("app_pages/visitor.py", label="Re-run the visitor check to see the effect", icon=":material/directions:")

st.subheader("Current status board", icon=":material/table_chart:")
render_status_board(latest_statuses(kb.facts, now.date()), key="report_status_board")

live = [c for c in kb.chunks if c.id.startswith("live_reports")]
if live:
    with st.expander(f"Reports added this session ({len(live)})", icon=":material/history:"):
        for c in reversed(live):
            st.markdown(f"**{c.heading}** - {c.date.isoformat()}  \n{c.text}")

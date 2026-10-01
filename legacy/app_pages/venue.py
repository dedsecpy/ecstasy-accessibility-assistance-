import streamlit as st

from nimbus.features import latest_statuses
from nimbus.pipeline import audit_listing
from nimbus.ui import demo_now, get_kb, get_llm, render_status_board

kb = get_kb(st.session_state.venue_id)
llm = get_llm()
now = demo_now()

st.title("Listing health", icon=":material/monitor_heart:")
st.caption(
    "For venue staff: does the public listing still match the evidence? Nimbus compares each claim with the latest dated "
    "facts, shows which upcoming events are affected, and drafts an honest replacement."
)

with st.spinner("Auditing listing..."):
    audit = audit_listing(kb, llm, now=now)

if audit.error:
    st.warning(audit.error, icon=":material/warning:")

contradicted = sum(c.verdict == "contradicted" for c in audit.claims)
qualified = sum(c.verdict == "qualified" for c in audit.claims)
unverified = sum(c.verdict == "unverified" for c in audit.claims)

with st.container(horizontal=True):
    with st.container(border=True):
        st.metric("Listing age", f"{audit.listing_age_days} d", help="Days since the public listing was last edited")
    with st.container(border=True):
        st.metric("Contradicted", contradicted, help="Listing claims contradicted by current evidence")
    with st.container(border=True):
        st.metric("Need qualifying", qualified + unverified, help="Claims that are only partly true or unverified")
    with st.container(border=True):
        st.metric("Stale statuses", len(audit.stale_features), help="Features not confirmed within their trust window")
    with st.container(border=True):
        st.metric("Events at risk", len(audit.affected_events), help="Upcoming events affected by current conditions")

VERDICT_BADGE = {
    "supported": ("Supported", "green", ":material/check_circle:"),
    "qualified": ("Needs qualification", "orange", ":material/warning:"),
    "unverified": ("Unverified", "gray", ":material/help:"),
    "contradicted": ("Contradicted", "red", ":material/cancel:"),
}

left, right = st.columns([1.2, 1])
with left:
    st.subheader("Claim by claim", icon=":material/fact_check:")
    for c in audit.claims:
        label, color, icon = VERDICT_BADGE[c.verdict]
        with st.container(border=True):
            with st.container(horizontal=True, vertical_alignment="center"):
                st.markdown(f"**\"{c.claim}\"**")
                st.badge(label, color=color, icon=icon)
            for r in c.reasons:
                st.caption(r)

with right:
    st.subheader("Upcoming events at risk", icon=":material/event_busy:")
    if not audit.affected_events:
        st.caption("No upcoming events are affected by current conditions.")
    for ev in audit.affected_events:
        with st.container(border=True):
            st.markdown(f"**{ev['name']}**  \n{ev['start'][:10]} {ev['start'][11:]} - {ev['location']}")
            for issue in ev["issues"]:
                st.markdown(f"- {issue}")

    st.subheader("Stale statuses", icon=":material/schedule:")
    if not audit.stale_features:
        st.caption("Every time-sensitive feature has been confirmed within its trust window.")
    for s in audit.stale_features:
        st.markdown(f"- **{s.feature.label}**: {s.status_label}, {s.freshness_text}")

st.subheader("Draft replacement listing", icon=":material/edit_note:")
with st.container(horizontal=True):
    st.badge(
        "Drafted by LLM" if audit.mode == "llm" else "Template draft (no LLM key)",
        icon=":material/smart_toy:" if audit.mode == "llm" else ":material/rule:",
        color="green" if audit.mode == "llm" else "orange",
    )
    st.download_button(
        "Download as Markdown",
        data=audit.draft_listing,
        file_name=f"{kb.id}_access_listing.md",
        mime="text/markdown",
        icon=":material/download:",
    )
with st.container(border=True):
    st.markdown(audit.draft_listing)

st.subheader("Keep it accurate", icon=":material/checklist:")
for a in audit.staff_actions:
    st.markdown(f"- {a}")

with st.expander("Full status board", icon=":material/table_chart:"):
    render_status_board(latest_statuses(kb.facts, now.date()), key="venue_status_board")

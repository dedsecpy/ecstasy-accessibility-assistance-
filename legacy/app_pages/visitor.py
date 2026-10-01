import streamlit as st

from nimbus.pipeline import MOBILITY_LABELS, NeedsProfile, answer_question
from nimbus.ui import demo_now, get_kb, get_llm, render_evidence, render_status_board

kb = get_kb(st.session_state.venue_id)
llm = get_llm()
now = demo_now()

st.title("Check before you travel", icon=":material/directions:")
st.caption(
    f"{kb.name}: a route-level answer for your needs and your visit time, built from dated evidence rather than the "
    f"public listing. Listing last updated {kb.config['listing_updated']}."
)

events = kb.config.get("events", [])
event_labels = ["General visit (not sure yet)"] + [
    f"{e['name']} - {e['start'][:10]} {e['start'][11:]} ({e['location']})" for e in events
]

with st.form("visitor_form", border=True):
    left, right = st.columns([1, 1])
    with left:
        event_idx = st.selectbox("What are you coming to?", range(len(event_labels)), format_func=lambda i: event_labels[i])
        mobility = st.selectbox(
            "How do you get around?",
            list(MOBILITY_LABELS),
            format_func=lambda m: MOBILITY_LABELS[m],
        )
    with right:
        question = st.text_area(
            "Your question, in your own words",
            value="Can I get from the door to my seat without steps, and is the lift working?",
            height=120,
        )
        free_text = st.text_input("Anything about your needs the options above miss", placeholder="e.g. my chair is 720 mm wide")
    needs = st.pills(
        "Anything else we should plan for?",
        ["Seating and rest points", "Avoid steep slopes", "Staff assistance on arrival"],
        selection_mode="multi",
    ) or []
    submitted = st.form_submit_button("Check this visit", type="primary", icon=":material/travel_explore:")

if submitted:
    profile = NeedsProfile(
        mobility=mobility,
        needs_seating="Seating and rest points" in needs,
        avoid_slopes="Avoid steep slopes" in needs,
        needs_assistance="Staff assistance on arrival" in needs,
        event=events[event_idx - 1] if event_idx > 0 else None,
        free_text=free_text,
    )
    with st.spinner("Checking evidence..." if not llm.available else "Retrieving evidence and asking the model..."):
        st.session_state.last_answer = answer_question(question, profile, kb, llm, now=now)

answer = st.session_state.last_answer
if answer is None:
    st.info(
        "Try the scenario from the complaint: a manual wheelchair user going to the Autumn Lecture (upstairs, 19:00 on a Thursday). "
        "Then try the second visitor: walks short distances, needs seating, going to the Community Fair.",
        icon=":material/lightbulb:",
    )
    st.stop()

if answer.error:
    st.warning(answer.error, icon=":material/warning:")

verdict_ui = {
    "no_go": (st.error, ":material/block:", "Do not rely on this venue for this visit"),
    "caution": (st.warning, ":material/warning:", "Possible, with conditions"),
    "go": (st.success, ":material/check_circle:", "Looks workable"),
}
fn, icon, label = verdict_ui.get(answer.verdict, verdict_ui["caution"])
fn(f"**{label}.** {answer.headline}", icon=icon)

st.markdown(answer.summary)

with st.container(horizontal=True):
    st.badge(
        "LLM answer" if answer.mode == "llm" else "Rule-based answer (no LLM key)",
        icon=":material/smart_toy:" if answer.mode == "llm" else ":material/rule:",
        color="green" if answer.mode == "llm" else "orange",
    )
    st.badge(f"{len(answer.hits)} passages retrieved", icon=":material/manage_search:", color="blue")
    if answer.visit.staffed is not None:
        st.badge(
            "Desk staffed at arrival" if answer.visit.staffed else "Desk NOT staffed at arrival",
            icon=":material/support_agent:",
            color="green" if answer.visit.staffed else "red",
        )

route_col, warn_col = st.columns([1, 1])
with route_col:
    with st.container(border=True):
        st.subheader("Your route", icon=":material/route:")
        for i, step in enumerate(answer.route, 1):
            st.markdown(f"{i}. {step}")
with warn_col:
    with st.container(border=True):
        st.subheader("Watch out for", icon=":material/report:")
        for w in answer.warnings:
            st.markdown(f"- {w}")

with st.container(border=True):
    st.subheader("Verify before you travel", icon=":material/call:")
    for v in answer.verify:
        st.checkbox(v, key=f"verify_{hash(v)}")

if answer.discrepancies:
    with st.container(border=True):
        st.subheader("Where the public listing is wrong or unsupported", icon=":material/campaign:")
        for d in answer.discrepancies:
            st.markdown(f"- {d}")

st.subheader("Evidence used", icon=":material/fact_check:")
st.caption("Numbers in brackets above refer to these passages. Newer operational reports are boosted; the public listing is weighted lowest.")
render_evidence(answer.hits, now.date())

with st.expander("Status board behind this answer", icon=":material/table_chart:"):
    st.caption("Latest known state per feature, collapsed from the dated fact log. 'Stale' means older than the trust window for that feature.")
    render_status_board(answer.statuses, key="visitor_status_board")

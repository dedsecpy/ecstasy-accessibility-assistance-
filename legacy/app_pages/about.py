import streamlit as st

from nimbus.ui import get_kb

kb = get_kb(st.session_state.venue_id)

st.title("Problem and approach", icon=":material/info:")

st.subheader("Problem statement", icon=":material/target:")
st.markdown(
    """
**A venue's "wheelchair accessible" label is a static, binary promise about a dynamic, route-level reality.**
It says nothing about *which* entrance is step-free, whether the lift is working *today*, what temporary
obstacles exist, or whether anyone will answer the gate at 18:30. Staff have no trigger to update it, so it
decays silently. Visitors with different needs (a wheelchair user, someone who walks short distances and needs
seating) are given the same one-word answer, discover the truth at the last staircase, and pay for it in missed
events and double transport costs.

**Focused question:** How can a visitor get an honest, personalised, current answer to *"Can I get from arrival to my seat
for this visit?"* from a venue whose only published fact is a two-year-old label, and how can the venue find out its
listing is wrong *before* a visitor does?
"""
)

st.subheader("What Nimbus does", icon=":material/accessible_forward:")
c1, c2, c3 = st.columns(3)
with c1:
    with st.container(border=True):
        st.markdown("**1. Check before you travel**")
        st.markdown(
            "Retrieval-augmented answer over venue documents (audit, lift log, staff notes, assistance hours, "
            "visitor reports). Tailored to the visitor's profile and visit time; every claim cited and dated; "
            "a clear verdict instead of a label."
        )
with c2:
    with st.container(border=True):
        st.markdown("**2. Report what you found**")
        st.markdown(
            "Free-text reports from visitors and staff become structured, dated facts via LLM extraction. They "
            "enter the evidence base immediately, so the next answer reflects reality, not the listing."
        )
with c3:
    with st.container(border=True):
        st.markdown("**3. Listing health**")
        st.markdown(
            "Each listing claim is checked against the latest evidence: supported, qualified, unverified or "
            "contradicted. Upcoming events at risk are flagged and an honest replacement listing is drafted."
        )

st.subheader("How the AI is used", icon=":material/smart_toy:")
st.markdown(
    """
- **RAG**: documents are chunked by section and dated; retrieval is BM25 with a recency boost for operational
  sources (maintenance log, staff notes, visitor reports) and a trust weighting that ranks the marketing listing lowest.
  A structured *status board* (latest fact per feature, with a per-feature staleness window) is passed alongside the
  passages so the model can reason about freshness explicitly.
- **LLM** (any OpenAI-compatible endpoint): synthesises a cited answer in a fixed JSON shape, extracts facts from
  reports, and drafts the replacement listing. Prompts forbid uncited claims, require freshness caveats, and
  prohibit "get someone to carry you" style advice.
- **Deterministic fallback**: when no key is configured the same pipeline runs with rule-based composition and
  keyword extraction, so the demo is reproducible offline. The UI always shows which mode produced an answer.
"""
)

st.subheader("Design choices that answer the complaint", icon=":material/design_services:")
st.markdown(
    """
| Complaint detail | Nimbus behaviour |
|---|---|
| "Your website said accessible" | The listing is the lowest-trust source; discrepancies are called out explicitly. |
| Main entrance had stairs | Route starts from the correct entrance for the visitor's mobility. |
| Side gate locked, no answer | Visit time is checked against assistance desk hours; pre-booking advice depends on how far away the visit is. |
| Lift out of service | Lift status carries a 7-day trust window; "last confirmed N days ago" is always shown; upstairs destination + lift out = **no-go**. |
| Guard suggested carrying | Prompt rule and fallback logic never offer carrying as a route. |
| Paid for transport twice | A concrete "verify before you travel" checklist with who to call and what to ask. |
| "We did not know the listing needed changing" | Listing-health page shows contradictions, stale statuses and affected events, and drafts the fix. |
| Second visitor: seating, no steep slopes | Profile-aware: distances, ramp gradient, benches and foyer seating surface for ambulatory visitors. |
"""
)

st.subheader("Data in this demo", icon=":material/database:")
docs = sorted({(c.doc_title, c.source_type, c.trust) for c in kb.chunks})
for title, stype, trust in docs:
    st.markdown(f"- **{title}** ({stype}, trust: {trust})")
st.caption("All venue data is synthetic and modelled on the scenario in the brief.")

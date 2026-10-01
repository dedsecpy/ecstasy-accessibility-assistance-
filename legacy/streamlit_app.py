import streamlit as st

from nimbus.ui import init_state, sidebar

st.set_page_config(
    page_title="Nimbus - accessible until the last staircase",
    page_icon=":material/accessible_forward:",
    layout="wide",
)

init_state()

page = st.navigation(
    [
        st.Page("app_pages/visitor.py", title="Check before you travel", icon=":material/directions:", default=True),
        st.Page("app_pages/report.py", title="Report what you found", icon=":material/rate_review:"),
        st.Page("app_pages/venue.py", title="Listing health (venue staff)", icon=":material/monitor_heart:"),
        st.Page("app_pages/about.py", title="Problem and approach", icon=":material/info:"),
    ],
    position="top",
)

sidebar()
page.run()

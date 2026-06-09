import streamlit as st
from lib.auth import try_login
from lib.environments import ENVIRONMENTS, DEFAULT_ENV

st.set_page_config(page_title="SSH MP Curation Toolkit", page_icon="🔍", layout="centered")

# Already logged in — go straight to the first tool
if st.session_state.get("authenticated"):
    st.switch_page("pages/1_Contributors.py")

st.title("SSH Open Marketplace — Curation Toolkit")
st.caption("Sign in with your Marketplace account to continue.")

with st.form("login_form"):
    env_name = st.radio(
        "Environment",
        list(ENVIRONMENTS.keys()),
        index=list(ENVIRONMENTS.keys()).index(DEFAULT_ENV),
        horizontal=True,
    )
    st.caption(ENVIRONMENTS[env_name]["api_url"])
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    submitted = st.form_submit_button("Sign in", use_container_width=True)

if submitted:
    if not username or not password:
        st.warning("Please enter both username and password.")
    else:
        with st.spinner("Authenticating…"):
            token = try_login(username, password, env_name)
        if token:
            st.session_state["authenticated"] = True
            st.session_state["bearer"] = token
            st.session_state["username"] = username
            st.session_state["env"] = ENVIRONMENTS[env_name]
            st.switch_page("pages/1_Contributors.py")
        else:
            st.error("Login failed. Please check your credentials.")

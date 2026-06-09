import requests
import streamlit as st
from lib.environments import ENVIRONMENTS, DEFAULT_ENV


def try_login(username: str, password: str, env_name: str) -> str | None:
    """POST credentials to the MP API. Returns the bearer token on success, None on failure."""
    server = ENVIRONMENTS[env_name]["api_url"]
    url = server + "/api/auth/sign-in"
    try:
        resp = requests.post(
            url,
            headers={"Content-type": "application/json"},
            json={"username": username, "password": password},
            timeout=10,
        )
    except requests.RequestException as e:
        st.error(f"Could not reach the Marketplace API: {e}")
        return None
    if resp.status_code == 200:
        return resp.headers.get("Authorization")
    return None


def require_login() -> None:
    """Redirect to the login page and stop rendering if the user is not authenticated."""
    if not st.session_state.get("authenticated"):
        st.switch_page("app.py")
        st.stop()

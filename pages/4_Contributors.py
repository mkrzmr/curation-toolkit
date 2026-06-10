import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
from lib.auth import require_login
from lib.mplib import get_util
from lib.snapshot import render_data_status, require_snapshot
from lib.api import fetch_all_actors

require_login()

st.set_page_config(page_title="Contributors — Curation Toolkit", page_icon="👥", layout="wide")

env = st.session_state["env"]
st.title("Contributors")
st.caption(f"Environment: **{env['label']}** — {env['api_url']}")

MP_SERVER = env["mp_url"]

require_snapshot()

@st.cache_data(show_spinner="Loading contributors…")
def load_contributors() -> pd.DataFrame:
    util = get_util()
    df = util.getContributors()
    if df.empty:
        return df
    df["MPUrl"] = MP_SERVER + df["category"] + "/" + df["persistentId"]
    return df


df = load_contributors()

if df.empty:
    st.warning("No contributor data found. Make sure the snapshot exists in data/.")
    st.stop()

# Join actor email/website from API data if already fetched
actor_details: pd.DataFrame | None = st.session_state.get("actor_details")
if actor_details is not None and not actor_details.empty:
    df = df.merge(
        actor_details[["id", "email"]].rename(columns={"id": "actor.id"}),
        on="actor.id",
        how="left",
    )

# --- Sidebar ---
with st.sidebar:
    st.header("Filters")

    categories = sorted(df["category"].dropna().unique().tolist())
    selected_cats = st.multiselect("Category", categories, default=categories)

    roles = sorted(df["role.label"].dropna().unique().tolist())
    selected_roles = st.multiselect("Role", roles, default=roles)

    name_query = st.text_input("Actor name contains", "")

    # Email filter — shown only once actor details are loaded
    email_query = ""
    if actor_details is not None:
        email_query = st.text_input("Actor email contains", "")
    else:
        st.caption("Email filter not available yet.")
        if st.button("Load actor emails from API", use_container_width=True):
            with st.spinner("Fetching actors from API…"):
                try:
                    details = fetch_all_actors(env["api_url"], st.session_state["bearer"])
                    st.session_state["actor_details"] = details
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to fetch actors: {e}")

render_data_status()

# --- Apply filters ---
mask = (
    df["category"].isin(selected_cats)
    & df["role.label"].isin(selected_roles)
)
if name_query.strip():
    mask &= df["actor.name"].str.contains(name_query.strip(), case=False, na=False)
if email_query.strip() and "email" in df.columns:
    mask &= df["email"].fillna("").str.contains(email_query.strip(), case=False)

filtered = df[mask].reset_index(drop=True)

# --- Metrics ---
col1, col2, col3 = st.columns(3)
col1.metric("Rows shown", len(filtered))
col2.metric("Unique actors", filtered["actor.name"].nunique())
col3.metric("Unique items", filtered["persistentId"].nunique())

# --- Build display columns ---
# MPUrl links to the item the actor contributed to (no dedicated actor page exists)
DISPLAY_COLS = ["actor.name", "email", "role.label", "label", "category", "persistentId", "actor.website", "MPUrl"]
show_cols = [c for c in DISPLAY_COLS if c in filtered.columns]

col_cfg = {
    "MPUrl": st.column_config.LinkColumn("Item link", display_text="Open"),
    "actor.website": st.column_config.LinkColumn("Website"),
    "email": st.column_config.TextColumn("Email"),
}

st.dataframe(
    filtered[show_cols],
    use_container_width=True,
    column_config=col_cfg,
    hide_index=True,
)

# --- Export ---
csv = filtered[show_cols].to_csv(index=False).encode("utf-8")
st.download_button(
    label="Download CSV",
    data=csv,
    file_name="contributors.csv",
    mime="text/csv",
)

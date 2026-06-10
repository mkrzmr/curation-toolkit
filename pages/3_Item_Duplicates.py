import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
from lib.auth import require_login
from lib.mplib import get_util
from lib.snapshot import render_data_status, require_snapshot

require_login()

st.set_page_config(page_title="Item Duplicates — Curation Toolkit", page_icon="📄", layout="wide")

env = st.session_state["env"]
st.title("Item Duplicates")
st.caption(f"Environment: **{env['label']}** — {env['api_url']}")

MP_SERVER = env["mp_url"]

require_snapshot()
render_data_status()


@st.cache_data(show_spinner="Loading snapshot…")
def load_snapshot() -> pd.DataFrame:
    return get_util()._load_snapshot()


snap = load_snapshot()

if snap.empty:
    st.warning("No snapshot data found.")
    st.stop()

col_left, col_right = st.columns([1, 2])

with col_left:
    all_categories = sorted(snap["category"].dropna().unique().tolist())
    selected_cats = st.multiselect(
        "Filter by category",
        all_categories,
        default=all_categories,
    )

    TOP_LEVEL_CHECKABLE = ["label", "description", "accessibleAt"]
    selected_props = st.multiselect(
        "Check for duplicates in",
        TOP_LEVEL_CHECKABLE,
        default=["label"],
    )

    run_items = st.button("Find Duplicates", use_container_width=True)

with col_right:
    if run_items:
        if not selected_props:
            st.warning("Select at least one property to check.")
        else:
            subset = snap[snap["category"].isin(selected_cats)].copy()
            props_csv = ",".join(selected_props)
            result = get_util().getDuplicates(subset, props_csv)

            if result is None or result.empty:
                st.success("No duplicates found with these settings.")
            else:
                st.metric("Duplicate rows found", len(result))
                disp_cols = ["label", "category", "persistentId"] + [
                    c for c in selected_props if c not in ["label", "category", "persistentId"]
                ]
                disp_cols = [c for c in dict.fromkeys(disp_cols) if c in result.columns]

                display = result[disp_cols].copy()
                if "MPUrl" in result.columns:
                    display["Link"] = MP_SERVER + result["MPUrl"].str.lstrip("/")
                    disp_cols = disp_cols + ["Link"]

                st.dataframe(
                    display,
                    use_container_width=True,
                    column_config={"Link": st.column_config.LinkColumn("Open in MP")},
                    hide_index=True,
                )

                csv = display[disp_cols].to_csv(index=False).encode("utf-8")
                st.download_button("Download CSV", csv, "item_duplicates.csv", "text/csv")

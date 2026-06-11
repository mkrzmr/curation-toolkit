"""
Item Duplicates — find and compare items that share identical field values.

The user selects which top-level fields to check (label, description,
accessibleAt) and which categories to include.  Items without an accessibleAt
URL are excluded before the check — they are stub entries that cannot be
meaningfully distinguished from each other.

Results are persisted in st.session_state so that fetching live API data
for side-by-side comparison does not re-trigger the duplicate scan.

Shared state (st.session_state keys)
  item_dup_result   – last getDuplicates() result DataFrame
  item_dup_props    – list of property names used for the last search
  item_dup_filtered – count of items excluded due to missing accessibleAt
  fetched_items     – dict of group_idx → {persistentId: live_item_dict}
"""

import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
from lib.auth import require_login
from lib.mplib import get_util
from lib.snapshot import render_data_status, require_snapshot
from lib.api import get_item

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


def _has_accessible_at(val) -> bool:
    """
    Return True when a snapshot accessibleAt value contains at least one URL.

    The field can appear as None, NaN, an empty list, the string "[]", or a
    non-empty list of URL strings.  All empty/missing forms return False.
    """
    if val is None:
        return False
    if isinstance(val, float) and pd.isna(val):
        return False
    if isinstance(val, list):
        return len(val) > 0
    s = str(val).strip()
    return s not in ("", "[]", "nan")


def _render_item_card(item: dict, mp_server: str) -> None:
    """
    Render a compact summary card for a single live API item.

    Shows label, persistent ID, category, status, source system, up to three
    access URLs, contributor names, and the first 400 characters of the
    description.  Used inside the side-by-side comparison expanders.
    """
    pid = item.get("persistentId", "—")
    cat = item.get("category", "—")
    status = item.get("status", "—")
    source = (item.get("source") or {}).get("label", "—")
    access_urls = item.get("accessibleAt") or []
    desc = (item.get("description") or "").strip()
    contributors = item.get("contributors") or []

    st.markdown(f"**{item.get('label', '—')}**")
    st.caption(f"`{pid}` · {cat}")
    st.caption(f"Status: **{status}**" + (f" · Source: {source}" if source != "—" else ""))

    if access_urls:
        for url in (access_urls if isinstance(access_urls, list) else [access_urls])[:3]:
            st.markdown(f"[{url}]({url})")

    if contributors:
        names = [
            c.get("actor", {}).get("name", "")
            for c in contributors[:5]
            if c.get("actor", {}).get("name")
        ]
        if names:
            st.caption("Contributors: " + ", ".join(names))

    if desc:
        st.text(desc[:400] + ("…" if len(desc) > 400 else ""))


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

# ── Run duplicate detection ───────────────────────────────────────────────────
if run_items:
    if not selected_props:
        st.warning("Select at least one property to check.")
    else:
        subset = snap[snap["category"].isin(selected_cats)].copy()

        # Filter out items without an access URL — they cannot be meaningfully deduped
        if "accessibleAt" in subset.columns:
            before = len(subset)
            subset = subset[subset["accessibleAt"].apply(_has_accessible_at)]
            filtered = before - len(subset)
        else:
            filtered = 0

        props_csv = ",".join(selected_props)
        result = get_util().getDuplicates(subset, props_csv)

        st.session_state["item_dup_result"] = result
        st.session_state["item_dup_props"] = list(selected_props)
        st.session_state["item_dup_filtered"] = filtered
        st.session_state["fetched_items"] = {}

# ── Display stored results ────────────────────────────────────────────────────
result: pd.DataFrame | None = st.session_state.get("item_dup_result")
stored_props: list = st.session_state.get("item_dup_props", [])
filtered_count: int = st.session_state.get("item_dup_filtered", 0)
fetched_items: dict = st.session_state.setdefault("fetched_items", {})

with col_right:
    if result is None:
        st.info("Select options and click **Find Duplicates** to search.")
    elif result.empty:
        if filtered_count:
            st.info(f"Excluded {filtered_count} items without an access URL.")
        st.success("No duplicates found with these settings.")
    else:
        if filtered_count:
            st.info(f"Excluded {filtered_count} items without an access URL.")

        st.metric("Duplicate rows found", len(result))

        disp_cols = ["label", "category", "persistentId"] + [
            c for c in stored_props if c not in ["label", "category", "persistentId"]
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

# ── Side-by-side comparison ───────────────────────────────────────────────────
if result is not None and not result.empty and stored_props:
    st.divider()
    st.subheader("Compare duplicate groups")

    key_cols = [c for c in stored_props if c in result.columns]
    # Lists (e.g. accessibleAt) are unhashable — stringify them for groupby
    groupby_df = result.copy()
    for col in key_cols:
        if groupby_df[col].apply(lambda x: isinstance(x, list)).any():
            groupby_df[col] = groupby_df[col].apply(lambda x: ", ".join(str(u) for u in x) if isinstance(x, list) else x)
    groups = list(groupby_df.groupby(key_cols, sort=False))

    for group_idx, (group_key, group_df) in enumerate(groups):
        if isinstance(group_key, str):
            group_key = (group_key,)
        label_str = " · ".join(str(k)[:80] for k in group_key)

        with st.expander(f"{label_str}  ({len(group_df)} items)"):
            rows = group_df.to_dict("records")
            group_fetched = fetched_items.get(group_idx)

            if group_fetched is None:
                # Show snapshot data + fetch button
                cols = st.columns(len(rows))
                for col, row in zip(cols, rows):
                    pid = row.get("persistentId", "")
                    cat = row.get("category", "")
                    mp_url = MP_SERVER + str(row.get("MPUrl", "")).lstrip("/") if "MPUrl" in row else None
                    with col:
                        st.markdown(f"**{row.get('label', '')}**")
                        st.caption(f"{cat} · `{pid}`")
                        if mp_url:
                            st.markdown(f"[Open in MP]({mp_url})")

                if st.button("Fetch live data from API", key=f"fetch_{group_idx}"):
                    group_data = {}
                    for row in rows:
                        pid = row.get("persistentId", "")
                        cat = row.get("category", "")
                        try:
                            group_data[pid] = get_item(
                                cat, pid, env["api_url"], st.session_state["bearer"]
                            )
                        except Exception as e:
                            group_data[pid] = {"error": str(e), "persistentId": pid}
                    fetched_items[group_idx] = group_data
                    st.rerun()
            else:
                # Show live data side-by-side
                cols = st.columns(len(rows))
                for col, row in zip(cols, rows):
                    pid = row.get("persistentId", "")
                    item = group_fetched.get(pid, {})
                    with col:
                        if "error" in item:
                            st.error(f"Failed to load `{pid}`: {item['error']}")
                        else:
                            _render_item_card(item, MP_SERVER)

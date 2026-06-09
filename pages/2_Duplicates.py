import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import re
import streamlit as st
import pandas as pd
from lib.auth import require_login
from lib.mplib import get_util
from lib.api import merge_actors, delete_actor, fetch_all_actors, verify_orphans
from lib.snapshot import render_data_status, require_snapshot

require_login()

st.set_page_config(page_title="Duplicates — Curation Toolkit", page_icon="🔎", layout="wide")

env = st.session_state["env"]
st.title("Duplicate Detection")
st.caption(f"Environment: **{env['label']}** — {env['api_url']}")

MP_SERVER = env["mp_url"]

require_snapshot()
render_data_status()


@st.cache_data(show_spinner="Loading snapshot…")
def load_snapshot() -> pd.DataFrame:
    return get_util()._load_snapshot()


@st.cache_data(show_spinner="Loading contributors…")
def load_actors() -> pd.DataFrame:
    util = get_util()
    c = util.getContributors()
    if c.empty:
        return pd.DataFrame()
    actors = (
        c[["actor.id", "actor.name", "actor.website", "actor.externalIds", "actor.affiliations"]]
        .drop_duplicates(subset=["actor.id"])
        .rename(columns={
            "actor.id": "id",
            "actor.name": "name",
            "actor.website": "website",
            "actor.externalIds": "externalIds",
            "actor.affiliations": "affiliations",
        })
    )
    # getDuplicatedActorsWithItems expects MPUrl to already be present
    return util._getMPUrl(actors)


tab_items, tab_actors, tab_orphans = st.tabs(["Item Duplicates", "Actor Duplicates", "Orphaned Actors"])

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — Item Duplicates
# ─────────────────────────────────────────────────────────────────────────────
with tab_items:
    st.subheader("Find items with duplicate field values")
    snap = load_snapshot()

    if snap.empty:
        st.warning("No snapshot data found.")
    else:
        col_left, col_right = st.columns([1, 2])

        with col_left:
            all_categories = sorted(snap["category"].dropna().unique().tolist())
            selected_cats = st.multiselect(
                "Filter by category",
                all_categories,
                default=all_categories,
                key="item_cats",
            )

            TOP_LEVEL_CHECKABLE = ["label", "description", "accessibleAt"]
            selected_props = st.multiselect(
                "Check for duplicates in",
                TOP_LEVEL_CHECKABLE,
                default=["label"],
                key="item_props",
            )

            run_items = st.button("Find Duplicates", key="btn_items", use_container_width=True)

        with col_right:
            if run_items:
                if not selected_props:
                    st.warning("Select at least one property to check.")
                else:
                    subset = snap[snap["category"].isin(selected_cats)].copy()
                    props_csv = ",".join(selected_props)
                    util = get_util()
                    result = util.getDuplicates(subset, props_csv)

                    if result is None or result.empty:
                        st.success("No duplicates found with these settings.")
                    else:
                        st.metric("Duplicate rows found", len(result))
                        disp_cols = ["MPUrl", "label", "category", "persistentId"] + [
                            c for c in selected_props if c not in ["label", "category", "persistentId"]
                        ]
                        disp_cols = [c for c in dict.fromkeys(disp_cols) if c in result.columns]

                        # Build clickable MP URLs
                        result["Link"] = MP_SERVER + result["MPUrl"].str.lstrip("/")

                        st.dataframe(
                            result[disp_cols].assign(Link=MP_SERVER + result["MPUrl"].str.lstrip("/")),
                            use_container_width=True,
                            column_config={"Link": st.column_config.LinkColumn("Open in MP")},
                            hide_index=True,
                        )

                        csv = result[disp_cols].to_csv(index=False).encode("utf-8")
                        st.download_button("Download CSV", csv, "item_duplicates.csv", "text/csv")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — Actor Duplicates
# ─────────────────────────────────────────────────────────────────────────────
with tab_actors:
    st.subheader("Find actors with the same name or website")
    actors = load_actors()

    if actors.empty:
        st.warning("No actor/contributor data found.")
    else:
        col_left, _ = st.columns([1, 2])
        with col_left:
            ACTOR_CHECKABLE = ["name", "website"]
            selected_actor_props = st.multiselect(
                "Check for duplicates in",
                ACTOR_CHECKABLE,
                default=["name"],
                key="actor_props",
            )
            run_actors = st.button("Find Duplicates", key="btn_actors", use_container_width=True)

        # Run search and persist results so merge buttons don't wipe them on re-run
        if run_actors:
            if not selected_actor_props:
                st.warning("Select at least one property to check.")
            else:
                props_csv = ",".join(selected_actor_props)
                util = get_util()
                try:
                    result_full, result_summary = util.getDuplicatedActorsWithItems(actors, props_csv)
                    st.session_state["actor_dup_summary"] = result_summary
                    st.session_state["actor_dup_full"] = result_full
                except Exception as e:
                    st.error(f"Error running duplicate check: {e}")

        result_summary = st.session_state.get("actor_dup_summary")
        result_full = st.session_state.get("actor_dup_full")
        actor_details = st.session_state.get("actor_details")  # loaded on Contributors page

        if result_summary is not None:
            if result_summary.empty:
                st.success("No duplicate actors found.")
            else:
                n_groups = result_summary["name"].nunique()
                st.metric("Duplicate actor groups", n_groups)

                merged_groups = st.session_state.setdefault("merged_groups", {})   # key -> msg
                expander_open = st.session_state.setdefault("expander_open", {})  # key -> bool

                # One expander per duplicate-name group with inline merge controls
                for i, (name, group) in enumerate(result_summary.groupby("name")):
                    actor_ids = group["id"].tolist()
                    key = f"g{i}_{re.sub(r'[^a-zA-Z0-9]', '_', name)[:30]}"

                    with st.expander(f"{name} — {len(group)} actors",
                                     expanded=expander_open.get(key, False)):
                        # Build per-actor rows with email + one real item link
                        rows = []
                        for _, actor_row in group.iterrows():
                            actor_id = int(actor_row["id"])
                            items_count = len(actor_row["itemPersistentId"])

                            # First item this actor contributed to
                            item_url, item_label = "", ""
                            if result_full is not None:
                                contrib = result_full[result_full["id"] == actor_id]
                                if not contrib.empty:
                                    first = contrib.iloc[0]
                                    item_url = MP_SERVER + first.get("category", "") + "/" + first.get("persistentId", "")
                                    item_label = first.get("label", "")

                            row = {"id": actor_id, "items": items_count,
                                   "example item": item_label, "item link": item_url}

                            if actor_details is not None:
                                match = actor_details.loc[actor_details["id"] == actor_id, "email"]
                                row["email"] = match.iloc[0] if not match.empty else ""

                            rows.append(row)

                        disp = pd.DataFrame(rows)
                        col_cfg = {"item link": st.column_config.LinkColumn("Item link")}
                        st.dataframe(disp, use_container_width=True,
                                     column_config=col_cfg, hide_index=True)

                        st.divider()

                        # Merge controls
                        options = {
                            f"ID {row['id']}  ({len(row['itemPersistentId'])} item(s))": int(row["id"])
                            for _, row in group.iterrows()
                        }
                        keep_label = st.selectbox(
                            "Keep this actor (merge others into it):",
                            list(options.keys()),
                            key=f"sel_{key}",
                        )
                        keep_id = options[keep_label]
                        merge_ids = [a for a in actor_ids if a != keep_id]

                        already_merged = key in merged_groups
                        if already_merged:
                            st.success(merged_groups[key])

                        if st.button(
                            f"Merge {len(merge_ids)} actor(s) into ID {keep_id}",
                            key=f"btn_{key}",
                            type="primary",
                            disabled=already_merged,
                        ):
                            ok, msg = merge_actors(keep_id, merge_ids)
                            if ok:
                                merged_groups[key] = msg
                                expander_open[key] = True
                                load_actors.clear()
                                st.rerun()
                            else:
                                st.error(msg)

                st.divider()
                with st.expander("Full detail table"):
                    if result_full is not None:
                        full_disp_cols = [
                            c for c in ["MPUrl", "id", "name", "website", "role.label", "label", "category", "persistentId"]
                            if c in result_full.columns
                        ]
                        st.dataframe(result_full[full_disp_cols], use_container_width=True, hide_index=True)

                csv = result_summary.to_csv(index=False).encode("utf-8")
                st.download_button("Download CSV", csv, "actor_duplicates.csv", "text/csv")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — Orphaned Actors
# ─────────────────────────────────────────────────────────────────────────────
with tab_orphans:
    st.subheader("Actors with no associated items")
    st.markdown(
        "Actors in the Marketplace may exist without being credited on any item — "
        "for example, leftover entries from past imports or merges. "
        "This tool finds and removes them in three steps."
    )

    # ── Step 1: load full actor list from API ────────────────────────────────
    st.markdown("#### Step 1 — Load actors from the API")
    st.caption(
        "Fetches the complete actor list (~9 000 entries) across all pages. "
        "Results are shared with the Contributors and Actor Duplicates tabs."
    )

    actor_details: pd.DataFrame | None = st.session_state.get("actor_details")

    col_load, _ = st.columns([1, 2])
    with col_load:
        if st.button("Load / refresh actors from API", key="load_orphan_actors", use_container_width=True):
            with st.spinner("Fetching actors from API…"):
                try:
                    details = fetch_all_actors(env["api_url"], st.session_state["bearer"])
                    st.session_state["actor_details"] = details
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to fetch actors: {e}")

    if actor_details is None:
        st.info("Load actor data from the API above to continue.")
        st.stop()

    # ── Step 2: snapshot cross-reference → candidates ────────────────────────
    st.divider()
    st.markdown("#### Step 2 — Cross-reference with snapshot")
    st.caption(
        "The local snapshot lists every actor that is credited on at least one item. "
        "Actors absent from the snapshot are *candidates* — they may be orphaned, "
        "or the snapshot may simply be stale. The next step confirms which is which."
    )

    snapshot_actor_ids = set(load_actors()["id"].dropna().astype(int))
    candidates = actor_details[~actor_details["id"].isin(snapshot_actor_ids)].copy().reset_index(drop=True)

    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric("Total actors (API)", len(actor_details))
    col_m2.metric("Not in snapshot", len(candidates),
                  help="Absent from the current local snapshot — not yet confirmed orphans.")

    if candidates.empty:
        st.success("Every actor in the API appears in the snapshot — no candidates to investigate.")
        st.stop()

    # ── Step 3: live API verification ────────────────────────────────────────
    st.divider()
    st.markdown("#### Step 3 — Verify candidates via the live API")
    st.caption(
        f"Calls `GET /api/actors/{{id}}?items=true` for each of the {len(candidates)} candidates "
        "to check whether the API itself considers them item-free. "
        "Requests run in batches to avoid overloading the API."
    )

    verified: dict | None = st.session_state.get("orphan_verified")

    v_col, b_col, _ = st.columns([2, 1, 1])
    with b_col:
        batch_size = st.number_input(
            "Batch size", min_value=10, max_value=200, value=50, step=10,
            key="orphan_batch_size",
            help="Requests per batch. Each batch runs concurrently; batches are separated by a short pause.",
        )
    with v_col:
        if st.button(
            f"Verify {len(candidates)} candidates via API",
            use_container_width=True,
            key="btn_verify_orphans",
        ):
            verified = verify_orphans(
                candidates["id"].astype(int).tolist(),
                env["api_url"],
                st.session_state["bearer"],
                batch_size=int(batch_size),
            )
            st.session_state["orphan_verified"] = verified
            st.rerun()

    if verified is None:
        st.info("Run the verification above to see confirmed orphans.")
        st.stop()

    # Annotate candidates with verification result
    candidates["api_has_items"] = candidates["id"].map(lambda i: verified.get(int(i)))
    confirmed_orphans = candidates[candidates["api_has_items"] == False].copy().reset_index(drop=True)  # noqa: E712
    uncertain = candidates[candidates["api_has_items"].isna()]

    col_m3.metric("Confirmed orphans (API)", len(confirmed_orphans),
                  help="API returned items=[] for these actors.")

    if not uncertain.empty:
        with st.expander(f"{len(uncertain)} actor(s) could not be verified — API errors or timeouts"):
            st.caption("These were excluded from the delete list. Re-run verification to retry them.")
            st.dataframe(uncertain[["id", "name", "email", "website"]].fillna(""),
                         use_container_width=True, hide_index=True)

    if confirmed_orphans.empty:
        st.success("All candidates have items on the live API — nothing to delete.")
        st.stop()

    # ── Step 4: review and delete ─────────────────────────────────────────────
    st.divider()
    st.markdown("#### Step 4 — Review and delete")
    st.markdown(
        "Check the actors you want to remove. "
        "Deletion uses `force=false`: actors that are affiliated with other actors "
        "(e.g. a researcher listed under a university) will be **refused by the API** "
        "and reported below — they are never silently skipped."
    )

    display = confirmed_orphans[["id", "name", "email", "website"]].fillna("").copy()
    display.insert(0, "delete", False)

    edited = st.data_editor(
        display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "delete": st.column_config.CheckboxColumn("Delete?", default=False),
            "id": st.column_config.NumberColumn("ID"),
            "website": st.column_config.LinkColumn("Website"),
        },
        disabled=["id", "name", "email", "website"],
        key="orphan_editor",
    )

    to_delete = edited[edited["delete"]]["id"].tolist()

    st.divider()

    if not to_delete:
        st.info("No actors selected — tick 'Delete?' in the table above to select.")
    else:
        st.error(
            f"**{len(to_delete)} actor(s) selected for deletion.**  \n"
            "This cannot be undone. Actors affiliated with others will be refused by the API and left intact."
        )
        confirmed_cb = st.checkbox(
            f"I understand that up to {len(to_delete)} actor(s) will be permanently deleted",
            key="orphan_confirm",
        )
        if st.button(
            f"Delete {len(to_delete)} actor(s)",
            type="primary",
            disabled=not confirmed_cb,
            key="btn_delete_orphans",
        ):
            successes, failures = [], []
            bar = st.progress(0, text=f"Deleting… 0 / {len(to_delete)}")
            for i, actor_id in enumerate(to_delete, 1):
                ok, msg = delete_actor(int(actor_id))
                (successes if ok else failures).append((actor_id, msg))
                bar.progress(i / len(to_delete), text=f"Deleting… {i} / {len(to_delete)}")
            bar.empty()

            if successes:
                st.success(f"Deleted {len(successes)} actor(s).")
            if failures:
                st.warning(
                    f"{len(failures)} actor(s) were not deleted "
                    "(affiliated with other actors, or an API error):"
                )
                for aid, msg in failures:
                    st.write(f"- ID {aid}: {msg}")

            # Remove deleted actors from both caches; keep orphan_verified
            # so the table stays open showing the remaining actors.
            deleted_ids = {aid for aid, _ in successes}
            remaining_ids = set(actor_details["id"]) - deleted_ids
            st.session_state["actor_details"] = actor_details[
                actor_details["id"].isin(remaining_ids)
            ].reset_index(drop=True)
            for aid in deleted_ids:
                st.session_state["orphan_verified"].pop(int(aid), None)
            st.rerun()

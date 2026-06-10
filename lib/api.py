import time
import requests
import pandas as pd
import streamlit as st
from lib.logger import log_action, log_api


def fetch_all_actors(api_url: str, bearer: str) -> pd.DataFrame:
    """
    Fetch all actors from GET /api/actors (paginated, 100/page) using the
    provided bearer token. Returns a DataFrame with columns:
    id, name, email, website.
    """
    url = f"{api_url}/api/actors"
    headers = {"Authorization": bearer}

    resp = requests.get(f"{url}?perpage=100&page=1", headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    total_pages = data.get("pages", 1)
    all_actors = list(data.get("actors", []))

    bar = st.progress(1 / max(total_pages, 1), text=f"Loading actors… 1 / {total_pages}")
    for page in range(2, total_pages + 1):
        r = requests.get(f"{url}?perpage=100&page={page}", headers=headers, timeout=15)
        r.raise_for_status()
        all_actors.extend(r.json().get("actors", []))
        bar.progress(page / total_pages, text=f"Loading actors… {page} / {total_pages}")
    bar.empty()

    if not all_actors:
        return pd.DataFrame(columns=["id", "name", "email", "website", "item_count"])

    df = pd.json_normalize(all_actors)
    for col in ["email", "website", "items"]:
        if col not in df.columns:
            df[col] = pd.NA
    df["item_count"] = df["items"].apply(
        lambda x: len(x) if isinstance(x, list) else (0 if pd.isna(x) else int(x))
    )
    result = df[["id", "name", "email", "website", "item_count"]].copy()
    log_action(f"Fetched {len(result)} actors from API ({api_url})")
    return result


def _check_one_actor(actor_id: int, api_url: str, bearer: str, retries: int = 3) -> tuple[int, bool | None]:
    """
    GET /api/actors/{id}?items=true with retry on transient errors.
    Returns (actor_id, has_items). None means uncertain after all retries.
    """
    url = f"{api_url}/api/actors/{actor_id}?items=true"
    headers = {"Authorization": bearer}
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                try:
                    items = resp.json().get("items", [])
                    return actor_id, len(items) > 0 if isinstance(items, list) else bool(items)
                except ValueError:
                    return actor_id, None  # malformed JSON
            if resp.status_code == 404:
                return actor_id, False  # actor gone — no items by definition
            if resp.status_code >= 500 and attempt < retries - 1:
                time.sleep(0.5 * (attempt + 1))
                continue
            return actor_id, None  # 4xx or exhausted retries
        except requests.exceptions.Timeout:
            if attempt < retries - 1:
                time.sleep(0.5)
                continue
        except requests.exceptions.ConnectionError:
            if attempt < retries - 1:
                time.sleep(1.0 * (attempt + 1))
                continue
        except Exception:
            return actor_id, None
    return actor_id, None


def verify_orphans(
    candidate_ids: list[int],
    api_url: str,
    bearer: str,
    batch_size: int = 50,
) -> dict[int, bool | None]:
    """
    Verify each candidate actor in batches. Within each batch requests run
    concurrently; a short pause between batches reduces pressure on the API.
    Returns a dict mapping actor_id → has_items (True/False/None-if-failed).
    Renders a Streamlit progress bar while running.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    results: dict[int, bool | None] = {}
    total = len(candidate_ids)
    bar = st.progress(0, text=f"Verifying… 0 / {total}")

    for batch_start in range(0, total, batch_size):
        batch = candidate_ids[batch_start : batch_start + batch_size]
        with ThreadPoolExecutor(max_workers=len(batch)) as pool:
            futures = {
                pool.submit(_check_one_actor, aid, api_url, bearer): aid
                for aid in batch
            }
            for future in as_completed(futures):
                aid, has_items = future.result()
                results[aid] = has_items
        done = min(batch_start + batch_size, total)
        bar.progress(done / total, text=f"Verifying… {done} / {total}")
        if done < total:
            time.sleep(0.3)  # brief pause between batches

    bar.empty()
    orphaned = sum(1 for v in results.values() if v is False)
    uncertain = sum(1 for v in results.values() if v is None)
    log_action(
        f"Verified {total} actor candidates — "
        f"{orphaned} orphaned, {uncertain} uncertain"
    )
    return results


def delete_actor(actor_id: int) -> tuple[bool, str]:
    """DELETE /api/actors/{actor_id}. Returns (success, message)."""
    env = st.session_state["env"]
    bearer = st.session_state["bearer"]
    url = f"{env['api_url']}/api/actors/{actor_id}?force=false"
    try:
        resp = requests.delete(url, headers={"Authorization": bearer}, timeout=15)
        ok = resp.status_code in (200, 204)
        log_api(
            "DELETE", url,
            f"Delete actor {actor_id} (force=false)",
            status=resp.status_code,
            response=resp.text[:300],
            ok=ok,
        )
        if ok:
            return True, f"Actor {actor_id} deleted."
        return False, f"API returned {resp.status_code}: {resp.text[:200]}"
    except requests.RequestException as e:
        log_api("DELETE", url, f"Delete actor {actor_id} — request failed", status="error",
                response=str(e), ok=False)
        return False, f"Request failed: {e}"


def fetch_all_keyword_concepts(api_url: str, bearer: str) -> pd.DataFrame:
    """
    GET /api/concept-search?types=keyword — paginate through all pages.
    No auth required for reads, but bearer is passed for consistency.
    Returns a DataFrame with columns: code, label, uri, notation, candidate, definition.
    """
    url = f"{api_url}/api/concept-search"
    headers = {"Authorization": bearer}
    params = {"types": "keyword", "perpage": 100, "page": 1}

    resp = requests.get(url, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    total_pages = data.get("pages", 1)
    all_concepts = list(data.get("concepts", []))

    if total_pages > 1:
        bar = st.progress(1 / total_pages, text=f"Loading concepts… 1 / {total_pages}")
        for page in range(2, total_pages + 1):
            r = requests.get(url, headers=headers,
                             params={**params, "page": page}, timeout=15)
            r.raise_for_status()
            all_concepts.extend(r.json().get("concepts", []))
            bar.progress(page / total_pages, text=f"Loading concepts… {page} / {total_pages}")
        bar.empty()

    if not all_concepts:
        return pd.DataFrame(columns=["code", "label", "uri", "notation", "candidate", "definition"])

    df = pd.json_normalize(all_concepts)
    for col in ["code", "label", "uri", "notation", "candidate", "definition"]:
        if col not in df.columns:
            df[col] = pd.NA
    return df[["code", "label", "uri", "notation", "candidate", "definition"]].copy()


def fetch_all_concepts(api_url: str, bearer: str) -> pd.DataFrame:
    """
    GET /api/concept-search (all types, all vocabularies) — paginated.
    Returns a DataFrame with columns: code, label, uri, notation,
    candidate, definition, vocabulary_code, type_code.
    """
    url = f"{api_url}/api/concept-search"
    headers = {"Authorization": bearer}
    params = {"perpage": 100, "page": 1}

    resp = requests.get(url, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    total_pages = data.get("pages", 1)
    all_concepts = list(data.get("concepts", []))

    bar = st.progress(1 / total_pages, text=f"Loading concepts… 1 / {total_pages}")
    for page in range(2, total_pages + 1):
        r = requests.get(url, headers=headers, params={**params, "page": page}, timeout=15)
        r.raise_for_status()
        all_concepts.extend(r.json().get("concepts", []))
        bar.progress(page / total_pages, text=f"Loading concepts… {page} / {total_pages}")
    bar.empty()

    if not all_concepts:
        return pd.DataFrame(columns=["code", "label", "uri", "notation",
                                     "candidate", "definition", "vocabulary_code", "type_code"])

    df = pd.json_normalize(all_concepts)
    if "vocabulary.code" in df.columns:
        df = df.rename(columns={"vocabulary.code": "vocabulary_code"})
    elif "vocabulary_code" not in df.columns:
        df["vocabulary_code"] = pd.NA

    # types is a list; take the code of the first entry
    if "types" in df.columns:
        df["type_code"] = df["types"].apply(
            lambda t: t[0]["code"] if isinstance(t, list) and t else pd.NA
        )
    else:
        df["type_code"] = pd.NA

    for col in ["code", "label", "uri", "notation", "candidate", "definition"]:
        if col not in df.columns:
            df[col] = pd.NA

    return df[["code", "label", "uri", "notation",
               "candidate", "definition", "vocabulary_code", "type_code"]].copy()


_CATEGORY_PATH = {
    "tool-or-service":   "tools-services",
    "training-material": "training-materials",
    "dataset":           "datasets",
    "publication":       "publications",
    "workflow":          "workflows",
    "step":              "steps",
}


def _item_url(api_url: str, category: str, persistent_id: str) -> str:
    path = _CATEGORY_PATH.get(category, category + "s")
    return f"{api_url}/api/{path}/{persistent_id}"


def get_item(category: str, persistent_id: str, api_url: str, bearer: str) -> dict:
    resp = requests.get(
        _item_url(api_url, category, persistent_id),
        headers={"Authorization": bearer},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def put_item(category: str, persistent_id: str, item_data: dict,
             api_url: str, bearer: str) -> tuple[bool, str]:
    import json as _json
    url = _item_url(api_url, category, persistent_id)
    resp = requests.put(
        url,
        headers={"Content-Type": "application/json", "Authorization": bearer},
        json=item_data,
        timeout=30,
    )
    ok = resp.status_code in (200, 201)
    log_api(
        "PUT", url,
        f"Update {category}/{persistent_id}",
        status=resp.status_code,
        request=_json.dumps({"persistentId": persistent_id, "category": category,
                             "label": item_data.get("label", "")})[:500],
        response=resp.text[:300],
        ok=ok,
    )
    if ok:
        return True, "Updated."
    return False, f"HTTP {resp.status_code}: {resp.text[:300]}"


def fix_item_keyword(
    category: str,
    persistent_id: str,
    old_concept_code: str,
    new_type_code: str,
    new_concept: dict,
    api_url: str,
    bearer: str,
) -> tuple[bool, str]:
    """
    GET the item, replace every property whose type=keyword and
    concept.code=old_concept_code with new_type_code / new_concept, PUT back.
    """
    try:
        item = get_item(category, persistent_id, api_url, bearer)
    except Exception as e:
        return False, f"GET failed: {e}"

    changed = False
    for prop in item.get("properties", []):
        if (prop.get("type", {}).get("code") == "keyword"
                and prop.get("concept", {}).get("code") == old_concept_code):
            prop["type"]["code"] = new_type_code
            prop["concept"] = new_concept
            changed = True

    if not changed:
        return False, "Property not found in item."

    return put_item(category, persistent_id, item, api_url, bearer)


def delete_concept(concept_code: str, vocab_code: str = "sshoc-keyword") -> tuple[bool, str]:
    """
    DELETE /api/vocabularies/{vocab_code}/concepts/{concept_code}?force=true

    force=true is required when the concept is referenced by existing item properties;
    the API will also remove those property references from the affected items.
    """
    env = st.session_state["env"]
    bearer = st.session_state["bearer"]
    url = f"{env['api_url']}/api/vocabularies/{vocab_code}/concepts/{concept_code}?force=true"
    try:
        resp = requests.delete(url, headers={"Authorization": bearer}, timeout=15)
        ok = resp.status_code in (200, 204)
        log_api(
            "DELETE", url,
            f"Delete concept '{concept_code}' from vocab '{vocab_code}' (force=true)",
            status=resp.status_code,
            response=resp.text[:300],
            ok=ok,
        )
        if ok:
            return True, f"Concept '{concept_code}' deleted."
        return False, f"API returned {resp.status_code}: {resp.text[:200]}"
    except requests.RequestException as e:
        log_api("DELETE", url, f"Delete concept '{concept_code}' — request failed",
                status="error", response=str(e), ok=False)
        return False, f"Request failed: {e}"


_CATEGORY_FETCH = [
    ("tools-services",     "tools"),
    ("publications",       "publications"),
    ("training-materials", "trainingMaterials"),
    ("workflows",          "workflows"),
    ("datasets",           "datasets"),
]


_SNAPSHOT_PERPAGE = 20   # smaller pages → shorter per-request response time
_SNAPSHOT_TIMEOUT = 60   # seconds per request
_SNAPSHOT_RETRIES = 3    # retries on timeout / 5xx before giving up


def _fetch_page(url: str, headers: dict, page: int, retries: int = _SNAPSHOT_RETRIES) -> dict:
    """GET a single paginated page with retry on timeout or 5xx."""
    paged = f"{url}?perpage={_SNAPSHOT_PERPAGE}&page={page}"
    for attempt in range(retries):
        try:
            resp = requests.get(paged, headers=headers, timeout=_SNAPSHOT_TIMEOUT)
            if resp.status_code < 500:
                resp.raise_for_status()
                return resp.json()
            # 5xx — wait and retry
        except requests.exceptions.Timeout:
            pass  # retry below
        if attempt < retries - 1:
            time.sleep(2 ** attempt)  # 1 s, 2 s back-off
    raise RuntimeError(
        f"Failed to fetch {paged} after {retries} attempts "
        f"(timeout={_SNAPSHOT_TIMEOUT}s)"
    )


def create_snapshot_from_api(api_url: str, bearer: str, data_dir) -> tuple[bool, str]:
    """
    Fetch all items from all 5 categories and save as full_items_{ts}.json.
    Uses small page sizes and retries to handle slow category endpoints.
    Returns (success, message).
    """
    import json
    import time as _time
    import pathlib as _pathlib

    headers = {"Authorization": bearer}
    all_items: list = []
    n_cats = len(_CATEGORY_FETCH)
    bar = st.progress(0.0, text="Starting…")

    for cat_idx, (path, items_key) in enumerate(_CATEGORY_FETCH):
        url = f"{api_url}/api/{path}"

        # First page — also gives us the total page count
        try:
            data = _fetch_page(url, headers, page=1)
        except Exception as e:
            bar.empty()
            return False, f"Failed to fetch {path}: {e}"

        total_pages = data.get("pages", 1)
        all_items.extend(data.get(items_key, []))
        bar.progress(
            (cat_idx + 1 / max(total_pages, 1)) / n_cats,
            text=f"{path}: page 1 / {total_pages}",
        )

        for page in range(2, total_pages + 1):
            try:
                r = _fetch_page(url, headers, page=page)
                all_items.extend(r.get(items_key, []))
            except Exception as e:
                bar.empty()
                return False, f"Failed fetching {path} page {page}: {e}"
            bar.progress(
                (cat_idx + page / total_pages) / n_cats,
                text=f"{path}: page {page} / {total_pages}",
            )

    bar.empty()
    ts = int(_time.time())
    out_path = _pathlib.Path(data_dir) / f"full_items_{ts}.json"
    try:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(all_items, fh)
    except Exception as e:
        log_action(f"Snapshot creation failed: {e}", ok=False)
        return False, f"Failed to save snapshot: {e}"

    msg = f"Created snapshot {out_path.name} with {len(all_items)} items from {api_url}"
    log_action(msg)
    return True, f"Created {out_path.name} with {len(all_items)} items."


def merge_actors(keep_id: int, merge_ids: list) -> tuple[bool, str]:
    """
    POST /api/actors/{keep_id}/merge?with={merge_ids}
    Returns (success, message).
    """
    env = st.session_state["env"]
    bearer = st.session_state["bearer"]
    with_param = ",".join(str(i) for i in merge_ids)
    url = f"{env['api_url']}/api/actors/{keep_id}/merge?with={with_param}"
    try:
        resp = requests.post(
            url,
            headers={"Content-Type": "application/json", "Authorization": bearer},
            timeout=15,
        )
        ok = resp.status_code == 200
        log_api(
            "POST", url,
            f"Merge actor(s) {merge_ids} into {keep_id}",
            status=resp.status_code,
            response=resp.text[:300],
            ok=ok,
        )
        if ok:
            return True, f"Actor(s) {merge_ids} merged into {keep_id}."
        return False, f"API returned {resp.status_code}: {resp.text[:200]}"
    except requests.RequestException as e:
        log_api("POST", url, f"Merge actors {merge_ids} into {keep_id} — request failed",
                status="error", response=str(e), ok=False)
        return False, f"Request failed: {e}"

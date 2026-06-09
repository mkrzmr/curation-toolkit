# SSH Open Marketplace — Curation Toolkit

A local Streamlit web application for curating the [SSH Open Marketplace](https://marketplace.sshopencloud.eu/) (SSHOMP). It reads data from a local [sshompitor](https://github.com/SSHOC/sshompitor) snapshot for fast offline analysis and writes back to the live Marketplace API for any changes.

---

## Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Setup](#setup)
4. [Running the app](#running-the-app)
5. [Architecture](#architecture)
6. [Login & environments](#login--environments)
7. [Tool reference](#tool-reference)
   - [Contributors](#contributors)
   - [Duplicates](#duplicates)
   - [URL Checker](#url-checker)
   - [Keywords](#keywords)
8. [Data freshness](#data-freshness)
9. [API reference](#api-reference)
10. [Library reference](#library-reference)
11. [Caveats & known limitations](#caveats--known-limitations)
12. [Troubleshooting](#troubleshooting)

---

## Overview

The SSH Open Marketplace accumulates data quality issues over time: duplicate actors, broken access URLs, orphaned entries, and keywords that duplicate concepts already defined in controlled vocabularies. These issues are difficult to spot and fix through the standard Marketplace web interface.

This toolkit provides a set of purpose-built curation screens that:

- Load the full Marketplace dataset from a local snapshot for fast, offline analysis
- Verify findings against the live API before making any changes
- Write changes back through the official Marketplace REST API with appropriate safeguards

The toolkit is intended for Marketplace **moderators and administrators**. All write operations require a valid account token and respect the API's own permission checks.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.10+ | Tested on 3.10–3.12 |
| Marketplace account | Moderator or administrator role required for write operations |

No local clone of sshompitor is required. The `sshmarketplacelib` Python package is installed directly from GitHub as part of the normal dependency install, and a bundled `config.yaml` provides the configuration it needs. Snapshot data is downloaded automatically on first use.

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

This installs all required packages including `sshmarketplacelib` (pulled directly from the [sshompitor GitHub repository](https://github.com/SSHOC/sshompitor)):

```
streamlit>=1.35, pandas, numpy, pyyaml, pillow, requests, fastparquet, sshmarketplacelib
```

### 2. Create the data directory

```bash
python3 setup.py
```

This creates the `data/` directory where snapshot files will be stored. That is all — no symlinks or local sshompitor clone required.

### 3. Download the first snapshot

Start the app (see below), log in, and click **Get latest data from GitHub** in the sidebar. This downloads the current snapshot (~70 MB) from the sshompitor repository automatically.

Alternatively, place any `full_items_*.json` file in the `data/` directory manually.

---

## Running the app

```bash
streamlit run app.py
```

Then open [http://localhost:8501](http://localhost:8501) in a browser. The app remains running until you press `Ctrl+C` in the terminal.

---

## Architecture

### Data flow

```
GitHub (SSHOC/sshompitor) ──► data/full_items_*.json  (downloaded on demand)
                                        │
                                        ▼
                          sshmarketplacelib.Util  (loaded once, cached as st.cache_resource)
                │
                ├── getContributors()     ──► Contributors page
                ├── _load_snapshot()      ──► Duplicates / URL Checker
                ├── getDuplicates()       ──► Item Duplicates tab
                ├── getDuplicatedActors…  ──► Actor Duplicates tab
                └── getAllProperties()    ──► Keywords page

Live Marketplace API  ◄──► lib/api.py  ◄──► all write operations + actor verification
```

### Streamlit multi-page structure

The app follows Streamlit's file-based page routing. `app.py` is the entry point (login). Each file in `pages/` becomes a navigation item. Page order is set by the filename prefix (`1_`, `2_`, etc.).

### Session state

Streamlit reruns the entire script on every user interaction. Persistent data is stored in `st.session_state`:

| Key | Type | Set by | Used by |
|---|---|---|---|
| `authenticated` | `bool` | Login page | All pages (via `require_login()`) |
| `bearer` | `str` | Login page | All API calls |
| `env` | `dict` | Login page | All pages |
| `actor_details` | `DataFrame` | Contributors / Duplicates | Contributors, Duplicates |
| `actor_dup_summary` | `DataFrame` | Duplicates | Duplicates |
| `actor_dup_full` | `DataFrame` | Duplicates | Duplicates |
| `merged_groups` | `dict` | Duplicates | Duplicates (disables merge buttons) |
| `expander_open` | `dict` | Duplicates | Duplicates (keeps expanders open after merge) |
| `orphan_verified` | `dict` | Duplicates | Duplicates (orphan verification results) |
| `url_check_input` | `DataFrame` | URL Checker | URL Checker |
| `url_check_results` | `DataFrame` | URL Checker | URL Checker |
| `keyword_vocab` | `DataFrame` | Keywords | Keywords |
| `all_concepts_cache` | `DataFrame` | Keywords | Keywords |

### Caching

| Decorator | Used for | Invalidated when |
|---|---|---|
| `@st.cache_resource` | `Util()` instance (loads the ~72 MB snapshot once) | Snapshot refreshed from GitHub |
| `@st.cache_data` | Per-page derived DataFrames | Snapshot refreshed, or explicitly via `.clear()` |

---

## Login & environments

The login screen lets you choose between **Production** and **Stage** before signing in.

| Environment | API base URL |
|---|---|
| Production | `https://marketplace-api.sshopencloud.eu` |
| Stage | `https://sshoc-marketplace-api-stage.acdh-dev.oeaw.ac.at` |

Credentials are sent via `POST /api/auth/sign-in`. On success the `Authorization` header from the response is stored as a bearer token in session state and attached to all subsequent API requests.

Navigating directly to any tool page without being logged in redirects back to the login screen (`require_login()` in `lib/auth.py`).

> **Recommendation**: always test changes on **Stage** first. The Stage environment is a full copy of Production and its data can be reset.

---

## Tool reference

### Contributors

**File:** `pages/1_Contributors.py`

Displays every actor–item contribution relationship from the current snapshot as a filterable, sortable table.

#### Data source

Built from `Util.getContributors()`, which reads the snapshot and returns one row per actor–item pair. Each row includes the item's `category`, `persistentId`, `label`, the actor's `name`, `website`, and the contribution `role.label`.

The `MPUrl` column is constructed as `{mp_url}{category}/{persistentId}` and links to the contributed item. Actors do not have dedicated public profile pages in the Marketplace.

#### Email filter

Actor email addresses are not stored in the snapshot — they are only returned by the authenticated API. Click **Load actor emails from API** in the sidebar to fetch all ~9,000 actors and join their email addresses into the table. This data is stored in `st.session_state["actor_details"]` and is reused across pages without re-fetching.

Once loaded, a free-text email filter appears in the sidebar.

#### Filters

| Filter | Behaviour |
|---|---|
| Category | Multiselect; defaults to all categories |
| Role | Multiselect; defaults to all roles |
| Actor name | Case-insensitive substring match |
| Actor email | Case-insensitive substring match; only shown after actor data is loaded |

#### Export

The filtered view can be downloaded as CSV. Columns: actor name, email (if loaded), role, item label, category, persistent ID, actor website, item link.

---

### Duplicates

**File:** `pages/2_Duplicates.py`

Three tabs for finding and resolving duplicate data.

---

#### Tab 1 — Item Duplicates

Scans snapshot items for shared values in selected fields.

**How to use:**
1. Select one or more categories to narrow the search scope.
2. Choose which fields to check: `label`, `description`, `accessibleAt`.
3. Click **Find Duplicates**.

Internally calls `Util.getDuplicates(subset, fields_csv)` from sshompitor. Results include the matched field values and links to each item in the Marketplace. Download as CSV for offline review.

---

#### Tab 2 — Actor Duplicates

Finds actors that share a `name` or `website` value. These are common when items are imported from different sources with slightly different contributor metadata.

**How to use:**
1. Select which field(s) to check: `name`, `website`.
2. Click **Find Duplicates**.

Results are grouped by duplicate name. For each group, an expander shows:
- A table with each actor's ID, item count, example item, and email (if actor data is loaded)
- A **Keep this actor** selectbox — the chosen actor absorbs the others
- A **Merge** button

**Merge behaviour:**
- Calls `POST /api/actors/{keep_id}/merge?with={other_ids}`
- The API merges all item associations and external IDs into the kept actor and deletes the others
- The merge button is disabled after a successful merge and remains disabled on page reload (stored in `merged_groups` session state)
- The results table and expander stay open — you do not need to re-run the duplicate search to see remaining groups

The underlying data for duplicate detection is from the snapshot. After merging, the snapshot is stale with respect to actor counts; re-running the search after refreshing the snapshot will reflect the merge.

---

#### Tab 3 — Orphaned Actors

Finds actors that are not associated with any Marketplace item and allows bulk deletion.

The process runs in four explicit steps:

**Step 1 — Load actors from the API**

Fetches the full actor list from `GET /api/actors` (paginated, 100 actors per page, ~95 pages for ~9,400 actors). This data is shared with the Contributors page — if you have already loaded actor emails there, you can skip this step. The API does not return item associations in the paginated listing, so item counts cannot be determined here.

**Step 2 — Cross-reference with snapshot**

The snapshot lists every actor that is credited on at least one item. Actors that appear in the API but not in the snapshot are flagged as **candidates**. A stale snapshot will produce false positives — actors that have been added to items after the snapshot was taken will appear here even though they are not orphaned.

**Step 3 — Verify candidates via the live API**

For each candidate, calls `GET /api/actors/{id}?items=true` and checks whether the response contains any items. This is the authoritative check.

Requests run in configurable batches (default: 50 concurrent per batch, adjustable via the sidebar input). A 300 ms pause between batches avoids overloading the API. Each request retries up to three times on HTTP 5xx errors, timeouts, and connection errors before being classified as **uncertain**. Uncertain actors are shown in a separate expander and excluded from deletion.

The verification result is stored in session state. You do not need to re-verify unless you reload actor data.

**Step 4 — Review and delete**

Confirmed orphans are shown in an editable table. All rows start **unchecked** — you must explicitly select actors for deletion.

Deletion calls `DELETE /api/actors/{id}?force=false`. The `force=false` parameter means the API will refuse to delete an actor that is affiliated with another actor (e.g. a researcher listed under a university). Refused deletions are reported individually and the actor is left intact. Successfully deleted actors are removed from session state immediately so the table updates without a full reload.

---

### URL Checker

**File:** `pages/3_URL_Checker.py`

Checks whether URLs in the snapshot are reachable, and surfaces items with broken or unreachable links.

#### Scope modes

| Mode | What is checked |
|---|---|
| `accessibleAt only` | The primary access URLs for each item (the `accessibleAt` field, which may be a list) |
| `All URLs in entry` | Every `http(s)` URL found in any field of the item, including thumbnails, media, external IDs, and descriptions |

#### Workflow

1. Select categories and scope, then click **Extract URLs**. The tool scans the snapshot and reports how many unique URLs were found and how many items they span — no HTTP requests are made yet.
2. Set **Timeout** (default 10 s) and **Parallel workers** (default 20), then click **Check URLs**.
3. Each URL is checked with an HTTP `HEAD` request. Servers that respond with `405 Method Not Allowed` or `501 Not Implemented` are retried with a streaming `GET` (connection closed immediately after headers).
4. Results are stored in session state. Changing filters or scope and clicking Extract/Check again overwrites the previous results.

#### Results

The results table is sorted by **items with the most broken URLs first**, then by item, then broken-before-OK within each item. A `Broken URLs` column shows the per-item count so the worst offenders are immediately visible.

Filter the view to **Broken only**, **OK only**, or **All** using the radio buttons. Each row links to both the checked URL and the item it belongs to. Download as CSV.

#### Deduplication

The same URL appearing on 50 different items is checked once. The result is joined back to all 50 rows.

---

### Keywords

**File:** `pages/4_Keywords.py`

Audits and curates the `sshoc-keyword` vocabulary — the open-ended keyword vocabulary where Marketplace users can propose new terms.

Unlike the other Marketplace vocabularies (languages, disciplines, standards, etc.), the keyword vocabulary grows organically and is not formally governed. This leads to three classes of quality issues:

1. **Unused concepts** — keywords registered in the vocabulary but not applied to any item
2. **Malformed labels** — keywords with leading spaces, no alphabetical characters, or excessive length
3. **Cross-vocabulary duplicates** — keywords whose labels already exist as concepts in a controlled vocabulary (e.g. `xml` duplicating the `xml` concept in the `standard` vocabulary)

#### Loading data

Click **Load keyword concepts from API** to fetch all concepts in the `sshoc-keyword` vocabulary from `GET /api/concept-search?types=keyword`. This returns all ~2,600 concepts across ~27 pages (100 per page) regardless of whether they are used on any item.

Keywords are also extracted from the local snapshot via `Util.getAllProperties()`, giving one row per item–keyword pair. These two datasets are cross-referenced by concept code (both use the same identifier system).

#### The `candidate` flag

The API marks concepts as `candidate: true` if they were submitted by a user but not yet formally reviewed. Most unused concepts are candidates. The **Candidates only** checkbox in the Unused tab lets you filter to this subset.

---

#### Tab 1 — Unused

Concepts registered in the vocabulary that do not appear on any item in the current snapshot. These are candidates for removal.

**Filters:** free-text search on label or code; toggle to show only candidate concepts.

**Deletion:** tick the `Delete?` checkbox for each concept to remove, confirm the irreversibility checkbox, and click **Delete**. Calls `DELETE /api/vocabularies/sshoc-keyword/concepts/{code}`. Successfully deleted concepts are removed from the in-session vocabulary immediately so the table stays open and reflects the current state.

> Note: snapshot freshness matters here. If the snapshot is stale, a concept used in a recently-added item may appear as unused. Refresh the snapshot before running bulk deletions.

---

#### Tab 2 — In use

All concepts that appear on at least one item, sorted by usage count descending.

**Quality filters** (independent, combinable):

| Filter | Detects |
|---|---|
| Starts with space | Labels like `" machine learning"` that sort and display incorrectly |
| No letters | Labels composed entirely of numbers or symbols (e.g. `"3D"` passes, `"123"` or `"???"` do not) |
| Longer than N characters | Labels that are suspiciously long — often pasted text rather than a proper keyword |

---

#### Tab 3 — Duplicates in other vocabs

Finds keywords whose label also exists as a concept in another Marketplace vocabulary. Example: `xml` in `sshoc-keyword` duplicates the `xml` concept in the `standard` vocabulary.

**How to use:**
1. Click **Load all concepts from API (~15 000)** to fetch all concepts across all vocabularies. This takes 1–2 minutes (152 pages at 100 per page) and is cached in session state.
2. The tool performs a case-insensitive label match between `sshoc-keyword` concepts and all other-vocabulary concepts.
3. Use the **concept type filter** to narrow results — for example, show only overlaps with `standard` or `discipline` concepts.

**Fixing items:**

When a keyword duplicates a controlled vocabulary concept, items using that keyword should be updated to reference the correct concept instead. The **Fix an entry** section below the results table provides a one-at-a-time workflow:

1. Select a keyword → target concept pair from the dropdown (e.g. `xml → xml [standard / standard]`).
2. The tool shows all items using that keyword. A warning is shown if more than one item will be affected.
3. Click **Fix N item(s)**.

For each affected item, the tool:
- Calls `GET /api/{category-path}/{persistentId}` to retrieve the full item payload
- Finds the property with `type.code = "keyword"` and `concept.code = {old_code}`
- Updates the property's `type.code` to the target type (e.g. `"standard"`) and replaces the `concept` object with the target concept's code, label, URI, and vocabulary
- Calls `PUT /api/{category-path}/{persistentId}` with the modified payload

Results are shown per-item so you can verify each one.

> **Important:** the PUT endpoint receives the complete item payload retrieved by GET. Only the matching property is modified; all other fields are unchanged. If the item has been edited by someone else between the GET and PUT, those concurrent changes will be overwritten.

---

#### Tab 4 — All concepts

Complete `sshoc-keyword` vocabulary with usage counts from the current snapshot. Searchable by label or code. Sortable by any column.

---

## Data freshness

The local snapshot is a JSON export of the full Marketplace catalogue. Snapshot filenames embed a Unix timestamp (`full_items_{timestamp}.json`) which the app uses to calculate age.

A **data age badge** appears in the sidebar of every page:
- **Green** — snapshot is less than 3 days old
- **Orange** — snapshot is 3 or more days old (warning)

Click **Get latest data from GitHub** to download the newest snapshot from the [sshompitor data directory](https://github.com/SSHOC/sshompitor/tree/main/data). The download streams in chunks with a progress bar (snapshots are typically 60–75 MB). After download, all page caches are cleared automatically.

A stale snapshot affects:
- **Orphaned actors** — recently-contributed actors may appear as candidates
- **Unused keywords** — recently-added keywords may appear as unused
- **Actor duplicate detection** — recently-merged actors may still appear as duplicates

---

## API reference

All write operations target the environment selected at login. Read operations may be unauthenticated where the API permits.

| Operation | Method | Endpoint | Notes |
|---|---|---|---|
| Login | POST | `/api/auth/sign-in` | Returns bearer token in `Authorization` header |
| List actors (paginated) | GET | `/api/actors?perpage=100&page={n}` | ~95 pages for full list |
| Check actor items | GET | `/api/actors/{id}?items=true` | Authoritative orphan check |
| Merge actors | POST | `/api/actors/{id}/merge?with={ids}` | Comma-separated list of IDs to absorb |
| Delete actor | DELETE | `/api/actors/{id}?force=false` | Refused if actor has affiliations |
| Get item | GET | `/api/{category-path}/{persistentId}` | Full item payload |
| Update item | PUT | `/api/{category-path}/{persistentId}` | Requires full item payload |
| List keyword concepts | GET | `/api/concept-search?types=keyword&perpage=100` | ~27 pages for full list |
| List all concepts | GET | `/api/concept-search?perpage=100` | ~152 pages; all vocabularies |
| Delete concept | DELETE | `/api/vocabularies/{vocab}/concepts/{code}` | Removes from vocabulary |

### Category path mapping

Item GET and PUT use pluralised paths that differ from the `category` field in the snapshot:

| Snapshot `category` | API path segment |
|---|---|
| `tool-or-service` | `tools-services` |
| `training-material` | `training-materials` |
| `dataset` | `datasets` |
| `publication` | `publications` |
| `workflow` | `workflows` |
| `step` | `steps` |

---

## Library reference

### `lib/environments.py`

Defines the two target environments (Production and Stage) with their API base URLs and frontend URLs. The `DEFAULT_ENV` constant sets which environment is pre-selected at login.

### `lib/auth.py`

`try_login(username, password, env_name)` — posts credentials to `/api/auth/sign-in` and returns the bearer token string, or `None` on failure.

`require_login()` — called at the top of every page file. Redirects to the login page and stops rendering if the session is unauthenticated.

### `lib/mplib.py`

Adds the sibling `sshompitor/` directory to `sys.path` so `sshmarketplacelib` can be imported without installation.

`get_util()` — returns a cached `Util` instance (decorated with `@st.cache_resource`). The `Util` class from sshompitor loads the snapshot on first instantiation. Subsequent calls return the same object, so the snapshot is only read from disk once per Streamlit session.

### `lib/api.py`

All functions that communicate with the live Marketplace API.

| Function | Description |
|---|---|
| `fetch_all_actors(api_url, bearer)` | Paginates `GET /api/actors`, returns DataFrame with `id`, `name`, `email`, `website`, `item_count` |
| `verify_orphans(ids, api_url, bearer, batch_size)` | Checks `GET /api/actors/{id}?items=true` in batches; returns `dict[id → has_items\|None]` |
| `delete_actor(actor_id)` | `DELETE /api/actors/{id}?force=false` |
| `merge_actors(keep_id, merge_ids)` | `POST /api/actors/{id}/merge?with={ids}` |
| `fetch_all_keyword_concepts(api_url, bearer)` | Paginates `GET /api/concept-search?types=keyword` |
| `fetch_all_concepts(api_url, bearer)` | Paginates `GET /api/concept-search` (all types) |
| `get_item(category, persistent_id, api_url, bearer)` | `GET /api/{path}/{id}`; returns full item dict |
| `put_item(category, persistent_id, item_data, api_url, bearer)` | `PUT /api/{path}/{id}` |
| `fix_item_keyword(category, persistent_id, old_code, new_type, new_concept, api_url, bearer)` | GET → modify property → PUT |
| `delete_concept(concept_code, vocab_code)` | `DELETE /api/vocabularies/{vocab}/concepts/{code}` |

### `lib/snapshot.py`

`get_latest_snapshot_info()` — scans `data/` for `full_items_*.json` files, parses the Unix timestamp from the filename, and returns `(path, age_timedelta, snapshot_datetime)`.

`fetch_latest_from_github()` — queries the GitHub Contents API to find the newest snapshot file, compares against local files, and streams the download with a progress bar if a newer file exists.

`render_data_status()` — renders the age badge and refresh button in the sidebar. Called from every page.

---

## Caveats & known limitations

**Snapshot staleness.** All analysis that reads from the local snapshot (contributor lists, keyword extraction, actor deduplication, orphan candidate detection) reflects the state of the Marketplace at the time the snapshot was taken. Changes made through the toolkit or by other users after the snapshot date will not be visible until the snapshot is refreshed. The data age badge in the sidebar makes this visible.

**Actor item count not in paginated API.** The `GET /api/actors` paginated endpoint does not return associated items in its response. Item counts are therefore determined by cross-referencing with the snapshot (step 2 of orphaned actor detection) and then verified individually via `GET /api/actors/{id}?items=true` (step 3). This means orphan detection requires two data sources.

**API instability.** The Stage environment in particular can return intermittent HTTP 5xx errors. All verification calls (`_check_one_actor`) retry up to three times with exponential backoff. Actors that cannot be verified after three attempts are classified as **uncertain** and excluded from deletion.

**Concurrent item edits.** The keyword fix workflow uses a GET-modify-PUT pattern. If another user edits the same item between the GET and PUT calls, their changes will be overwritten. Use this feature during low-traffic periods and on Stage before Production.

**`force=false` on actor deletion.** The API will refuse to delete an actor that is the target of an affiliation relationship (i.e. an actor listed as an affiliated organisation for another actor). This is intentional — `force=false` is a safety parameter. Such actors must have their affiliations removed before they can be deleted, or they can be merged into the affiliated actor instead.

**Keyword extraction column prefix.** `Util.getAllProperties()` from sshompitor prefixes item-level metadata columns with `ts_` (`ts_persistentId`, `ts_category`, `ts_label`). The keyword extraction function in this toolkit accounts for this prefix.

**Item PUT requires full payload.** The Marketplace API does not support partial updates (PATCH). Every item update sends the complete item object as returned by GET, with only the target field modified. Fields not present in the GET response will be absent from the PUT and may be cleared on the server side.

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'sshmarketplacelib'`**
The package was not installed. Run `pip install -r requirements.txt`. If pip cannot reach GitHub, install manually: `pip install git+https://github.com/SSHOC/sshompitor.git#egg=sshmarketplacelib`. As a last resort, clone sshompitor into `../sshompitor/` — `lib/mplib.py` will find it automatically.

**`No snapshot found in data/`**
The `data/` symlink does not exist or points to an empty directory. Run `python3 setup.py` and check that `../sshompitor/data/` contains `full_items_*.json` files.

**Login fails with a network error**
The selected API server is unreachable. Check your internet connection and verify that the Stage or Production API is accessible. The Stage environment is occasionally taken offline for maintenance.

**`GET latest data from GitHub` downloads the same file again**
The local snapshot filename must exactly match the GitHub filename (including the Unix timestamp). If the file was renamed or copied, the comparison will fail and it will be re-downloaded.

**Orphan verification produces many `uncertain` results**
The API is under load or returning intermittent errors. Lower the batch size (try 20–30) and re-run verification. Alternatively, wait and retry — uncertain actors are excluded from deletion and the verification result is cached in session state.

**Item PUT returns HTTP 422 after keyword fix**
The updated property type code is not accepted by the API for the chosen vocabulary concept. The target concept may belong to a vocabulary that is not valid for the detected property type. Review the `type_code` in the cross-vocabulary match and ensure it is one of the recognised property type codes in the Marketplace schema.

**After merging actors, the group still appears in the results**
The snapshot has not been refreshed. The merge is complete on the server, but the local snapshot still reflects the pre-merge state. Refresh the snapshot from GitHub and re-run duplicate detection.

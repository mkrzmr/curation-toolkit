# SSH Open Marketplace — Curation Toolkit

A local Streamlit web app for curating the [SSH Open Marketplace](https://marketplace.sshopencloud.eu/). It reads data from a local [sshompitor](https://github.com/SSHOC/sshompitor) snapshot and can write back to the Marketplace API (stage or production).

## Requirements

- Python 3.10+
- The `sshompitor` repository cloned as a sibling directory (`../sshompitor/`)
- A Marketplace account with moderator or administrator privileges

## Setup

Install dependencies and create the symlinks that point the app at sshompitor's data:

```bash
pip install -r requirements.txt
python3 setup.py
```

`setup.py` creates two symlinks in the project root:

| Symlink | Points to |
|---|---|
| `data/` | `../sshompitor/data/` |
| `config.yaml` | `../sshompitor/config.yaml` |

The app reads snapshots from `data/` and uses the sshompitor library directly — no data is copied.

## Running

```bash
streamlit run app.py
```

Then open [http://localhost:8501](http://localhost:8501) in a browser.

## Login

The login screen lets you choose between **Production** and **Stage** environments before signing in. Your bearer token is stored in the session and used for all subsequent API calls. Navigating to any tool page without being logged in redirects back to the login screen.

## Tools

### Contributors (`pages/1_Contributors.py`)

Displays every actor–item relationship from the current snapshot as a filterable table.

**Filters (sidebar):**
- Category multiselect
- Role multiselect
- Actor name (free text)
- Actor email — available after loading actor data from the API (see button in sidebar)

**Columns:** actor name, email, role, item label, category, persistent ID, actor website, item link.  
Item links go to the contributed item (actors have no dedicated public page).

**Export:** CSV download of the filtered view.

---

### Duplicates (`pages/2_Duplicates.py`)

Three tabs for finding and resolving duplicate data.

#### Item Duplicates

Scans snapshot items for shared values in `label`, `description`, or `accessibleAt`. Select the category and field(s) to check, then click **Find Duplicates**. Results can be downloaded as CSV.

#### Actor Duplicates

Finds actors with the same `name` or `website`. Each duplicate group is shown in an expander with:
- A table of matching actors, their item count, an example item link, and email (if actor data has been loaded)
- A selectbox to choose which actor to keep
- A **Merge** button that calls `POST /api/actors/{id}/merge?with={ids}`

Merge buttons are disabled after a successful merge. Expanders stay open so you can review the result without re-running the search.

#### Orphaned Actors

Finds and removes actors that are not associated with any item. The process runs in four steps:

1. **Load actors from API** — fetches the full actor list (~9 000 entries, paginated).
2. **Cross-reference with snapshot** — actors absent from the snapshot are flagged as candidates. A stale snapshot can produce false positives, so this is a first filter only.
3. **Verify via live API** — calls `GET /api/actors/{id}?items=true` for each candidate in configurable batches (default 50). Requests within a batch run concurrently; a short pause between batches avoids overloading the API. Actors that cannot be verified due to API errors are shown separately and excluded from deletion.
4. **Review and delete** — confirmed orphans are shown in a table with unchecked checkboxes. Select the actors to remove, confirm, and click **Delete**. Deletion uses `force=false`: the API refuses to delete any actor that is still affiliated with another actor (e.g. a researcher listed under a university). Refused actors are reported in the results and left intact.

---

### URL Checker (`pages/3_URL_Checker.py`)

Checks whether URLs in the snapshot are reachable.

**Scope toggle:**
- `accessibleAt only` — checks the primary access URLs for each item
- `All URLs in entry` — scans every field for `http(s)` links (thumbnails, media, external IDs, etc.)

**Workflow:**
1. Select categories and scope, click **Extract URLs** to see the URL count before making any requests.
2. Adjust timeout (default 10 s) and parallel workers (default 20), then click **Check URLs**.
3. Results show HTTP status, error message, and a link back to the item. Filter by All / Broken only / OK only.
4. Results are grouped by item and sorted by number of broken URLs — items with the most problems appear first.

HEAD requests are used by default; servers that reject HEAD fall back to a streaming GET. Results can be downloaded as CSV.

## Data freshness

A badge in the sidebar of every page shows the age of the local snapshot and warns if it is more than 3 days old. The **Get latest data from GitHub** button downloads the newest `full_items_*.json` from the [sshompitor data directory](https://github.com/SSHOC/sshompitor/tree/main/data) and refreshes all caches automatically.

## Project structure

```
curation toolkit/
├── app.py                  # Login page and environment selector
├── setup.py                # Creates data/ and config.yaml symlinks
├── requirements.txt
├── pages/
│   ├── 1_Contributors.py   # Contributor browser
│   ├── 2_Duplicates.py     # Duplicate finder and orphan cleaner
│   └── 3_URL_Checker.py    # URL reachability checker
└── lib/
    ├── environments.py     # Stage / Production API URLs
    ├── auth.py             # Login helper and page guard
    ├── mplib.py            # sshompitor sys.path injection and cached Util
    ├── api.py              # API calls: fetch actors, merge, delete, verify
    └── snapshot.py         # Data-age badge and GitHub download
```

## API endpoints used

| Operation | Endpoint |
|---|---|
| Login | `POST /api/auth/sign-in` |
| List actors (paginated) | `GET /api/actors?perpage=100&page={n}` |
| Check actor items | `GET /api/actors/{id}?items=true` |
| Merge actors | `POST /api/actors/{id}/merge?with={ids}` |
| Delete actor | `DELETE /api/actors/{id}?force=false` |

import pathlib
import datetime
import requests
import streamlit as st

_DATA_DIR = pathlib.Path(__file__).parent.parent / "data"
_GITHUB_API = "https://api.github.com/repos/SSHOC/sshompitor/contents/data"
_STALE_DAYS = 3


def _parse_ts(filename: str) -> int:
    """Extract the Unix timestamp from a full_items_{ts}.json filename."""
    try:
        return int(pathlib.Path(filename).stem.replace("full_items_", ""))
    except ValueError:
        return 0


def get_latest_snapshot_info() -> tuple:
    """Return (path, age_timedelta, snapshot_datetime) for the newest full_items_*.json."""
    files = sorted(_DATA_DIR.glob("full_items_*.json"), key=lambda p: _parse_ts(p.name))
    if not files:
        return None, None, None
    latest = files[-1]
    ts = _parse_ts(latest.name)
    snapshot_dt = datetime.datetime.fromtimestamp(ts) if ts else datetime.datetime.fromtimestamp(latest.stat().st_mtime)
    age = datetime.datetime.now() - snapshot_dt
    return latest, age, snapshot_dt


def fetch_latest_from_github() -> tuple[bool, str]:
    """
    List the GitHub data/ directory, find the newest full_items_*.json,
    download it into the data/ directory if not already present.
    Returns (success, message).
    """
    try:
        resp = requests.get(_GITHUB_API, timeout=15)
        resp.raise_for_status()
        entries = resp.json()
    except Exception as e:
        return False, f"Failed to list GitHub data directory: {e}"

    if not isinstance(entries, list):
        return False, "Unexpected response from GitHub API."

    json_files = [e for e in entries if e.get("name", "").startswith("full_items_") and e["name"].endswith(".json")]
    if not json_files:
        return False, "No full_items_*.json files found on GitHub."

    latest_entry = max(json_files, key=lambda e: _parse_ts(e["name"]))
    target = _DATA_DIR / latest_entry["name"]

    if target.exists():
        return True, f"{latest_entry['name']} is already in data/ — nothing to download."

    download_url = latest_entry.get("download_url")
    if not download_url:
        return False, f"No download_url for {latest_entry['name']}."

    file_size = latest_entry.get("size", 0)

    try:
        r = requests.get(download_url, timeout=120, stream=True)
        r.raise_for_status()
    except Exception as e:
        return False, f"Download request failed: {e}"

    progress_bar = st.progress(0, text=f"Downloading {latest_entry['name']}…")
    downloaded = 0
    try:
        with open(target, "wb") as fh:
            for chunk in r.iter_content(chunk_size=65536):
                fh.write(chunk)
                downloaded += len(chunk)
                if file_size:
                    progress_bar.progress(min(downloaded / file_size, 1.0),
                                          text=f"Downloading… {downloaded // 1_048_576} / {file_size // 1_048_576} MB")
        progress_bar.empty()
    except Exception as e:
        target.unlink(missing_ok=True)
        return False, f"Write failed: {e}"

    return True, f"Downloaded {latest_entry['name']} ({file_size // 1_048_576} MB)."


def render_data_status() -> None:
    """Render data-age badge and GitHub refresh button in the sidebar."""
    with st.sidebar:
        st.divider()
        path, age, snapshot_dt = get_latest_snapshot_info()

        if path is None:
            st.warning("No snapshot found in data/")
        else:
            age_days = age.total_seconds() / 86400
            if age_days < 1:
                age_str = f"{int(age.total_seconds() // 3600)}h ago"
            elif age_days < 2:
                age_str = "1 day ago"
            else:
                age_str = f"{int(age_days)} days ago"

            if age_days > _STALE_DAYS:
                st.warning(
                    f"**MP data is {age_str}**  \n"
                    f"{snapshot_dt.strftime('%Y-%m-%d')} — more than {_STALE_DAYS} days old."
                )
            else:
                st.success(
                    f"**MP data: {age_str}**  \n"
                    f"{snapshot_dt.strftime('%Y-%m-%d %H:%M')}"
                )

        if st.sidebar.button("Get latest data from GitHub", use_container_width=True):
            with st.spinner("Checking GitHub…"):
                ok, msg = fetch_latest_from_github()
            if ok:
                st.sidebar.success(msg)
                st.cache_data.clear()
                st.cache_resource.clear()
                st.rerun()
            else:
                st.sidebar.error(msg)

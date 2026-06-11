"""
Session-scoped action and API call log.

Every significant operation (login, merge, delete, snapshot creation) and
every API write call is appended to a list in st.session_state.  The log
lives for the duration of the browser session and can be exported as CSV
or JSON from the Session Log page.

Log entry columns:
  time        – ISO-8601 timestamp (seconds precision)
  type        – "action" for high-level events, "api" for HTTP calls
  ok          – True if the operation succeeded
  description – Human-readable summary
  method      – HTTP verb (api entries only)
  url         – Full request URL (api entries only)
  request     – Abbreviated request body (api entries only, ≤ 2 000 chars)
  status      – HTTP status code as string (api entries only)
  response    – Abbreviated response body, prettified if JSON (api entries only, ≤ 1 000 chars)
"""

import datetime
import json
import pandas as pd
import streamlit as st

_COLS = ["time", "type", "ok", "description", "method", "url", "request", "status", "response"]


def _init() -> None:
    """Ensure the session log list exists in st.session_state."""
    if "session_log" not in st.session_state:
        st.session_state["session_log"] = []


def log_action(description: str, ok: bool = True) -> None:
    """Append a high-level action entry (non-API event) to the session log."""
    _init()
    st.session_state["session_log"].append({
        "time":        datetime.datetime.now().isoformat(timespec="seconds"),
        "type":        "action",
        "ok":          ok,
        "description": description,
        "method":      "",
        "url":         "",
        "request":     "",
        "status":      "",
        "response":    "",
    })


def _readable_response(raw: str) -> str:
    """If the response is a standard API error JSON, return a compact readable form."""
    if not raw:
        return raw
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return raw
        parts = []
        if "error" in data:
            parts.append(str(data["error"]))
        if "message" in data:
            parts.append(str(data["message"]))
        if "path" in data:
            parts.append(f"path: {data['path']}")
        if parts:
            return " — ".join(parts)
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return raw


def log_api(
    method: str,
    url: str,
    description: str,
    status: int | str,
    request: str = "",
    response: str = "",
    ok: bool | None = None,
) -> None:
    """
    Append an API call entry to the session log.

    Parameters
    ----------
    method      HTTP verb (GET, POST, PUT, DELETE).
    url         Full request URL including query string.
    description Short human-readable summary of what the call does.
    status      HTTP status code returned by the server, or "error" on network failure.
    request     Optional abbreviated request body (truncated to 2 000 chars).
    response    Optional response body (truncated to 1 000 chars; JSON error envelopes
                are collapsed to their "error" / "message" fields for readability).
    ok          Explicit success flag.  If None it is inferred as status < 400.
    """
    _init()
    if ok is None:
        try:
            ok = int(status) < 400
        except (ValueError, TypeError):
            ok = False
    st.session_state["session_log"].append({
        "time":        datetime.datetime.now().isoformat(timespec="seconds"),
        "type":        "api",
        "ok":          ok,
        "description": description,
        "method":      method,
        "url":         url,
        "request":     (request or "")[:2000],
        "status":      str(status),
        "response":    _readable_response((response or "")[:1000]),
    })


def get_log() -> list[dict]:
    """Return a copy of the full session log as a list of dicts."""
    _init()
    return list(st.session_state["session_log"])


def get_log_df() -> pd.DataFrame:
    """Return the session log as a DataFrame with the canonical column order."""
    entries = get_log()
    if not entries:
        return pd.DataFrame(columns=_COLS)
    return pd.DataFrame(entries, columns=_COLS)

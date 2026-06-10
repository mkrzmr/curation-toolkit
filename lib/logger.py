import datetime
import json
import pandas as pd
import streamlit as st

_COLS = ["time", "type", "ok", "description", "method", "url", "request", "status", "response"]


def _init() -> None:
    if "session_log" not in st.session_state:
        st.session_state["session_log"] = []


def log_action(description: str, ok: bool = True) -> None:
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


def log_api(
    method: str,
    url: str,
    description: str,
    status: int | str,
    request: str = "",
    response: str = "",
    ok: bool | None = None,
) -> None:
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
        "response":    (response or "")[:1000],
    })


def get_log() -> list[dict]:
    _init()
    return list(st.session_state["session_log"])


def get_log_df() -> pd.DataFrame:
    entries = get_log()
    if not entries:
        return pd.DataFrame(columns=_COLS)
    return pd.DataFrame(entries, columns=_COLS)

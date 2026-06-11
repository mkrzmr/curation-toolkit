"""
Thin wrapper around the sshmarketplacelib (sshompitor) helper.

The library can be either pip-installed as the `sshmarketplacelib` package
or used directly from a sibling clone of the sshompitor repository.
`get_util()` is cached with `st.cache_resource` so the snapshot is loaded
from disk only once per Streamlit server process.
"""

import sys
import pathlib
import streamlit as st

try:
    from sshmarketplacelib.helper import Util
except ImportError:
    # Fall back to a sibling sshompitor clone if the package is not pip-installed
    _SSHOMPITOR = pathlib.Path(__file__).parent.parent.parent / "sshompitor"
    if str(_SSHOMPITOR) not in sys.path:
        sys.path.insert(0, str(_SSHOMPITOR))
    from sshmarketplacelib.helper import Util


@st.cache_resource(show_spinner="Loading Marketplace snapshot…")
def get_util() -> Util:
    """
    Return a cached Util instance backed by the local snapshot.

    Uses cache_resource (process-level) rather than cache_data (session-level)
    so the snapshot DataFrame is shared across browser sessions and not
    re-parsed on every rerun.
    """
    return Util()

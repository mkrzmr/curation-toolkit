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
    return Util()

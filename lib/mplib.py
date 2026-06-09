import sys
import pathlib

# Make sshompitor importable without installing it
_SSHOMPITOR = pathlib.Path(__file__).parent.parent.parent / "sshompitor"
if str(_SSHOMPITOR) not in sys.path:
    sys.path.insert(0, str(_SSHOMPITOR))

import streamlit as st
from sshmarketplacelib.helper import Util  # noqa: E402


@st.cache_resource(show_spinner="Loading Marketplace snapshot…")
def get_util() -> Util:
    return Util()

"""
Known deployment environments for the SSH Open Marketplace.

Each entry maps a human-readable label to the API base URL and the
public-facing Marketplace URL used to build item deep-links.
Add new entries here when additional environments (e.g. a dev stack)
need to be reachable from the toolkit.
"""

ENVIRONMENTS = {
    "Production": {
        "label": "Production",
        "api_url": "https://marketplace-api.sshopencloud.eu",
        "mp_url": "https://marketplace.sshopencloud.eu/",
    },
    "Stage": {
        "label": "Stage",
        "api_url": "https://sshoc-marketplace-api-stage.acdh-dev.oeaw.ac.at",
        "mp_url": "https://sshoc-marketplace-stage.acdh-dev.oeaw.ac.at/",
    },
}

DEFAULT_ENV = "Production"

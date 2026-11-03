"""veil: a personal, stealth-first proxy toolkit built on sing-box + Caddy."""
import os

__version__ = "0.2.0"

# GitHub repository (owner/name) that `veil update` and the release check use.
# A fork changes this line, or sets VEIL_REPO in the environment.
REPO = os.environ.get("VEIL_REPO", "instl999/veil")

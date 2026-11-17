"""Overrides: rules that beat the data, in layers DATA < REPO < APP < LOCAL.

REPO rules ship in `placewise/overrides/repo/` and every install inherits them; APP rules come from
the calling app; LOCAL rules are the user's own file and win over everything. See docs/overrides.md.

    from placewise.overrides import load_overrides

    overrides = load_overrides()            # repo + the user's file
    result = overrides.apply(result, lat, lon)
    result.sources["city"]                  # "override:local:overrides.toml#2"
"""

from .engine import OverrideEngine
from .loading import REPO_DIR, load_overrides

__all__ = ["REPO_DIR", "OverrideEngine", "load_overrides"]

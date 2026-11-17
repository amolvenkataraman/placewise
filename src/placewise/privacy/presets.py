"""Ready-made policies; their numbers, and why, live in placewise.constants.privacy.PRESETS.

- "public_share": anyone can see it. ~0.5-1 km trimmed from each end, keyed 100 m snapping,
  hour-level times.
- "friends": people you know, but posts travel. 200-400 m trims, exact route, minute-level times.
- "research": aggregate analysis. Planar Laplace noise at ε = ln 4 / 200 m, 200-400 m trims,
  hour-level times.

All strip metadata. None knows your sensitive places: pass them as zones.
"""

from placewise.constants.privacy import PRESETS
from placewise.model.privacy import PrivacyPolicy

NAMES = tuple(PRESETS)


def preset(name, zones=()):
    """The named preset as a PrivacyPolicy, with your zones added."""
    try:
        numbers = PRESETS[name]
    except KeyError:
        raise ValueError(f"unknown preset {name!r}; choose one of {', '.join(NAMES)}") from None
    return PrivacyPolicy(zones=tuple(zones), **numbers)

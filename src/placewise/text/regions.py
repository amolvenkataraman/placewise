"""Finding macro regions that limit remote work (data: constants.countries.regions)."""

import functools

from placewise.constants._keys import key
from placewise.constants.countries.macro_regions import MACRO_REGIONS as REGIONS


@functools.cache
def _index():
    return {key(alias): region for region in REGIONS for alias in (region.name, *region.aliases)}


def find(text):
    """The macro region a name means ("EMEA", "Asia Pacific", "Worldwide"), or None."""
    return _index().get(key(text)) if text else None

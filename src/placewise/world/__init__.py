"""Countries, their subdivisions and country groups: lookups by code or name, lists by group or
continent, memberships over time, metro regions and country profiles.

    from placewise import world
    world.country("can").alpha2                        # "CA"
    world.countries(group="US & Canada")               # [Canada, United States]
    world.is_member("GB", "EU", on="2019-06-01")       # True
    world.subregion("ON", country="CA").code           # "CA-ON"
    world.profile("CA").currency.code                  # "CAD" (reads the world data pack)

Reference data lives in constants.countries (and datasets/); profiles in the world pack's
country_facts layer. See docs/world.md.
"""

from .countries import countries, country
from .groups import group, groups, is_member, members
from .profiles import profile
from .regions import regions
from .subregions import subregion, subregions

__all__ = [
    "countries",
    "country",
    "group",
    "groups",
    "is_member",
    "members",
    "profile",
    "regions",
    "subregion",
    "subregions",
]

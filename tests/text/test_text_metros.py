"""Finding metros and city aliases by any of their names."""

import pytest

from placewise.constants import countries
from placewise.text import metros

# city aliases seen in real-world location strings (airport codes, nicknames, official renames);
# every one reads here, as a city alias, a metro, a metro's member city or a country code
REAL_WORLD_ALIASES = [
    "sf", "sfo", "nyc", "ny", "new york", "la", "lax", "dc", "atl", "chi", "bos", "sea", "pdx", "phx",
    "philly", "dt", "den", "mpls", "slc", "stl", "nola", "lv", "sd", "sj", "rdu", "pgh", "clt", "dfw",
    "hou", "sa", "aus", "jax", "cbus", "indy", "mke", "kcmo", "orl", "tpa", "rva", "bmore", "abq", "reno",
    "kc", "okc", "vegas", "atx", "phl", "msp", "twin cities", "sjc", "south sf", "ssf", "bay area",
    "sf bay area", "san francisco bay area", "silicon valley", "rtp", "research triangle",
    "research triangle park", "raleigh-durham", "dallas-fort worth", "bronx", "tor", "yyz", "van", "yvr",
    "mtl", "yul", "ott", "yow", "cal", "yyc", "edm", "yeg", "win", "ywg", "kw", "kitchener-waterloo", "gta",
    "north york", "quebec city", "québec city", "yqb", "yhz", "hk", "hkg", "sg", "ldn", "frankfurt",
    "bangalore", "bombay", "gurgaon", "zurich", "cologne", "saigon",
]  # fmt: skip


@pytest.mark.parametrize("alias", REAL_WORLD_ALIASES)
def test_every_real_world_city_alias_is_known(alias):
    known = metros.city_alias(alias) or metros.find(alias) or metros.is_member_city(alias)
    assert known or countries.lookup(alias), alias  # "hkg" is Hong Kong's alpha-3


def test_metro_lookup():
    gta = metros.find("Greater Toronto Area")
    assert gta.key == "GTA" and gta.country == "CA" and gta.admin1 == ("ON",)
    assert metros.find("gtha").key == "GTA"
    assert metros.find("S.F. Bay Area").key == "Bay Area"  # dots and case don't matter
    assert metros.find("Atlantis") is None
    bangalore = metros.city_alias("Bangalore")
    assert (bangalore.city, bangalore.admin1, bangalore.country) == ("Bengaluru", "KA", "IN")
    assert bangalore.metro is metros.find("Bengaluru")
    pdx = metros.city_alias("PDX")  # a city alias with no metro
    assert (pdx.city, pdx.admin1, pdx.country, pdx.metro) == ("Portland", "OR", "US", None)
    assert metros.metro_of("Mississauga", "CA", "ON").key == "GTA"

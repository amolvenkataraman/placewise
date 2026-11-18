"""Shipped defaults: opinionated, documented, and all overridable in placewise.toml or per call."""

# disputed areas: describe who administers a place today, endorsing no claim
WORLDVIEW = ("de_facto",)
NAMES_PREFER = "official"  # Bengaluru, not Bangalore (aliases still parse)
LABEL_STYLE = "locality"  # "Emeryville, Bay Area" rather than "San Francisco area"
LABEL_PARKS = True  # "Yosemite Valley, Yosemite National Park" rather than "..., California, United States"

# what counts as "near", km
NEAR_KM = {
    "park_tier1": 25.0,
    "park_tier2": 10.0,
    "park_tier3": 1.0,
    "lake_large": 5.0,
    "lake": 1.0,
    "river": 0.3,
    "coast": 2.0,
    "airport": 10.0,
    "notable_urban": 2.0,
    "notable_rural": 25.0,
}
MAX_NEAR = 5

AUTO_UPDATE = "never"  # data never changes answers behind the user's back
# How packs arrive (DataSettings.mode): "auto" fetches the packs a lookup or search needs, but by
# default only country packs, the ones that change the main answer (city, county, postal code);
# parks, water, notable and postal packs are opt-in (data.auto_packs). The world pack always
# installs on first use unless the mode is "locked".
DATA_MODE = "auto"
DATA_AUTO_PACKS = ("country",)

SERVER_HOST = "127.0.0.1"  # exposing a server is a deliberate choice
SERVER_PORT = 8770
SERVER_MAX_BATCH = 10_000

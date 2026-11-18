"""Tier crosswalks (placewise.constants.parks: 1 national, 2 state / provincial, 3 regional, 4 local)
and the name and id rules every park source shares. docs/parks.md explains the choices.

A code missing from a crosswalk is dropped: easements, private and NGO land, habitat
designations, military and tribal land (tribal land belongs to the boundary layers, not parks).
"""

import re
import unicodedata

from placewise.constants.parks import LOCAL, NATIONAL, REGIONAL, STATE
from placewise.engine._within import generic_name  # the name rule the engine shares

# NPS UNIT_TYPE (plural, as the service has it) -> (tier, designation). Flagship types are
# national; the rest (historic sites, memorials, battlefields) are small sites a person names only
# nearby; linear units (trails, rivers, parkways) only from inside, their outline being a corridor.
NPS_TYPES = {
    "National Parks": (NATIONAL, "National Park"),
    "National Preserves": (NATIONAL, "National Preserve"),
    "National Reserves": (NATIONAL, "National Reserve"),
    "National Seashores": (NATIONAL, "National Seashore"),
    "National Lakeshores": (NATIONAL, "National Lakeshore"),
    "National Recreation Areas": (NATIONAL, "National Recreation Area"),
    "National Monuments": (NATIONAL, "National Monument"),  # small ones demoted: NPS_SMALL_KM2
    "National Historical Parks": (REGIONAL, "National Historical Park"),
    "National Historic Sites": (REGIONAL, "National Historic Site"),
    "International Historic Sites": (REGIONAL, "International Historic Site"),
    "National Memorials": (REGIONAL, "National Memorial"),
    "National Battlefields": (REGIONAL, "National Battlefield"),
    "National Battlefield Parks": (REGIONAL, "National Battlefield Park"),
    "National Battlefield Sites": (REGIONAL, "National Battlefield Site"),
    "National Military Parks": (REGIONAL, "National Military Park"),
    "Other Designations": (REGIONAL, "Park"),  # National Mall, Prince William Forest Park ...
    "Affiliated Areas": (REGIONAL, "Affiliated Area"),
    "National Rivers": (LOCAL, "National River"),
    "National Wild & Scenic Rivers": (LOCAL, "National Wild and Scenic River"),
    "National Scenic Trails": (LOCAL, "National Scenic Trail"),
    "National Trails System": (LOCAL, "National Trail"),
    "Parkways": (LOCAL, "Parkway"),
}
NPS_SMALL_KM2 = 10.0  # a national monument smaller than this (Statue of Liberty) is a site: tier 3

# PAD-US 4.1 Des_Tp (designation type) -> (tier, designation). NPS units, national forests and
# grasslands come from the NPS and USFS layers instead, and national wildlife refuges from the
# Proclamation layer (their fee parcels under-cover the refuge).
PADUS_TYPES = {
    "NM": (STATE, "National Monument"),  # not NPS-managed (BLM, USFS): Grand Staircase-Escalante
    "NRA": (STATE, "National Recreation Area"),  # not NPS-managed (USFS)
    "NCA": (STATE, "National Conservation Area"),
    "NSBV": (STATE, "National Scenic or Botanical Area"),
    "NWR": (STATE, "National Wildlife Refuge"),
    "SP": (STATE, "State Park"),
    "SREC": (STATE, "State Recreation Area"),
    "SW": (STATE, "State Wilderness"),
    "SCA": (REGIONAL, "State Conservation Area"),
    "SHCA": (REGIONAL, "State Historic or Cultural Area"),
    "SRMA": (REGIONAL, "State Resource Management Area"),
    "SOTH": (REGIONAL, "State Other"),
    "RMA": (REGIONAL, "Recreation Management Area"),
    "HCA": (REGIONAL, "Historic or Cultural Area"),
    "REC": (REGIONAL, "Recreation Area"),
    "SDA": (REGIONAL, "Special Designation Area"),
    "LCA": (REGIONAL, "Local Conservation Area"),
    "LRMA": (REGIONAL, "Local Resource Management Area"),
    "LP": (LOCAL, "Local Park"),
    "LREC": (LOCAL, "Local Recreation Area"),
    "LHCA": (LOCAL, "Local Historic or Cultural Area"),
}
# PAD-US Pub_Access "XA": closed to the public
PADUS_CLOSED = "XA"

# CPCAD TYPE_E -> tier, kept only for public owners or governments (OWNER_TYPE 1 federal,
# 2 provincial/territorial, 3 municipal, 4 Indigenous, 10 multiple; GOV_TYPE 1-3 or 10 for 9/10)
# and protected areas (PA_OECM_DF 1 or 3). Private, NGO and habitat designations are left out.
CPCAD_TYPES = {
    "National Park": NATIONAL,
    "National Park Reserve": NATIONAL,
    "National Urban Park": NATIONAL,
    "National Marine Conservation Area": NATIONAL,
    "National Marine Park": NATIONAL,
    "Provincial Park": STATE,
    "A - Park": STATE,  # British Columbia's Class A parks
    "B - Park": STATE,
    "C - Park": STATE,
    "Wildland Provincial Park": STATE,
    "Territorial Park": STATE,
    "Quebec's national park": STATE,  # parcs nationaux du Québec: provincial parks
    "Quebec's national park reserve": STATE,
    "Conservation Park": STATE,  # Gatineau Park (National Capital Commission)
    "Wilderness Park": STATE,
    "Natural Environment Park": STATE,
    "Recreation Park": STATE,
    "Historic Park": STATE,
    "Marine Park": STATE,
    "Provincial Recreation Area": STATE,
    "National Wildlife Area": REGIONAL,
    "Marine National Wildlife Area": REGIONAL,
    "Migratory Bird Sanctuary": REGIONAL,
    "Conservation Reserve": REGIONAL,
    "Ecological Reserve": REGIONAL,
    "Representative Area Ecological Reserve": REGIONAL,
    "Conservancy": REGIONAL,
    "Protected Area": REGIONAL,
    "Protected Natural Area": REGIONAL,
    "Wilderness Area": REGIONAL,
    "Nature Reserve": REGIONAL,
    "Natural Area": REGIONAL,
    "Provincially Owned Natural Area": REGIONAL,
    "Provincially Owned Conservation Area": REGIONAL,
    "Conservation Area": REGIONAL,
    "Regional Park": REGIONAL,
    "Recreation Site": REGIONAL,
    "Wildlife Management Area": REGIONAL,
    "Provincial Wildlife Management Area": REGIONAL,
    "Biodiversity reserve": REGIONAL,
    "Marine Protected Area": REGIONAL,
    "Indigenous protected and conserved area": REGIONAL,
    "Municipal Heritage/Natural Area": LOCAL,
    "Municipal Park": LOCAL,
    "City Park; Ecologically Signficant Natural Land": LOCAL,
    "Park Recreation Open Space": LOCAL,
    "Nature Park": LOCAL,
    "Park": LOCAL,  # British Columbia municipal parks (OWNER_TYPE 3)
}
CPCAD_OWNERS = {1, 2, 3, 4, 10}
CPCAD_PROTECTED = {1, 3}  # protected area, interim protected area (not OECMs)
CPCAD_DELISTED = 0

# Wikidata class (P31, or a subclass of it) -> tier, for the point layer
WIKIDATA_CLASSES = {
    "Q46169": NATIONAL,  # national park
    "Q5533772": NATIONAL,  # tiger reserve of India
    "Q1377575": STATE,  # wildlife refuge (wildlife sanctuaries)
}
# names that say more than Wikidata's typing (India's items are often just "protected area")
NAME_TIERS = (
    (re.compile(r"\b(national park|tiger reserve)\b", re.IGNORECASE), NATIONAL),
    (re.compile(r"\b(wildlife|bird) sanctuary\b", re.IGNORECASE), STATE),
)

_SUFFIX_OF_CANADA = re.compile(r"\s+of\s+canada$", re.IGNORECASE)
_CLASS = re.compile(r"\s*\([^)]*\bclass\)$", re.IGNORECASE)
_GENERATED = re.compile(r"(\d+|#\S*)$")  # PAD-US fills gaps with a manager name plus a number
_OWNER_ONLY = re.compile(r"^(city|town|county|village|borough|township|state) of\b", re.IGNORECASE)
_PLACEHOLDER = {"", "unknown", "unk", "none", "n/a", "na", "other", "private"}


def name_tier(name):
    """The tier a name's own words give ("Kaziranga National Park" 1), or None."""
    return next((tier for pattern, tier in NAME_TIERS if pattern.search(name)), None)


def usable_name(name):
    """Whether a name labels a place: not empty, a placeholder, generated ("BLM 123") or just an
    owner ("City of Newport")."""
    name = (name or "").strip()
    return not (name.lower() in _PLACEHOLDER or _GENERATED.search(name) or _OWNER_ONLY.match(name))


def place_name(name, *fallbacks):
    """The first of a name and its fallbacks (a parcel's local name) that labels a place: usable
    and not generic ("Open Space", placewise.constants.parks.GENERIC_NAMES); "" when none does."""
    for candidate in (name, *fallbacks):
        candidate = " ".join((candidate or "").split())
        if usable_name(candidate) and not generic_name(candidate):
            return candidate
    return ""


def cpcad_name(name):
    """(name, official) for a CPCAD NAME_E: "Banff National Park Of Canada" is "Banff National Park"
    with the official "Banff National Park of Canada" kept as an alias; Ontario's class suffix
    "(Natural Environment Class)" is dropped. official is "" when it equals the name."""
    name = " ".join((name or "").split())
    if _SUFFIX_OF_CANADA.search(name):
        return _SUFFIX_OF_CANADA.sub("", name), _SUFFIX_OF_CANADA.sub(" of Canada", name)
    return _CLASS.sub("", name).strip(), ""


def short_name(name, designation):
    """The name without its designation, as people often say it: "Yosemite National Park" ->
    "Yosemite"; "" when the name doesn't end with the designation or nothing would be left."""
    if designation and name.lower().endswith(" " + designation.lower()):
        return name[: -len(designation)].strip()
    return ""


def slug(text):
    """Lower-case ASCII words joined by "-": "Mount Rainier National Park" -> "mount-rainier-national-park"."""  # noqa: E501
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")

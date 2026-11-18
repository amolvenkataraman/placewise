"""CPCAD, the Canadian Protected and Conserved Areas Database (ECCC, December 2025, OGL-Canada 2.0).

Read from ECCC's map service of the database (the download is a File Geodatabase), in its native
EPSG:3978 (NAD83 / Canada Atlas Lambert, used as WGS84: 1-2 m apart), generalised by the service
to 10 m and unprojected here (packbuild.projection).

Kept: protected areas (PA_OECM_DF 1 or interim 3, not delisted), of a type tiers.CPCAD_TYPES
ranks, held or governed by a public body or Indigenous government (tiers.CPCAD_OWNERS, or
GOV_TYPE 1-3). Dropped: private and NGO land, habitat designations (waterfowl gathering areas,
deer yards, heronries), OECMs, proposed areas. Zones of one area share its PARENT_ID, which is the
park's id (`cpcad:<PARENT_ID>`: Banff 710300000, Rouge 717900000); a park takes the most
significant tier among its zones, and the name of its parent zone (else its largest zone).
Names are cleaned (tiers.cpcad_name): "Banff National Park Of Canada" is "Banff National Park",
with "Banff National Park of Canada" and "Banff" as aliases.
"""

import logging
from collections import defaultdict

from packbuild.projection import LambertConformalConic

from .. import url
from . import tiers
from ._common import ParkRow, feature_of
from ._rest import fetch_query, read_pages

SOURCE = "cpcad"
FIELDS = (
    "NAME_E,NAME_F,NAME_IND,TYPE_E,MGMT_E,OWNER_TYPE,GOV_TYPE,STATUS,PA_OECM_DF,ZONE_ID,PARENT_ID,LOC,"
    "O_AREA_HA,IUCN_CAT,BIOME,ZONEDESC_E"
)
GENERALISE_M = 10  # maxAllowableOffset, EPSG:3978 metres
GOVERNMENTS = {1, 2, 3}  # GOV_TYPE: national, sub-national, government-delegated

# EPSG:3978 "NAD83 / Canada Atlas Lambert"
CANADA_ATLAS_LAMBERT = LambertConformalConic(lat_origin=49.0, lon_origin=-95.0, lat_1=49.0, lat_2=77.0)
log = logging.getLogger(__name__)


def fetch(cache_dir, refresh=False):
    """The cached query pages of every zone (filtered when read, so the rules can change)."""
    return fetch_query(
        url(SOURCE, "service"), "1=1", cache_dir, "cpcad_2025", fields=FIELDS, out_sr=3978,
        offset=GENERALISE_M, precision=0, page_size=200, refresh=refresh,
    )  # fmt: skip


def keep(attrs):
    """Whether a CPCAD zone is a public protected area of a ranked type."""
    return (
        attrs.get("TYPE_E") in tiers.CPCAD_TYPES
        and attrs.get("PA_OECM_DF") in tiers.CPCAD_PROTECTED
        and attrs.get("STATUS") != tiers.CPCAD_DELISTED
        and (attrs.get("OWNER_TYPE") in tiers.CPCAD_OWNERS or attrs.get("GOV_TYPE") in GOVERNMENTS)
    )


def parks(folder):
    """ParkRows: one per kept zone, grouped into parks by PARENT_ID."""
    zones = defaultdict(list)
    dropped = 0
    for attrs, rings in read_pages(folder):
        if not keep(attrs):
            dropped += 1
            continue
        parent = attrs.get("PARENT_ID") or attrs.get("ZONE_ID")
        feature = feature_of(rings, CANADA_ATLAS_LAMBERT, f"cpcad:{attrs.get('ZONE_ID')}")
        if feature is not None:
            zones[int(parent)].append((attrs, feature))
    rows = []
    for parent, members in sorted(zones.items()):
        head = next((a for a, _ in members if a.get("ZONE_ID") == parent), None)
        head = head or max(members, key=lambda m: m[0].get("O_AREA_HA") or 0)[0]
        name, official = tiers.cpcad_name(head.get("NAME_E"))
        if not tiers.place_name(name):  # a placeholder, an owner or a kind of land: not a name
            continue
        tier, designation = min((tiers.CPCAD_TYPES[a["TYPE_E"]], a["TYPE_E"]) for a, _ in members)
        designation = _designation(designation)
        short = tiers.short_name(name, designation)
        aliases = tuple(dict.fromkeys(a for a in (official, short) if a and a != name))
        for _, feature in members:
            rows.append(ParkRow(f"cpcad:{parent}", name, tier, designation, feature, SOURCE, aliases))
    log.info("cpcad: kept %d zones in %d parks, dropped %d", len(rows), len(zones), dropped)
    return rows


_DESIGNATIONS = {
    "A - Park": "Provincial Park",
    "B - Park": "Provincial Park",
    "C - Park": "Provincial Park",
    "Quebec's national park": "Quebec National Park",
    "Quebec's national park reserve": "Quebec National Park Reserve",
    "Park": "Municipal Park",
}


def _designation(type_e):
    return _DESIGNATIONS.get(type_e, type_e)

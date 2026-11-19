"""National Park Service unit boundaries (public domain): every NPS unit, with its 4-letter code.

Read from the NPS Land Resources Division's feature service (layer `nps_boundary`, the
administrative boundaries IRMA also publishes as a File Geodatabase), in Web Mercator, generalised
by the service (packbuild.sources.parks._rest). Ids are `nps:<UNIT_CODE>` ("nps:YOSE"); the name
without its designation ("Yosemite") is an alias.
"""

import logging

from placewise.constants.parks import REGIONAL

from ... import url
from .. import tiers
from .._common import ParkRow, WebMercator, feature_of
from .._rest import fetch_query, read_pages

SOURCE = "nps-boundaries"
FIELDS = "UNIT_CODE,UNIT_NAME,UNIT_TYPE,PARKNAME,STATE,REGION"
GENERALISE_M = 10  # maxAllowableOffset, Web Mercator metres
log = logging.getLogger(__name__)


def fetch(cache_dir, refresh=False):
    """The cached query pages of every unit (packbuild.sources.parks._rest)."""
    return fetch_query(
        url(SOURCE, "boundary"), "1=1", cache_dir, "nps_boundary", fields=FIELDS, out_sr=3857,
        offset=GENERALISE_M, precision=0, page_size=50, refresh=refresh,
    )  # fmt: skip


def parks(folder):
    """ParkRows for the units in the downloaded pages; unknown unit types are dropped (logged)."""
    rows, unknown = [], set()
    for attrs, rings in read_pages(folder):
        code = (attrs.get("UNIT_CODE") or "").strip().upper()
        name = " ".join((attrs.get("UNIT_NAME") or "").split())
        kind = (attrs.get("UNIT_TYPE") or "").strip()
        if kind not in tiers.NPS_TYPES:
            unknown.add(kind)
            continue
        tier, designation = tiers.NPS_TYPES[kind]
        if not code or not tiers.usable_name(name):
            continue
        feature = feature_of(rings, WebMercator, f"nps:{code}")
        if feature is None:
            continue
        aliases = _aliases(name, " ".join((attrs.get("PARKNAME") or "").split()), designation)
        row = ParkRow(f"nps:{code}", name, tier, designation, feature, SOURCE, aliases=aliases, code=code)
        if designation == "National Monument" and row.area_km2 < tiers.NPS_SMALL_KM2:
            row.tier = REGIONAL
        rows.append(row)
    if unknown:
        log.info("nps: unit types without a tier (dropped): %s", ", ".join(sorted(unknown)))
    return _unique_ids(rows)


def _unique_ids(rows):
    """One code can name two units (Denali National Park and Denali National Preserve, DENA): the
    most significant keeps `nps:<code>`, the others add their designation (`nps:DENA:national-preserve`)."""
    by_code = {}
    for row in rows:
        by_code.setdefault(row.code, []).append(row)
    for group in by_code.values():
        group.sort(key=lambda r: (r.tier, r.designation != "National Park", -r.area_km2))
        for row in group[1:]:
            row.park = f"nps:{row.code}:{tiers.slug(row.designation)}"
    return rows


def _aliases(name, park_name, designation):
    """PARKNAME when it differs from the name, and the name without its designation."""
    found = [a for a in (park_name, tiers.short_name(name, designation)) if a and a != name]
    return tuple(dict.fromkeys(found))

"""PAD-US 4.1 (USGS Gap Analysis Project, public domain): state, regional and local parks.

Read from USGS's own feature services of PAD-US 4.1 (the full inventory is published only as a
File Geodatabase): the Fee layer (`Fee_Managers_PADUS`, one row per parcel) for the designation
types of tiers.PADUS_TYPES, and the Proclamation layer for national wildlife refuges, whose fee
parcels under-cover them. NPS units and national forests come from their agencies (nps, usfs).

PAD-US has no persistent unit id and a park is often many parcels, some from other parks of the
same name ("Central Park" is a park in several New York towns). So parcels are grouped by (state,
designation type, name), each group split into clusters of parcels whose bounding boxes come
within CLUSTER_GAP_M of each other, and each cluster is one park, with the id
`pad-us:<state>:<des_tp>:<name slug>:<geohash>` (lower case; the geohash, GEOHASH_CHARS long, is
that of the centre of the cluster's largest parcel), stable as long as the park keeps its name and
its largest parcel stays put. Parcels closed to the public (Pub_Access "XA") and names that don't
label a place (tiers.usable_name) are left out.
"""

import logging
from collections import defaultdict

import numpy as np

from placewise.geo import from_web_mercator, geohash_encode

from .. import url
from . import tiers
from ._common import ParkRow, WebMercator, feature_area, feature_of
from ._rest import fetch_query, read_pages, ungeneralised

SOURCE = "padus"
FIELDS = "OBJECTID,Unit_Nm,Loc_Nm,Loc_Ds,Mang_Name,Mang_Type,Des_Tp,State_Nm,Source_PAID,Pub_Access,GIS_Acres"
# the Fee rows worth reading (tiers.PADUS_TYPES), and the Proclamation layer's refuges
FEE_WHERE = (
    "Des_Tp IN ('SP','SREC','SW','NCA','NSBV','SCA','SHCA','SRMA','SOTH','LCA','LRMA','RMA','HCA','REC','SDA',"  # noqa: E501
    "'LP','LREC','LHCA') OR (Des_Tp IN ('NM','NRA') AND Mang_Name <> 'NPS')"
)
REFUGES_WHERE = "Des_Tp='PROC' AND Mang_Name='FWS' AND Loc_Ds='NWR'"
GENERALISE_M = 10  # maxAllowableOffset, Web Mercator metres
CLUSTER_GAP_M = 1_000.0  # Web Mercator metres (about 750 m on the ground at 40°N)
GEOHASH_CHARS = 5  # about 5 km by 5 km
UNGENERALISED_TOLERANCE_M = 10.0  # simplify, in Mercator metres, what the service sent at full resolution
log = logging.getLogger(__name__)


def fetch(cache_dir, refresh=False):
    """(Fee pages, refuge pages): the cached query folders."""
    common = {"fields": FIELDS, "out_sr": 3857, "offset": GENERALISE_M, "precision": 0, "refresh": refresh}
    fee = fetch_query(url(SOURCE, "fee"), FEE_WHERE, cache_dir, "padus41_fee", page_size=1000, **common)
    refuges = fetch_query(
        url(SOURCE, "proclamation"),
        REFUGES_WHERE,
        cache_dir,
        "padus41_proclamation_nwr",
        page_size=50,
        **common,
    )
    return fee, refuges


def parks(fee_folder, nwr_folder=None):
    """ParkRows from the Fee pages (and the Proclamation refuge pages, when given)."""
    parcels = list(_parcels(fee_folder, refuges=False))
    if nwr_folder is not None:
        parcels += _parcels(nwr_folder, refuges=True)
    groups = defaultdict(list)
    for p in parcels:
        groups[(p["state"], p["des_tp"], p["name"])].append(p)
    rows = []
    for (state, des_tp, name), members in sorted(groups.items()):
        tier, designation = tiers.PADUS_TYPES[des_tp]
        for cluster in _clusters(members):
            biggest = max(cluster, key=lambda p: p["area"])
            x0, y0, x1, y1 = biggest["box"]
            lat, lon = from_web_mercator((x0 + x1) / 2, (y0 + y1) / 2)
            where = geohash_encode(lat, lon, GEOHASH_CHARS)
            park = f"pad-us:{state.lower()}:{des_tp.lower()}:{tiers.slug(name)}:{where}"
            short = tiers.short_name(name, designation)
            for p in cluster:
                aliases = (short,) if short else ()
                rows.append(
                    ParkRow(park, name, tier, designation, p["feature"], SOURCE, aliases, area_km2=p["area"])
                )
    return rows


def _parcels(folder, refuges):
    full = ungeneralised(folder)
    dropped = defaultdict(int)
    for attrs, rings in read_pages(folder):
        des_tp = "NWR" if refuges else (attrs.get("Des_Tp") or "").strip()
        name = " ".join((attrs.get("Unit_Nm") or "").split())
        if des_tp not in tiers.PADUS_TYPES or (des_tp in ("NM", "NRA") and attrs.get("Mang_Name") == "NPS"):
            dropped["designation"] += 1
            continue
        if attrs.get("Pub_Access") == tiers.PADUS_CLOSED:
            dropped["closed"] += 1
            continue
        if not tiers.usable_name(name):
            dropped["name"] += 1
            continue
        tolerance = UNGENERALISED_TOLERANCE_M if attrs.get("OBJECTID") in full else 0.0
        feature = feature_of(rings, WebMercator, name, tolerance)
        if feature is None:
            dropped["geometry"] += 1
            continue
        stacked = np.vstack(rings)
        box = (*stacked.min(axis=0), *stacked.max(axis=0))
        yield {
            "state": (attrs.get("State_Nm") or "").strip().upper(), "des_tp": des_tp, "name": name,
            "feature": feature, "box": box, "area": feature_area(feature),
        }  # fmt: skip
    log.info("pad-us %s: dropped %s", folder.name, dict(dropped))


def _clusters(members):
    """Groups of parcels whose bounding boxes, grown by CLUSTER_GAP_M / 2, overlap (transitively)."""
    if len(members) == 1:
        return [members]
    box = np.array([m["box"] for m in members]) + np.array([-1, -1, 1, 1]) * CLUSTER_GAP_M / 2
    parent = list(range(len(members)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(members)):
        near = np.flatnonzero(
            (box[i + 1 :, 0] <= box[i, 2]) & (box[i + 1 :, 2] >= box[i, 0])
            & (box[i + 1 :, 1] <= box[i, 3]) & (box[i + 1 :, 3] >= box[i, 1])
        ) + i + 1  # fmt: skip
        for j in near.tolist():
            parent[root(j)] = root(i)
    out = defaultdict(list)
    for i, m in enumerate(members):
        out[root(i)].append(m)
    return list(out.values())

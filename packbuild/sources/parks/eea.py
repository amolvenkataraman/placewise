"""EEA Nationally designated areas (NatDA, formerly CDDA), July 2026 public version, CC BY 4.0: the
parks and protected areas of 37 European countries, for the eur-parks pack.

One GeoPackage (packbuild.gpkg) in ETRS89-LAEA (EPSG:3035, unprojected with
packbuild.projection.ETRS89_LAEA): `ProtectedSite` has one (multi)polygon per site, keyed by
`natDAId`, which `DesignatedArea` gives a designation type and IUCN category and
`DesignationType` an English name; tiers.eea_tier turns those into a tier, or leaves the site out.
Sites reported only as a point are skipped. Each site is one row, simplified to `tolerance_m`.

Names are the national ones as reported (tiers.eea_name cleans Sweden's id prefix, Latvia's zone
codes, ALL CAPS), in English where Wikidata has an English label for an item whose WDPA id (P809)
is the site's natDAId (`wdpa_names`); the national name is then an alias.

A park reported as several sites (Hohe Tauern: a core and an outer zone in each of three states;
Latvia's national parks: dozens of zones) is one park: sites of one country and designation type
whose boxes come within MERGE_KM and one of whose names holds the other's ("Hohe Tauern" in
"Nationalpark Hohe Tauern Kernzone") share the park id of the site with an English name, else of
the one with the shortest name. Only tiers 1 and 2: reserves are many and rarely split that way.
Ids are `eea:<natDAId>` (the site code, stable across versions).
"""

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from placewise.constants.parks import REGIONAL
from placewise.engine.naming.rules import fold

from ... import gpkg
from ...fetch import fetch as fetch_file
from ...polygons import signed_area
from ...projection import ETRS89_LAEA
from .. import url
from ..notable.wikidata import rows as tsv_rows
from . import tiers
from ._common import ParkRow, feature_of

SOURCE = "eea-natda"
TABLE = "ProtectedSite"
DEFAULT_TOLERANCE_M = 10.0
MERGE_KM = 1.0
MIN_MERGE_NAME = 4  # a name this short never stands for another's
# the EEA's country codes that aren't ISO 3166-1 alpha-2
COUNTRY_CODES = {"EL": "GR", "UK": "GB"}
_ITEM = re.compile(r"^<http://www\.wikidata\.org/entity/(Q\d+)>$")
log = logging.getLogger(__name__)


def fetch(cache_dir, refresh=False):
    """(the cached GeoPackage, the cached Wikidata WDPA-id labels)."""
    cache_dir = Path(cache_dir)
    sites = fetch_file(url(SOURCE, "sites"), cache_dir / "eea-natda", refresh=refresh, timeout=120)
    labels = fetch_file(
        url("wikidata", "parks_wdpa"), cache_dir / "wikidata-parks-wdpa", refresh=refresh, timeout=300
    )
    return sites, labels


def wdpa_names(path):
    """{WDPA id: (qid, English label)} from the Wikidata TSV export; the oldest item when several
    items share an id (the main article's, not a zone's)."""
    out = {}
    for row in tsv_rows(path):
        item = _ITEM.match(row["item"])
        raw, label = row["wdpa"].strip(), " ".join(row["name"].split())
        if not item or not raw.isdigit() or not label or label == item[1]:
            continue
        qid, known = item[1], out.get(int(raw))
        if known is None or int(qid[1:]) < int(known[0][1:]):
            out[int(raw)] = (qid, label)
    return out


def designations(path):
    """{natDAId: (country, designation type code, category, English type name, IUCN, km²)}."""
    with gpkg.connect(path) as db:
        types = {c: (cat, en) for c, cat, en in db.execute(
            "SELECT designationTypeCode, designationTypeCategory, designationTypeNameEnglish "
            "FROM DesignationType"
        )}  # fmt: skip
        rows = db.execute(
            "SELECT natDAId, natDACountryCode, designationTypeCode, iucnCategory, siteArea "
            "FROM DesignatedArea"
        ).fetchall()
    out = {}
    for site, country, code, iucn, hectares in rows:
        category, english = types.get(code, ("", ""))
        country = COUNTRY_CODES.get(country, country)
        out[int(site)] = (country, code, category, english, iucn or "", (hectares or 0.0) / 100)
    return out


def parks(paths, tolerance_m=DEFAULT_TOLERANCE_M):
    """ParkRows for the kept sites of the GeoPackage, `paths` being fetch's pair."""
    sites_path, labels_path = paths
    english = wdpa_names(labels_path)
    kinds = designations(sites_path)
    sites, dropped = [], 0
    rows = gpkg.read_polygons(sites_path, TABLE, ("natDAId", "siteName"), where="geomType = 'polygon'")
    for attrs, polygons in rows:
        site = int(attrs["natDAId"])
        country, code, category, kind, iucn, km2 = kinds.get(site, ("", "", "", "", "", 0.0))
        found = tiers.eea_tier(category, kind, iucn, km2, code=code)
        national = tiers.place_name(tiers.eea_name(attrs["siteName"]))
        qid, label = english.get(site, ("", ""))
        if found is None or not polygons or not (national or label):
            dropped += 1
            continue
        rings = _oriented(polygons)
        feature = feature_of(rings, ETRS89_LAEA, f"eea:{site}", tolerance_m)
        if feature is None:
            dropped += 1
            continue
        box = np.array([min(r[:, 0].min() for r in rings), min(r[:, 1].min() for r in rings),
                        max(r[:, 0].max() for r in rings), max(r[:, 1].max() for r in rings)])  # fmt: skip
        sites.append(_Site(site, country, code, found[0], found[1], national, qid, label, box, feature))
    out = []
    for group in _groups(sites):
        out += _rows(group)
    log.info(
        "eea-natda: kept %d sites in %d parks, dropped %d", len(out), len({r.park for r in out}), dropped
    )
    return out


def countries(rows):
    """The alpha-2 codes of the countries the rows' sites are in (pack.json `covers`)."""
    return sorted({r.country for r in rows if r.country})


@dataclass(eq=False)
class _Site:
    id: int  # natDAId
    country: str
    code: str  # designation type
    tier: int
    designation: str
    national: str  # the name as reported, cleaned
    qid: str  # the Wikidata item with this WDPA id, and its English label
    label: str
    box: np.ndarray  # projected (xmin, ymin, xmax, ymax)
    feature: object
    folded: str = field(init=False)

    def __post_init__(self):
        self.folded = " ".join(fold(self.national).casefold().split()) if self.national else ""


def _oriented(polygons):
    """Every polygon's shell clockwise and holes counter-clockwise (the convention of
    polygons.to_feature), flattened: WKB writers don't agree on a winding."""
    rings = []
    for polygon in polygons:
        for k, ring in enumerate(polygon):
            clockwise = signed_area(ring) < 0
            rings.append(ring if clockwise == (k == 0) else ring[::-1])
    return rings


def _groups(sites):
    """Sites grouped into parks: lists, the head (whose id and name the park takes) first."""
    parent = list(range(len(sites)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    by_kind = defaultdict(list)
    for i, s in enumerate(sites):
        if s.tier < REGIONAL and len(s.folded) >= MIN_MERGE_NAME:
            by_kind[(s.country, s.code)].append(i)
    reach = MERGE_KM * 1000
    for members in by_kind.values():
        boxes = np.array([sites[i].box for i in members])
        for a, i in enumerate(members):
            near = np.flatnonzero(
                (boxes[:, 0] <= boxes[a, 2] + reach) & (boxes[:, 2] >= boxes[a, 0] - reach)
                & (boxes[:, 1] <= boxes[a, 3] + reach) & (boxes[:, 3] >= boxes[a, 1] - reach)
            )  # fmt: skip
            for b in near[near > a]:
                j = members[b]
                if _contains(sites[i].folded, sites[j].folded):
                    parent[find(j)] = find(i)
    groups = defaultdict(list)
    for i in range(len(sites)):
        groups[find(i)].append(sites[i])
    out = []
    for members in groups.values():
        named = sorted((s for s in members if s.qid), key=lambda s: int(s.qid[1:]))
        head = named[0] if named else min(members, key=lambda s: (len(s.national), s.id))
        out.append([head, *(s for s in sorted(members, key=lambda s: s.id) if s is not head)])
    return sorted(out, key=lambda g: g[0].id)


def _contains(a, b):
    """Whether one folded name holds the other as whole words."""
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    return bool(re.search(rf"(?<!\w){re.escape(short)}(?!\w)", long))


def _rows(group):
    head = group[0]
    name = head.label or head.national
    tier, designation = min((s.tier, s.designation) for s in group)
    nationals = [s.national for s in group if s.national]
    short = tiers.short_name(name, designation)
    aliases = tuple(dict.fromkeys(a for a in (short, *nationals) if a and a != name))[:6]
    credit = "wikidata" if head.label else ""
    return [
        ParkRow(f"eea:{head.id}", name, tier, designation, s.feature, SOURCE, aliases, country=s.country,
                name_source=credit)
        for s in group
    ]  # fmt: skip

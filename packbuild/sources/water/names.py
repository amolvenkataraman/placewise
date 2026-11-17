"""Names for HydroLAKES' outlines, joined from Natural Earth's lakes and Wikidata (CC0).

HydroLAKES draws lakes better (1:100k-1:250k) but names few of them; Natural Earth names its
lakes (with Wikidata ids) but draws them at 1:10m. `join` keeps HydroLAKES' outline wherever
both have the lake:

1. Natural Earth. A Natural Earth lake is *covered* when at least COVERED of the sample points
   inside it (a grid over its bounding box) fall in HydroLAKES outlines. A covered lake is left
   out, and gives its name, Wikidata id and aliases to the outline holding most of its points,
   unless a larger Natural Earth lake already named it (Whitefish Bay, drawn inside Lake
   Superior, leaves Lake Superior its name). Uncovered Natural Earth lakes stay as they are.
2. Wikidata. An outline still unnamed takes the English label of a Wikidata lake whose point
   lies inside it (the oldest item, the lowest Q number, when several do), unless that item
   already names another lake.
3. HydroLAKES' own name ("Lake Ontario" from "Ontario"), if it has one.

Outlines with no name after that are left out: a lookup has nothing to call them. Ids are
"wikidata:Q..." where the lake has a Wikidata id, else the source's own; rows are sorted smallest
first. Spatial tests run on temporary packs (placewise's own polygon queries).
"""

import json
import re
import shutil
import tempfile
from pathlib import Path

import numpy as np

from placewise.constants import water as const
from placewise.model import Feature
from placewise.packs import open_pack

from ...layer import LayerData, write_pack
from .naturalearth import SOURCE as NE_SOURCE

WIKIDATA = "wikidata"
COVERED = 0.5
_GRID = (8, 32)  # sample grid sides: the coarse one first, the fine one for thin lakes
_POINT = re.compile(r"Point\(\s*([-0-9.eE]+)\s+([-0-9.eE]+)\s*\)")


def wikidata_points(paths):
    """[(qid, English label, lat, lon)] from SPARQL JSON results with ?item ?label ?coord."""
    found = []
    for path in paths:
        for row in json.loads(Path(path).read_text(encoding="utf-8"))["results"]["bindings"]:
            match = _POINT.match(row["coord"]["value"])
            if match:
                lon, lat = float(match.group(1)), float(match.group(2))
                found.append((row["item"]["value"].rsplit("/", 1)[-1], row["label"]["value"], lat, lon))
    return found


def join(hydrolakes, natural_earth, points, workdir):
    """One lakes LayerData from HydroLAKES (named as above) and Natural Earth's uncovered lakes."""
    hl, ne = _rows(hydrolakes), _rows(natural_earth)
    work = Path(tempfile.mkdtemp(prefix="lakes-", dir=_mkdir(workdir)))
    try:
        hl_layer = _polygons(work, "hl", hydrolakes.features)
        ne_layer = _polygons(work, "ne", natural_earth.features)
        covered = _cover(ne, hl, hl_layer, ne_layer)
        used = {r["wikidata"] for r in ne if r["wikidata"]}
        _name_from_wikidata(hl, hl_layer, points, used)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    keep = [(r, f) for r, f in zip(hl, hydrolakes.features, strict=True) if r["name"]]
    keep += [
        (r, f) for i, (r, f) in enumerate(zip(ne, natural_earth.features, strict=True)) if i not in covered
    ]
    keep.sort(key=lambda rf: rf[0]["area_km2"])
    ids, seen = [], set()
    for r, _ in keep:
        pid = f"wikidata:{r['wikidata']}" if r["wikidata"] else r["id"]
        ids.append(pid if pid not in seen else r["id"])
        seen.add(ids[-1])
    columns = {"id": ids} | {
        k: [r[k] for r, _ in keep] for k in ("name", "type", "wikidata", "aliases", "source")
    }
    columns["area_km2"] = [r["area_km2"] for r, _ in keep]
    features = [Feature(f.outlines, {}, i) for (_, f), i in zip(keep, ids, strict=True)]
    types = {k: "str" for k in columns} | {"area_km2": "f8"}
    sources = tuple(dict.fromkeys((*hydrolakes.sources, NE_SOURCE, WIKIDATA)))
    return LayerData(const.LAKES, "polygon", columns, sources, features=features, types=types)


def _cover(ne, hl, hl_layer, ne_layer):
    """Indexes of the covered Natural Earth lakes; their names go to the outlines (in `hl`)."""
    rows = {}  # NE lake -> HydroLAKES row of each sample point inside it
    todo = np.arange(ne_layer.count)
    for side in _GRID:
        if not len(todo):
            break
        lake, lat, lon = _samples(ne_layer, todo, side)
        inside = ne_layer.contains(lat, lon, lake)
        lake, lat, lon = lake[inside], lat[inside], lon[inside]
        found = np.atleast_1d(hl_layer.query(lat, lon))
        for i in np.unique(lake).tolist():
            rows[i] = found[lake == i]
        todo = np.setdiff1d(todo, lake)
    covered, best = set(), {}
    for i, hits in rows.items():
        if np.mean(hits >= 0) < COVERED:
            continue
        covered.add(i)
        target = int(np.bincount(hits[hits >= 0]).argmax())
        if target not in best or ne[i]["area_km2"] > ne[best[target]]["area_km2"]:
            best[target] = i
    for target, i in best.items():
        hl[target].update({k: ne[i][k] for k in ("name", "wikidata", "aliases")})
    return covered


def _name_from_wikidata(hl, hl_layer, points, used):
    unnamed = {i for i, r in enumerate(hl) if not r["name"]}
    if not points or not unnamed:
        return
    lat = np.array([p[2] for p in points])
    lon = np.array([p[3] for p in points])
    found = np.atleast_1d(hl_layer.query(lat, lon))
    choice = {}
    for (qid, label, _, _), row in zip(points, found.tolist(), strict=True):
        if row in unnamed and qid not in used and (row not in choice or _qnum(qid) < _qnum(choice[row][0])):
            choice[row] = (qid, label)
    for row, (qid, label) in sorted(choice.items(), key=lambda kv: _qnum(kv[1][0])):
        if qid not in used:
            hl[row].update(name=label, wikidata=qid)
            used.add(qid)


def _samples(layer, lakes, side):
    """(lake, lat, lon): a side x side grid of cell centres over each lake's bounding box."""
    boxes = layer.bboxes()[lakes]
    t = (np.arange(side) + 0.5) / side
    gy, gx = np.meshgrid(t, t, indexing="ij")
    gy, gx = gy.ravel(), gx.ravel()
    south, west, north, east = (boxes[:, k : k + 1] for k in range(4))
    width = np.where(east >= west, east - west, east + 360 - west)
    lat = south + (north - south) * gy
    lon = west + width * gx
    lon = np.where(lon > 180, lon - 360, lon)
    return np.repeat(lakes, side * side), lat.ravel(), lon.ravel()


def _polygons(work, name, features):
    columns = {"id": [f"{name}{i}" for i in range(len(features))], "name": [""] * len(features)}
    feats = [Feature(f.outlines, {}, i) for f, i in zip(features, columns["id"], strict=True)]
    write_pack(work, name, "2000.01", [LayerData(name, "polygon", columns, ("build",), features=feats)])
    return open_pack(work / f"{name}-2000.01")[name]


def _rows(layer):
    keys = ("id", "name", "type", "wikidata", "aliases", "source", "area_km2")
    return [
        dict(zip(keys, values, strict=True)) for values in zip(*(layer.columns[k] for k in keys), strict=True)
    ]


def _qnum(qid):
    return int(qid[1:]) if qid[1:].isdigit() else 1 << 62


def _mkdir(path):
    Path(path).mkdir(parents=True, exist_ok=True)
    return path

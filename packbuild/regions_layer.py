"""The `regions` layer of the country packs: each curated region (datasets/regions) as one polygon
feature, the union of its members' polygons.

    layer = from_features(regions, {member id: Feature}, sources)       # US counties, India PIN areas
    layer = region_layer(regions, {region id: union(...)}, sources)     # Canada: unions of raw rings

Every member must be a feature of the pack being built (`check_members`, run by every builder): a
region whose members are missing fails the build rather than ship with a hole. India regions also
list the districts their definition names; their members must be exactly the PIN areas the pack
files under those districts (`check_districts`).

The union is a dissolve without a geometry library: member rings are cut into directed edges,
every edge two members share (one each way) is dropped, and what is left is stitched back into
simple rings. Dropping a pair of coincident edges changes no point's even-odd count, so the union
answers exactly as the members' rings do, with the internal borders gone. It needs the members'
shared borders to have the same vertices on both sides, which Census and StatCan files have
before any simplification; borders that don't match stay in, harmlessly (the answer is the same),
and members that overlap leave the overlap outside the region under even-odd, so build from
unsimplified rings where the source simplifies per feature (packbuild.ca does).

Rows are sorted smallest region first (`area_km2`, the union's area on the sphere), so a lookup
taking the first hit gets the most specific region; query_all gives every one.
"""

import numpy as np

from placewise.geo.shapes import area
from placewise.model import Feature, Outline

from .layer import LayerData
from .polygons import _inside, signed_area, simplify_ring

LAYER = "regions"
CURATED_SOURCE = "placewise-regions"  # the curated dataset itself (CC BY 4.0), in the registry


class _LonLat:
    """The identity 'projection': rings already in (lon, lat)."""

    @staticmethod
    def inverse(x, y):
        return x, y


LONLAT = _LonLat()


# --- membership --------------------------------------------------------------------------------


def check_members(regions, known_ids):
    """Raise ValueError listing every region with no members or a member not in `known_ids`."""
    known = set(known_ids)
    problems = []
    for r in regions:
        if not r["members"]:
            problems.append(f"{r['id']}: no members")
        problems += [f"{r['id']}: {m}" for m in r["members"] if m not in known]
    if problems:
        raise ValueError(
            "region members missing from the pack's layers (fix datasets/regions):\n  "
            + "\n  ".join(problems)
        )


def check_districts(regions, pin_rows):
    """For regions with `districts`: members must be exactly the PIN areas filed under them.
    `pin_rows` are (pin id, state code "IN-DL", district) from the pincodes layer."""
    by_district = {}
    for pid, state, district in pin_rows:
        by_district.setdefault((state, (district or "").upper()), set()).add(pid)
    problems = []
    for r in regions:
        if "districts" not in r:
            continue
        want = set()
        for code, names in r["districts"].items():
            for name in names:
                pins = by_district.get((f"IN-{code}", name.upper()))
                if not pins:
                    problems.append(f"{r['id']}: no PIN area in {code} {name}")
                want |= pins or set()
        members = set(r["members"])
        if missing := sorted(want - members):
            problems.append(f"{r['id']}: missing {', '.join(missing)}")
        if extra := sorted(members - want):
            problems.append(f"{r['id']}: members not in its districts: {', '.join(extra)}")
    if problems:
        raise ValueError("region districts and members disagree:\n  " + "\n  ".join(problems))


# --- union -------------------------------------------------------------------------------------


def feature_rings(features):
    """Every ring of the features as an (n, 2) (lon, lat) array, open, shells clockwise and holes
    counter-clockwise (x east, y north), whatever winding they came in."""
    out = []
    for f in features:
        for outline in f.outlines:
            for k, ring in enumerate(outline.rings):
                pts = np.asarray(ring, dtype=np.float64)[:, ::-1]
                if len(pts) > 1 and np.array_equal(pts[0], pts[-1]):
                    pts = pts[:-1]
                if (signed_area(pts) < 0) != (k == 0):
                    pts = pts[::-1]
                out.append(pts)
    return out


def dissolve(rings):
    """Rings (n, 2 arrays, shells and holes wound oppositely) with every edge two of them share in
    opposite directions removed, stitched into simple rings (no vertex visited twice)."""
    rings = [np.asarray(r, dtype=np.float64) for r in rings]
    rings = [r[:-1] if len(r) > 1 and np.array_equal(r[0], r[-1]) else r for r in rings]
    rings = [r for r in rings if len(r) >= 3]
    if not rings:
        return []
    vertices, index = np.unique(np.vstack(rings), axis=0, return_inverse=True)
    index = index.ravel()
    tails, heads, at = [], [], 0
    for r in rings:
        ids = index[at : at + len(r)]
        at += len(r)
        tails.append(ids)
        heads.append(np.roll(ids, -1))
    a, b = np.concatenate(tails), np.concatenate(heads)
    a, b = a[a != b], b[a != b]
    n = np.int64(len(vertices))
    lo, hi = np.minimum(a, b).astype(np.int64), np.maximum(a, b).astype(np.int64)
    keys, which = np.unique(lo * n + hi, return_inverse=True)
    net = np.bincount(which.ravel(), weights=np.where(a < b, 1, -1), minlength=len(keys)).astype(np.int64)
    kept = net != 0
    lo, hi, net = keys[kept] // n, keys[kept] % n, net[kept]
    src = np.repeat(np.where(net > 0, lo, hi), np.abs(net))
    dst = np.repeat(np.where(net > 0, hi, lo), np.abs(net))
    return [vertices[c] for c in _cycles(src.tolist(), dst.tolist())]


def _cycles(src, dst):
    """Split a set of directed edges in which every vertex has as many edges in as out into simple
    cycles: walk unused edges, cutting a loop off whenever the walk comes back to a vertex on it."""
    out = {}
    for s, d in zip(src, dst, strict=True):
        out.setdefault(s, []).append(d)
    cycles = []
    for start in list(out):
        while out[start]:
            path, pos = [start], {start: 0}
            while True:
                edges = out.get(path[-1])
                if not edges:
                    raise ValueError("dissolve: unbalanced edges (rings not closed?)")
                nxt = edges.pop()
                if nxt not in pos:
                    pos[nxt] = len(path)
                    path.append(nxt)
                    continue
                i = pos[nxt]
                cycles.append(path[i:])
                for v in path[i + 1 :]:
                    del pos[v]
                del path[i + 1 :]
                if len(path) == 1 and not out[start]:
                    break
    return [c for c in cycles if len(c) >= 3]


def union(region_id, rings, tolerance=0.0, projection=LONLAT):
    """The region's Feature: `rings` (shells clockwise, in the projection's x/y) dissolved, each
    ring simplified to `tolerance` (projection units; 0 keeps every vertex) and unprojected. Each
    shell is an outline with the holes inside it; containment doesn't depend on that grouping
    (even-odd over every ring), only the outlines' look does."""
    shells, holes = [], []
    for ring in dissolve(rings):
        kept = simplify_ring(ring, tolerance)
        if kept is not None:
            (shells if signed_area(kept) < 0 else holes).append(kept)
    if not shells:
        raise ValueError(f"{region_id}: the union of its members has no area")
    shells.sort(key=lambda s: signed_area(s), reverse=True)  # smallest first, so a hole finds its own
    groups = [[s] for s in shells]
    for hole in holes:
        owner = next((g for g, s in zip(groups, shells, strict=True) if _holds(s, hole)), None)
        if owner is not None:
            owner.append(hole)
        else:  # a hole no shell holds (simplification moved it): its own part, same answer
            groups.append([hole])
    outlines = [Outline(tuple(_latlon(r, projection) for r in g)) for g in groups]
    return Feature(tuple(outlines), {}, region_id)


def _holds(shell, hole):
    lo, hi = shell.min(axis=0), shell.max(axis=0)
    if not (np.all(hole.min(axis=0) >= lo) and np.all(hole.max(axis=0) <= hi)):
        return False
    return _inside(shell, hole[:3].mean(axis=0))


def _latlon(ring, projection):
    lon, lat = projection.inverse(ring[:, 0], ring[:, 1])
    return tuple(zip(np.asarray(lat).tolist(), np.asarray(lon).tolist(), strict=True))


# --- the layer ---------------------------------------------------------------------------------


def region_area_km2(feature):
    """Shells minus holes on the sphere; parts don't overlap, so they add up."""
    total = 0.0
    for outline in feature.outlines:
        for ring in outline.rings:
            a = area([ring])
            pts = np.asarray(ring)[:, ::-1]
            total += a if signed_area(pts) < 0 else -a
    return total


def region_layer(regions, shapes, sources):
    """The `regions` LayerData: one row per region, smallest first. `shapes` maps region id to its
    union Feature; `sources` are the member layers' source ids (the curated dataset is added)."""
    rows = sorted(
        ((r, shapes[r["id"]], region_area_km2(shapes[r["id"]])) for r in regions),
        key=lambda t: (t[2], t[0]["id"]),
    )
    columns = {
        "id": [r["id"] for r, _, _ in rows],
        "name": [r["name"] for r, _, _ in rows],
        "short_name": [r["short_name"] for r, _, _ in rows],
        "kind": [r["kind"] for r, _, _ in rows],
        "country": [r["country"] for r, _, _ in rows],
        "members": [",".join(r["members"]) for r, _, _ in rows],
        "aliases": ["|".join(r["aliases"]) for r, _, _ in rows],
        "area_km2": [round(a, 1) for _, _, a in rows],
    }
    types = {k: "str" for k in columns} | {"area_km2": "f8"}
    return LayerData(
        LAYER,
        "polygon",
        columns,
        (CURATED_SOURCE, *dict.fromkeys(sources)),
        features=[f for _, f, _ in rows],
        types=types,
    )


def from_features(regions, members, sources):
    """The layer for regions whose members are features of the pack (`members`: id -> Feature, in
    longitude/latitude, as built): checked, dissolved without simplifying, and sorted."""
    check_members(regions, members)
    shapes = {r["id"]: union(r["id"], feature_rings(members[m] for m in r["members"])) for r in regions}
    return region_layer(regions, shapes, sources)


def for_country(regions, country):
    """The regions of one country (ISO 3166-1 alpha-2); `regions` None means the curated dataset."""
    if regions is None:
        from .regions import load  # the dataset loader; imported here so tests can pass their own

        regions = load()
    return [r for r in regions if r["country"] == country]


def by_id(*layers):
    """{feature id: Feature} over built polygon layers (LayerData), for from_features."""
    return {fid: f for layer in layers for fid, f in zip(layer.columns["id"], layer.features, strict=True)}

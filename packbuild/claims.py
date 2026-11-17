"""Areas India claims, kept out of other countries' packs.

placewise ships no area whose sovereignty India disputes inside another country's pack. Nepal's
COD-AB (Survey Department of Nepal, 2024) draws Nepal's view of two sectors of its border with
India: about 35 km2 round Kalapani (the "Near Om Parvat" area Natural Earth marks as administered by
India and claimed by Nepal) and about 15 km2 at Susta on the Gandak. In those sectors every
feature is cut back to India's line as Natural Earth's India point-of-view edition draws it
(`ne_10m_admin_0_countries_ind`, public domain): the part of each feature inside India's polygon
there is removed (packbuild.clip). Elsewhere along the border the two datasets differ only by the
generalisation of Natural Earth's 1:10m line (hundreds of metres, in both directions), and the
features are left as Nepal's survey draws them: the lookup applies a COD-AB pack only to points the
world pack puts in that country (engine/naming/codab.py).

A sector is a box (south, west, north, east) in degrees, wide enough to hold the whole of the
disputed area as both sides draw it (Limpiyadhura, which Nepal's 2020 map adds and its COD-AB
does not, lies inside the first box too). After cutting, `leftover` samples each box on a grid and
the build fails if any point inside India's polygon is still inside a feature.
"""

import numpy as np

from placewise.model import Feature, Outline

from . import clip

CLAIMANT = "IND"  # Natural Earth ADM0_A3 of the country whose claims are kept out
SECTORS = {
    "npl": (
        ("Kalapani, Lipulekh and Limpiyadhura", (29.95, 80.35, 30.55, 81.15)),
        ("Susta", (27.30, 83.85, 27.60, 84.20)),
    ),
}
CHECK_STEP_DEG = 0.002  # about 200 m


def claim_cuts(claimant_features, sectors):
    """[(sector name, ring)] with each ring (lon, lat) the part of the claimant's polygons inside a
    sector box: what is cut out of every feature there."""
    cuts = []
    for name, (south, west, north, east) in sectors:
        box = np.array([(west, south), (east, south), (east, north), (west, north)], dtype=np.float64)
        for feature in claimant_features:
            for outline in feature.outlines:
                ring = _xy(outline.rings[0])
                if _overlaps(_bounds(ring), (west, south, east, north)):
                    cuts += [(name, r) for r in clip.intersection(ring, box)]
    return cuts


def cut(feature, cuts):
    """The feature with every cut removed; None if nothing is left. A hole of the feature that
    crosses a cut is not handled (ValueError): no COD-AB unit has one in a sector."""
    polygons = [[_xy(r) for r in o.rings] for o in feature.outlines]
    for name, ring in cuts:
        bounds = _bounds(ring)
        out = []
        for shell, *holes in polygons:
            if not _overlaps(_bounds(shell), bounds):
                out.append([shell, *holes])
                continue
            pieces = clip.difference(shell, ring)
            for hole in holes:
                if len(clip.intersection(hole, ring)) and not clip.inside(ring, *hole[0]):
                    raise ValueError(f"{feature.id}: a hole crosses the {name} cut")
                if clip.inside(ring, *hole[0]):
                    continue  # inside the removed area already
                owner = next((p for p in pieces if clip.inside(p[0], *hole[0])), None)
                if owner is not None:
                    owner.append(hole)
            out += pieces
        polygons = out
    if not polygons:
        return None
    outlines = tuple(Outline(tuple(_latlon(r) for r in p)) for p in polygons)
    return Feature(outlines, feature.properties, feature.id)


def leftover(features, sectors, cuts, step=CHECK_STEP_DEG):
    """[(feature id, sector name, points)] for every feature still holding grid points of a
    sector that lie inside the claimant's polygon. Empty when the cut worked."""
    found = []
    for name, (south, west, north, east) in sectors:
        # cell centres: a grid on the box's own edges would sample the shared borders exactly
        rows, cols = np.arange(south + step / 2, north, step), np.arange(west + step / 2, east, step)
        lat, lon = (a.ravel() for a in np.meshgrid(rows, cols, indexing="ij"))
        claimed = np.zeros(lat.shape, dtype=bool)
        for cut_name, ring in cuts:
            if cut_name == name:
                claimed |= clip.inside(ring, lon, lat)
        lat, lon = lat[claimed], lon[claimed]
        if not len(lat):
            continue
        for f in features:
            hits = sum(int(np.count_nonzero(o.contains(lat, lon))) for o in f.outlines)
            if hits:
                found.append((f.id, name, hits))
    return found


def _xy(ring):
    a = np.asarray(ring, dtype=np.float64)[:, ::-1]  # (lat, lon) -> (x, y) = (lon, lat)
    return a[:-1] if len(a) > 1 and np.array_equal(a[0], a[-1]) else a


def _latlon(ring):
    return tuple(zip(ring[:, 1].tolist(), ring[:, 0].tolist(), strict=True))


def _bounds(ring):
    return (*ring.min(axis=0), *ring.max(axis=0))


def _overlaps(a, b):
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]

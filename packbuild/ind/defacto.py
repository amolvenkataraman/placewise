"""Which parts of the PIN areas lie outside India's de facto administered area.

India Post's PIN areas follow India's official boundary: they cover Gilgit-Baltistan and the part
of Kashmir Pakistan administers, Aksai Chin and the Shaksgam valley. Each PIN area that reaches
into a neighbouring country's de facto polygon (Natural Earth's admin-0 countries, the world
pack's `countries`) is cut along it (`clip.split`): the part on the neighbour's ground becomes
its own piece, `india_view_only` = true, so the engine shows it only under the IN worldview.
Ground no country polygon covers (the sea beyond Natural Earth's coast) is left alone: no
country is named there under any view.

Units Natural Earth gives nobody but placewise answers as India de facto (Siachen Glacier,
constants.worldviews.DE_FACTO_UNITS: where de facto is unclear placewise leans towards India) are
not neighbours: PIN areas there answer under every view.

Generalised PIN areas also overlap the neighbours' borders by a few hundred metres in many places
(Bangladesh, Nepal, Myanmar); those slivers are cut the same way. Natural Earth's 1:10m borders
are themselves generalised, so pieces near any border are approximate.
"""

import tempfile

import numpy as np

from placewise.constants.worldviews import DE_FACTO_UNITS
from placewise.packs import open_pack

from ..layer import LayerData, write_pack
from ..regions_layer import feature_rings
from . import clip
from .layers import Piece

INDIA_ID = "iso:IN"
INDIA_A3 = "IND"


class Neighbours:
    """The countries layer (LayerData) as a clip region: every unit but India (and the units
    answered as India de facto) whose box reaches India's."""

    def __init__(self, countries):
        ids = countries.columns["id"]
        a3 = countries.columns.get("adm0_a3") or [""] * len(ids)
        india = ids.index(INDIA_ID)
        lo, hi = _box(feature_rings([countries.features[india]]), pad=1.0)
        self.rows, self.rings = [], []
        for i, f in enumerate(countries.features):
            if i == india or DE_FACTO_UNITS.get(a3[i]) == INDIA_A3:
                continue
            rings = feature_rings([f])
            a, b = _box(rings)
            if np.all(a <= hi) and np.all(lo <= b):
                self.rows.append(i)
                self.rings.extend(rings)
        self.edges = clip._edges(self.rings)
        self.box = _box(self.rings) if self.rings else (np.full(2, np.inf), np.full(2, -np.inf))
        self._tmp = tempfile.TemporaryDirectory(prefix="placewise-defacto-")
        layer = LayerData(
            "countries", "polygon",
            {"id": [ids[i] for i in self.rows], "name": [ids[i] for i in self.rows]},
            countries.sources, features=[countries.features[i] for i in self.rows],
        )  # fmt: skip
        self.layer = open_pack(write_pack(self._tmp.name, "defacto", "2000.01", [layer]))["countries"]

    def contains(self, x, y):
        """Per point (lon x, lat y): inside one of the neighbours."""
        if not len(x):
            return np.zeros(0, dtype=bool)
        return np.atleast_1d(self.layer.query(np.asarray(y), np.asarray(x))) >= 0

    def near(self, rings):
        """The neighbours' edges within the rings' box, as (n, 2) two-vertex 'rings' for clip."""
        lo, hi = _box(rings)
        a, b = self.edges
        keep = np.all(np.minimum(a, b) <= hi, axis=1) & np.all(lo <= np.maximum(a, b), axis=1)
        return a[keep], b[keep]

    def split(self, rings):
        """(rings in India, rings on a neighbour's ground) for one PIN area's rings."""
        a, b = self.near(rings)
        verts = np.vstack(rings)
        if not len(a):  # no border near: wholly in India or wholly on a neighbour's ground
            lo, hi = self.box
            inside = bool(np.all(lo <= verts[0]) and np.all(verts[0] <= hi))
            inside = inside and self.contains(verts[:1, 0], verts[:1, 1]).any()
            return ([], list(rings)) if inside else (list(rings), [])
        sa, sb = clip._edges(rings)
        crossing = len(clip._crossings(sa, sb, a, b)[0]) > 0
        if not crossing and not self.contains(verts[:1, 0], verts[:1, 1]).any():
            return list(rings), []  # (a neighbour wholly inside one PIN area is not looked for)
        claimed, india = clip.split_edges(rings, a, b, self.contains)
        return india, claimed


def _box(rings, pad=0.0):
    pts = np.vstack(rings)
    return pts.min(axis=0) - pad, pts.max(axis=0) + pad


def pieces(rings_per_pin, neighbours):
    """[Piece] for every PIN area: its rings in India, and those on a neighbour's ground
    (view_only); a PIN area with nothing on a neighbour's ground is one piece, unchanged."""
    out = []
    for i, rings in enumerate(rings_per_pin):
        india, claimed = neighbours.split(rings)
        if india:
            out.append(Piece(i, tuple(india), False))
        if claimed:
            out.append(Piece(i, tuple(claimed), True))
    return out

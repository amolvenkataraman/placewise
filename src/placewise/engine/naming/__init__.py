"""Naming over the country packs: three names per point (docs/naming.md).

`sublocality` (what a local adds), `locality` (the municipality, corrected for how people talk) and
`city` (what you'd tell someone far away), plus admin2, borough, postal and regions, by each
country's rules (usa, can, ind) wherever its pack is loaded. A pack's rules apply only to points
the world pack places in that country, on ground whose data agrees (disputed areas keep the world
answer), so the world-only behaviour is unchanged everywhere else.

The rules run in two steps around the GeoNames city score: `boundaries` (polygon lookups, and
the admin1 correction the score must see), then `names`.
"""

import numpy as np

from .can import Can
from .ind import Ind
from .usa import Usa

RULES = (Usa, Can, Ind)
FIELDS = ("sublocality", "locality", "city", "borough", "admin2", "postal")


class Naming:
    def __init__(self, packs, layers, admin, cities):
        self.admin = admin
        self.rules = []
        for cls in RULES:
            pack = next((p for p in packs if cls.accepts(p)), None)
            if pack is not None:
                self.rules.append(cls(pack, layers, admin, cities))

    def __bool__(self):
        return bool(self.rules)

    def boundaries(self, a, lat, lon):
        """Per country with a pack: its points, and the state `names` continues from. Corrects
        a["aidx"] in place."""
        iso2, agreed = self.admin.iso2_of_view(a), self.admin.undisputed(a)
        work = []
        for rule in self.rules:
            pts = np.flatnonzero(agreed & (iso2 == rule.country))
            if len(pts):
                work.append((rule, pts, rule.boundaries(a, pts, lat[pts], lon[pts])))
        return work

    def names(self, a, lat, lon, work):
        """{field: object array (n,)} of Places, plus "regions" (tuples) and "sources" (one dict
        per point the rules answered, else None)."""
        n = len(lat)
        out = {f: np.full(n, None, dtype=object) for f in (*FIELDS, "regions", "sources")}
        for rule, pts, state in work:
            named = rule.names(a, pts, lat[pts], lon[pts], state)
            for field in FIELDS:
                out[field][pts] = getattr(named, field)
            out["regions"][pts] = named.regions
            sources = np.empty(len(pts), dtype=object)
            sources[:] = named.sources
            out["sources"][pts] = sources
        return out

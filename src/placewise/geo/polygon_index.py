"""Point-in-polygon at scale against full-detail polygons (your own GeoJSON or shapefile, or pack outlines).

Two stages, so detail costs little: a coarse grid of bounding boxes picks the handful of candidate
outlines for each point, then the exact even-odd test runs on the full geometry for those only.
"""

import numpy as np

from .shapes import bbox_contains


class PolygonIndex:
    def __init__(self, features, cell_deg=1.0):
        """features: placewise.model.Feature objects (e.g. from placewise.io.read_geojson).
        cell_deg: grid size; smaller cells mean fewer candidates per point but more buckets."""
        self.features = list(features)
        self.cell_deg = float(cell_deg)
        # (feature index, outline, bbox) in feature order, so the first hit is the lowest feature index
        self._outlines = [(i, o, o.bbox.as_tuple()) for i, f in enumerate(self.features) for o in f.outlines]
        self._buckets = {}
        for k, (_, _, (south, west, north, east)) in enumerate(self._outlines):
            for row in range(self._cell(south), self._cell(north) + 1):
                for col in range(self._cell(west), self._cell(east) + 1):
                    self._buckets.setdefault((row, col), []).append(k)

    def query(self, lats, lons):
        """Index of the first feature containing each point, or -1."""
        lat, lon = np.broadcast_arrays(np.asarray(lats, dtype=np.float64), np.asarray(lons, dtype=np.float64))
        flat_lat, flat_lon = lat.ravel(), lon.ravel()
        result = np.full(flat_lat.shape, -1, dtype=np.int64)
        rows, cols = self._cell(flat_lat), self._cell(flat_lon)
        cells, inverse = np.unique(np.stack([rows, cols], axis=1), axis=0, return_inverse=True)
        for c, (row, col) in enumerate(cells):
            candidates = self._buckets.get((int(row), int(col)))
            if not candidates:
                continue
            members = np.flatnonzero(inverse.ravel() == c)
            open_ = np.ones(len(members), dtype=bool)
            for k in candidates:
                feature, outline, box = self._outlines[k]
                todo = members[open_]
                if not len(todo):
                    break
                hit = np.zeros(len(todo), dtype=bool)
                in_box = np.asarray(bbox_contains(box, flat_lat[todo], flat_lon[todo]))
                if in_box.any():
                    hit[in_box] = outline.contains(flat_lat[todo][in_box], flat_lon[todo][in_box])
                result[todo[hit]] = feature
                open_[np.flatnonzero(open_)[hit]] = False
        result = result.reshape(lat.shape)
        return int(result) if result.ndim == 0 else result

    def query_all(self, lat, lon):
        """Indices of every feature containing one point, ascending."""
        candidates = self._buckets.get((self._cell(lat), self._cell(lon)), [])
        return sorted({self._outlines[k][0] for k in candidates if self._outlines[k][1].contains(lat, lon)})

    def _cell(self, value):
        cells = np.floor(np.asarray(value, dtype=np.float64) / self.cell_deg).astype(np.int64)
        return int(cells) if cells.ndim == 0 else cells

"""Outlines of a set of grid cells: the rings along the cells' edges.

A cluster is given as runs, (row, first col, end col) with the end exclusive, rows counting down.
Every ring keeps the cluster on its right, so in a y-up frame (x = col, y = -row) the outer ring
runs clockwise and holes counter-clockwise, the shapefile convention packbuild.polygons reads.
Where two cells of the cluster touch only at a corner, the ring turns right there, so they stay
apart (4-connectivity: such cells are joined only through other cells). Vertices are the corners
where the ring turns; straight runs of edges are one segment.
"""

from collections import defaultdict

import numpy as np

E, S, W, N = (1, 0), (0, 1), (-1, 0), (0, -1)  # (dcol, drow): rows count down
_RIGHT = {E: S, S: W, W: N, N: E}
_LEFT = {v: k for k, v in _RIGHT.items()}


def subtract(spans, minus):
    """The parts of sorted disjoint [a, b) spans not covered by the sorted disjoint `minus`."""
    out, k = [], 0
    for a, b in spans:
        while k < len(minus) and minus[k][1] <= a:
            k += 1
        j = k
        while j < len(minus) and minus[j][0] < b:
            lo, hi = minus[j]
            if lo > a:
                out.append((a, lo))
            a = max(a, hi)
            j += 1
        if a < b:
            out.append((a, b))
    return out


def edges(runs):
    """{start corner (col, row): [(direction, end corner), ...]} of the boundary of the cells."""
    by_row = defaultdict(list)
    for row, c0, c1 in runs:
        by_row[row].append((c0, c1))
    for spans in by_row.values():
        spans.sort()
    out = defaultdict(list)
    for row in sorted(set(by_row) | {r + 1 for r in by_row}):
        here, above = by_row.get(row, []), by_row.get(row - 1, [])
        for a, b in subtract(here, above):  # top edges of this row, eastward
            out[a, row].append((E, (b, row)))
        for a, b in subtract(above, here):  # bottom edges of the row above, westward
            out[b, row].append((W, (a, row)))
        for c0, c1 in here:
            out[c0, row + 1].append((N, (c0, row)))
            out[c1, row].append((S, (c1, row + 1)))
    return out


def rings(runs):
    """The cluster's rings, each an (n, 2) int array of (col, row) corners, not closed."""
    out_edges = edges(runs)
    found = []
    for start in sorted(out_edges):
        while out_edges.get(start):
            first, at = out_edges[start].pop(0)
            heading, corners = first, []
            while True:
                options = out_edges.get(at, [])
                if at == start:  # the first edge, already taken, may be where the ring goes on
                    options = [*options, (first, None)]
                pick = _turn(heading, options)
                direction, end = options[pick]
                if end is None:
                    if heading != first:
                        corners.append(at)
                    break
                del options[pick]
                if direction != heading:
                    corners.append(at)
                heading, at = direction, end
            found.append(np.array(corners, dtype=np.int64))
    return found


def _turn(heading, options):
    """Index of the option to follow: a right turn first, then straight on, then left."""
    for want in (_RIGHT[heading], heading, _LEFT[heading]):
        for k, (direction, _) in enumerate(options):
            if direction == want:
                return k
    raise ValueError("a ring ran into a dead end: the edges don't close")

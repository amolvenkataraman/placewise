"""Town and city outlines from the GHS-SMOD grid, named from GeoNames (the world-towns layer).

1. The settlement cells: urban centres (class 30) and towns (dense and semi-dense urban clusters,
   classes 23 and 22) of the 1 km Mollweide grid.
2. Each cell's country at its centre, from the world pack's countries (de facto, with the 12 nmi
   offshore reach the lookups use). Cells of the countries left out (those with their own packs)
   and cells out at sea are dropped.
3. Clusters: 4-connected cells of one class and one country, so a cluster crossing a border is cut
   along the cells' edges (the lookup checks the point's country too).
4. A name: the most populous GeoNames place of the cluster's country (sections, historic and
   abandoned places left out) whose point lies in one of its cells; failing that, one in a cell
   next to it (a town's point just outside its own cells). Clusters without one are dropped.
5. Population: GHS-SMOD's own vector extracts give each urban centre and dense urban cluster its
   2020 population at a population-weighted centroid; an outline gets it when it is that whole
   cluster (not cut by a border or a dropped country), else none (-1).
6. The outline: the cells' edges as rings, holes of up to HOLE_FILL_KM2 filled (a park or a river
   inside a town is still in it), simplified to `tolerance` metres and unprojected.
"""

import logging
from dataclasses import replace

import numpy as np

from packbuild import polygons
from packbuild.projection import WORLD_MOLLWEIDE

from . import trace
from .cells import clusters, read_cells

log = logging.getLogger(__name__)

CENTRE, TOWN = 0, 1
CLASS_NAMES = ("centre", "town")
SMOD_GROUPS = {30: CENTRE, 23: TOWN, 22: TOWN}  # GHS-SMOD class -> group
HOLE_FILL_KM2 = 25  # holes of up to this many 1 km cells are filled
NO_NAME_CODES = frozenset({"PPLX", "PPLH", "PPLQ", "PPLW", "PPLCH"})  # never name an outline
NO_POPULATION = -1
_NEIGHBOURS = [(dr, dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1) if dr or dc]


def outlines(tif, country_of, cities, centroids=None, excluded=(), tolerance=400.0):
    """(features, columns) of the named outlines, centres first, each class most populous first.

    tif: the GHS-SMOD GeoTiff; country_of(lon, lat) -> a country code per point ("" for none);
    cities: {"id" ("geonames:<n>"), "name", "population", "country", "feature_code", "lat",
    "lon": one entry per place}; centroids: (group, population, x, y) arrays of the vector
    extracts' clusters, or None; excluded: country codes left out."""
    grid = tif.grid
    every = read_cells(tif, SMOD_GROUPS)
    x, y = grid.x0 + (every.col + 0.5) * grid.dx, grid.y0 - (every.row + 0.5) * grid.dy
    lon, lat = WORLD_MOLLWEIDE.inverse(x, y)
    code = np.asarray(country_of(lon, lat), dtype=object)
    keep = (code != "") & ~np.isin(code, list(excluded))
    log.info("ghs-smod: %d settlement cells, %d kept", len(code), int(keep.sum()))
    cells = every.subset(keep)
    vocab, code_int = np.unique(code[keep].astype(str), return_inverse=True)
    code_int = code_int.ravel()
    found = clusters(cells, cells.group.astype(np.int64) * max(len(vocab), 1) + code_int)
    first = np.searchsorted(found.run_of_cell, np.unique(found.label, return_index=True)[1])
    cluster_code, cluster_group = vocab[code_int[first]], cells.group[first]
    place = _names(found, cells, cluster_code, cities, grid)
    population = _population(found, every, keep, first, centroids, grid)
    city_pop = np.asarray(cities["population"], dtype=np.float64)
    named = sorted(
        np.flatnonzero(place >= 0).tolist(), key=lambda k: (int(cluster_group[k]), -city_pop[place[k]], k)
    )
    log.info("ghs-smod: %d clusters, %d named", found.count, len(named))
    members = found.members()
    records = []
    for k in named:
        m = members[k]
        runs = zip(found.row[m].tolist(), found.c0[m].tolist(), found.c1[m].tolist(), strict=True)
        rings = [r for r in trace.rings(list(runs)) if not 0 < _cells_area(r) <= HOLE_FILL_KM2]
        projected = [
            np.column_stack([grid.x0 + r[:, 0] * grid.dx, grid.y0 - r[:, 1] * grid.dy]) for r in rings
        ]
        records.append((projected, k))
    features = polygons.to_features(records, tolerance, WORLD_MOLLWEIDE)
    columns = {
        "id": [f"ghs:{cluster_code[k]}:{_number(cities['id'][place[k]])}" for k in named],
        "name": [cities["name"][place[k]] for k in named],
        "geonames": [cities["id"][place[k]] for k in named],
        "class": [CLASS_NAMES[cluster_group[k]] for k in named],
        "country": [str(cluster_code[k]) for k in named],
        "population": np.array([population[k] for k in named], dtype=np.int64),
    }
    return [replace(f, id=i) for f, i in zip(features, columns["id"], strict=True)], columns


def _cells_area(ring):
    """Signed area in cells of a (col, row) ring, y up: negative for an outer (clockwise) ring."""
    x, y = ring[:, 0].astype(np.float64), -ring[:, 1].astype(np.float64)
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


def _number(geonames_id):
    return geonames_id.rpartition(":")[2]


def _cell_of(grid, x, y):
    return np.floor((grid.y0 - y) / grid.dy).astype(np.int64), np.floor((x - grid.x0) / grid.dx).astype(
        np.int64
    )


def _names(found, cells, cluster_code, cities, grid):
    """Per cluster, the city row naming it, or -1."""
    x, y = WORLD_MOLLWEIDE.forward(np.asarray(cities["lon"]), np.asarray(cities["lat"]))
    row, col = _cell_of(grid, x, y)
    pop = np.asarray(cities["population"], dtype=np.float64)
    number = np.array([int(_number(i)) for i in cities["id"]], dtype=np.int64)
    country = np.asarray(cities["country"], dtype=object)
    eligible = ~np.isin(np.asarray(cities["feature_code"], dtype=object), list(NO_NAME_CODES))
    cluster_cells = np.bincount(found.label, weights=found.c1 - found.c0, minlength=found.count)

    def cluster_at(r, c):
        pos = cells.find(r, c)
        return np.where(pos >= 0, found.label[found.run_of_cell[np.maximum(pos, 0)]], -1)

    def agrees(cl):  # the place's country is the cluster's (or the place has none)
        return (cl >= 0) & ((country == "") | (country == cluster_code[np.maximum(cl, 0)]))

    inside = cluster_at(row, col)
    best = _best(inside, agrees(inside) & eligible, pop, number, found.count)
    # places just outside: the biggest unnamed cluster in a cell next to theirs
    halo = np.full(len(pop), -1, dtype=np.int64)
    loose = eligible & (inside < 0)
    for dr, dc in _NEIGHBOURS:
        near = cluster_at(row + dr, col + dc)
        ok = loose & agrees(near) & (best[np.maximum(near, 0)] < 0)
        bigger = ok & ((halo < 0) | (cluster_cells[np.maximum(near, 0)] > cluster_cells[np.maximum(halo, 0)]))
        halo[bigger] = near[bigger]
    second = _best(halo, halo >= 0, pop, number, found.count)
    return np.where(best >= 0, best, second)


def _best(cluster, ok, pop, number, count):
    """Per cluster, the row among `ok` rows in it with the most people (lowest id on a tie)."""
    rows = np.flatnonzero(ok)
    out = np.full(count, -1, dtype=np.int64)
    if not len(rows):
        return out
    order = rows[np.lexsort((number[rows], -pop[rows], cluster[rows]))]
    first = np.concatenate(([True], cluster[order][1:] != cluster[order][:-1]))
    out[cluster[order][first]] = order[first]
    return out


def _population(found, every, keep, first, centroids, grid):
    """Per cluster, the vector extracts' population of the one cluster it is all of, else -1."""
    out = np.full(found.count, NO_POPULATION, dtype=np.int64)
    if centroids is None or not found.count:
        return out
    whole = clusters(every, every.group)  # the clusters as GHS-SMOD draws them: no borders
    whole_of_cell = whole.label[whole.run_of_cell]
    whole_cells = np.bincount(whole_of_cell, minlength=whole.count)
    own_cells = np.bincount(found.label[found.run_of_cell], minlength=found.count)
    parent = whole_of_cell[np.flatnonzero(keep)[first]]
    group, people, x, y = (np.asarray(a) for a in centroids)
    row, col = _cell_of(grid, x, y)
    pos = every.find(row, col)
    hit = pos >= 0
    hit[hit] = every.group[pos[hit]] == group[hit]
    seen = np.bincount(whole_of_cell[pos[hit]], minlength=whole.count)
    total = np.zeros(whole.count)
    np.add.at(total, whole_of_cell[pos[hit]], people[hit])
    ok = (whole_cells[parent] == own_cells) & (seen[parent] == 1)
    out[ok] = np.round(total[parent[ok]]).astype(np.int64)
    return out

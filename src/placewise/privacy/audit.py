"""A pre-share check: what an observer could infer from your data.

This is for looking at your own tracks before you share them. It runs the simple inferences anyone
holding the data could run, and reports them so you can add zones or pick a stronger policy:

- likely home: where you are stationary at night (local 00-06);
- likely work: where you are stationary on weekday working hours (local 09-17, Monday-Friday);
- repeated endpoints: places where several recordings start or end.

A clean report is not a guarantee. Real adversaries use more data (other people's tracks, maps,
photos, timing) and better methods; this only catches the most obvious leaks, and only for the
data you pass in. Run it on the processed output too, not just the raw input.
"""

from dataclasses import dataclass

import numpy as np

from placewise.constants import privacy as c
from placewise.geo import haversine
from placewise.model._base import Model
from placewise.model.geometry import Point
from placewise.tracks import Track

from ._common import segment_bounds


@dataclass(frozen=True, slots=True)
class Finding(Model):
    """One inference. `evidence` counts independent observations: distinct local days for home
    and work, recordings starting or ending there for endpoints. `precision_m` is the RMS distance
    of the cluster's points from its centre: how tightly the data pins the place down."""

    kind: str  # "home", "work" or "endpoint"
    point: Point
    precision_m: float
    evidence: int
    points: int  # raw points in the cluster
    severity: str  # "low", "medium" or "high"


@dataclass(frozen=True, slots=True)
class AuditReport(Model):
    home: Finding | None = None
    work: Finding | None = None
    endpoints: tuple[Finding, ...] = ()

    @property
    def findings(self):
        return tuple(f for f in (self.home, self.work, *self.endpoints) if f is not None)


def audit(data, *, utc_offset_h=0.0, cell_m=c.AUDIT_CELL_M):
    """Report the likely home, likely work and repeated endpoints in `data`: a Track, several
    Tracks, or a (time, lat, lon) tuple of arrays (a bag of points with no segments, so no
    endpoints). utc_offset_h turns UTC times into the local clock that "night" refers to: one
    offset in hours for every point, or one per point (a history that crosses time zones; all the
    tracks' points in order, a bag's in the order given), e.g. from each fix's lookup time zone."""
    tracks, bag, order = _as_tracks(data)
    offsets = _offsets(utc_offset_h, sum(len(t) for t in tracks), order)
    time, lat, lon, stationary, day = [], [], [], [], []
    starts, ends = [], []
    at = 0
    for track in tracks:
        if len(track) == 0:
            continue
        local = track.time + offsets[at : at + len(track)] * 3600.0
        at += len(track)
        time.append(local)
        lat.append(track.lat)
        lon.append(track.lon)
        stationary.append(_stationary(track))
        day.append(np.floor(local / 86400.0))
        for start, end in segment_bounds(track):
            starts.append((track.lat[start], track.lon[start]))
            ends.append((track.lat[end - 1], track.lon[end - 1]))
    if not time:
        return AuditReport()
    time, lat, lon = np.concatenate(time), np.concatenate(lat), np.concatenate(lon)
    stationary, day = np.concatenate(stationary), np.concatenate(day)
    hour = (time % 86400.0) / 3600.0
    weekday = (day.astype(np.int64) + 3) % 7  # 1970-01-01 was a Thursday; Monday = 0

    night = stationary & _within(hour, c.AUDIT_NIGHT_HOURS)
    work = stationary & _within(hour, c.AUDIT_WORK_HOURS) & np.isin(weekday, c.AUDIT_WORK_WEEKDAYS)
    home_finding = _densest("home", lat[night], lon[night], day[night], cell_m)
    work_finding = _densest("work", lat[work], lon[work], day[work], cell_m)

    endpoints = ()
    if starts and not bag:
        e = np.array(starts + ends)
        endpoints = _endpoint_clusters(e[:, 0], e[:, 1], cell_m)
    return AuditReport(home_finding, work_finding, endpoints)


def _as_tracks(data):
    """(tracks, whether the input was a bare bag of points, the order a bag's points were sorted
    into or None)."""
    if isinstance(data, Track):
        return [data], False, None
    if isinstance(data, tuple) and len(data) == 3 and not any(isinstance(d, Track) for d in data):
        points = Track(*data)
        order = np.argsort(points.time, kind="stable")
        return [points[order]], True, order  # speeds need time order
    return list(data), False, None


def _offsets(utc_offset_h, n, order):
    """utc_offset_h as n hours, one per point in the tracks' order (a bag's offsets re-sorted)."""
    hours = np.asarray(utc_offset_h, dtype=np.float64)
    if hours.ndim == 0:
        return np.full(n, float(hours))
    hours = hours.ravel()
    if len(hours) != n:
        raise ValueError(f"{n} points but {len(hours)} UTC offsets")
    if not np.isfinite(hours).all():
        raise ValueError("UTC offsets must be finite hours")
    return hours[order] if order is not None else hours


def _within(hour, bounds):
    start, end = bounds
    return (hour >= start) & (hour < end)


def _stationary(track):
    """Points whose slower neighbouring step (within the segment) is below walking pace; a lone
    point has nothing to say it moved, so it counts as a stop."""
    n = len(track)
    speed = np.full(n + 1, np.inf)  # speed[i] is the step from point i-1 to point i
    d = np.asarray(haversine(track.lat[:-1], track.lon[:-1], track.lat[1:], track.lon[1:])) * 1000
    dt = np.abs(np.diff(track.time))
    with np.errstate(divide="ignore", invalid="ignore"):
        speed[1:n] = np.where(dt > 0, d / dt, np.where(d > 0, np.inf, 0.0))
    for start in track.segments[1:]:
        speed[start] = np.inf  # no step across a recording gap
    before, after = speed[:n], speed[1:]
    alone = np.isinf(before) & np.isinf(after)
    return (np.minimum(before, after) <= c.AUDIT_STATIONARY_MPS) | alone


def _grid(lat, lon, cell_m):
    """Integer cells of a plain metric grid (rows cell_m tall, columns cell_m wide at the row)."""
    dlat = cell_m / c.METRES_PER_DEGREE
    row = np.floor((lat + 90.0) / dlat).astype(np.int64)
    centre = -90.0 + (row + 0.5) * dlat
    dlon = np.minimum(dlat / np.maximum(np.cos(np.radians(centre)), 1e-12), 360.0)
    col = np.floor((lon + 180.0) / dlon).astype(np.int64)
    return row, col


def _block_counts(row, col):
    """Each occupied cell and how many points fall in its 3x3 neighbourhood. Taking blocks rather
    than single cells keeps a place that straddles a cell boundary in one cluster."""
    cells, counts = np.unique(np.stack([row, col], axis=1), axis=0, return_counts=True)
    lookup = {(int(r), int(k)): int(n) for (r, k), n in zip(cells, counts, strict=True)}
    block = np.array(
        [
            sum(lookup.get((int(r) + dr, int(k) + dk), 0) for dr in (-1, 0, 1) for dk in (-1, 0, 1))
            for r, k in cells
        ]
    )
    return cells, block


def _cluster(row, col):
    """Mask of points in the densest 3x3 block."""
    cells, block = _block_counts(row, col)
    r, k = cells[int(np.argmax(block))]
    return (np.abs(row - r) <= 1) & (np.abs(col - k) <= 1)


def _centre_and_spread(lat, lon):
    centre_lat, centre_lon = float(np.mean(lat)), float(np.mean(lon))
    d = np.asarray(haversine(lat, lon, centre_lat, centre_lon)) * 1000
    return Point(centre_lat, centre_lon), float(np.sqrt(np.mean(d**2)))


def _severity(evidence):
    if evidence >= c.AUDIT_SEVERITY["high"]:
        return "high"
    return "medium" if evidence >= c.AUDIT_SEVERITY["medium"] else "low"


def _densest(kind, lat, lon, day, cell_m):
    if len(lat) == 0:
        return None
    row, col = _grid(lat, lon, cell_m)
    member = _cluster(row, col)
    point, spread = _centre_and_spread(lat[member], lon[member])
    evidence = len(np.unique(day[member]))
    return Finding(kind, point, spread, evidence, int(member.sum()), _severity(evidence))


def _endpoint_clusters(lat, lon, cell_m):
    """Greedy: take the densest block, report it if it repeats, remove its points, repeat."""
    findings = []
    remaining = np.ones(len(lat), dtype=bool)
    row, col = _grid(lat, lon, cell_m)
    while remaining.sum() >= c.AUDIT_MIN_ENDPOINTS:
        idx = np.flatnonzero(remaining)
        member = _cluster(row[idx], col[idx])
        if member.sum() < c.AUDIT_MIN_ENDPOINTS:
            break
        point, spread = _centre_and_spread(lat[idx[member]], lon[idx[member]])
        n = int(member.sum())
        findings.append(Finding("endpoint", point, spread, n, n, _severity(n)))
        remaining[idx[member]] = False
    return tuple(findings)

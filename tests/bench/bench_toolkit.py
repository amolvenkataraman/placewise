"""Benchmarks for the data-free toolkit (geo, tracks, io, privacy). Run on demand, not by pytest:

    uv run python tests/bench/bench_toolkit.py                 # every workload
    uv run python tests/bench/bench_toolkit.py frechet gpx     # workloads whose name contains a word
    uv run python tests/bench/bench_toolkit.py --digest out.json

Each workload is timed as the best of a few runs, in CPU seconds of this process (steadier than
wall time on a busy machine; BLAS is held to one thread so CPU time is the work done). --digest
also writes a SHA-256 of every workload's output, so two checkouts can be compared for
byte-identical results:

    PYTHONPATH=<other checkout>/src uv run python tests/bench/bench_toolkit.py --digest before.json

Inputs are the anonymised real rides in tests/data/tracks, scaled up synthetically: one ride is
laid end to end, each copy starting where the last ended (mirrored north-south every other
copy, so latitudes stay put), with a small seeded jitter per copy and times running on at the ride's own 1 Hz.
"""

import hashlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
TESTS = HERE.parent
sys.path.insert(0, str(TESTS / "io"))  # fit_writer, the test suite's FIT encoder

from fit_writer import MESG_EVENT, MESG_FILE_ID, MESG_RECORD, FitWriter, semicircles  # noqa: E402

from placewise import geo, privacy, tracks  # noqa: E402
from placewise import io as pio  # noqa: E402
from placewise.model.geometry import Point  # noqa: E402
from placewise.model.privacy import PrivacyZone  # noqa: E402

_ONE_THREAD = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")

RIDE = TESTS / "data" / "tracks" / "hyderabad_bengaluru_highway.gpx"
KEY = bytes(range(32))


# -- inputs ---------------------------------------------------------------------------------------


def scaled_track(n, seed=0, ride=RIDE):
    """A continuous n-point Track built from copies of a real ride (see the module docstring)."""
    base = pio.read_gpx(ride).tracks[0]
    rng = np.random.default_rng(seed)
    m = len(base)
    copies = -(-n // m)
    dlat, dlon = base.lat - base.lat[0], base.lon - base.lon[0]
    lat, lon, others = [], [], {c: [] for c in base.columns[3:]}
    at_lat, at_lon = base.lat[0], base.lon[0]
    for k in range(copies):
        sign = 1.0 if k % 2 == 0 else -1.0  # mirrored north-south every other copy
        lat.append(at_lat + sign * dlat + rng.normal(0, 2e-5, m))  # ~2 m of jitter
        lon.append(at_lon + dlon + rng.normal(0, 2e-5, m))
        at_lat, at_lon = at_lat + sign * dlat[-1], at_lon + dlon[-1]
        for c in others:
            others[c].append(getattr(base, c))
    columns = {
        "time": base.time[0] + np.arange(n, dtype=np.float64),
        "lat": np.concatenate(lat)[:n],
        "lon": np.concatenate(lon)[:n],
        **{c: np.concatenate(v)[:n] for c, v in others.items()},
        "hr": 120 + 20 * np.sin(np.arange(n) / 300.0),
    }
    return tracks.Track.from_columns(columns, meta=base.meta)


def fit_bytes(track):
    w = FitWriter()
    w.define(0, MESG_FILE_ID, [(0, "enum"), (1, "uint16"), (2, "uint16"), (4, "uint32")])
    w.message(0, {0: 4, 1: 1, 2: 1, 4: 1_000_000_000})
    w.define(
        1,
        MESG_RECORD,
        [
            (253, "uint32"),
            (0, "sint32"),
            (1, "sint32"),
            (78, "uint32"),
            (3, "uint8"),
            (5, "uint32"),
            (73, "uint32"),
            (13, "sint8"),
        ],
    )
    w.define(2, MESG_EVENT, [(253, "uint32"), (0, "enum"), (1, "enum")])
    t0 = 1_000_000_000
    lat, lon, ele, hr = track.lat, track.lon, track.ele, track.hr
    dist = np.r_[0.0, np.cumsum(np.asarray(geo.haversine(lat[:-1], lon[:-1], lat[1:], lon[1:])))] * 1e5
    for i in range(len(track)):
        if i and i % 50_000 == 0:  # a timer stop and start now and then
            w.message(2, {253: t0 + i, 0: 0, 1: 4})
            w.message(2, {253: t0 + i, 0: 0, 1: 0})
        w.message(
            1,
            {
                253: t0 + i,
                0: semicircles(lat[i]),
                1: semicircles(lon[i]),
                78: round((ele[i] + 500) * 5),
                3: round(hr[i]),
                5: round(dist[i]),
                73: round(abs(np.sin(i / 50)) * 20000),
                13: 25,
            },
        )
    return w.to_bytes()


# -- digests --------------------------------------------------------------------------------------


def digest(value):
    h = hashlib.sha256()
    _feed(h, value)
    return h.hexdigest()


def _feed(h, value):
    if isinstance(value, tracks.Track):
        h.update(repr((value.columns, value.segments, value.meta)).encode())
        for c in value.columns:
            _feed(h, getattr(value, c))
    elif isinstance(value, np.ndarray):
        h.update(str(value.dtype).encode() + str(value.shape).encode())
        h.update(np.ascontiguousarray(value).tobytes())
    elif isinstance(value, list | tuple) and not hasattr(value, "_fields"):
        h.update(b"[")
        for v in value:
            _feed(h, v)
        h.update(b"]")
    elif hasattr(value, "_fields"):  # NamedTuple
        _feed(h, tuple(value))
    elif hasattr(value, "__dataclass_fields__"):
        _feed(h, tuple(getattr(value, f) for f in value.__dataclass_fields__))
    elif isinstance(value, float):
        h.update(np.float64(value).tobytes())
    else:
        h.update(repr(value).encode())


# -- workloads ------------------------------------------------------------------------------------


def workloads():
    """(name, setup) pairs; setup() returns a zero-argument callable to time."""
    rng = np.random.default_rng(1)
    n = 1_000_000
    lat1, lon1 = rng.uniform(-80, 80, n), rng.uniform(-180, 180, n)
    lat2, lon2 = lat1 + rng.normal(0, 1, n), lon1 + rng.normal(0, 1, n)
    lat2 = np.clip(lat2, -89, 89)

    cache = {}

    def track(k):
        if k not in cache:
            cache[k] = scaled_track(k, seed=k % 997)
        return cache[k]

    def gpx_50mb():
        if "gpx" not in cache:
            t = track(400_000)
            cache["gpx"] = pio.write_gpx(t, None).encode()
        return cache["gpx"]

    def fit_big():
        if "fit" not in cache:
            cache["fit"] = fit_bytes(track(400_000))
        return cache["fit"]

    yield "geo.haversine 1M", lambda: lambda: geo.haversine(lat1, lon1, lat2, lon2)
    yield "geo.equirectangular 1M", lambda: lambda: geo.equirectangular(lat1, lon1, lat2, lon2)
    yield "geo.initial_bearing 1M", lambda: lambda: geo.initial_bearing(lat1, lon1, lat2, lon2)
    yield "geo.final_bearing 1M", lambda: lambda: geo.final_bearing(lat1, lon1, lat2, lon2)
    yield "geo.destination 1M", lambda: lambda: geo.destination(lat1, lon1, lon1 % 360, 5.0)
    yield "geo.midpoint 1M", lambda: lambda: geo.midpoint(lat1, lon1, lat2, lon2)
    yield (
        "geo.cross_track 1M",
        lambda: lambda: geo.bearing.cross_track(lat1, lon1, lat2, lon2, lat1 + 0.1, lon1),
    )
    yield "geo.to_utm 1M", lambda: lambda: geo.to_utm(lat1, lon1)
    yield "geo.to_ecef+from_ecef 1M", lambda: lambda: geo.from_ecef(*geo.to_ecef(lat1, lon1, 100.0))
    yield "geo.to_mgrs 100k", lambda: lambda: geo.to_mgrs(lat1[:100_000], lon1[:100_000])
    yield "geo.geohash_encode 100k", lambda: lambda: geo.geohash_encode(lat1[:100_000], lon1[:100_000])

    def polyline():
        t = track(100_000)
        pts = np.column_stack([t.lat, t.lon])
        return lambda: geo.polyline_decode(geo.polyline_encode(pts))

    yield "geo.polyline encode+decode 100k", polyline

    def simplify():
        t = track(100_000)
        pts = np.column_stack([t.lat, t.lon])
        return lambda: geo.simplify(pts, 10.0)

    yield "geo.simplify 100k", simplify

    def sun():
        when = 1_700_000_000.0 + np.arange(100_000) * 600.0
        return lambda: geo.sun_position(lat1[:100_000], lon1[:100_000], when)

    yield "geo.sun_position 100k", sun

    yield "tracks.clean 100k", lambda: (lambda t: lambda: t.clean())(track(100_000))
    yield "tracks.stats 100k", lambda: (lambda t: lambda: t.stats())(track(100_000))
    yield "tracks.smooth 100k", lambda: (lambda t: lambda: t.smooth())(track(100_000))
    yield (
        "tracks.smooth_elevation 100k",
        lambda: (lambda t: lambda: tracks.cleaning.smooth_elevation(t))(track(100_000)),
    )
    yield "tracks.thin 100k", lambda: (lambda t: lambda: t.thin())(track(100_000))
    yield "tracks.splits 100k", lambda: (lambda t: lambda: t.splits())(track(100_000))
    yield "tracks.best_efforts 100k", lambda: (lambda t: lambda: tracks.best_efforts(t))(track(100_000))
    yield "tracks.stays+trips 100k", lambda: (lambda t: lambda: t.trips())(track(100_000))
    yield "tracks.travel_mode 100k", lambda: (lambda t: lambda: tracks.travel_mode(t))(track(100_000))
    yield (
        "tracks.resample every_m 100k",
        lambda: (lambda t: lambda: t.resample(every_m=5.0))(track(100_000)),
    )

    def position_at():
        t = track(100_000)
        times = np.sort(rng.uniform(t.time[0] - 100, t.time[-1] + 100, 100_000))
        return lambda: t.position_at(times)

    yield "tracks.position_at 100k times", position_at

    def geotag():
        t = track(100_000)
        times = np.sort(rng.uniform(t.time[0], t.time[-1], 100_000))
        return lambda: tracks.geotag(t, times)

    yield "tracks.geotag 100k times", geotag

    def frechet():
        a = track(10_000)
        b = scaled_track(10_000, seed=99)
        return lambda: tracks.frechet_km(a, b, simplify_m=None)

    yield "tracks.frechet_km 10k x 10k", frechet

    def frechet_long():
        a, b = track(30_000), scaled_track(30_000, seed=98)
        return lambda: tracks.frechet_km(a, b, simplify_m=None)

    yield "tracks.frechet_km 30k x 30k", frechet_long

    def hausdorff():
        a, b = track(100_000), scaled_track(100_000, seed=97)
        return lambda: tracks.hausdorff_km(a, b)

    yield "tracks.hausdorff_km 100k x 100k", hausdorff

    def overlap():
        a, b = track(100_000), scaled_track(100_000, seed=96)
        return lambda: tracks.overlap(a, b)

    yield "tracks.overlap 100k x 100k", overlap

    def merge():
        a, b = track(100_000), scaled_track(100_000, seed=95)
        b = b.replace(time=b.time + 0.5)
        return lambda: tracks.merge([a, b])

    yield "tracks.merge 2 x 100k", merge

    yield "io.read_gpx 50 MB", lambda: (lambda d: lambda: pio.read_gpx(d))(gpx_50mb())
    yield "io.write_gpx 400k", lambda: (lambda t: lambda: pio.write_gpx(t, None))(track(400_000))
    yield "io.read_fit 400k records", lambda: (lambda d: lambda: pio.read_fit(d))(fit_big())

    def tcx():
        data = pio.write_tcx(track(100_000))
        return lambda: pio.read_tcx(data)

    yield "io.read_tcx 100k", tcx

    def kml():
        t = track(100_000)
        coords = " ".join(f"{lo},{la},{e}" for la, lo, e in zip(t.lat, t.lon, t.ele, strict=True))
        when = "".join(f"<when>{pio._track_common.format_iso_time(s)}</when>" for s in t.time)
        doc = (
            '<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2" '
            'xmlns:gx="http://www.google.com/kml/ext/2.2"><Document><Placemark><gx:Track>'
            + when
            + "".join(
                f"<gx:coord>{lo} {la} {e}</gx:coord>" for la, lo, e in zip(t.lat, t.lon, t.ele, strict=True)
            )
            + "</gx:Track></Placemark><Placemark><LineString><coordinates>"
            + coords
            + "</coordinates></LineString></Placemark></Document></kml>"
        ).encode()
        return lambda: pio.read_kml(doc)

    yield "io.read_kml 100k", kml

    def csv():
        path = Path(sys.argv[0]).resolve().parent / ".bench_tmp.csv"
        pio.write_csv_track(track(100_000), path)
        data = path.read_bytes()
        path.unlink()
        return lambda: pio.read_csv_track(data)

    yield "io.read_csv 100k", csv

    def geojson():
        doc = json.dumps(pio.write_geojson_track(track(100_000))).encode()
        return lambda: pio.read_geojson_tracks(doc)

    yield "io.read_geojson_tracks 100k", geojson

    def nmea():
        t = track(100_000)
        lines = []
        for s, la, lo in zip(t.time.tolist(), t.lat.tolist(), t.lon.tolist(), strict=True):
            hh, mm, ss = time.gmtime(s)[3:6]
            body = (
                f"GPRMC,{hh:02d}{mm:02d}{ss:02d}.00,A,{int(abs(la)):02d}{abs(la) % 1 * 60:07.4f},"
                f"{'N' if la >= 0 else 'S'},{int(abs(lo)):03d}{abs(lo) % 1 * 60:07.4f},"
                f"{'E' if lo >= 0 else 'W'},10.0,90.0,010101,,,A"
            )
            check = 0
            for ch in body.encode():
                check ^= ch
            lines.append(f"${body}*{check:02X}")
        data = ("\r\n".join(lines) + "\r\n").encode()
        return lambda: pio.read_nmea(data)

    yield "io.read_nmea 100k", nmea

    def privacy_apply(name):
        def setup():
            t = track(400_000)
            mid = len(t) // 2
            zone = PrivacyZone("zone", Point(float(t.lat[mid]), float(t.lon[mid])), 500.0)
            policy = privacy.preset(name, zones=[zone])
            return lambda: privacy.apply(t, policy, KEY)

        return setup

    yield "privacy.apply public_share 400k", privacy_apply("public_share")
    yield "privacy.apply research 400k", privacy_apply("research")

    def audit():
        t = track(400_000)
        return lambda: privacy.audit.audit([t])

    yield "privacy.audit 400k", audit


def main(argv):
    if any(os.environ.get(name) != "1" for name in _ONE_THREAD):  # BLAS reads these at import
        env = {**os.environ, **dict.fromkeys(_ONE_THREAD, "1")}
        os.execve(sys.executable, [sys.executable, __file__, *argv], env)
    out_path = None
    if "--digest" in argv:
        i = argv.index("--digest")
        out_path = Path(argv[i + 1])
        argv = argv[:i] + argv[i + 2 :]
    repeat = 3
    if "--repeat" in argv:
        i = argv.index("--repeat")
        repeat = int(argv[i + 1])
        argv = argv[:i] + argv[i + 2 :]
    words = argv
    digests = {}
    for name, setup in workloads():
        if words and not any(w in name for w in words):
            continue
        fn = setup()
        best, result = np.inf, None
        for _ in range(repeat):
            start = time.process_time()
            result = fn()
            best = min(best, time.process_time() - start)
        digests[name] = digest(result)
        print(f"{name:45s} {best * 1000:10.1f} ms", flush=True)
    if out_path is not None:
        out_path.write_text(json.dumps(digests, indent=1, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1:])

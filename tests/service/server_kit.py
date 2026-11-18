"""A fake geocoder and a test-server helper for the server, service and client tests.

The fake answers with Results for a few public landmarks (the nearest one to the query point), so
tests never need data packs and can count how often the engine was asked.
"""

import math
import threading
from contextlib import contextmanager

from placewise.model import BBox, Entity, Place, PlaceKind, Point, Result, Settings

DATA_VERSION = "2026.11-test"

# public landmarks: (lat, lon, label, city, admin1, country, iso2, tz)
LANDMARKS = {
    "cn_tower": (
        43.642566,
        -79.387057,
        "CN Tower, Toronto",
        "Toronto",
        "Ontario",
        "Canada",
        "CA",
        "America/Toronto",
    ),
    "eiffel": (
        48.858370,
        2.294481,
        "Eiffel Tower, Paris",
        "Paris",
        "Ile-de-France",
        "France",
        "FR",
        "Europe/Paris",
    ),
    "opera_house": (
        -33.856784,
        151.215297,
        "Sydney Opera House, Sydney",
        "Sydney",
        "New South Wales",
        "Australia",
        "AU",
        "Australia/Sydney",
    ),
}
CN_TOWER = LANDMARKS["cn_tower"][:2]
EIFFEL = LANDMARKS["eiffel"][:2]
OPERA_HOUSE = LANDMARKS["opera_house"][:2]


def _result(lat, lon):
    best = min(LANDMARKS.values(), key=lambda m: math.hypot(m[0] - lat, m[1] - lon))
    _, _, label, city, admin1, country, iso2, tz = best
    key = iso2.lower()
    return Result(
        lat=lat,
        lon=lon,
        label=label,
        country=Place(id=f"test:{key}", name=country, kind=PlaceKind.COUNTRY, codes={"iso2": iso2}),
        admin1=Place(id=f"test:{key}-1", name=admin1, kind=PlaceKind.ADMIN1),
        city=Place(id=f"test:{key}-city", name=city, kind=PlaceKind.LOCALITY, point=Point(best[0], best[1])),
        tz=tz,
        sources={"city": "test"},
        data_version=DATA_VERSION,
    )


def _entity(name):
    m = LANDMARKS[name]
    place = Place(
        id=f"test:{name}", name=m[2].split(",")[0], kind=PlaceKind.LANDMARK, point=Point(m[0], m[1])
    )
    box = BBox(m[0] - 0.001, m[1] - 0.001, m[0] + 0.001, m[1] + 0.001)
    return Entity(place, point=place.point, bbox=box, radius_km=0.1, city=m[3], country=m[6], score=1.0)


class FakeSearch:
    """find / get over the landmarks (a name in their label), recording the options asked for."""

    def find(self, text, **options):
        self._record("find", 1, options)
        return [_entity(k) for k, m in LANDMARKS.items() if text.lower() in m[2].lower()][
            : options.get("limit", 10)
        ]

    def get(self, ident, **options):
        self._record("get", 1, options)
        name = ident.removeprefix("test:")
        if name not in LANDMARKS:
            raise KeyError(ident)
        return _entity(name)


class FakeGeocoder(FakeSearch):
    """Duck-typed Geocoder: lookup / lookup_many / data_version / settings, with call counting."""

    def __init__(self, settings=None, *, fail=False):
        self.settings = settings or Settings()
        self.data_version = DATA_VERSION
        self.fail = fail
        self.calls = []  # ("lookup" | "lookup_many", n_points, worldview)
        self._lock = threading.Lock()

    def _record(self, kind, n, worldview):
        with self._lock:
            self.calls.append((kind, n, worldview))

    @property
    def points_looked_up(self):
        return sum(n for _, n, _ in self.calls)

    def lookup(self, lat, lon, *, worldview=None):
        self._record("lookup", 1, worldview)
        if self.fail:
            raise RuntimeError("secret internal detail /srv/placewise/packs")
        return _result(float(lat), float(lon))

    def lookup_many(self, lats, lons, *, worldview=None):
        lats, lons = list(lats), list(lons)
        self._record("lookup_many", len(lats), worldview)
        if self.fail:
            raise RuntimeError("secret internal detail /srv/placewise/packs")
        return [_result(float(a), float(b)) for a, b in zip(lats, lons, strict=True)]


def expected(lat, lon):
    """What FakeGeocoder returns for a point, to compare round trips against."""
    return _result(float(lat), float(lon))


class FakeClock:
    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@contextmanager
def running(server):
    """Serve in a background thread for the duration of the block."""
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


class Reply:
    def __init__(self, status, headers, body):
        self.status = status
        self.headers = headers
        self.body = body

    @property
    def json(self):
        import json

        return json.loads(self.body)

    @property
    def error_code(self):
        return self.json["error"]["code"]


def call(server, method, path, *, json_body=None, body=None, headers=None):
    """One HTTP request to a test server (TCP or Unix socket); returns a Reply."""
    import http.client
    import json
    import socket

    headers = dict(headers or {})
    if json_body is not None:
        body = json.dumps(json_body).encode()
        headers.setdefault("Content-Type", "application/json")
    if isinstance(body, str):
        body = body.encode()
    if isinstance(server.server_address, str):  # Unix socket

        class _Unix(http.client.HTTPConnection):
            def connect(self):
                self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.sock.settimeout(5)
                self.sock.connect(server.server_address)

        conn = _Unix("localhost", timeout=5)
    else:
        host, port = server.server_address[:2]
        conn = http.client.HTTPConnection(host, port, timeout=5)
    try:
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        return Reply(resp.status, resp.headers, resp.read())
    finally:
        conn.close()

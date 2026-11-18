"""The threaded server shares one real Geocoder between concurrent requests: every answer is the
one a lone request gets, and later answers stay right (no cache half built by another request)."""

import sys
import threading

import numpy as np
import pytest
from server_kit import call

from placewise.engine import Geocoder
from tests.engine.lookup_kit import write_ragged_world

CLIENTS = 8


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    return write_ragged_world(tmp_path_factory.mktemp("server-threads"))


def _requests():
    rng = np.random.default_rng(91)
    out = []
    for _ in range(CLIENTS * 3):
        n = int(rng.integers(1, 30))
        lats, lons = rng.uniform(-0.1, 2.6, n), rng.uniform(-140.1, -137.9, n)
        out.append({"points": [[round(a, 6), round(b, 6)] for a, b in zip(lats, lons, strict=True)]})
    return out


def test_concurrent_requests_share_one_geocoder_safely(serve, world):
    requests = _requests()
    alone = serve(Geocoder(packs=[world]))
    want = [call(alone, "POST", "/v1/lookup", json_body=r).json for r in requests]
    server = serve(Geocoder(packs=[world]))
    got, errors = {}, []
    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)

    def client(mine):
        try:
            for i in mine:
                got[i] = call(server, "POST", "/v1/lookup", json_body=requests[i]).json
        except Exception as err:  # reported below
            errors.append(err)

    try:
        threads = [
            threading.Thread(target=client, args=(range(c, len(requests), CLIENTS),)) for c in range(CLIENTS)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        sys.setswitchinterval(old)
    assert not errors
    assert [got[i] for i in range(len(requests))] == want
    assert [call(server, "POST", "/v1/lookup", json_body=r).json for r in requests] == want

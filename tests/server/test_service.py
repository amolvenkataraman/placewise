"""The local service: the coordinate cache, and serving over a Unix socket."""

import os
import socket
import stat

import pytest
from server_kit import CN_TOWER, EIFFEL, OPERA_HOUSE, FakeGeocoder, call, expected, running

from placewise.client import Client
from placewise.model import Settings, WorldviewSettings
from placewise.service import CachedGeocoder, make_service

LAT, LON = CN_TOWER


def test_repeat_lookups_hit_the_cache(fake):
    cached = CachedGeocoder(fake, size=100)
    first = cached.lookup(LAT, LON)
    second = cached.lookup(LAT, LON)
    assert first == second == expected(LAT, LON)
    assert len(fake.calls) == 1
    info = cached.cache_info()
    assert (info["hits"], info["misses"], info["size"], info["max_size"]) == (1, 1, 1, 100)


def test_points_within_rounding_share_an_entry_but_echo_their_own_coordinates(fake):
    cached = CachedGeocoder(fake, size=100)
    cached.lookup(LAT, LON)
    near = cached.lookup(LAT + 2e-6, LON - 2e-6)  # same 1e-5 cell
    assert len(fake.calls) == 1
    assert (near.lat, near.lon) == (LAT + 2e-6, LON - 2e-6)
    assert near.label == expected(LAT, LON).label
    cached.lookup(LAT + 2e-5, LON)  # a different cell
    assert len(fake.calls) == 2


def test_worldview_is_part_of_the_key(fake):
    cached = CachedGeocoder(fake, size=100)
    cached.lookup(LAT, LON)
    cached.lookup(LAT, LON, worldview=("IN",))
    cached.lookup(LAT, LON, worldview=["IN"])
    cached.lookup(LAT, LON, worldview="IN")
    assert len(fake.calls) == 2


def test_with_a_lock_worldview_is_not_part_of_the_key():
    fake = FakeGeocoder(Settings(worldview=WorldviewSettings(lock=True)))
    cached = CachedGeocoder(fake, size=100)
    cached.lookup(LAT, LON, worldview=("IN",))
    cached.lookup(LAT, LON, worldview=("UN",))
    assert len(fake.calls) == 1


def test_lru_eviction(fake):
    cached = CachedGeocoder(fake, size=2)
    cached.lookup(*CN_TOWER)
    cached.lookup(*EIFFEL)
    cached.lookup(*CN_TOWER)  # now most recent; Eiffel is least recent
    cached.lookup(*OPERA_HOUSE)  # evicts Eiffel
    assert cached.cache_info()["size"] == 2
    n = len(fake.calls)
    cached.lookup(*CN_TOWER)
    assert len(fake.calls) == n  # still cached
    cached.lookup(*EIFFEL)
    assert len(fake.calls) == n + 1  # was evicted


def test_lookup_many_fetches_only_misses_in_one_call(fake):
    cached = CachedGeocoder(fake, size=100)
    cached.lookup(*EIFFEL)
    points = [CN_TOWER, EIFFEL, OPERA_HOUSE, CN_TOWER]
    results = cached.lookup_many([p[0] for p in points], [p[1] for p in points])
    assert results == [expected(*p) for p in points]
    assert fake.calls[-1] == ("lookup_many", 2, None)
    cached.lookup_many([p[0] for p in points], [p[1] for p in points])
    assert len(fake.calls) == 2


def test_size_zero_disables_the_cache(fake):
    cached = CachedGeocoder(fake, size=0)
    cached.lookup(LAT, LON)
    cached.lookup(LAT, LON)
    assert len(fake.calls) == 2


def test_passes_through_version_and_settings(fake):
    cached = CachedGeocoder(fake, size=10)
    assert cached.data_version == fake.data_version
    assert cached.settings is fake.settings


def test_service_over_http_caches(fake):
    server = make_service(fake, port=0, cache_size=1000)
    with running(server):
        for _ in range(5):
            assert call(server, "GET", f"/v1/lookup?lat={LAT}&lon={LON}").status == 200
        health = call(server, "GET", "/v1/health").json
    assert len(fake.calls) == 1
    assert health["cache"]["hits"] == 4
    assert not server.require_keys


def test_service_binds_loopback_without_keys(fake):
    server = make_service(fake, port=0)
    try:
        assert server.server_address[0] == "127.0.0.1"
        assert not server.require_keys
    finally:
        server.server_close()


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX") or os.name != "posix", reason="Unix sockets")
class TestUnixSocket:
    @pytest.fixture
    def sock_path(self, tmp_path):
        # AF_UNIX paths are limited to ~100 bytes, and pytest tmp paths can be long
        import tempfile

        d = tempfile.mkdtemp(prefix="pw-")
        yield os.path.join(d, "placewise.sock")
        for name in os.listdir(d):
            os.unlink(os.path.join(d, name))
        os.rmdir(d)

    def test_serves_over_a_unix_socket(self, fake, sock_path):
        server = make_service(fake, socket_path=sock_path)
        with running(server):
            assert stat.S_ISSOCK(os.stat(sock_path).st_mode)
            assert stat.S_IMODE(os.stat(sock_path).st_mode) == 0o600
            reply = call(server, "GET", f"/v1/lookup?lat={LAT}&lon={LON}")
            assert reply.status == 200 and reply.json == expected(LAT, LON).to_dict()
            client = Client(f"unix://{sock_path}")
            assert client.lookup(*EIFFEL) == expected(*EIFFEL)
            assert client.lookup_many([LAT], [LON]) == [expected(LAT, LON)]
            client.close()
        assert not os.path.exists(sock_path)  # removed on close
        assert not server.require_keys

    def test_replaces_a_stale_socket(self, fake, sock_path):
        stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        stale.bind(sock_path)
        stale.close()  # file left behind, nobody listening
        server = make_service(fake, socket_path=sock_path)
        with running(server):
            assert call(server, "GET", "/v1/health").status == 200

    def test_refuses_a_live_socket_or_a_regular_file(self, fake, sock_path):
        server = make_service(fake, socket_path=sock_path)
        with running(server), pytest.raises(OSError, match="in use"):
            make_service(fake, socket_path=sock_path)
        with open(sock_path, "w") as f:
            f.write("not a socket")
        with pytest.raises(OSError, match="not a socket"):
            make_service(fake, socket_path=sock_path)
        with open(sock_path) as f:
            assert f.read() == "not a socket"

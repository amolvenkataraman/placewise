"""placewise.service.Client against a real test server: round trips, batching and error mapping."""

import socket

import numpy as np
import pytest
from server_kit import CN_TOWER, DATA_VERSION, EIFFEL, OPERA_HOUSE, FakeGeocoder, expected

from placewise import attribution
from placewise.model import Result, ServerSettings, Settings
from placewise.service import (
    AuthenticationError,
    BadRequestError,
    Client,
    ForbiddenError,
    NotFoundError,
    PayloadTooLargeError,
    RateLimitError,
    ServerError,
    ServiceError,
    TransportError,
)


def url(server):
    return server.url


def test_lookup_round_trip(serve):
    client = Client(url(serve()))
    result = client.lookup(*CN_TOWER)
    assert isinstance(result, Result)
    assert result == expected(*CN_TOWER)


def test_lookup_with_worldview(serve, fake):
    client = Client(url(serve()))
    assert client.lookup(*EIFFEL, worldview=("UN",)) == expected(*EIFFEL, ("UN",))
    assert client.lookup(*EIFFEL, worldview="IN,de_facto").worldview == ("IN", "de_facto")
    assert fake.calls[-1][2] == ("IN", "de_facto")


def test_lookup_many_round_trip_accepts_numpy(serve):
    client = Client(url(serve()))
    points = [CN_TOWER, EIFFEL, OPERA_HOUSE]
    lats, lons = np.array([p[0] for p in points]), np.array([p[1] for p in points])
    assert client.lookup_many(lats, lons) == [expected(*p) for p in points]
    assert client.lookup_many([], []) == []


def test_lookup_many_splits_into_server_max_batch(serve, fake):
    server = serve(Settings(server=ServerSettings(max_batch=3)))
    client = Client(url(server))
    lats = [CN_TOWER[0] + i * 1e-3 for i in range(8)]
    lons = [CN_TOWER[1]] * 8
    results = client.lookup_many(lats, lons)
    assert [r.lat for r in results] == lats  # order kept across chunks
    assert [n for kind, n, _ in fake.calls if kind == "lookup_many"] == [3, 3, 2]


def test_explicit_max_batch(serve, fake):
    client = Client(url(serve()), max_batch=2)
    client.lookup_many([1.0] * 5, [2.0] * 5)
    assert [n for _, n, _ in fake.calls] == [2, 2, 1]


def test_mismatched_lengths(serve):
    with pytest.raises(ValueError):
        Client(url(serve())).lookup_many([1.0, 2.0], [3.0])


def test_data_version_health_version_attribution(serve):
    client = Client(url(serve()))
    assert client.data_version == DATA_VERSION
    assert client.health()["status"] == "ok"
    assert client.version()["api"] == "v1"
    assert client.attribution() == attribution.render_markdown()
    assert set(client.attribution(format="json")) == set(attribution.load_sources())


def test_key_is_sent(serve, keys):
    _, token = keys.add()
    server = serve(keys=keys, require_keys=True)
    assert Client(url(server), key=token).lookup(*CN_TOWER) == expected(*CN_TOWER)
    with pytest.raises(AuthenticationError) as info:
        Client(url(server)).lookup(*CN_TOWER)
    assert info.value.status == 401 and info.value.code == "unauthorized"
    with pytest.raises(AuthenticationError):
        Client(url(server), key="pw_wrong").lookup(*CN_TOWER)


def test_errors_map_to_exceptions(serve, clock):
    server = serve(Settings(server=ServerSettings(max_batch=2)), ip_rate_limit=6)
    client = Client(url(server), max_batch=10)  # bigger than the server allows
    with pytest.raises(BadRequestError) as info:
        client.lookup(91, 0)
    assert isinstance(info.value, ValueError) and isinstance(info.value, ServiceError)
    assert info.value.status == 400 and "lat" in info.value.message
    clock.advance(100)
    with pytest.raises(PayloadTooLargeError):
        client.lookup_many([1.0] * 3, [1.0] * 3)
    clock.advance(100)
    client.lookup(*CN_TOWER)
    with pytest.raises(RateLimitError) as info:
        client.lookup(*CN_TOWER)
    assert info.value.retry_after == 10


def test_server_and_not_found_errors(serve):
    client = Client(url(serve(FakeGeocoder(fail=True))))
    with pytest.raises(ServerError) as info:
        client.lookup(*CN_TOWER)
    assert info.value.status == 500 and "secret" not in str(info.value)
    with pytest.raises(NotFoundError):
        client._request("GET", "/v1/nothing")


def test_forbidden(serve):
    client = Client(url(serve()), headers={"Origin": "https://evil.example"})
    with pytest.raises(ForbiddenError):
        client.lookup(*CN_TOWER)


def test_transport_error_when_nothing_listens():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    client = Client(f"http://127.0.0.1:{port}", timeout=2)
    with pytest.raises(TransportError) as info:
        client.lookup(*CN_TOWER)
    assert isinstance(info.value, ConnectionError)


def test_bad_urls():
    for bad in ("ftp://example.org", "example.org:8770", "unix://"):
        with pytest.raises(ValueError):
            Client(bad)


def test_warns_when_a_key_would_travel_in_clear_text():
    with pytest.warns(UserWarning, match="https"):
        Client("http://geo.example.org", key="pw_x")
    Client("https://geo.example.org", key="pw_x")
    Client("http://127.0.0.1:8770", key="pw_x")


def test_reuses_the_connection_and_recovers_after_restart(serve, fake):
    server = serve()
    client = Client(url(server))
    for _ in range(3):
        client.lookup(*CN_TOWER)
    assert len(fake.calls) == 3
    client.close()
    assert client.lookup(*CN_TOWER) == expected(*CN_TOWER)


def test_context_manager(serve):
    with Client(url(serve())) as client:
        assert client.lookup(*EIFFEL).label.startswith("Eiffel")

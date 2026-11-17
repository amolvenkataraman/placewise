"""The HTTP API over real sockets: endpoints, bad input, routing and errors, worldview lock."""

import json
import logging
import socket

import pytest
from server_kit import CN_TOWER, DATA_VERSION, EIFFEL, OPERA_HOUSE, FakeGeocoder, call, expected

from placewise import __version__, attribution
from placewise.constants import defaults
from placewise.constants import server as const
from placewise.model import ServerSettings, Settings, WorldviewSettings

LAT, LON = CN_TOWER
LOOKUP = f"/v1/lookup?lat={LAT}&lon={LON}"


def settings(**server):
    return Settings(server=ServerSettings(**server))


# -- endpoints -------------------------------------------------------------------------------------


def test_get_lookup_returns_the_result_dict(serve):
    server = serve()
    reply = call(server, "GET", LOOKUP)
    assert reply.status == 200
    assert reply.json == expected(LAT, LON).to_dict()
    assert reply.headers["Content-Type"] == "application/json"


def test_lookup_security_headers_and_no_server_banner(serve):
    reply = call(serve(), "GET", LOOKUP)
    assert reply.headers["Cache-Control"] == "no-store"
    assert reply.headers["X-Content-Type-Options"] == "nosniff"
    assert "Server" not in reply.headers
    assert "Python" not in str(reply.headers) and "BaseHTTP" not in str(reply.headers)


def test_get_lookup_passes_the_worldview(serve, fake):
    reply = call(serve(), "GET", LOOKUP + "&worldview=IN,de_facto")
    assert reply.status == 200
    assert fake.calls[-1] == ("lookup", 1, ("IN", "de_facto"))
    assert "worldview" not in reply.json


def test_post_lookup_batch(serve, fake):
    points = [CN_TOWER, EIFFEL, OPERA_HOUSE]
    reply = call(serve(), "POST", "/v1/lookup", json_body={"points": points, "worldview": ["UN"]})
    assert reply.status == 200
    assert reply.json["results"] == [expected(a, b).to_dict() for a, b in points]
    assert fake.calls[-1] == ("lookup_many", 3, ("UN",))
    assert reply.headers["Cache-Control"] == "no-store"


def test_post_lookup_empty_batch(serve):
    reply = call(serve(), "POST", "/v1/lookup", json_body={"points": []})
    assert (reply.status, reply.json) == (200, {"results": []})


def test_health(serve, clock):
    server = serve()
    clock.advance(12.5)
    reply = call(server, "GET", "/v1/health")
    assert reply.status == 200
    assert reply.json["status"] == "ok"
    assert reply.json["data_version"] == DATA_VERSION
    assert reply.json["uptime_s"] == pytest.approx(12.5)
    assert reply.headers["Cache-Control"] == "no-store"


def test_attribution_markdown_and_json(serve):
    server = serve()
    reply = call(server, "GET", "/v1/attribution")
    assert reply.status == 200
    assert reply.headers["Content-Type"].startswith("text/markdown")
    assert reply.body.decode() == attribution.render_markdown()

    reply = call(server, "GET", "/v1/attribution?format=json")
    assert reply.status == 200
    assert reply.json == {i: s.to_dict() for i, s in attribution.load_sources().items()}

    assert call(server, "GET", "/v1/attribution?format=xml").error_code == "bad_request"


class _Pack:
    def __init__(self, *sources):
        self.sources = sources


def test_attribution_lists_the_sources_of_the_packs_served(serve, fake):
    fake.packs = [_Pack("naturalearth", "geonames"), _Pack("uscensus", "not-in-the-registry")]
    server = serve()
    served = ["naturalearth", "geonames", "uscensus"]
    reply = call(server, "GET", "/v1/attribution")
    subject = "the data packs served here"
    assert reply.body.decode() == attribution.render_markdown(only=served, subject=subject)
    assert set(call(server, "GET", "/v1/attribution?format=json").json) == set(served)

    reply = call(server, "GET", "/v1/attribution?all=1")
    assert reply.body.decode() == attribution.render_markdown()
    everything = call(server, "GET", "/v1/attribution?format=json&all=1").json
    assert set(everything) == set(attribution.load_sources())
    assert call(server, "GET", "/v1/attribution?all=yes").error_code == "bad_request"


def test_attribution_through_a_wrapping_geocoder_reads_the_wrapped_packs(serve, fake):
    from placewise.service.local import CachedGeocoder

    fake.packs = [_Pack("geonames")]
    reply = call(serve(CachedGeocoder(fake)), "GET", "/v1/attribution?format=json")
    assert set(reply.json) == {"geonames"}


def test_version(serve):
    reply = call(serve(settings(max_batch=7)), "GET", "/v1/version")
    assert reply.json == {
        "placewise": __version__,
        "api": "v1",
        "data_version": DATA_VERSION,
        "max_batch": 7,
        "worldview": {"order": ["de_facto"], "locked": False},
    }


def test_version_describes_the_worldview_lock(serve):
    locked = Settings(worldview=WorldviewSettings(order=("IN", "de_facto"), lock=True))
    reply = call(serve(settings=locked), "GET", "/v1/version")
    assert reply.json["worldview"] == {"order": ["IN", "de_facto"], "locked": True}


def test_keep_alive_serves_several_requests_on_one_connection(serve):
    import http.client

    server = serve()
    conn = http.client.HTTPConnection(*server.server_address[:2], timeout=5)
    try:
        for _ in range(3):
            conn.request("GET", LOOKUP)
            resp = conn.getresponse()
            assert resp.status == 200 and json.loads(resp.read())["label"]
    finally:
        conn.close()


# -- bad input --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "lon=1",
        "lat=1",
        "lat=abc&lon=1",
        "lat=nan&lon=1",
        "lat=1&lon=inf",
        "lat=-Infinity&lon=1",
        "lat=90.5&lon=1",
        "lat=-91&lon=1",
        "lat=1&lon=180.01",
        "lat=1&lat=2&lon=1",
        "lat=1&lon=1&lng=2",
        "lat=1&lon=1&worldview=atlantis",
        "lat=1&lon=1&worldview=",
        "lat=&lon=1",
    ],
)
def test_get_lookup_rejects_bad_query(serve, query, fake):
    reply = call(serve(), "GET", f"/v1/lookup?{query}")
    assert reply.status == 400
    assert set(reply.json) == {"error"}
    assert reply.error_code == "bad_request"
    assert reply.json["error"]["message"]
    assert fake.calls == []


@pytest.mark.parametrize(
    "body",
    [
        b"{not json",
        b"[1, 2]",
        b'{"points": "43,-79"}',
        b'{"points": [[43.6]]}',
        b'{"points": [[43.6, -79.4, 0]]}',
        b'{"points": [[true, -79.4]]}',
        b'{"points": [["43.6", -79.4]]}',
        b'{"points": [[NaN, -79.4]]}',
        b'{"points": [[1e999, -79.4]]}',
        b'{"points": [[95, -79.4]]}',
        b'{"points": [[43.6, -79.4]], "worldview": "atlantis"}',
        b'{"points": [[43.6, -79.4]], "extra": 1}',
        b'{"worldview": ["UN"]}',
        b"[" * 100_000,
        b"\xff\xfe",
    ],
)
def test_post_lookup_rejects_bad_body(serve, body, fake):
    reply = call(serve(), "POST", "/v1/lookup", body=body, headers={"Content-Type": "application/json"})
    assert reply.status == 400, reply.body
    assert reply.error_code == "bad_request"
    assert fake.calls == []


def test_post_needs_json_content_type(serve):
    reply = call(
        serve(), "POST", "/v1/lookup", body=b'{"points": []}', headers={"Content-Type": "text/plain"}
    )
    assert (reply.status, reply.error_code) == (415, "unsupported_media_type")


def test_post_needs_content_length(serve):
    server = serve()
    with socket.create_connection(server.server_address[:2], timeout=5) as sock:
        sock.sendall(
            b"POST /v1/lookup HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\n"
            b"Transfer-Encoding: chunked\r\n\r\n0\r\n\r\n"
        )
        head = sock.recv(4096).decode()
    assert head.startswith("HTTP/1.1 411")


def test_batch_limit(serve, fake):
    server = serve(settings(max_batch=5))
    ok = call(server, "POST", "/v1/lookup", json_body={"points": [CN_TOWER] * 5})
    assert ok.status == 200 and len(ok.json["results"]) == 5
    reply = call(server, "POST", "/v1/lookup", json_body={"points": [CN_TOWER] * 6})
    assert (reply.status, reply.error_code) == (413, "batch_too_large")
    assert "5" in reply.json["error"]["message"]
    assert fake.points_looked_up == 5


def test_body_size_limit(serve, fake):
    server = serve(max_body=200)
    small = call(server, "POST", "/v1/lookup", json_body={"points": [CN_TOWER]})
    assert small.status == 200
    reply = call(server, "POST", "/v1/lookup", json_body={"points": [CN_TOWER] * 20})
    assert (reply.status, reply.error_code) == (413, "payload_too_large")
    assert fake.points_looked_up == 1


def test_body_size_limit_is_checked_before_reading(serve):
    server = serve(max_body=200)
    with socket.create_connection(server.server_address[:2], timeout=5) as sock:
        sock.sendall(
            b"POST /v1/lookup HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\n"
            b"Content-Length: 1000000000\r\n\r\n"
        )
        head = sock.recv(4096).decode()  # answered without waiting for a gigabyte
    assert head.startswith("HTTP/1.1 413")
    assert "Connection: close" in head


def test_default_body_limit_fits_a_full_batch():
    worst = json.dumps({"points": [[-89.123456789012, -179.12345678901]] * defaults.SERVER_MAX_BATCH})
    assert len(worst) < const.MAX_BODY_BYTES


def _read_all(sock):
    """Everything until the server closes the connection (headers and body can come separately)."""
    chunks = []
    while chunk := sock.recv(4096):
        chunks.append(chunk)
    return b"".join(chunks)


# -- routing ----------------------------------------------------------------------------------------


def test_unknown_path_is_404(serve):
    reply = call(serve(), "GET", "/v2/lookup")
    assert (reply.status, reply.error_code) == (404, "not_found")
    assert call(serve(), "GET", "/").status == 404


@pytest.mark.parametrize(
    ("method", "path", "allow"),
    [
        ("DELETE", "/v1/lookup", "GET, POST, OPTIONS"),
        ("PUT", "/v1/health", "GET, OPTIONS"),
        ("POST", "/v1/version", "GET, OPTIONS"),
    ],
)
def test_wrong_method_is_405(serve, method, path, allow):
    reply = call(serve(), method, path, json_body={})
    assert (reply.status, reply.error_code) == (405, "method_not_allowed")
    assert reply.headers["Allow"] == allow


def test_unknown_method_and_garbage_get_json_errors(serve):
    server = serve()
    reply = call(server, "BREW", "/v1/lookup")
    assert reply.status == 501 and reply.error_code
    assert "Server" not in reply.headers
    with socket.create_connection(server.server_address[:2], timeout=5) as sock:
        sock.sendall(b"NONSENSE\r\n\r\n")
        data = _read_all(sock).decode()
    assert data.startswith("HTTP/1.") and " 400 " in data.split("\r\n")[0]
    assert '"error"' in data and "Server:" not in data


def test_internal_error_is_500_without_details(serve, caplog):
    server = serve(FakeGeocoder(fail=True))
    with caplog.at_level(logging.DEBUG, logger="placewise"):
        reply = call(server, "GET", LOOKUP)
        batch = call(server, "POST", "/v1/lookup", json_body={"points": [CN_TOWER]})
    for r in (reply, batch):
        assert (r.status, r.error_code) == (500, "internal")
        assert b"secret" not in r.body and b"/srv" not in r.body and b"Traceback" not in r.body
    assert "secret internal detail" not in caplog.text  # could carry coordinates
    assert "RuntimeError" in caplog.text


# -- worldview lock ---------------------------------------------------------------------------------


def test_worldview_lock_ignores_request_worldview(serve, fake):
    locked = Settings(worldview=WorldviewSettings(order=("de_facto",), lock=True))
    server = serve(settings=locked)
    reply = call(server, "GET", LOOKUP + "&worldview=IN")
    assert reply.status == 200
    assert fake.calls[-1] == ("lookup", 1, None)
    assert reply.json["worldview_locked"] is True
    batch = call(
        server, "POST", "/v1/lookup", json_body={"points": [CN_TOWER, CN_TOWER], "worldview": ["IN"]}
    )
    assert fake.calls[-1] == ("lookup_many", 2, None)
    assert batch.json["worldview_locked"] is True  # once per response, not per result
    assert all("worldview_locked" not in r and "worldview" not in r for r in batch.json["results"])
    plain = call(server, "GET", LOOKUP)
    assert plain.json["worldview_locked"] is True


def test_unlocked_answers_carry_no_lock_flag(serve):
    server = serve()
    assert "worldview_locked" not in call(server, "GET", LOOKUP).json
    batch = call(server, "POST", "/v1/lookup", json_body={"points": [CN_TOWER]})
    assert "worldview_locked" not in batch.json and "worldview_locked" not in batch.json["results"][0]


def test_worldview_lock_from_the_geocoder_settings(serve):
    fake = FakeGeocoder(Settings(worldview=WorldviewSettings(lock=True)))
    server = serve(fake)
    call(server, "GET", LOOKUP + "&worldview=IN")
    assert fake.calls[-1][2] is None


def test_worldview_lock_reject_mode(serve, fake):
    locked = Settings(worldview=WorldviewSettings(order=("UN",), lock=True, conflict="reject"))
    server = serve(settings=locked)
    reply = call(server, "GET", LOOKUP + "&worldview=IN")
    assert (reply.status, reply.error_code) == (403, "worldview_locked")
    assert call(server, "GET", LOOKUP + "&worldview=UN").status == 200
    assert call(server, "GET", LOOKUP).status == 200

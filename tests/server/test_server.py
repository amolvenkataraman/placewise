"""The HTTP API over real sockets: endpoints, errors, auth, rate limits, CORS, logging, worldview lock."""

import hmac
import json
import logging
import os
import signal
import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest
from server_kit import CN_TOWER, DATA_VERSION, EIFFEL, OPERA_HOUSE, FakeGeocoder, call, expected

from placewise import __version__, attribution
from placewise.constants import defaults
from placewise.constants import server as const
from placewise.model import ServerSettings, Settings, WorldviewSettings
from placewise.server import keys_required

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
    assert reply.json["worldview"] == ["IN", "de_facto"]


def test_post_lookup_batch(serve, fake):
    points = [CN_TOWER, EIFFEL, OPERA_HOUSE]
    reply = call(serve(), "POST", "/v1/lookup", json_body={"points": points, "worldview": ["UN"]})
    assert reply.status == 200
    assert reply.json["results"] == [expected(a, b, ("UN",)).to_dict() for a, b in points]
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


def test_version(serve):
    reply = call(serve(settings(max_batch=7)), "GET", "/v1/version")
    assert reply.json == {
        "placewise": __version__,
        "api": "v1",
        "data_version": DATA_VERSION,
        "max_batch": 7,
    }


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


# -- API keys ---------------------------------------------------------------------------------------


def test_keys_required_by_bind_address():
    assert not keys_required("127.0.0.1", ServerSettings())
    assert not keys_required("localhost", ServerSettings())
    assert not keys_required("::1", ServerSettings())
    assert keys_required("0.0.0.0", ServerSettings())
    assert keys_required("", ServerSettings())
    assert keys_required("192.0.2.10", ServerSettings())
    assert keys_required("example.org", ServerSettings())
    assert not keys_required("0.0.0.0", ServerSettings(require_keys=False))


def test_lookup_needs_a_valid_key(serve, keys, fake):
    _, token = keys.add(label="tests")
    server = serve(keys=keys, require_keys=True)

    missing = call(server, "GET", LOOKUP)
    assert (missing.status, missing.error_code) == (401, "unauthorized")
    assert missing.headers["WWW-Authenticate"].startswith("Bearer")

    wrong = call(server, "GET", LOOKUP, headers={"Authorization": "Bearer " + token[:-2] + "xx"})
    assert (wrong.status, wrong.error_code) == (401, "unauthorized")
    assert "invalid_token" in wrong.headers["WWW-Authenticate"]

    basic = call(server, "GET", LOOKUP, headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert basic.status == 401

    ok = call(server, "GET", LOOKUP, headers={"Authorization": f"Bearer {token}"})
    assert ok.status == 200
    batch = call(
        server,
        "POST",
        "/v1/lookup",
        json_body={"points": [EIFFEL]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert batch.status == 200
    assert fake.points_looked_up == 2

    # health, version and attribution stay open for load balancers and attribution links
    for path in ("/v1/health", "/v1/version", "/v1/attribution"):
        assert call(server, "GET", path).status == 200


def test_revoked_key_stops_working_without_restart(serve, keys, tmp_path):
    record, token = keys.add(label="soon revoked")
    server = serve(keys=tmp_path / "keys.json", require_keys=True)
    auth = {"Authorization": f"Bearer {token}"}
    assert call(server, "GET", LOOKUP, headers=auth).status == 200
    keys.revoke(record.id)
    time.sleep(0.01)
    assert call(server, "GET", LOOKUP, headers=auth).status == 401


def test_required_keys_without_any_keys_rejects_everything(serve):
    server = serve(require_keys=True)
    assert call(server, "GET", LOOKUP, headers={"Authorization": "Bearer pw_anything"}).status == 401


def test_key_check_uses_constant_time_comparison(serve, keys, monkeypatch):
    calls = []
    real = hmac.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(hmac, "compare_digest", spy)
    keys.add(label="a")
    _, token = keys.add(label="b")
    server = serve(keys=keys, require_keys=True)
    assert call(server, "GET", LOOKUP, headers={"Authorization": f"Bearer {token}"}).status == 200
    assert len(calls) >= 2  # every stored key is compared, not just until the first match
    assert call(server, "GET", LOOKUP, headers={"Authorization": "Bearer pw_wrong"}).status == 401
    assert len(calls) >= 4


def test_keyless_loopback_server_ignores_authorization(serve):
    reply = call(serve(), "GET", LOOKUP, headers={"Authorization": "Bearer whatever"})
    assert reply.status == 200


# -- rate limiting ----------------------------------------------------------------------------------


def test_rate_limit_per_key(serve, keys, clock):
    per_minute = 12  # 0.2/s; bucket holds BURST_SECONDS of it = 2 requests
    burst = int(per_minute * const.BURST_SECONDS / 60)
    _, token_a = keys.add(label="a", rate_limit=per_minute)
    _, token_b = keys.add(label="b", rate_limit=per_minute)
    server = serve(keys=keys, require_keys=True)
    a = {"Authorization": f"Bearer {token_a}"}
    b = {"Authorization": f"Bearer {token_b}"}

    for _ in range(burst):
        assert call(server, "GET", LOOKUP, headers=a).status == 200
    limited = call(server, "GET", LOOKUP, headers=a)
    assert (limited.status, limited.error_code) == (429, "rate_limited")
    assert int(limited.headers["Retry-After"]) == 5  # one token at 0.2/s
    assert call(server, "GET", LOOKUP, headers=b).status == 200  # separate bucket

    clock.advance(5)
    assert call(server, "GET", LOOKUP, headers=a).status == 200
    assert call(server, "GET", LOOKUP, headers=a).status == 429


def test_rate_limit_per_ip_without_keys(serve, clock):
    server = serve(ip_rate_limit=6)  # 0.1/s, a bucket of one
    assert call(server, "GET", LOOKUP).status == 200
    limited = call(server, "GET", LOOKUP)
    assert limited.status == 429 and int(limited.headers["Retry-After"]) == 10
    clock.advance(10)
    assert call(server, "GET", LOOKUP).status == 200


def test_big_batches_cost_more(serve, clock):
    points = [CN_TOWER] * (const.POINTS_PER_TOKEN * 150)
    server = serve(settings(max_batch=len(points)), ip_rate_limit=600)  # 10/s, bucket of 100
    assert call(server, "POST", "/v1/lookup", json_body={"points": points}).status == 200
    reply = call(server, "GET", LOOKUP)  # the bucket is now 50 tokens in debt
    assert reply.status == 429 and int(reply.headers["Retry-After"]) == 6
    clock.advance(6)
    assert call(server, "GET", LOOKUP).status == 200


# -- CORS -------------------------------------------------------------------------------------------

APP = "https://maps.example.org"


def test_cors_allowed_origin(serve):
    server = serve(settings(cors_origins=(APP,)))
    reply = call(server, "GET", LOOKUP, headers={"Origin": APP})
    assert reply.status == 200
    assert reply.headers["Access-Control-Allow-Origin"] == APP
    assert "Origin" in reply.headers["Vary"]

    pre = call(
        server,
        "OPTIONS",
        "/v1/lookup",
        headers={
            "Origin": APP,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization, content-type",
        },
    )
    assert pre.status == 204
    assert pre.headers["Access-Control-Allow-Origin"] == APP
    assert "POST" in pre.headers["Access-Control-Allow-Methods"]
    assert "Authorization" in pre.headers["Access-Control-Allow-Headers"]


def test_cors_denied_origin(serve, fake):
    server = serve(settings(cors_origins=(APP,)))
    for origin in ("https://evil.example", APP + ".evil.example", "null"):
        reply = call(server, "GET", LOOKUP, headers={"Origin": origin})
        assert (reply.status, reply.error_code) == (403, "forbidden")
        assert "Access-Control-Allow-Origin" not in reply.headers
        pre = call(
            server,
            "OPTIONS",
            "/v1/lookup",
            headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
        )
        assert pre.status == 403 and "Access-Control-Allow-Origin" not in pre.headers
    assert fake.calls == []


def test_no_cors_origins_means_no_browser_access(serve):
    reply = call(serve(), "GET", LOOKUP, headers={"Origin": APP})
    assert reply.status == 403 and "Access-Control-Allow-Origin" not in reply.headers
    assert call(serve(), "GET", LOOKUP).status == 200  # non-browser clients send no Origin


def test_cors_wildcard_only_when_configured(serve):
    reply = call(serve(settings(cors_origins=("*",))), "GET", LOOKUP, headers={"Origin": APP})
    assert reply.status == 200 and reply.headers["Access-Control-Allow-Origin"] == "*"


# -- local-only protections -------------------------------------------------------------------------


def test_loopback_server_rejects_foreign_host_header(serve):
    server = serve()
    port = server.server_address[1]
    assert call(server, "GET", LOOKUP, headers={"Host": "rebind.example:8770"}).status == 403
    for host in (f"localhost:{port}", f"127.0.0.1:{port}", "localhost"):
        assert call(server, "GET", LOOKUP, headers={"Host": host}).status == 200


def test_keyless_loopback_server_refuses_proxied_requests(serve, keys):
    reply = call(serve(), "GET", LOOKUP, headers={"X-Forwarded-For": "198.51.100.7"})
    assert (reply.status, reply.error_code) == (403, "forbidden")
    assert "require-keys" in reply.json["error"]["message"]
    _, token = keys.add()
    keyed = serve(keys=keys, require_keys=True)
    headers = {"X-Forwarded-For": "198.51.100.7", "Authorization": f"Bearer {token}"}
    assert call(keyed, "GET", LOOKUP, headers=headers).status == 200


def test_connection_limit_answers_503(serve):
    server = serve(max_connections=1)
    with socket.create_connection(server.server_address[:2], timeout=5):  # holds the only slot
        time.sleep(0.2)
        reply = call(server, "GET", LOOKUP)
    assert (reply.status, reply.error_code) == (503, "busy")
    time.sleep(0.2)
    assert call(server, "GET", LOOKUP).status == 200


# -- logging ----------------------------------------------------------------------------------------

LAT_DIGITS, LON_DIGITS = "642566", "387057"


def _traffic(server):
    call(server, "GET", LOOKUP)
    call(server, "GET", f"/v1/lookup?lat={LAT}&lon=999")  # 400s too
    call(server, "POST", "/v1/lookup", json_body={"points": [CN_TOWER]})
    call(server, "POST", "/v1/lookup", body=f"[{LAT}, {LON}", headers={"Content-Type": "application/json"})
    call(server, "GET", f"/v1/lookup/{LAT},{LON}")  # unknown path holding coordinates
    with socket.create_connection(server.server_address[:2], timeout=5) as sock:
        sock.sendall(f"GET /v1/lookup?lat={LAT}&lon={LON} HTTP/9.9\r\n\r\n".encode())
        sock.recv(4096)


def test_logs_never_hold_coordinates(serve, caplog, capfd):
    server = serve()
    with caplog.at_level(logging.DEBUG):
        _traffic(server)
        time.sleep(0.05)
    out, err = capfd.readouterr()
    logged = caplog.text + out + err
    assert LAT_DIGITS not in logged and LON_DIGITS not in logged
    access = [r.getMessage() for r in caplog.records if r.name == "placewise.server.access"]
    assert any(m.startswith("GET /v1/lookup 200 ") and m.endswith("ms") for m in access)
    assert any(m.startswith("POST /v1/lookup 200 ") for m in access)
    assert any(" 400 " in m for m in access)


def test_logs_hold_coordinates_when_enabled(serve, caplog):
    server = serve(settings(log_coordinates=True))
    with caplog.at_level(logging.DEBUG):
        call(server, "GET", LOOKUP)
        call(server, "POST", "/v1/lookup", json_body={"points": [EIFFEL]})
        time.sleep(0.05)
    assert LAT_DIGITS in caplog.text and LON_DIGITS in caplog.text
    assert "858370" in caplog.text or "85837" in caplog.text


# -- worldview lock ---------------------------------------------------------------------------------


def test_worldview_lock_ignores_request_worldview(serve, fake):
    locked = Settings(worldview=WorldviewSettings(order=("de_facto",), lock=True))
    server = serve(settings=locked)
    reply = call(server, "GET", LOOKUP + "&worldview=IN")
    assert reply.status == 200
    assert fake.calls[-1] == ("lookup", 1, None)
    assert reply.json["worldview_locked"] is True
    batch = call(server, "POST", "/v1/lookup", json_body={"points": [CN_TOWER], "worldview": ["IN"]})
    assert fake.calls[-1] == ("lookup_many", 1, None)
    assert batch.json["results"][0]["worldview_locked"] is True
    plain = call(server, "GET", LOOKUP)
    assert plain.json["worldview_locked"] is True


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


# -- shutdown ---------------------------------------------------------------------------------------


@pytest.mark.skipif(os.name != "posix", reason="SIGTERM is POSIX")
def test_sigterm_shuts_down_gracefully(tmp_path):
    script = tmp_path / "srv.py"
    script.write_text(
        textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {str(Path(__file__).parent)!r})
        from server_kit import FakeGeocoder
        from placewise.server import make_server, run
        server = make_server(FakeGeocoder(), port=0)
        print(server.server_address[1], flush=True)
        run(server)
        print("stopped", flush=True)
    """)
    )
    proc = subprocess.Popen([sys.executable, str(script)], stdout=subprocess.PIPE, text=True)
    try:
        port = int(proc.stdout.readline())
        with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
            sock.sendall(b"GET /v1/health HTTP/1.0\r\n\r\n")
            assert b"200" in sock.recv(4096)
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(10) == 0
        assert proc.stdout.read().strip() == "stopped"
    finally:
        proc.kill()

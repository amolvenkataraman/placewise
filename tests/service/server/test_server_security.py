"""Who may call the API, over real sockets: API keys, rate limits, CORS, local-only protections."""

import hmac
import time

from server_kit import CN_TOWER, EIFFEL, call

from placewise.constants import server as const
from placewise.model import ServerSettings, Settings
from placewise.service.server import keys_required

LAT, LON = CN_TOWER
LOOKUP = f"/v1/lookup?lat={LAT}&lon={LON}"


def settings(**server):
    return Settings(server=ServerSettings(**server))


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

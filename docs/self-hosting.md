# Self-hosting placewise

`placewise serve` runs the HTTP JSON API. On your own machine it is the **local service**: it
listens on `127.0.0.1:8770` (or a Unix socket), keeps packs memory-mapped and answers cached in RAM,
with no keys needed. Bound anywhere else it is the **web server**: API keys, rate limits, CORS and
coordinate-free logs. This page covers hosting it for other people.

## The API

| Request | Answer |
|---|---|
| `GET /v1/lookup?lat=43.6426&lon=-79.3871&worldview=IN,de_facto` | one `Result` |
| `POST /v1/lookup` `{"points": [[lat, lon], ...], "worldview": ["UN"]}` | `{"results": [Result, ...]}` |
| `GET /v1/health` | `{"status", "data_version", "uptime_s"}` (and `cache` for the service) |
| `GET /v1/attribution` / `?format=json` | the attribution markdown / the source registry |
| `GET /v1/version` | `{"placewise", "api", "data_version", "max_batch"}` |

A `Result` is exactly `Result.to_dict()`. Errors are `{"error": {"code": ..., "message": ...}}`:

| Status | `code` | When |
|---|---|---|
| 400 | `bad_request` | lat/lon missing, not finite or out of range; bad JSON; unknown parameter |
| 401 | `unauthorized` | missing, invalid or revoked API key |
| 403 | `forbidden`, `worldview_locked` | browser origin not allowed; wrong Host on loopback; proxied request to a keyless server; a different worldview with `conflict = "reject"` |
| 404 / 405 | `not_found` / `method_not_allowed` | unknown path / wrong method (`Allow` lists the right ones) |
| 411 / 415 | `length_required` / `unsupported_media_type` | POST without Content-Length / not `application/json` |
| 413 | `batch_too_large` / `payload_too_large` | more than `server.max_batch` points / body over 1 MiB |
| 429 | `rate_limited` | over the key's (or address's) rate; wait `Retry-After` seconds |
| 500 / 503 | `internal` / `busy` | a failure (details are never sent) / too many connections |

Clients in Python use `placewise.service.Client` (also `placewise.Client`), which has the same
`lookup` / `lookup_many` as the library's `Geocoder`, batches transparently and raises one exception
class per error:

```python
from placewise.service import Client
geo = Client("https://geo.example.org", key="pw_...")
geo.lookup(43.6426, -79.3871).label
```

## API keys

Keys are required on any non-loopback bind (`server.require_keys`, on by default).

```
placewise server keys add --label "photo app" --rate-limit 600   # prints the key once
placewise server keys list                                       # ids, labels, limits; never keys
placewise server keys revoke 3f9a1c2b                            # a running server notices at once
```

- A key is `pw_` plus 32 random bytes. It is printed once and never stored: the keys file holds
  its SHA-256 (with id, label, creation time and rate limit), and checks use
  `hmac.compare_digest` against every stored hash, so a stolen keys file grants nothing and timing
  reveals nothing.
- The file is `$PLACEWISE_KEYS_FILE`, else `~/.config/placewise/server-keys.json` (macOS:
  `~/Library/Application Support/placewise/`, Windows: `%APPDATA%\placewise\`). It is written
  atomically with mode 0600 in a 0700 directory. Pass `--keys-file` to `serve` and `keys` to use
  another one.
- Clients send `Authorization: Bearer <key>`. Only send keys over HTTPS. The Python client warns
  when a key would go over plain `http://` to another machine.
- `--rate-limit` is requests per minute, 0 for unlimited (default 600). Each key has a token
  bucket holding 10 seconds of its rate. A batch costs one token per 100 points, so one big batch is
  answered and later requests wait out the debt.

## TLS via a reverse proxy

placewise speaks plain HTTP. Put a TLS-terminating proxy in front of it, and bind placewise to
loopback with `--require-keys`. Requests then all arrive from 127.0.0.1, and a loopback bind
alone would not ask for keys.

As a safety net, a loopback server *without* keys refuses any request that carries
`X-Forwarded-For`, `Forwarded`, `X-Real-IP` or `X-Forwarded-Host` (403, "restart with
--require-keys"). If you forget the flag, the proxy fails closed instead of opening your instance
to the internet.

```
placewise serve --host 127.0.0.1 --port 8770 --require-keys
```

**Caddy** (certificates are automatic):

```
geo.example.org {
    reverse_proxy 127.0.0.1:8770
    request_body {
        max_size 1MB
    }
}
```

**nginx**:

```nginx
server {
    listen 443 ssl;
    http2 on;
    server_name geo.example.org;
    ssl_certificate     /etc/letsencrypt/live/geo.example.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/geo.example.org/privkey.pem;

    client_max_body_size 1m;
    access_log off;            # or a format without $request / $args: query strings hold coordinates

    location / {
        proxy_pass http://127.0.0.1:8770;
        proxy_set_header X-Forwarded-For $remote_addr;   # fine: keys are required
        proxy_read_timeout 60s;
    }
}
```

The proxy's own access log is the usual leak. The default nginx `combined` format logs
`$request`, whose query string holds `lat` and `lon`. Turn the log off or use a format with
`$uri` instead. The Python client always sends lookups as POST bodies, so coordinates never appear
in URLs.

nginx can also proxy to a Unix socket (`proxy_pass http://unix:/run/placewise/placewise.sock;`
with `placewise serve --socket /run/placewise/placewise.sock --require-keys`). The socket is
mode 0600, so run nginx's worker as the same user or put both in a group and adjust it.

## Run as non-root, with a read-only data directory

placewise never needs root. Ports above 1024 need no privileges, and the proxy owns 443. Install
packs once as an admin step, then give the service read-only access:

```
sudo useradd --system --home /var/lib/placewise --shell /usr/sbin/nologin placewise
sudo -u placewise placewise --data-dir /var/lib/placewise/data data install world
sudo -u placewise placewise server keys add --label "my app" --keys-file /etc/placewise/server-keys.json
```

A systemd unit (`/etc/systemd/system/placewise.service`):

```ini
[Unit]
Description=placewise geocoding server
After=network.target

[Service]
User=placewise
Group=placewise
ExecStart=/usr/local/bin/placewise --offline --data-dir /var/lib/placewise/data serve \
    --host 127.0.0.1 --port 8770 --require-keys --keys-file /etc/placewise/server-keys.json
Environment=PLACEWISE_CONFIG=/etc/placewise/placewise.toml
Restart=on-failure
# the data, config and keys are read-only; nothing is written at runtime
ReadOnlyPaths=/var/lib/placewise/data /etc/placewise
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
NoNewPrivileges=true
CapabilityBoundingSet=
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
MemoryDenyWriteExecute=true

[Install]
WantedBy=multi-user.target
```

`--offline` means the server never downloads anything. Updating data is a deliberate step
(`placewise data update`, then `systemctl restart placewise`). On SIGTERM (`systemctl stop`) the
server stops accepting connections, lets requests already in progress finish (up to 10 s) and
exits.

In a container, mount the data directory read-only (`-v /srv/placewise/data:/data:ro`), run as a
non-root UID, and use `--read-only` for the root filesystem.

## Configuration that matters for hosting

In `placewise.toml` (or `PLACEWISE_SERVER_*` variables):

```toml
[server]
host = "127.0.0.1"
port = 8770
require_keys = true        # turning this off on a public address is logged as a warning
log_coordinates = false    # coordinates reveal where people live; keep it off
max_batch = 10000
cors_origins = ["https://app.example.org"]   # browsers on other origins get 403; "*" only if you list it

[worldview]
lock = true                # requests can't change the worldview; answers say worldview_locked
conflict = "ignore"        # or "reject": a request for another worldview gets 403 worldview_locked
```

## What the server does for you

- **Logs:** each request is logged as method, path (without the query string), status and
  duration. Coordinates, client addresses, request lines, unknown paths and exception messages are
  never logged unless `log_coordinates = true`. The standard library's own request logging is
  switched off.
- **Headers:** `X-Content-Type-Options: nosniff`, a `Content-Security-Policy` allowing nothing,
  `Referrer-Policy: no-referrer` and `Cache-Control: no-store` on lookups. There is no `Server`
  header with a version banner.
- **Input:** `lat` and `lon` must be finite and in range. Unknown or repeated parameters, strings
  in JSON, NaN/Infinity, deep nesting and chunked bodies are rejected. Bodies are limited to 1 MiB,
  checked against Content-Length before anything is read.
- **Connections:** at most 256 at once (the rest get an immediate 503). Each socket read times out
  after 30 s, so idle or slow clients can't hold threads.
- **Loopback:** a server bound to loopback only answers requests addressed to `localhost`,
  `127.0.0.1` or `[::1]`, which blocks DNS rebinding from web pages. A Unix socket is created with
  mode 0600, so other local users can't connect.

## What it doesn't do

- No TLS of its own (use a proxy, above).
- It doesn't trust `X-Forwarded-For`. Per-address rate limiting sees the proxy's address, which is
  why keys (rate limited per key) are required behind one.
- It isn't a DDoS shield. Put connection and request-rate limits in the proxy for a public
  instance.

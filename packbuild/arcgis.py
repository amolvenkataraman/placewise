"""Download one layer of an ArcGIS REST map service as Esri JSON query pages, cached once.

Used for Statistics Canada's map service of the 2021 boundary files, whose file server
(www12.statcan.gc.ca) answers scripted downloads with a browser check. The layer is found by name
in the service's layer list and read in the service's native spatial reference (`out_sr`), so the
coordinates are those of the published files.

The service's gateway gives up after 60 s, which the largest boundaries don't fit in at full
resolution (Ontario alone, or Nunavut's 190,000 km of coastline). So the build first asks for every
feature's perimeter (SHAPE_Length, no geometry), then requests OBJECTID ranges of at most
`batch_km` of perimeter; a feature longer than `solo_km` comes alone, and one longer than
`full_km` with ArcGIS's own generalisation (maxAllowableOffset, metres) scaled to its length. A
request that still times out is split, or its generalisation doubled. Every generalised feature is
listed in the sidecar.

Cache layout, beside fetch()'s files: `<cache>/<layer>/page-0000.json ...` and a `<layer>.json`
sidecar (service layer URL, feature and page counts, generalised features, SHA-256 and size of the
pages, retrieval date) written last, so a layer is reused only when it was downloaded completely.
"""

import datetime as dt
import hashlib
import json
import logging
import shutil
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .fetch import USER_AGENT, track

BATCH_KM = 8_000  # ~4 s of server time at full resolution
SOLO_KM = 10_000
FULL_KM = 15_000
GENERALISE_STEPS_M = (25, 50, 100, 200, 400, 800, 1600)
_RETRY_STATUS = {500, 502, 503, 504}

log = logging.getLogger(__name__)


def fetch_layer(
    service_url,
    layer_name,
    cache_dir,
    refresh=False,
    out_sr=3347,
    batch_km=None,
    solo_km=None,
    full_km=None,
    page_size=500,
):
    """Folder of query pages for the layer whose name ends with `layer_name` (e.g. "lcsd000b21s_e").
    The size limits default to the module's BATCH_KM, SOLO_KM and FULL_KM."""
    batch_km = BATCH_KM if batch_km is None else batch_km
    solo_km = SOLO_KM if solo_km is None else solo_km
    full_km = FULL_KM if full_km is None else full_km
    cache_dir = Path(cache_dir)
    dest = cache_dir / layer_name
    meta_path = cache_dir / f"{layer_name}.json"
    if dest.is_dir() and meta_path.exists() and not refresh:
        return track(dest)
    info = _json(f"{service_url}?f=json")
    matches = [layer for layer in info.get("layers", []) if str(layer.get("name", "")).endswith(layer_name)]
    if len(matches) != 1:
        raise ValueError(f"{service_url}: expected one layer named *{layer_name}, found {len(matches)}")
    layer_url = f"{service_url}/{matches[0]['id']}"
    lengths = _lengths(layer_url)
    queue = plan(lengths, batch_km, solo_km, full_km, page_size)
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{layer_name}.", dir=cache_dir))
    generalised = {}
    try:
        digest, size, pages, features = hashlib.sha256(), 0, 0, 0
        while queue:
            oids, offset = queue.pop(0)
            try:
                body = _get(_query_url(layer_url, oids, out_sr, offset))
            except (urllib.error.URLError, TimeoutError) as e:
                if not _retryable(e):
                    raise
                queue[:0] = _retry(oids, offset, layer_url, e)
                continue
            page = json.loads(body)
            if "error" in page:
                # an overloaded query comes back as HTTP 200 with {"error": {"code": 500, ...}}
                if page["error"].get("code") not in _RETRY_STATUS:
                    raise ValueError(f"{layer_url}: {page['error']}")
                queue[:0] = _retry(oids, offset, layer_url, page["error"])
                continue
            got = len(page.get("features", []))
            if got != len(oids):
                raise ValueError(
                    f"{layer_url}: asked for {len(oids)} features (OBJECTID {oids[0]}..), got {got}"
                )
            if offset:
                generalised[str(oids[0])] = offset
            (tmp / f"page-{pages:04d}.json").write_bytes(body)
            digest.update(body)
            size += len(body)
            pages += 1
            features += got
        if dest.exists():
            shutil.rmtree(dest)
        tmp.rename(dest)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    if generalised:
        log.info("%s: generalised by the service (OBJECTID: metres): %s", layer_name, generalised)
    meta = {
        "url": layer_url,
        "layer": matches[0]["name"],
        "out_sr": out_sr,
        "features": features,
        "pages": pages,
        "generalised_m": generalised,
        "sha256": digest.hexdigest(),
        "size": size,
        "retrieved": dt.datetime.now(dt.timezone.utc).date().isoformat(),
    }
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    return track(dest)


def plan(lengths, batch_km, solo_km, full_km, page_size):
    """[(OBJECTIDs, maxAllowableOffset metres or None), ...] for [(OBJECTID, perimeter km), ...]."""
    out, current, current_km = [], [], 0.0
    for oid, km in lengths:
        if km > solo_km:
            if current:
                out.append((current, None))
                current, current_km = [], 0.0
            out.append(([oid], generalisation(km) if km > full_km else None))
            continue
        if current and (current_km + km > batch_km or len(current) >= page_size):
            out.append((current, None))
            current, current_km = [], 0.0
        current.append(oid)
        current_km += km
    if current:
        out.append((current, None))
    return out


def generalisation(km):
    """maxAllowableOffset (metres) for a feature of this perimeter: about 1 m per 600 km, which
    keeps Ontario (39,000 km) and Nunavut (190,000 km) inside the gateway's 60 s."""
    return next((m for m in GENERALISE_STEPS_M if m >= km / 600), GENERALISE_STEPS_M[-1])


def _retryable(error):
    """A gateway error or a timeout (urlopen wraps a read timeout in URLError) is worth retrying
    smaller; anything else (404, refused connection, bad host) is not."""
    if isinstance(error, urllib.error.HTTPError):
        return error.code in _RETRY_STATUS
    if isinstance(error, urllib.error.URLError):
        return isinstance(error.reason, TimeoutError)
    return isinstance(error, TimeoutError)


def _retry(oids, offset, layer_url, error):
    if len(oids) > 1:
        half = len(oids) // 2
        log.info("%s: %s for %d features; splitting", layer_url, error, len(oids))
        return [(oids[:half], offset), (oids[half:], offset)]
    bigger = [m for m in GENERALISE_STEPS_M if m > (offset or 0)]
    if not bigger:
        raise RuntimeError(
            f"{layer_url}: OBJECTID {oids[0]} times out even generalised to {offset} m"
        ) from error
    log.info("%s: %s for OBJECTID %s at %s m; trying %s m", layer_url, error, oids[0], offset, bigger[0])
    return [(oids, bigger[0])]


def _query_url(layer_url, oids, out_sr, offset):
    params = {
        "where": f"OBJECTID>={oids[0]} AND OBJECTID<={oids[-1]}",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": str(out_sr),
        "orderByFields": "OBJECTID",
        "f": "json",
    }
    if offset:
        params["maxAllowableOffset"] = str(offset)
    return f"{layer_url}/query?" + urllib.parse.urlencode(params)


def _lengths(layer_url, page=2000):
    """[(OBJECTID, perimeter km), ...] in OBJECTID order, without geometry."""
    out = []
    while True:
        params = {
            "where": "1=1",
            "outFields": "OBJECTID,SHAPE_Length",
            "returnGeometry": "false",
            "orderByFields": "OBJECTID",
            "resultOffset": str(len(out)),
            "resultRecordCount": str(page),
            "f": "json",
        }
        data = _json(f"{layer_url}/query?" + urllib.parse.urlencode(params))
        rows = [f["attributes"] for f in data.get("features", [])]
        out += [(int(a["OBJECTID"]), float(a.get("SHAPE_Length") or 0) / 1000) for a in rows]
        if not rows or not data.get("exceededTransferLimit"):
            return out


def _json(url):
    data = json.loads(_get(url))
    if "error" in data:
        raise ValueError(f"{url}: {data['error']}")
    return data


def _get(url, timeout=120):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()

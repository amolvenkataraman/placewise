"""Download the features of an ArcGIS REST layer that match a `where` clause, as Esri JSON pages.

The park sources publish their outlines as ArcGIS feature or map services (PAD-US 4.1 and NPS on
ArcGIS Online, CPCAD on maps-cartes.ec.gc.ca); their file downloads are File Geodatabases, which
placewise cannot read without GDAL. So the build asks the service for the object ids matching
`where`, then for the features in pages of `page_size` ids (POST), in the spatial reference
`out_sr`, generalised by the service to `offset` (maxAllowableOffset, in out_sr units) and
rounded to `precision` decimals. A page the service refuses (timeout, gateway or service
error, transfer limit) is split in half and asked again; a single feature it refuses is asked
for ungeneralised (listed in the sidecar's `ungeneralised`), and fails if that is refused too.

Cache layout: `<cache>/<name>/page-0000.json ...` plus a `<name>.json` sidecar (layer URL, the
query, feature and page counts, SHA-256 and size of the pages, retrieval date), written last, so
a download is reused only when it finished.
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

import numpy as np

from ...fetch import USER_AGENT

_RETRY_STATUS = {500, 502, 503, 504}
log = logging.getLogger(__name__)


def fetch_query(
    layer_url, where, cache_dir, name, *, fields="*", out_sr=3857, offset=None, precision=None,
    page_size=500, refresh=False, post=None,
):  # fmt: skip
    """Folder of query pages for the features of `layer_url` matching `where`. `post(url, params)`
    returns the response body (default: urllib POST); tests pass their own."""
    post = post or _post
    cache_dir = Path(cache_dir)
    dest, meta_path = cache_dir / name, cache_dir / f"{name}.json"
    if dest.is_dir() and meta_path.exists() and not refresh:
        return dest
    ids = _ids(post, layer_url, where)
    params = {"outFields": fields, "returnGeometry": "true", "outSR": str(out_sr), "f": "json"}
    if offset:
        params["maxAllowableOffset"] = str(offset)
    if precision is not None:
        params["geometryPrecision"] = str(precision)
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{name}.", dir=cache_dir))
    try:
        queue = [ids[i : i + page_size] for i in range(0, len(ids), page_size)]
        digest, size, pages, ungeneralised = hashlib.sha256(), 0, 0, []
        while queue:
            batch = queue.pop(0)
            body, problem = _page(post, layer_url, params, batch)
            if problem is not None and len(batch) == 1 and offset:
                # some geometries the service can't generalise (an Alaska parcel of 1,259 rings)
                full = {k: v for k, v in params.items() if k != "maxAllowableOffset"}
                body, problem = _page(post, layer_url, full, batch)
                ungeneralised += batch if problem is None else []
            if problem is not None:
                if len(batch) == 1:
                    raise RuntimeError(f"{layer_url}: object id {batch[0]}: {problem}")
                log.info("%s: %s for %d features; splitting", name, problem, len(batch))
                half = len(batch) // 2
                queue[:0] = [batch[:half], batch[half:]]
                continue
            (tmp / f"page-{pages:04d}.json").write_bytes(body)
            digest.update(body)
            size += len(body)
            pages += 1
        if dest.exists():
            shutil.rmtree(dest)
        tmp.rename(dest)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    meta = {
        "url": layer_url,
        "where": where,
        "query": params,
        "features": len(ids),
        "pages": pages,
        "ungeneralised": ungeneralised,
        "sha256": digest.hexdigest(),
        "size": size,
        "retrieved": dt.datetime.now(dt.timezone.utc).date().isoformat(),
    }
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    return dest


def ungeneralised(folder):
    """The object ids the service sent at full resolution (the sidecar's `ungeneralised`)."""
    meta = Path(folder).with_name(Path(folder).name + ".json")
    return set(json.loads(meta.read_text()).get("ungeneralised", ())) if meta.exists() else set()


def read_pages(folder):
    """[(attributes, rings), ...] in page order; rings are (n, 2) float arrays in the query's
    spatial reference. Features without geometry are left out."""
    out = []
    for page in sorted(Path(folder).glob("page-*.json")):
        for feature in json.loads(page.read_bytes()).get("features", []):
            rings = (feature.get("geometry") or {}).get("rings") or []
            if rings:
                out.append((feature["attributes"], [np.asarray(r, dtype=np.float64) for r in rings]))
    return out


def _ids(post, layer_url, where):
    data = json.loads(post(f"{layer_url}/query", {"where": where, "returnIdsOnly": "true", "f": "json"}))
    if "error" in data:
        raise ValueError(f"{layer_url}: {data['error']}")
    return sorted(int(i) for i in data.get("objectIds") or [])


def _page(post, layer_url, params, batch):
    """(body, None), or (None, why) when the page should be split and asked again."""
    try:
        body = post(f"{layer_url}/query", {**params, "objectIds": ",".join(map(str, batch))})
    except urllib.error.HTTPError as e:
        if e.code in _RETRY_STATUS:
            return None, f"HTTP {e.code}"
        raise
    except (urllib.error.URLError, TimeoutError) as e:
        if isinstance(e, urllib.error.URLError) and not isinstance(e.reason, TimeoutError):
            raise
        return None, "timeout"
    page = json.loads(body)
    if "error" in page:  # an overloaded page can come back as 400 "Cannot perform query" too
        return None, f"service error {page['error']}"
    got = len(page.get("features", []))
    if page.get("exceededTransferLimit") or got != len(batch):
        return None, f"{got} of {len(batch)} features"
    return body, None


def _post(url, params, timeout=180):
    data = urllib.parse.urlencode(params).encode()
    request = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()

"""Members of a remote zip, downloaded with HTTP range requests instead of the whole archive.

Some packages put every level of a country in one zip (Thailand's COD-AB shapefiles are 377 MB, the
tambon level alone 179 MB of it); a build that needs some members reads the zip's central
directory from its end and then only those members' bytes. The server must honour `Range` (HDX
answers with a redirect to S3, which does). zipfile checks each member's CRC-32 as it is read.

Members land in `<cache>/<zip name without .zip>/`, the folder `fetch.unzip` would extract the
whole archive to, with a `<folder>.members.json` sidecar recording the URL, retrieval date, the
archive's size and each member's SHA-256 and size. If the whole zip is already cached (by
`fetch.fetch`), it is unzipped instead and nothing is downloaded.
"""

import datetime as dt
import hashlib
import io
import json
import os
import shutil
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from .fetch import DEFAULT_CACHE, USER_AGENT, unzip

BLOCK = 4 << 20  # bytes per range request: few requests, little over-read


def fetch_members(url, members, cache_dir=DEFAULT_CACHE, refresh=False, ranged=None):
    """The folder holding `members` (names inside the zip at `url`, or a function choosing them
    from the zip's member names), downloading those missing. `ranged(url, start, end) -> (bytes,
    total size, final url)` reads bytes start..end inclusive (default: urllib with a Range header).
    A name the zip lacks is a KeyError listing what it has."""
    cache_dir = Path(cache_dir)
    name = Path(urllib.parse.urlparse(url).path).name
    if not name.endswith(".zip"):
        raise ValueError(f"{url!r} does not name a .zip")
    whole = cache_dir / name
    if whole.exists() and whole.with_name(name + ".json").exists() and not refresh:
        folder = unzip(whole)
        if callable(members):
            members(sorted(p.name for p in folder.iterdir()))  # checks the choice still works
        return folder
    folder = cache_dir / name[: -len(".zip")]
    sidecar = folder.with_name(folder.name + ".members.json")
    meta = json.loads(sidecar.read_text()) if sidecar.exists() and not refresh else {}
    have = meta.get("members", {})
    if not callable(members) or "names" in meta:
        missing = _missing(members, meta.get("names"), have, folder)
        if not missing:
            return folder
    remote = RemoteFile(url, ranged or _urllib_range)
    with zipfile.ZipFile(io.BufferedReader(remote, BLOCK)) as z:
        names = z.namelist()
        missing = _missing(members, names, have, folder)
        known = set(names)
        if absent := [m for m in missing if m not in known]:
            raise KeyError(f"{name} has no member(s) {absent}; it has {sorted(known)}")
        folder.mkdir(parents=True, exist_ok=True)
        for member in missing:
            have[member] = _extract(z, member, folder)
    meta = {
        "url": url,
        "retrieved": dt.datetime.now(dt.timezone.utc).date().isoformat(),
        "archive_size": remote.size,
        "names": names,
        "members": dict(sorted(have.items())),
    }
    sidecar.write_text(json.dumps(meta, indent=2) + "\n")
    return folder


def _missing(members, names, have, folder):
    wanted = list(dict.fromkeys(members(names) if callable(members) else members))
    return [m for m in wanted if m not in have or not (folder / m).is_file()]


def _extract(z, member, folder):
    """Write one member (flat, by its base name: members are plain file names) atomically."""
    target = folder / Path(member).name
    if target.name != member:
        raise ValueError(f"member {member!r} is in a folder; only top-level members are fetched")
    partial = target.with_name(target.name + ".part")
    digest, size = hashlib.sha256(), 0
    try:
        with z.open(member) as src, partial.open("wb") as out:
            while chunk := src.read(1 << 20):
                digest.update(chunk)
                size += len(chunk)
                out.write(chunk)
        os.replace(partial, target)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return {"sha256": digest.hexdigest(), "size": size}


class RemoteFile(io.RawIOBase):
    """A read-only, seekable file over HTTP range requests. The first request resolves redirects
    and the total size; later ones go to the resolved URL, resolving again once if it has expired
    (S3 pre-signed URLs do)."""

    def __init__(self, url, ranged):
        self.url, self._ranged, self.pos = url, ranged, 0
        _, self.size, self._final = ranged(url, 0, 0)
        self.fetched = 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=io.SEEK_SET):
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self.pos, io.SEEK_END: self.size}[whence]
        self.pos = max(0, base + offset)
        return self.pos

    def readinto(self, buffer):
        n = min(len(buffer), self.size - self.pos)
        if n <= 0:
            return 0
        data = self._get(self.pos, self.pos + n - 1)
        buffer[: len(data)] = data
        self.pos += len(data)
        self.fetched += len(data)
        return len(data)

    def _get(self, start, end):
        try:
            data, _, _ = self._ranged(self._final, start, end)
        except urllib.error.HTTPError as e:
            if e.code not in (400, 403):
                raise
            _, _, self._final = self._ranged(self.url, 0, 0)
            data, _, _ = self._ranged(self._final, start, end)
        if len(data) != end - start + 1:
            raise ValueError(f"{self.url}: asked for {end - start + 1} bytes at {start}, got {len(data)}")
        return data


def _urllib_range(url, start, end, timeout=120):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Range": f"bytes={start}-{end}"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 206:
            raise OSError(f"{url}: the server ignored the Range header (HTTP {response.status})")
        total = int(response.headers["Content-Range"].rpartition("/")[2])
        out = io.BytesIO()
        shutil.copyfileobj(response, out)
        return out.getvalue(), total, response.url

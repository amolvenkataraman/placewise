"""Download-once cache for build inputs.

Each file lands in the cache directory under its URL's basename, with a `<name>.json` sidecar
recording the URL, SHA-256, size and retrieval date (the attribution `retrieved` date). A file that
is already cached is never downloaded again unless `refresh=True`.
"""

import datetime as dt
import hashlib
import json
import os
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

USER_AGENT = "placewise-build"
ENV_CACHE = "PACKBUILD_CACHE"  # not PLACEWISE_*: placewise's config loader rejects unknown ones
# downloads and built packs live with everything else placewise downloads, unless configured
DEFAULT_CACHE = Path(os.environ.get(ENV_CACHE) or Path.home() / ".placewise" / "packbuild").expanduser()
_CHUNK = 1 << 20


def fetch(url, cache_dir=DEFAULT_CACHE, refresh=False, timeout=60):
    """Path of the cached copy of `url`, downloading it first if needed."""
    cache_dir = Path(cache_dir)
    name = Path(urllib.parse.urlparse(url).path).name
    if not name:
        raise ValueError(f"no file name in {url!r}")
    path = cache_dir / name
    meta_path = path.with_name(name + ".json")
    if path.exists() and meta_path.exists() and not refresh:
        return path
    cache_dir.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(name + ".part")
    digest, size = hashlib.sha256(), 0
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, partial.open("wb") as out:
            while chunk := response.read(_CHUNK):
                digest.update(chunk)
                size += len(chunk)
                out.write(chunk)
        os.replace(partial, path)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    meta = {
        "url": url,
        "sha256": digest.hexdigest(),
        "size": size,
        "retrieved": dt.datetime.now(dt.timezone.utc).date().isoformat(),
    }
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    return path


def metadata(path):
    """The sidecar record written by `fetch` for a cached file."""
    path = Path(path)
    return json.loads(path.with_name(path.name + ".json").read_text())


def unzip(archive, dest=None):
    """Extract a zip into `dest` (default: beside it, named after it) once; returns the directory.
    Members that would land outside the directory are refused."""
    archive = Path(archive)
    dest = Path(dest) if dest else archive.with_suffix("")
    done = dest / ".extracted"
    if done.exists():
        return dest
    root = dest.resolve()
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            target = (root / member.filename).resolve()
            if target != root and root not in target.parents:
                raise ValueError(f"{archive.name}: member {member.filename!r} is outside the target")
        dest.mkdir(parents=True, exist_ok=True)
        z.extractall(dest)
    done.write_text(archive.name + "\n")
    return dest

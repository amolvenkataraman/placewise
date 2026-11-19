"""Download-once cache for build inputs, and deleting them once the build has parsed them.

Each file lands in the cache directory under its URL's basename, with a `<name>.json` sidecar
recording the URL, SHA-256, size and retrieval date (the attribution `retrieved` date). A file that
is already cached is never downloaded again unless `refresh=True`.

Every raw file or folder a build fetches or extracts (here, and in the other downloaders: ArcGIS
pages, HydroLAKES, LGD's 7z) is noted with `track`. A builder's `main` ends with
`delete_downloads(args)`, which deletes exactly those, with their sidecars, once the pack is
written (owner: no duplicate data on disk); a failed build never gets there, so a retry finds its
downloads cached. `--keep-downloads` (`add_keep_downloads`) keeps them.
"""

import datetime as dt
import hashlib
import json
import logging
import os
import shutil
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

USER_AGENT = "placewise-build"
ENV_CACHE = "PACKBUILD_CACHE"  # not PLACEWISE_*: placewise's config loader rejects unknown ones
# downloads and built packs live with everything else placewise downloads, unless configured
DEFAULT_CACHE = Path(os.environ.get(ENV_CACHE) or Path.home() / ".placewise" / "packbuild").expanduser()
_CHUNK = 1 << 20
_FETCHED = {}  # raw files and folders this process fetched or extracted (track), in order
log = logging.getLogger(__name__)


def track(path, sidecar=True):
    """Note `path` (a file or folder) as a raw download or extraction of this build, with its
    `<name>.json` sidecar unless `sidecar=False`, for delete_downloads; returns it."""
    path = Path(path)
    _FETCHED[path] = None
    if sidecar:
        _FETCHED[path.with_name(path.name + ".json")] = None
    return path


def add_keep_downloads(parser):
    """The builders' --keep-downloads flag (argparse)."""
    parser.add_argument(
        "--keep-downloads", action="store_true", help="keep the raw downloads after a successful build"
    )


def delete_downloads(args):
    """After a successful build: delete what it fetched or extracted (track) inside
    `args.cache_dir`, then the folders that left empty; never `args.out` or anything in it, never
    a file this build didn't touch. Nothing with `args.keep_downloads`. Returns the paths deleted."""
    found, keep = list(_FETCHED), getattr(args, "keep_downloads", False)
    _FETCHED.clear()
    if keep:
        log.info("kept %d raw downloads (--keep-downloads)", sum(p.exists() for p in found))
        return []
    cache = Path(args.cache_dir).resolve()
    out = Path(args.out).resolve() if getattr(args, "out", None) else None
    deleted, size = [], 0
    for path in found:
        full = path.resolve()
        if cache not in full.parents or _holds_out(full, out):
            continue
        if full.is_dir() and not full.is_symlink():
            size += sum(f.stat().st_size for f in full.rglob("*") if f.is_file())
            shutil.rmtree(full)
        elif full.exists() or full.is_symlink():
            size += full.lstat().st_size
            full.unlink()
        else:
            continue
        deleted.append(path)
        _prune(full.parent, cache, out)
    log.info("deleted %d raw downloads (%.1f MB)", len(deleted), size / 1e6)
    return deleted


def _holds_out(path, out):
    """Whether `path` is the output folder, inside it, or a folder holding it."""
    return out is not None and (path == out or out in path.parents or path in out.parents)


def _prune(folder, cache, out):
    """Remove `folder` and its parents below `cache` while they are empty (never out/)."""
    while folder != cache and cache in folder.parents and folder != out:
        try:
            folder.rmdir()
        except OSError:  # not empty, or already gone
            return
        folder = folder.parent


def fetch(url, cache_dir=DEFAULT_CACHE, refresh=False, timeout=60):
    """Path of the cached copy of `url`, downloading it first if needed."""
    cache_dir = Path(cache_dir)
    name = Path(urllib.parse.urlparse(url).path).name
    if not name:
        raise ValueError(f"no file name in {url!r}")
    path = cache_dir / name
    meta_path = path.with_name(name + ".json")
    if path.exists() and meta_path.exists() and not refresh:
        return track(path)
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
    return track(path)


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
        return track(dest, sidecar=False)
    root = dest.resolve()
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            target = (root / member.filename).resolve()
            if target != root and root not in target.parents:
                raise ValueError(f"{archive.name}: member {member.filename!r} is outside the target")
        dest.mkdir(parents=True, exist_ok=True)
        z.extractall(dest)
    done.write_text(archive.name + "\n")
    return track(dest, sidecar=False)

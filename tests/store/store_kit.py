"""Hand-built packs, archives and indexes for the store tests, independent of the real pack writer.

A "release" directory mimics what a publisher uploads: one index.json plus one tar.xz per pack.
`make_store` points a Store at a release; `install_versions` installs several versions of "world".
"""

import functools
import hashlib
import http.server
import io
import json
import tarfile
import threading
import typing
from pathlib import Path

from placewise.model import DataSettings
from placewise.store import Store


def sha256(data):
    return hashlib.sha256(data).hexdigest()


DEFAULT_FILES = {
    "countries/layer.json": b'{"name": "countries", "kind": "point", "count": 0}',
    "countries/col/id.npy": b"\x93NUMPY fake column bytes",
}


def pack_json(name, version, files, schema=1, listed=None):
    """The manifest; `listed` overrides the file list (to fake a wrong hash or a missing entry)."""
    if listed is None:
        listed = {path: {"sha256": sha256(data), "size": len(data)} for path, data in files.items()}
    doc = {
        "schema": schema,
        "name": name,
        "version": version,
        "created": "2026-11-17T00:00:00Z",
        "layers": ["countries"],
        "sources": ["naturalearth"],
        "files": listed,
    }
    return json.dumps(doc).encode()


def tar_xz(entries):
    """entries: list of (TarInfo, bytes | None). Returns the compressed archive bytes."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:xz") as tar:
        for info, data in entries:
            if data is not None:
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            else:
                tar.addfile(info)
    return buf.getvalue()


def file_entry(path, data):
    info = tarfile.TarInfo(path)
    info.mode = 0o644
    return info, data


def dir_entry(path):
    info = tarfile.TarInfo(path)
    info.type = tarfile.DIRTYPE
    info.mode = 0o755
    return info, None


def special_entry(path, kind, target=""):
    info = tarfile.TarInfo(path)
    info.type = kind
    info.linkname = target
    return info, None


def pack_entries(name, version, files=None, schema=1, listed=None, manifest=None):
    """Tar entries for a well-formed pack directory, `<name>-<version>/...`."""
    files = DEFAULT_FILES if files is None else files
    top = f"{name}-{version}"
    manifest = pack_json(name, version, files, schema, listed) if manifest is None else manifest
    entries = [dir_entry(top), file_entry(f"{top}/pack.json", manifest)]
    entries += [file_entry(f"{top}/{path}", data) for path, data in files.items()]
    return entries


class Release:
    """A publisher's release directory with an index.json that lists what's been added."""

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.packs = {}

    @property
    def index_url(self):
        return (self.root / "index.json").as_uri()

    def add(
        self, name, version, entries=None, *, schema=1, sha=None, size=None, url=None, meta=None, **pack_kw
    ):
        """Add a pack archive and its index entry; the keyword overrides fake a lying index, `meta`
        adds coverage fields (kind, covers, requires, installed_bytes) to the entry."""
        data = tar_xz(entries if entries is not None else pack_entries(name, version, **pack_kw))
        filename = f"{name}-{version}.tar.xz"
        (self.root / filename).write_bytes(data)
        self.packs[name] = {
            "version": version,
            "schema": schema,
            "url": url or filename,
            "sha256": sha or sha256(data),
            "size_bytes": len(data) if size is None else size,
            "sources": ["naturalearth"],
            **(meta or {}),
        }
        self.write()
        return data

    def write(self, doc=None):
        doc = {"schema": 1, "packs": self.packs} if doc is None else doc
        (self.root / "index.json").write_text(json.dumps(doc))


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    user_agents: typing.ClassVar[list] = []  # replaced per server, see LocalServer

    def log_message(self, *args):
        pass

    def end_headers(self):
        self.user_agents.append(self.headers.get("User-Agent"))
        super().end_headers()


class LocalServer:
    """An HTTP server on 127.0.0.1 serving a directory from a background thread."""

    def __init__(self, directory):
        handler = type("Handler", (_QuietHandler,), {"user_agents": []})
        self.handler = handler
        self.httpd = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), functools.partial(handler, directory=str(directory))
        )
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def url(self):
        return f"http://127.0.0.1:{self.httpd.server_address[1]}/"

    @property
    def user_agents(self):
        return self.handler.user_agents

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join()


# -- stores fed from a release ----------------------------------------------------------------------


def make_store(data_dir, release, **settings):
    return Store(data_dir, DataSettings(**settings), index_url=release.index_url)


def leftovers(data_dir):
    """Anything in packs/ that isn't a finished pack: temp dirs, partial downloads."""
    packs = data_dir / "packs"
    return sorted(p.name for p in packs.iterdir() if p.name.startswith(".")) if packs.exists() else []


def install_versions(data_dir, release, *versions, **settings):
    store = None
    for v in versions:
        release.add("world", v)
        store = make_store(data_dir, release, **settings)
        store.install("world")
    return store

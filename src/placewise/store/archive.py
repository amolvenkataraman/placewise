"""Unpacking pack archives safely and checking pack directories against their pack.json.

Archives are untrusted until every file matches pack.json, so extraction never hands control to
tarfile's own extract: each entry is checked and then written by hand, regular files and directories
only, always below the destination.
"""

import hashlib
import json
import lzma
import os
import shutil
import stat
import tarfile

from placewise.constants import store as const

from .errors import IntegrityError


def safe_parts(path):
    """The path's components if it's a plain relative path that stays put, else None.

    Refuses absolute paths, `..`, backslashes (a Windows separator that POSIX treats as a character)
    and colons (drive letters and NTFS streams), so the same archive is safe on every OS.
    """
    if not isinstance(path, str) or not path or path.startswith("/") or "\\" in path or ":" in path:
        return None
    if "\0" in path:
        return None
    parts = [p for p in path.split("/") if p not in ("", ".")]
    if not parts or ".." in parts:
        return None
    return parts


def unpack_limit(archive_size):
    return max(const.MIN_UNPACK_LIMIT_BYTES, const.MAX_UNPACK_RATIO * archive_size)


def safe_extract(archive, dest, top, max_bytes):
    """Unpack the tar.xz `archive` into `dest`. Every entry must sit under `top/`."""
    try:
        with open(archive, "rb") as f, tarfile.open(fileobj=f, mode="r|xz") as tar:
            _extract_members(tar, dest, top, max_bytes)
    except (tarfile.TarError, lzma.LZMAError, EOFError) as e:
        raise IntegrityError(f"not a valid tar.xz archive ({e})") from None


def _extract_members(tar, dest, top, max_bytes):
    seen = set()
    total = count = 0
    for member in tar:
        name = member.name
        count += 1
        if count > const.MAX_ARCHIVE_MEMBERS:
            raise IntegrityError(f"archive has more than {const.MAX_ARCHIVE_MEMBERS} entries")
        parts = safe_parts(name)
        if parts is None:
            raise IntegrityError(f"archive entry {name!r} has an unsafe path")
        if parts[0] != top:
            raise IntegrityError(f"archive entry {name!r} is outside {top}/")
        if member.issym() or member.islnk():
            raise IntegrityError(f"archive entry {name!r} is a link; packs hold only files and directories")
        target = dest.joinpath(*parts)
        key = "/".join(parts)
        try:
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isreg() or member.issparse():
                raise IntegrityError(f"archive entry {name!r} is a device or special file")
            if key in seen:
                raise IntegrityError(f"archive has a duplicate entry {name!r}")
            seen.add(key)
            total += member.size
            if total > max_bytes:
                raise IntegrityError(f"archive unpacks to more than {max_bytes} bytes")
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            with open(target, "xb") as out:
                shutil.copyfileobj(source, out, const.CHUNK_BYTES)
        except (FileExistsError, NotADirectoryError, IsADirectoryError):
            raise IntegrityError(f"archive entry {name!r} clashes with another entry") from None


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(const.CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def check_pack_dir(root, name, version, expected_from):
    """Problems with the pack directory `root` (empty if it's intact): pack.json must name this pack
    and a supported schema, and the files on disk must be exactly the ones it lists, byte for byte."""
    manifest_path = root / const.PACK_MANIFEST
    if manifest_path.is_symlink() or not manifest_path.is_file():
        return [f"{const.PACK_MANIFEST} is missing"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        return [f"{const.PACK_MANIFEST} is unreadable ({e})"]
    if not isinstance(manifest, dict):
        return [f"{const.PACK_MANIFEST} is not a JSON object"]
    schema = manifest.get("schema")
    if schema != const.PACK_SCHEMA:
        # a different schema may lay files out differently, so nothing else can be judged
        return [
            f"{const.PACK_MANIFEST} has schema {schema!r}; this placewise reads schema {const.PACK_SCHEMA}"
        ]
    problems = []
    said = (manifest.get("name"), manifest.get("version"))
    if said != (name, version):
        problems.append(
            f"{const.PACK_MANIFEST} says {said[0]} {said[1]}, but {expected_from} says {name} {version}"
        )
    listed, bad = _listed_files(manifest.get("files"))
    problems += bad
    present, odd = _files_on_disk(root)
    problems += odd
    for rel in sorted(listed):
        sha, size = listed[rel]
        path = present.get(rel)
        if path is None:
            problems.append(f"{rel}: listed in {const.PACK_MANIFEST} but missing")
        elif (actual := path.stat().st_size) != size:
            problems.append(f"{rel}: {actual} bytes, {const.PACK_MANIFEST} says {size}")
        elif sha256_file(path) != sha:
            problems.append(f"{rel}: sha256 doesn't match {const.PACK_MANIFEST}")
    for rel in sorted(set(present) - set(listed) - {const.PACK_MANIFEST}):
        problems.append(f"{rel}: not listed in {const.PACK_MANIFEST}")
    return problems


def _listed_files(files):
    if not isinstance(files, dict):
        return {}, [f"{const.PACK_MANIFEST} has no files table"]
    listed, problems = {}, []
    for rel, meta in files.items():
        parts = safe_parts(rel)
        if parts is None:
            problems.append(f"{const.PACK_MANIFEST} lists an unsafe path {rel!r}")
            continue
        sha = meta.get("sha256") if isinstance(meta, dict) else None
        size = meta.get("size") if isinstance(meta, dict) else None
        if not isinstance(sha, str) or not isinstance(size, int) or isinstance(size, bool):
            problems.append(f"{rel}: {const.PACK_MANIFEST} entry needs a sha256 and a size")
            continue
        listed["/".join(parts)] = (sha.lower(), size)
    return listed, problems


def _files_on_disk(root):
    """{relative posix path: Path} of regular files, plus problems for anything else found."""
    present, problems = {}, []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        here = os.path.relpath(dirpath, root)
        for entry in dirnames + filenames:
            path = os.path.join(dirpath, entry)
            rel = entry if here == "." else f"{here}/{entry}".replace(os.sep, "/")
            mode = os.lstat(path).st_mode
            if stat.S_ISDIR(mode):
                continue
            if not stat.S_ISREG(mode):
                problems.append(f"{rel}: a link or special file, not a regular file")
                continue
            present[rel] = root / rel
    return present, problems

"""Members of a remote zip archive, fetched by HTTP range requests, whole or only their start.

HydroLAKES ships as one 820 MB zip whose polygons are ordered largest first, so the lakes the
pack keeps are a prefix of its .shp member. Reading the archive's central directory from its last
64 KiB, then inflating just that prefix, downloads a fraction of the archive (packbuild.water).
Only stored and deflated members, and archives without ZIP64 records, are read.
"""

import struct
import urllib.request
import zlib
from dataclasses import dataclass
from pathlib import Path

from ...fetch import USER_AGENT

_TAIL = 65_536 + 22  # the end-of-central-directory record and the longest comment
_CHUNK = 1 << 20


@dataclass(frozen=True)
class Member:
    name: str
    method: int  # 0 stored, 8 deflated
    compressed: int
    size: int
    header: int  # offset of its local file header


def open_range(url, first, last=None, timeout=60):
    """(chunks, total size) of bytes first..last of url (first < 0: the last -first bytes)."""
    spec = f"bytes={first}" if first < 0 else f"bytes={first}-{'' if last is None else last}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Range": spec})
    response = urllib.request.urlopen(request, timeout=timeout)
    if response.status != 206:
        response.close()
        raise OSError(f"{url}: the server ignored the range request (HTTP {response.status})")
    total = int(response.headers["Content-Range"].rsplit("/", 1)[1])

    def chunks():
        with response:
            while chunk := response.read(_CHUNK):
                yield chunk

    return chunks(), total


class RemoteZip:
    def __init__(self, url, opener=open_range):
        self.url, self.opener = url, opener
        self._members = None

    def members(self):
        """{name: Member} from the central directory."""
        if self._members is None:
            chunks, total = self.opener(self.url, -_TAIL, None)
            tail = b"".join(chunks)
            end = tail.rfind(b"PK\x05\x06")
            if end < 0:
                raise ValueError(f"{self.url}: no zip end-of-central-directory record")
            count, cd_size, cd_offset = struct.unpack("<HII", tail[end + 10 : end + 20])
            start = cd_offset - (total - len(tail))
            if start < 0:  # a directory larger than the tail: fetch it
                chunks, _ = self.opener(self.url, cd_offset, cd_offset + cd_size - 1)
                directory, start = b"".join(chunks), 0
            else:
                directory = tail
            found, pos = {}, start
            for _ in range(count):
                if directory[pos : pos + 4] != b"PK\x01\x02":
                    raise ValueError(f"{self.url}: malformed central directory")
                method = struct.unpack("<H", directory[pos + 10 : pos + 12])[0]
                csize, usize = struct.unpack("<II", directory[pos + 20 : pos + 28])
                n_len, e_len, c_len = struct.unpack("<HHH", directory[pos + 28 : pos + 34])
                header = struct.unpack("<I", directory[pos + 42 : pos + 46])[0]
                name = directory[pos + 46 : pos + 46 + n_len].decode("utf-8")
                found[name] = Member(name, method, csize, usize, header)
                pos += 46 + n_len + e_len + c_len
            self._members = found
        return self._members

    def extract(self, name, dest, limit=None):
        """Write member `name` (its first `limit` bytes, if given) to dest; returns dest."""
        member = self.members().get(name)
        if member is None:
            raise KeyError(f"{self.url} has no member {name!r}")
        if member.method not in (0, 8):
            raise ValueError(f"{name}: compression method {member.method} is not stored or deflate")
        want = member.size if limit is None else min(limit, member.size)
        chunks, _ = self.opener(self.url, member.header, member.header + 29)
        local = b"".join(chunks)
        n_len, e_len = struct.unpack("<HH", local[26:30])
        data_start = member.header + 30 + n_len + e_len
        dest = Path(dest)
        partial = dest.with_name(dest.name + ".part")
        inflate = zlib.decompressobj(-15) if member.method == 8 else None
        written = 0
        chunks, _ = self.opener(self.url, data_start, data_start + member.compressed - 1)
        try:
            with partial.open("wb") as out:
                for chunk in chunks:
                    data = inflate.decompress(chunk, want - written) if inflate else chunk[: want - written]
                    out.write(data)
                    written += len(data)
                    if written >= want:
                        break
            if written < want:
                raise OSError(f"{name}: got {written} of {want} bytes")
            partial.replace(dest)
        finally:
            partial.unlink(missing_ok=True)
            close = getattr(chunks, "close", None)
            if close:
                close()
        return dest

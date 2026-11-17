"""Read members of a 7z archive with the standard library (lzma): just enough of the format for
the LGD monthly archives (7z format spec, 7-Zip's DOC/7zFormat.txt).

Supported: LZMA and LZMA2 coders (and stored, "copy"), solid or not, plain or compressed
("encoded") headers, CRC checks. Not supported (ValueError): encryption, filters such as BCJ,
multi-coder folders. A member is decoded by streaming its folder and keeping only its bytes, so a
month of daily CSVs (1.5 GB unpacked from 7 MB) costs time, not memory.

    names = [m.name for m in members(path)]
    data = read(path, "districts.31Oct2026.csv")
    csv_path = extract_newest(path, out_dir)       # the newest daily file, extracted once
"""

import datetime as dt
import lzma
import os
import re
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

SIGNATURE = b"7z\xbc\xaf\x27\x1c"
_CHUNK = 1 << 20
# property ids (7zFormat.txt)
_END, _HEADER, _ARCHIVE_PROPERTIES, _ADDITIONAL_STREAMS, _MAIN_STREAMS, _FILES = 0, 1, 2, 3, 4, 5
_PACK_INFO, _UNPACK_INFO, _SUBSTREAMS, _SIZE, _CRC, _FOLDER = 6, 7, 8, 9, 10, 11
_CODERS_UNPACK_SIZE, _NUM_UNPACK_STREAM, _EMPTY_STREAM, _NAME, _ENCODED_HEADER, _DUMMY = (
    12,
    13,
    14,
    17,
    23,
    25,
)
_COPY, _LZMA, _LZMA2 = b"\x00", b"\x03\x01\x01", b"\x21"
_DAY = re.compile(r"\.(\d{2}[A-Z][a-z]{2}\d{4})\.")


@dataclass(frozen=True)
class Member:
    name: str
    size: int
    folder: int  # -1: an empty file (no stream)
    offset: int  # within its folder's unpacked bytes
    crc: int | None


@dataclass(frozen=True)
class _Folder:
    method: bytes
    props: bytes
    pack_offset: int  # from the end of the signature header
    pack_size: int
    unpack_size: int
    crc: int | None


def members(path):
    """The archive's files, in archive order."""
    return _Archive(Path(path)).members


def read(path, name):
    """The bytes of member `name`; KeyError if there is none."""
    archive = _Archive(Path(path))
    member = archive.member(name)
    chunks = list(archive.stream(member))
    return b"".join(chunks)


def newest(path):
    """The member whose name carries the latest date (LGD daily files: "<dataset>.31Oct2026.csv"),
    else the last member."""
    found = members(path)
    if not found:
        raise ValueError(f"{Path(path).name}: empty archive")
    dated = [(d, m.name) for m in found if (d := _day(m.name)) is not None]
    return max(dated)[1] if dated else found[-1].name


def extract_newest(path, out_dir):
    """Extract the newest member into out_dir once (an existing copy is reused); returns its path."""
    archive = _Archive(Path(path))
    member = archive.member(newest(path))
    out_dir = Path(out_dir)
    target = out_dir / Path(member.name).name
    if target.exists():
        return target
    out_dir.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    try:
        with partial.open("wb") as out:
            for chunk in archive.stream(member):
                out.write(chunk)
        os.replace(partial, target)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return target


def _day(name):
    m = _DAY.search(name)
    if not m:
        return None
    try:
        return dt.datetime.strptime(m.group(1), "%d%b%Y").date()
    except ValueError:
        return None


class _Archive:
    def __init__(self, path):
        self.path = path
        with path.open("rb") as f:
            start = f.read(32)
            if len(start) < 32 or start[:6] != SIGNATURE:
                raise ValueError(f"{path.name}: not a 7z archive")
            offset, size, crc = struct.unpack("<QQI", start[12:32])
            f.seek(32 + offset)
            header = f.read(size)
        if len(header) != size or zlib.crc32(header) != crc:
            raise ValueError(f"{path.name}: header fails its CRC check (truncated or damaged)")
        while header[:1] == bytes([_ENCODED_HEADER]):
            folders, _ = _Reader(header, 1).streams_info()
            header = b"".join(self._decode(folders[0], folders[0].unpack_size))
        r = _Reader(header)
        if r.byte() != _HEADER:
            raise ValueError(f"{path.name}: unexpected 7z header")
        self.members, self.folders = r.header()

    def member(self, name):
        for m in self.members:
            if m.name == name:
                return m
        raise KeyError(f"{self.path.name} has no member {name!r}")

    def stream(self, member):
        """The member's bytes, in chunks, CRC-checked."""
        if member.folder < 0 or member.size == 0:
            return
        folder = self.folders[member.folder]
        crc, skip, left = 0, member.offset, member.size
        for chunk in self._decode(folder, member.offset + member.size):
            if skip >= len(chunk):
                skip -= len(chunk)
                continue
            piece = chunk[skip : skip + left]
            skip = 0
            left -= len(piece)
            crc = zlib.crc32(piece, crc)
            yield piece
            if not left:
                break
        if left or (member.crc is not None and crc != member.crc):
            raise ValueError(f"{self.path.name}: {member.name} fails its CRC check (damaged archive)")

    def _decode(self, folder, limit):
        """Unpacked bytes of a folder, in chunks, up to `limit` bytes."""
        with self.path.open("rb") as f:
            f.seek(32 + folder.pack_offset)
            left_in, produced = folder.pack_size, 0
            if folder.method == _COPY:
                while left_in and produced < limit:
                    chunk = f.read(min(_CHUNK, left_in, limit - produced))
                    if not chunk:
                        break
                    left_in -= len(chunk)
                    produced += len(chunk)
                    yield chunk
                return
            decoder = lzma.LZMADecompressor(lzma.FORMAT_RAW, filters=[_filter(folder)])
            try:
                while produced < limit:
                    data = b""
                    if decoder.needs_input:
                        data = f.read(min(_CHUNK, left_in)) if left_in else b""
                        left_in -= len(data)
                        if not data and decoder.needs_input:
                            break
                    out = decoder.decompress(data, max_length=min(_CHUNK, limit - produced))
                    produced += len(out)
                    if out:
                        yield out
                    if decoder.eof:
                        break
            except lzma.LZMAError as e:
                raise ValueError(f"{self.path.name}: fails its CRC check or can't be decoded ({e})") from None


def _filter(folder):
    if folder.method == _LZMA2:
        return {"id": lzma.FILTER_LZMA2, "dict_size": _lzma2_dict(folder.props[0])}
    if folder.method == _LZMA:
        lclppb, dict_size = folder.props[0], struct.unpack("<I", folder.props[1:5])[0]
        lc, rest = lclppb % 9, lclppb // 9
        return {"id": lzma.FILTER_LZMA1, "lc": lc, "lp": rest % 5, "pb": rest // 5, "dict_size": dict_size}
    raise ValueError(f"7z coder {folder.method.hex()} is not supported (only LZMA, LZMA2 and copy)")


def _lzma2_dict(prop):
    if prop > 40:
        raise ValueError(f"bad LZMA2 dictionary property {prop}")
    return 0xFFFFFFFF if prop == 40 else (2 | (prop & 1)) << (prop // 2 + 11)


class _Reader:
    """A cursor over header bytes."""

    def __init__(self, data, pos=0):
        self.data, self.pos = data, pos

    def byte(self):
        b = self.data[self.pos]
        self.pos += 1
        return b

    def take(self, n):
        out = self.data[self.pos : self.pos + n]
        self.pos += n
        return out

    def number(self):
        first, mask, value = self.byte(), 0x80, 0
        for i in range(8):
            if not first & mask:
                return value | ((first & (mask - 1)) << (8 * i))
            value |= self.byte() << (8 * i)
            mask >>= 1
        return value

    def bits(self, n):
        out, mask, byte = [], 0, 0
        for _ in range(n):
            if not mask:
                byte, mask = self.byte(), 0x80
            out.append(bool(byte & mask))
            mask >>= 1
        return out

    def digests(self, n):
        defined = [True] * n if self.byte() else self.bits(n)
        return [struct.unpack("<I", self.take(4))[0] if d else None for d in defined]

    # -- structures ---------------------------------------------------------------------------

    def streams_info(self):
        """(folders, per-folder [(size, crc)] substreams)."""
        pack_pos, pack_sizes, folders, coders, unpack = 0, [], [], [], []
        substreams = None
        while (prop := self.byte()) != _END:
            if prop == _PACK_INFO:
                pack_pos, pack_sizes = self._pack_info()
            elif prop == _UNPACK_INFO:
                coders, unpack, crcs = self._unpack_info()
                offset = pack_pos
                for i, ((method, props), size) in enumerate(zip(coders, unpack, strict=True)):
                    folders.append(_Folder(method, props, offset, pack_sizes[i], size, crcs[i]))
                    offset += pack_sizes[i]
            elif prop == _SUBSTREAMS:
                substreams = self._substreams(folders)
            else:
                raise ValueError(f"unexpected 7z property {prop} in streams info")
        if substreams is None:
            substreams = [[(f.unpack_size, f.crc)] for f in folders]
        return folders, substreams

    def _pack_info(self):
        pos, count = self.number(), self.number()
        sizes = []
        while (prop := self.byte()) != _END:
            if prop == _SIZE:
                sizes = [self.number() for _ in range(count)]
            elif prop == _CRC:
                self.digests(count)
        return pos, sizes

    def _unpack_info(self):
        if self.byte() != _FOLDER:
            raise ValueError("7z: expected folder info")
        count = self.number()
        if self.byte():
            raise ValueError("7z: external folder info is not supported")
        coders = [self._folder() for _ in range(count)]
        if self.byte() != _CODERS_UNPACK_SIZE:
            raise ValueError("7z: expected unpack sizes")
        sizes = [self.number() for _ in range(count)]
        crcs = [None] * count
        while (prop := self.byte()) != _END:
            if prop == _CRC:
                crcs = self.digests(count)
        return coders, sizes, crcs

    def _folder(self):
        if self.number() != 1:
            raise ValueError("7z: folders with several coders (filters such as BCJ) are not supported")
        flag = self.byte()
        method = self.take(flag & 0x0F)
        if flag & 0x10:
            raise ValueError("7z: complex coders are not supported")
        props = self.take(self.number()) if flag & 0x20 else b""
        if flag & 0x80:
            raise ValueError("7z: alternative coder methods are not supported")
        return method, props

    def _substreams(self, folders):
        counts = [1] * len(folders)
        sizes = None
        prop = self.byte()
        if prop == _NUM_UNPACK_STREAM:
            counts = [self.number() for _ in folders]
            prop = self.byte()
        if prop == _SIZE:
            sizes = []
            for folder, n in zip(folders, counts, strict=True):
                some = [self.number() for _ in range(n - 1)] if n else []
                sizes.append([*some, folder.unpack_size - sum(some)] if n else [])
            prop = self.byte()
        if sizes is None:
            sizes = [[f.unpack_size] if n else [] for f, n in zip(folders, counts, strict=True)]
        unknown = [n != 1 or f.crc is None for f, n in zip(folders, counts, strict=True)]
        crcs = [[f.crc] if not u else [None] * n for f, n, u in zip(folders, counts, unknown, strict=True)]
        while prop != _END:
            if prop == _CRC:
                digests = iter(self.digests(sum(n for n, u in zip(counts, unknown, strict=True) if u)))
                crcs = [
                    [next(digests) for _ in range(n)] if u else crcs[i]
                    for i, (n, u) in enumerate(zip(counts, unknown, strict=True))
                ]
            prop = self.byte()
        return [list(zip(s, c, strict=True)) for s, c in zip(sizes, crcs, strict=True)]

    def header(self):
        """(members, folders) of a plain header (after kHeader)."""
        folders, substreams = [], []
        names, empty = [], []
        while (prop := self.byte()) != _END:
            if prop == _ARCHIVE_PROPERTIES:
                while self.byte() != _END:
                    self.take(self.number())
            elif prop in (_ADDITIONAL_STREAMS, _MAIN_STREAMS):
                found = self.streams_info()
                if prop == _MAIN_STREAMS:
                    folders, substreams = found
            elif prop == _FILES:
                names, empty = self._files()
            else:
                raise ValueError(f"unexpected 7z property {prop} in header")
        streams = iter((i, s) for i, subs in enumerate(substreams) for s in _offsets(subs))
        out = []
        for k, name in enumerate(names):
            if empty and empty[k]:
                out.append(Member(name, 0, -1, 0, None))
                continue
            folder, (offset, size, crc) = next(streams)
            out.append(Member(name, size, folder, offset, crc))
        return out, folders

    def _files(self):
        count = self.number()
        names, empty = [f"#{i}" for i in range(count)], []
        while (prop := self.byte()) != _END:
            size = self.number()
            end = self.pos + size
            if prop == _NAME:
                if self.byte():
                    raise ValueError("7z: external file names are not supported")
                names = self.take(end - self.pos).decode("utf-16-le").split("\x00")[:count]
            elif prop == _EMPTY_STREAM:
                empty = self.bits(count)
            self.pos = end
        return names, empty


def _offsets(subs):
    at = 0
    for size, crc in subs:
        yield at, size, crc
        at += size

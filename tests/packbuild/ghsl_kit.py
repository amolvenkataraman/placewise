"""Small GeoTIFFs written in memory for the GHSL reader's tests: a TIFF LZW encoder and a writer
for classic or BigTIFF, strips or tiles, any byte order, with a pixel scale and tie point."""

import struct
import zlib

import numpy as np


def lzw_encode(data):
    """TIFF LZW (MSB first; the writer's width grows when the next code reaches 512, 1024, 2048)."""
    codes = []
    table = {bytes([i]): i for i in range(256)}
    nxt, bits = 258, 9
    codes.append((256, bits))
    w = b""
    for byte in data:
        wc = w + bytes([byte])
        if wc in table:
            w = wc
            continue
        codes.append((table[w], bits))
        table[wc] = nxt
        nxt += 1
        if nxt in (512, 1024, 2048):
            bits += 1
        if nxt == 4093:
            codes.append((256, bits))
            table = {bytes([i]): i for i in range(256)}
            nxt, bits = 258, 9
        w = bytes([byte])
    if w:
        codes.append((table[w], bits))
    codes.append((257, bits))
    acc, n, out = 0, 0, bytearray()
    for code, b in codes:
        acc = (acc << b) | code
        n += b
        while n >= 8:
            n -= 8
            out.append((acc >> n) & 0xFF)
    if n:
        out.append((acc << (8 - n)) & 0xFF)
    return bytes(out)


def write_tiff(
    array, *, tile=None, rows_per_strip=None, compression=1, predictor=1, big=False, order="<",
    origin=(-1000.0, 3000.0), scale=1000.0, nodata="-200", citation="World_Mollweide",
):  # fmt: skip
    """The bytes of a one-band (Geo)TIFF holding `array` (2-d, any integer or float dtype)."""
    array = np.asarray(array)
    h, w = array.shape
    if tile:
        bw, bh = tile
    else:
        bw, bh = w, rows_per_strip or h
    blocks = []
    for top in range(0, h, bh):
        for left in range(0, w, bw):
            part = array[top : top + bh, left : left + bw]
            if tile:  # tiles are always full size, padded
                full = np.zeros((bh, bw), dtype=array.dtype)
                full[: part.shape[0], : part.shape[1]] = part
                part = full
            part = part.astype(array.dtype.newbyteorder(order))
            if predictor == 2:
                u = part.astype(part.dtype.str.replace("i", "u"))
                diff = u.copy()
                diff[:, 1:] = u[:, 1:] - u[:, :-1]
                part = diff.view(part.dtype)
            raw = part.tobytes()
            raw = lzw_encode(raw) if compression == 5 else zlib.compress(raw) if compression == 8 else raw
            blocks.append(raw)
    kind = {"u": 1, "i": 2, "f": 3}[array.dtype.kind]
    tags = [
        (256, 3, [w]), (257, 3, [h]), (258, 3, [array.dtype.itemsize * 8]), (259, 3, [compression]),
        (262, 3, [1]), (277, 3, [1]), (284, 3, [1]), (317, 3, [predictor]), (339, 3, [kind]),
        (33550, 12, [scale, scale, 0.0]), (33922, 12, [0.0, 0.0, 0.0, origin[0], origin[1], 0.0]),
        (34737, 2, citation.encode() + b"\0"), (42113, 2, nodata.encode() + b"\0"),
    ]  # fmt: skip
    off_tag, size_tag = (324, 325) if tile else (273, 279)
    if tile:
        tags += [(322, 3, [bw]), (323, 3, [bh])]
    else:
        tags += [(278, 3, [bh])]
    head = 16 if big else 8
    data = bytearray()
    offsets = []
    for b in blocks:
        offsets.append(head + len(data))
        data += b
    tags += [(off_tag, 16 if big else 4, offsets), (size_tag, 16 if big else 4, [len(b) for b in blocks])]
    tags.sort()
    codes = {2: "s", 3: "H", 4: "I", 12: "d", 16: "Q"}
    ifd_at = head + len(data)
    entry, inline = (20, 8) if big else (12, 4)
    extra_at = ifd_at + (8 if big else 2) + entry * len(tags) + (8 if big else 4)
    ifd, extra = bytearray(), bytearray()
    ifd += struct.pack(order + ("Q" if big else "H"), len(tags))
    for tag, typ, values in tags:
        n = len(values)
        payload = bytes(values) if typ == 2 else struct.pack(f"{order}{n}{codes[typ]}", *values)
        ifd += struct.pack(order + "HH", tag, typ) + struct.pack(order + ("Q" if big else "I"), n)
        if len(payload) <= inline:
            ifd += payload.ljust(inline, b"\0")
        else:
            ifd += struct.pack(order + ("Q" if big else "I"), extra_at + len(extra))
            extra += payload
            extra += b"\0" * (len(extra) % 2)
    ifd += b"\0" * (8 if big else 4)
    bo = b"II" if order == "<" else b"MM"
    header = bo + (
        struct.pack(order + "HHHQ", 43, 8, 0, ifd_at) if big else struct.pack(order + "HI", 42, ifd_at)
    )
    return bytes(header + data + ifd + extra)

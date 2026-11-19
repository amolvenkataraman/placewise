"""TIFF's LZW decompression (TIFF 6.0, section 13), in pure Python.

Codes are read most significant bit first, 9 bits wide to start with and widening to 10, 11 and
12 bits one code early, as TIFF writers do ("early change": when the table is about to reach 511,
1023 and 2047 entries). 256 clears the table, 257 ends the strip.
"""

CLEAR, END = 256, 257
_FIRST = [bytes([i]) for i in range(256)] + [b"", b""]
_WIDTH_AT = {511: 10, 1023: 11, 2047: 12}  # table size reached -> width of the codes after it


def decode(data):
    """The bytes an LZW-compressed strip or tile holds."""
    data = bytes(data)
    total_bits = len(data) * 8
    padded = data + b"\0\0\0\0"
    out = []
    table = _FIRST[:]
    width, pos, previous = 9, 0, None
    while pos + width <= total_bits:
        start = pos >> 3
        word = int.from_bytes(padded[start : start + 4], "big")
        code = (word >> (32 - (pos & 7) - width)) & ((1 << width) - 1)
        pos += width
        if code == END:
            break
        if code == CLEAR:
            table = _FIRST[:]
            width, previous = 9, None
            continue
        if code > len(table) or (previous is None and code == len(table)):
            raise ValueError(f"LZW code {code} past the table's {len(table)} entries")
        if previous is None:  # the first code after a clear adds nothing to the table
            entry = table[code]
        elif code < len(table):
            entry = table[code]
            table.append(previous + entry[:1])
        else:  # the entry being defined: previous plus its own first byte
            entry = previous + previous[:1]
            table.append(entry)
        out.append(entry)
        previous = entry
        width = _WIDTH_AT.get(len(table), width)
    return b"".join(out)

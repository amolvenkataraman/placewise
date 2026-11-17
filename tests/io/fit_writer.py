"""A small FIT encoder for building test fixtures, written from the public FIT protocol description.

It writes raw field values exactly as given (no scale, offset or unit conversion), so a test can
place any byte pattern it needs, invalid values included. fitdecode then confirms each fixture is
valid FIT before placewise's reader is compared with it, which keeps this encoder honest.
"""

import struct
from datetime import datetime, timezone

FIT_EPOCH = datetime(1989, 12, 31, tzinfo=timezone.utc)

# name: (base type byte as written in definitions, struct code, size, invalid value)
BASE_TYPES = {
    "enum": (0x00, "B", 1, 0xFF),
    "sint8": (0x01, "b", 1, 0x7F),
    "uint8": (0x02, "B", 1, 0xFF),
    "sint16": (0x83, "h", 2, 0x7FFF),
    "uint16": (0x84, "H", 2, 0xFFFF),
    "sint32": (0x85, "i", 4, 0x7FFFFFFF),
    "uint32": (0x86, "I", 4, 0xFFFFFFFF),
    "string": (0x07, "s", 1, b""),
    "float32": (0x88, "f", 4, float("nan")),
    "uint8z": (0x0A, "B", 1, 0),
    "uint16z": (0x8B, "H", 2, 0),
    "uint32z": (0x8C, "I", 4, 0),
    "byte": (0x0D, "s", 1, b""),
}

# The FIT SDK's nibble-wise CRC-16 table and update step, kept deliberately different from the
# byte-table form placewise uses so the two implementations check each other
_CRC_TABLE = (
    0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
    0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400,
)  # fmt: skip

MESG_FILE_ID, MESG_SESSION, MESG_LAP, MESG_RECORD, MESG_EVENT, MESG_DEVICE_INFO = 0, 18, 19, 20, 21, 23
MESG_FIELD_DESCRIPTION, MESG_DEVELOPER_DATA_ID = 206, 207


def crc16(data, crc=0):
    for byte in data:
        tmp = _CRC_TABLE[crc & 0xF]
        crc = ((crc >> 4) & 0x0FFF) ^ tmp ^ _CRC_TABLE[byte & 0xF]
        tmp = _CRC_TABLE[crc & 0xF]
        crc = ((crc >> 4) & 0x0FFF) ^ tmp ^ _CRC_TABLE[(byte >> 4) & 0xF]
    return crc


def fit_time(iso):
    """Seconds since the FIT epoch for an ISO-8601 UTC timestamp."""
    return int((datetime.fromisoformat(iso.replace("Z", "+00:00")) - FIT_EPOCH).total_seconds())


def semicircles(degrees):
    return round(degrees * 2**31 / 180)


class FitWriter:
    """Build a FIT file message by message: `define` a local message, then write `message`s to it."""

    def __init__(self):
        self._body = bytearray()
        self._defs = {}

    def define(self, local, mesg_num, fields, *, big_endian=False, dev_fields=()):
        """`fields` are (field number, base type name) or (number, "string"/"byte", size);
        `dev_fields` are (field number, base type name, developer data index)."""
        endian = ">" if big_endian else "<"
        header = 0x40 | local | (0x20 if dev_fields else 0)
        out = bytearray([header, 0, int(big_endian)])
        out += struct.pack(f"{endian}HB", mesg_num, len(fields))
        layout = []
        for num, kind, *size in fields:
            type_byte, code, base_size, invalid = BASE_TYPES[kind]
            size = size[0] if size else base_size
            out += bytes([num, size, type_byte])
            layout.append((num, f"{size}s" if code == "s" else code, invalid))
        dev_layout = []
        if dev_fields:
            out.append(len(dev_fields))
            for num, kind, dev_index in dev_fields:
                _, code, size, _ = BASE_TYPES[kind]
                out += bytes([num, size, dev_index])
                dev_layout.append(code)
        self._body += out
        self._defs[local] = (endian, layout, dev_layout)

    def message(self, local, values, *, dev_values=(), time_offset=None):
        """`values` maps field number to raw value; a defined field left out is written invalid.
        `time_offset` (0-31) writes a compressed-timestamp header instead of a normal one."""
        endian, layout, dev_layout = self._defs[local]
        if time_offset is None:
            header = local
        else:
            assert local < 4 and 0 <= time_offset < 32
            header = 0x80 | (local << 5) | time_offset
        out = bytearray([header])
        for num, code, invalid in layout:
            value = values.get(num, invalid)
            if isinstance(value, str):
                value = value.encode()
            out += struct.pack(f"{endian}{code}", value)
        for code, value in zip(dev_layout, dev_values, strict=True):
            out += struct.pack(f"{endian}{code}", value)
        self._body += out

    def describe_developer_field(self, local, dev_index, field_num, kind, name, units):
        """The developer_data_id and field_description messages a developer field needs."""
        self.define(local, MESG_DEVELOPER_DATA_ID, [(1, "byte", 16), (3, "uint8")])
        self.message(local, {1: bytes(range(16)), 3: dev_index})
        self.define(
            local,
            MESG_FIELD_DESCRIPTION,
            [(0, "uint8"), (1, "uint8"), (2, "uint8"), (3, "string", 16), (8, "string", 8)],
        )
        self.message(local, {0: dev_index, 1: field_num, 2: BASE_TYPES[kind][0], 3: name, 8: units})

    def to_bytes(self, *, header_size=14, header_crc=True):
        header = struct.pack("<BBHI4s", header_size, 0x20, 2132, len(self._body), b".FIT")
        if header_size == 14:
            header += struct.pack("<H", crc16(header) if header_crc else 0)
        data = header + bytes(self._body)
        return data + struct.pack("<H", crc16(data))

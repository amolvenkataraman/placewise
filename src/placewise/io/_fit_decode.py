"""The FIT binary layer: file headers, CRCs, definition messages and the data messages they lay out.

Data messages are kept as raw bytes, one buffer per definition, and turned into columns by numpy
in one go (`_Definition.columns`). Consecutive data messages of one local message number, the bulk
of any activity file, are found by their repeated header byte and copied as one slice, so the
per-message work in Python is a byte comparison.
"""

import functools
import struct

import numpy as np

from placewise.constants import fit

_TIMESTAMP = fit.Field("timestamp", kind="time")
_NO_TIME = 0xFFFFFFFF  # uint32 invalid


class FitError(ValueError):
    """Not a FIT file, truncated, malformed, or failing its CRC."""


class _Definition:
    """One definition message's layout, plus the data messages decoded with it: their raw bytes
    (header byte included), timestamps and sequence numbers in the file (files often alternate
    definitions, so each keeps its own rows and the sequence numbers restore the order)."""

    __slots__ = (
        "bases",
        "blob",
        "count",
        "dtype",
        "fields",
        "keep",
        "mesg_num",
        "record",
        "seq",
        "size",
        "stamp",
        "time_index",
        "times",
    )

    def __init__(self, mesg_num, size, fields, bases, dtype, stamp, time_index):
        self.mesg_num = mesg_num
        self.size = size  # bytes of a data message, after its header byte
        self.record = size + 1
        self.fields = fields
        self.bases = bases
        self.dtype = dtype  # a whole record, header byte included, as a numpy structured type
        self.stamp = stamp  # a Struct reading the timestamp from a whole record, or None
        self.time_index = time_index
        self.keep = mesg_num in fit.MESSAGE_FIELDS  # otherwise decoded only for its timestamp
        self.blob, self.count, self.times, self.seq = bytearray(), 0, [], []

    def columns(self):
        """The raw values of each field (numpy arrays, b"" padded strings for text), by position."""
        rows = np.frombuffer(self.blob, dtype=self.dtype, count=self.count)
        return [rows[f"f{k}"] for k in range(len(self.fields))]


def decode(data, check_crc):
    """The definitions of each wanted global message, holding their decoded data messages."""
    messages = {num: [] for num in fit.MESSAGE_FIELDS}
    pos = _decode_file(data, 0, check_crc, messages)
    while len(data) - pos >= fit.HEADER_SIZES[0] and data[pos + 8 : pos + 12] == fit.HEADER_SIGNATURE:
        pos = _decode_file(data, pos, check_crc, messages)  # a chained FIT file
    return messages


def _decode_file(data, start, check_crc, messages):
    header_size = data[start] if start < len(data) else 0
    if (
        len(data) - start < fit.HEADER_SIZES[0]
        or header_size not in fit.HEADER_SIZES
        or data[start + 8 : start + 12] != fit.HEADER_SIGNATURE
    ):
        raise FitError(f"not a FIT file: no 12- or 14-byte header with the .FIT signature at byte {start}")
    if header_size == 14 and check_crc:
        stored = int.from_bytes(data[start + 12 : start + 14], "little")
        computed = crc16(data[start : start + 12])
        if stored and stored != computed:  # writers may leave it 0, meaning "not computed"
            raise FitError(f"header CRC mismatch (stored 0x{stored:04X}, computed 0x{computed:04X})")
    data_size = int.from_bytes(data[start + 4 : start + 8], "little")
    body, end = start + header_size, start + header_size + data_size
    if end + fit.CRC_SIZE > len(data):
        raise FitError(f"truncated: the header announces {data_size} data bytes plus a CRC after byte {body}")
    if check_crc:
        stored = int.from_bytes(data[end : end + fit.CRC_SIZE], "little")
        computed = crc16(memoryview(data)[start:end])
        if stored != computed:
            raise FitError(
                f"file CRC mismatch (stored 0x{stored:04X}, computed 0x{computed:04X}): the file is corrupt"
            )
    _decode_records(data, body, end, messages)
    return end + fit.CRC_SIZE


def _decode_records(data, pos, end, messages):
    local = [None] * (fit.LOCAL_MESSAGE_MASK + 1)
    seq = sum(d.count for kept in messages.values() for d in kept)  # chained files number on
    last_time = None  # compressed timestamps count on from the last full one, in any message
    view = memoryview(data)
    while pos < end:
        header = data[pos]
        pos += 1
        if header & fit.HEADER_COMPRESSED:
            number = (header >> fit.COMPRESSED_LOCAL_SHIFT) & fit.COMPRESSED_LOCAL_MASK
            offset = header & fit.COMPRESSED_OFFSET_MASK
            if last_time is None:
                time = None
            else:
                # the offset is the timestamp's low five bits; a smaller one rolled over
                time = (last_time & ~fit.COMPRESSED_OFFSET_MASK) + offset
                if offset < last_time & fit.COMPRESSED_OFFSET_MASK:
                    time += fit.COMPRESSED_OFFSET_MASK + 1
                last_time = time
        elif header & fit.HEADER_DEFINITION:
            try:
                definition, pos = _read_definition(data, pos, header & fit.HEADER_DEVELOPER)
            except (IndexError, struct.error) as error:
                raise FitError(f"truncated or malformed record near byte {pos}") from error
            local[header & fit.LOCAL_MESSAGE_MASK] = definition
            if definition.keep:
                messages[definition.mesg_num].append(definition)
            continue
        else:
            number, time = header & fit.LOCAL_MESSAGE_MASK, None
        definition = local[number]
        if definition is None:
            raise FitError(
                f"byte {pos - 1}: data message uses local message {number}, which has no definition"
            )
        record, start = definition.record, pos - 1
        if not header & fit.HEADER_COMPRESSED:
            # the same normal header byte again right after this message: the same layout, so
            # a run of them is one slice (each wholly inside the data, as checked here)
            stop = start + record
            while stop + record <= end and data[stop] == header:
                stop += record
            if stop > start + record:
                count = (stop - start) // record
                if definition.stamp is not None:
                    stamps = [s for (s,) in definition.stamp.iter_unpack(view[start:stop])]
                    times = [None if s == _NO_TIME else s for s in stamps]
                    last_time = next((s for s in reversed(times) if s is not None), last_time)
                else:
                    times = [None] * count
                if definition.keep:
                    definition.blob += view[start:stop]
                    definition.times += times
                    definition.seq += range(seq, seq + count)
                    definition.count += count
                    seq += count
                pos = stop
                continue
        if start + record > len(data):
            raise FitError(f"truncated or malformed record near byte {pos}")
        if definition.stamp is not None:
            stamp = definition.stamp.unpack_from(data, start)[0]
            if stamp == _NO_TIME:
                time = None
            else:
                time = last_time = stamp
        pos += definition.size
        if definition.keep:
            definition.blob += view[start : start + record]
            definition.times.append(time)
            definition.seq.append(seq)
            definition.count += 1
            seq += 1
    if pos != end:
        raise FitError(f"truncated: the last record runs {pos - end} bytes past the announced data size")


def _read_definition(data, pos, developer):
    architecture = data[pos + 1]
    if architecture > 1:
        raise FitError(f"byte {pos}: unknown architecture {architecture} in a definition message")
    endian = ">" if architecture else "<"
    mesg_num = int.from_bytes(data[pos + 2 : pos + 4], "big" if architecture else "little")
    n_fields = data[pos + 4]
    pos += 5
    profile = fit.MESSAGE_FIELDS.get(mesg_num, {})
    names, formats, offsets, fields, bases, offset, time_index = [], [], [], [], [], 1, -1
    for _ in range(n_fields):
        number, size, base_byte = data[pos], data[pos + 1], data[pos + 2]
        pos += 3
        field = profile.get(number) or (_TIMESTAMP if number == fit.FIELD_TIMESTAMP else None)
        base = fit.BASE_TYPES.get(base_byte & fit.BASE_TYPE_NUMBER_MASK)
        is_text = base is not None and base.code == "s"
        # arrays and fields of an unexpected type are skipped rather than guessed at
        usable = (
            field is not None
            and base is not None
            and (field.kind == "string") == is_text
            and (is_text or size == base.size)
            and (field.name != "timestamp" or size == 4)
        )
        if usable:
            if field.name == "timestamp":
                time_index = len(fields)
                stamp_offset, stamp_code = offset, base.code
            names.append(f"f{len(fields)}")
            formats.append(f"S{size}" if is_text else endian + base.code)
            offsets.append(offset)
            fields.append(field)
            bases.append(base)
        offset += size
    if developer:
        n_developer = data[pos]
        pos += 1
        for _ in range(n_developer):
            offset += data[pos + 1]  # (field number, size, developer data index)
            pos += 3
    dtype = np.dtype({"names": names, "formats": formats, "offsets": offsets, "itemsize": offset})
    # the timestamp of a whole record (header byte included), alone
    stamp = None
    if time_index >= 0:
        stamp = struct.Struct(f"{endian}{stamp_offset}x{stamp_code}{offset - stamp_offset - 4}x")
    return _Definition(mesg_num, offset - 1, tuple(fields), tuple(bases), dtype, stamp, time_index), pos


@functools.cache
def _crc_table():
    # CRC-16/ARC (reflected polynomial 0x8005): the FIT SDK's nibble table describes the same CRC
    table = []
    for byte in range(256):
        crc = byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
        table.append(crc)
    return np.array(table, dtype=np.uint16)


def crc16(data):
    """The FIT CRC, run as about sqrt(n) lanes in parallel with numpy instead of n Python steps.

    With a zero start value the CRC is linear, so crc(A + B) = shift(crc(A), len(B)) ^ crc(B), where
    shift runs the register over zero bytes, and leading zero bytes change nothing; zero-padding the
    front to a whole number of equal lanes keeps the result exact.
    """
    buf = np.frombuffer(data, dtype=np.uint8)
    n = len(buf)
    if n == 0:
        return 0
    width = int(np.ceil(np.sqrt(n)))
    lanes = -(-n // width)
    padded = np.zeros(lanes * width, dtype=np.uint8)
    padded[lanes * width - n :] = buf
    columns = np.ascontiguousarray(padded.reshape(lanes, width).T)
    # 512 extra registers fed zeros learn `shift` over one lane for every low and every high byte
    basis = np.concatenate([np.arange(256), np.arange(256) << 8]).astype(np.uint16)
    crc = np.concatenate([np.zeros(lanes, dtype=np.uint16), basis])
    zeros = np.zeros(len(basis), dtype=np.uint8)
    table = _crc_table()
    for column in columns:
        crc = (crc >> 8) ^ table[(crc ^ np.concatenate([column, zeros])) & 0xFF]
    lane_crcs = crc[:lanes].tolist()
    shift_low, shift_high = crc[lanes : lanes + 256].tolist(), crc[lanes + 256 :].tolist()
    total = 0
    for lane_crc in lane_crcs:
        total = shift_low[total & 0xFF] ^ shift_high[total >> 8] ^ lane_crc
    return total

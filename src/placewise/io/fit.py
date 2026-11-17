"""Garmin FIT activity files into a Track, laps, sessions and the recording device, without dependencies.

Follows the FIT protocol description in the public FIT SDK: a 12- or 14-byte file header, then
records, each a definition message (the layout of a local message number: global message, byte
order, field numbers, sizes and base types) or a data message laid out by the latest definition of
its local number, then a CRC-16 of everything before it. FIT files may be chained back to back.
Only the activity fields in `constants.fit.MESSAGE_FIELDS` are decoded; every other field, message
and developer field is skipped by the size its definition gives, so unknown content never breaks a
read.
"""

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from placewise.constants import fit
from placewise.model._base import Model
from placewise.tracks import Track, TrackMeta

_TIMESTAMP = fit.Field("timestamp", kind="time")
_NO_TIME = 0xFFFFFFFF  # uint32 invalid


class FitError(ValueError):
    """Not a FIT file, truncated, malformed, or failing its CRC."""


@dataclass(frozen=True, slots=True)
class _Summary(Model):
    sport: str | None = None
    start_time: float | None = None  # UTC unix seconds
    end_time: float | None = None  # the message timestamp, written when the lap or session closed
    total_elapsed_time: float | None = None  # s, pauses included
    total_timer_time: float | None = None  # s, with the timer running
    total_distance: float | None = None  # m


@dataclass(frozen=True, slots=True)
class FitLap(_Summary):
    pass


@dataclass(frozen=True, slots=True)
class FitSession(_Summary):
    pass


@dataclass(frozen=True, slots=True)
class FitDevice(Model):
    device_index: int | None = None  # 0 is the creator, the device that wrote the file
    manufacturer: int | None = None
    manufacturer_name: str | None = None  # from the FIT profile, for the common makers
    product: int | None = None
    product_name: str | None = None
    serial_number: int | None = None
    software_version: float | None = None


@dataclass(frozen=True, eq=False)
class FitFile:
    track: Track  # records with a valid position, split into segments at timer stop / start
    laps: tuple[FitLap, ...]
    sessions: tuple[FitSession, ...]
    device: FitDevice | None  # the creator: file_id merged with its device_info
    devices: tuple[FitDevice, ...]  # every device_info device (sensors too), last report of each
    distance: np.ndarray | None  # m along the track, aligned with its points (Track has no column)
    file_type: str | None
    time_created: float | None  # UTC unix seconds
    skipped_records: int  # record messages without a valid timestamp and position


def read_fit(source, *, check_crc=True):
    """A FitFile from a path, bytes, or binary file object. Raises FitError (a ValueError) for a
    file that is not FIT, is truncated, or fails a CRC check (unless `check_crc=False`)."""
    data, name = _read_source(source)
    messages = _decode(data, check_crc)
    records, record_time = _table(messages[fit.MESG_RECORD])
    events, event_time = _table(messages[fit.MESG_EVENT])
    track, distance, skipped = _track(records, record_time)
    sessions = tuple(_summaries(FitSession, *_table(messages[fit.MESG_SESSION])))
    file_id, _ = _table(messages[fit.MESG_FILE_ID])
    devices = _devices(*_table(messages[fit.MESG_DEVICE_INFO]))
    device = _creator(file_id, devices)
    meta = TrackMeta(
        activity=next((s.sport for s in sessions if s.sport is not None), None),
        device=_device_label(device),
        source=name,
    )
    segments = _segment_starts(track["time"], events, event_time)
    file_type = _first(file_id, "type")
    return FitFile(
        track=Track.from_columns(track, segments, meta),
        laps=tuple(_summaries(FitLap, *_table(messages[fit.MESG_LAP]))),
        sessions=sessions,
        device=device,
        devices=devices,
        distance=distance,
        file_type=None if file_type is None else fit.FILE_TYPES.get(file_type, str(file_type)),
        time_created=_first(file_id, "time_created", int_=False),
        skipped_records=skipped,
    )


def _read_source(source):
    if isinstance(source, bytes | bytearray | memoryview):
        return bytes(source), None
    if hasattr(source, "read"):
        name = getattr(source, "name", None)
        return source.read(), Path(name).name if isinstance(name, str) else None
    path = Path(source)
    return path.read_bytes(), path.name


# --- the binary layer ---


class _Definition:
    """One definition message's layout, plus the data messages decoded with it: their value tuples,
    timestamps and sequence numbers in the file (files often alternate definitions, so each keeps
    its own rows and the sequence numbers restore the order)."""

    __slots__ = (
        "bases",
        "fields",
        "keep",
        "mesg_num",
        "rows",
        "seq",
        "size",
        "struct",
        "time_index",
        "times",
    )

    def __init__(self, mesg_num, struct_, fields, bases, time_index):
        self.mesg_num = mesg_num
        self.struct = struct_
        self.size = struct_.size
        self.fields = fields
        self.bases = bases
        self.time_index = time_index
        self.keep = mesg_num in fit.MESSAGE_FIELDS  # otherwise decoded only for its timestamp
        self.rows, self.times, self.seq = [], [], []


def _decode(data, check_crc):
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
        computed = _crc16(data[start : start + 12])
        if stored and stored != computed:  # writers may leave it 0, meaning "not computed"
            raise FitError(f"header CRC mismatch (stored 0x{stored:04X}, computed 0x{computed:04X})")
    data_size = int.from_bytes(data[start + 4 : start + 8], "little")
    body, end = start + header_size, start + header_size + data_size
    if end + fit.CRC_SIZE > len(data):
        raise FitError(f"truncated: the header announces {data_size} data bytes plus a CRC after byte {body}")
    if check_crc:
        stored = int.from_bytes(data[end : end + fit.CRC_SIZE], "little")
        computed = _crc16(memoryview(data)[start:end])
        if stored != computed:
            raise FitError(
                f"file CRC mismatch (stored 0x{stored:04X}, computed 0x{computed:04X}): the file is corrupt"
            )
    _decode_records(data, body, end, messages)
    return end + fit.CRC_SIZE


def _decode_records(data, pos, end, messages):
    local = [None] * (fit.LOCAL_MESSAGE_MASK + 1)
    seq = sum(len(d.rows) for kept in messages.values() for d in kept)  # chained files number on
    last_time = None  # compressed timestamps count on from the last full one, in any message
    try:
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
                definition, pos = _read_definition(data, pos, header & fit.HEADER_DEVELOPER)
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
            values = definition.struct.unpack_from(data, pos)
            pos += definition.size
            if definition.time_index >= 0:
                stamp = values[definition.time_index]
                if stamp == _NO_TIME:
                    time = None
                else:
                    time = last_time = stamp
            if definition.keep:
                definition.rows.append(values)
                definition.times.append(time)
                definition.seq.append(seq)
                seq += 1
    except (IndexError, struct.error) as error:
        raise FitError(f"truncated or malformed record near byte {pos}") from error
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
    formats, fields, bases, pad, time_index = [endian], [], [], 0, -1
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
        if not usable:
            pad += size
            continue
        if pad:
            formats.append(f"{pad}x")
            pad = 0
        if field.name == "timestamp":
            time_index = len(fields)
        formats.append(f"{size}s" if is_text else base.code)
        fields.append(field)
        bases.append(base)
    if developer:
        n_developer = data[pos]
        pos += 1
        for _ in range(n_developer):
            pad += data[pos + 1]  # (field number, size, developer data index)
            pos += 3
    if pad:
        formats.append(f"{pad}x")
    return _Definition(
        mesg_num, struct.Struct("".join(formats)), tuple(fields), tuple(bases), time_index
    ), pos


def _make_crc_table():
    # CRC-16/ARC (reflected polynomial 0x8005): the FIT SDK's nibble table describes the same CRC
    table = []
    for byte in range(256):
        crc = byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
        table.append(crc)
    return np.array(table, dtype=np.uint16)


_CRC_TABLE = _make_crc_table()


def _crc16(data):
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
    for column in columns:
        crc = (crc >> 8) ^ _CRC_TABLE[(crc ^ np.concatenate([column, zeros])) & 0xFF]
    lane_crcs = crc[:lanes].tolist()
    shift_low, shift_high = crc[lanes : lanes + 256].tolist(), crc[lanes + 256 :].tolist()
    total = 0
    for lane_crc in lane_crcs:
        total = shift_low[total & 0xFF] ^ shift_high[total >> 8] ^ lane_crc
    return total


# --- from raw values to columns and objects ---


def _table(definitions):
    """Columns by field name (float64 with NaN for invalid, or lists of str / None for text) and the
    message times as UTC unix seconds (NaN where a message had none), in file order."""
    used = [d for d in definitions if d.rows]
    n = sum(len(d.rows) for d in used)
    if not used:
        return {}, np.zeros(0)
    order = np.argsort(np.concatenate([d.seq for d in used]), kind="stable")
    rank = np.empty(n, dtype=np.intp)
    rank[order] = np.arange(n)  # where each definition's rows go in file order
    columns, time, start = {}, np.empty(n), 0
    for d in used:
        where = rank[start : start + len(d.rows)]
        start += len(d.rows)
        time[where] = np.array(d.times, dtype=np.float64)  # None becomes NaN
        for field, base, values in zip(d.fields, d.bases, zip(*d.rows, strict=True), strict=True):
            if field.name == "timestamp":
                continue  # already in d.times, alongside compressed-header times
            if field.name not in columns:
                columns[field.name] = [None] * n if field.kind == "string" else np.full(n, np.nan)
            target = columns[field.name]
            if field.kind == "string":
                for i, value in zip(where.tolist(), values, strict=True):
                    target[i] = _text(value)
            else:
                target[where] = _numbers(values, field, base)
    return columns, time + fit.EPOCH_UNIX_S


def _numbers(values, field, base):
    raw = np.array(values, dtype=np.dtype(base.code))
    out = raw.astype(np.float64)
    if base.invalid is not None:
        out[raw == base.invalid] = np.nan  # floats carry NaN already
    if field.kind == "semicircles":
        out *= fit.SEMICIRCLES_TO_DEGREES
    elif field.kind == "time":
        out += fit.EPOCH_UNIX_S
    else:
        if field.scale != 1:
            out /= field.scale
        if field.offset:
            out -= field.offset
    return out


def _text(raw):
    return raw.split(b"\0", 1)[0].decode("utf-8", errors="replace") or None


_TRACK_COLUMNS = {
    "ele": ("enhanced_altitude", "altitude"),  # the enhanced (32-bit) field wins when both exist
    "speed": ("enhanced_speed", "speed"),
    "hr": ("heart_rate",),
    "cadence": ("cadence",),
    "power": ("power",),
    "temperature": ("temperature",),
    "accuracy": ("gps_accuracy",),
}


def _track(records, time):
    """Track columns from records with a timestamp and an in-range position; columns with no
    value at any kept point are left out. Returns (columns, distance, skipped count)."""
    lat, lon = records.get("position_lat"), records.get("position_long")
    if lat is None or lon is None:
        keep = np.zeros(len(time), dtype=bool)
        lat = lon = np.full(len(time), np.nan)
    else:
        keep = np.isfinite(time) & (np.abs(lat) <= 90) & (np.abs(lon) <= 180)  # NaN fails both
    columns = {"time": time[keep], "lat": lat[keep], "lon": lon[keep]}
    for column, names in _TRACK_COLUMNS.items():
        if (values := _preferred(records, names, keep)) is not None:
            columns[column] = values
    return columns, _preferred(records, ("distance",), keep), int(len(time) - keep.sum())


def _preferred(records, names, keep):
    out = None
    for name in names:
        if (values := records.get(name)) is not None:
            out = values.copy() if out is None else np.where(np.isnan(out), values, out)
    if out is None:
        return None
    out = out[keep]
    if not np.any(np.isfinite(out)):
        return None
    out.flags.writeable = False
    return out


def _segment_starts(time, events, event_time):
    """A new segment begins at the first point after a timer stop that a later start resumed."""
    if len(time) == 0:
        return ()
    boundaries, running, stopped_at = [], True, None
    for t, event, kind in zip(
        event_time, events.get("event", ()), events.get("event_type", ()), strict=False
    ):
        if event != fit.EVENT_TIMER or np.isnan(t):
            continue
        if kind in fit.EVENT_TYPES_STOP and running:
            running, stopped_at = False, t
        elif kind == fit.EVENT_TYPE_START and not running:
            running = True
            boundaries.append(stopped_at)
    starts = {0}
    for boundary in boundaries:
        after = time > boundary
        if after.any():
            starts.add(int(np.argmax(after)))  # records can be out of order; take the first later one
    return tuple(sorted(starts))


def _opt(value, int_=False):
    if value is None or np.isnan(value):
        return None
    return int(value) if int_ else float(value)


def _first(columns, name, int_=True):
    values = columns.get(name)
    return None if values is None or len(values) == 0 else _opt(values[0], int_)


def _sport(value):
    code = _opt(value, int_=True)
    return None if code is None else fit.SPORTS.get(code, str(code))


def _summaries(cls, columns, time):
    def col(name):
        return columns.get(name, np.full(len(time), np.nan))

    for i in range(len(time)):
        yield cls(
            sport=_sport(col("sport")[i]),
            start_time=_opt(col("start_time")[i]),
            end_time=_opt(time[i]),
            total_elapsed_time=_opt(col("total_elapsed_time")[i]),
            total_timer_time=_opt(col("total_timer_time")[i]),
            total_distance=_opt(col("total_distance")[i]),
        )


def _manufacturer_name(code):
    return None if code is None else fit.MANUFACTURERS.get(code)


def _devices(columns, time):
    """One FitDevice per device index, its last report winning (devices report at start and end)."""
    by_index = {}
    for i in range(len(time)):

        def get(name, int_=True, i=i):
            values = columns.get(name)
            return None if values is None else _opt(values[i], int_)

        index = get("device_index")
        names = columns.get("product_name")
        device = FitDevice(
            device_index=index,
            manufacturer=get("manufacturer"),
            manufacturer_name=_manufacturer_name(get("manufacturer")),
            product=get("product"),
            product_name=None if names is None else names[i],
            serial_number=get("serial_number"),
            software_version=get("software_version", int_=False),
        )
        by_index[index if index is not None else ("unindexed", i)] = device
    return tuple(by_index.values())


def _creator(file_id, devices):
    info = next((d for d in devices if d.device_index == 0), None)
    if not file_id and info is None:
        return None
    info = info or FitDevice()
    names = file_id.get("product_name")
    manufacturer = _first(file_id, "manufacturer")
    manufacturer = info.manufacturer if manufacturer is None else manufacturer
    product = _first(file_id, "product")
    serial = _first(file_id, "serial_number")
    return FitDevice(
        device_index=0,
        manufacturer=manufacturer,
        manufacturer_name=_manufacturer_name(manufacturer),
        product=info.product if product is None else product,
        product_name=(names[0] if names else None) or info.product_name,
        serial_number=info.serial_number if serial is None else serial,
        software_version=info.software_version,
    )


def _device_label(device):
    if device is None:
        return None
    if device.product_name:
        return device.product_name
    if device.manufacturer is None and device.product is None:
        return None
    maker = device.manufacturer_name or (
        None if device.manufacturer is None else f"manufacturer {device.manufacturer}"
    )
    product = None if device.product is None else str(device.product)
    return " ".join(p for p in (maker, product) if p)

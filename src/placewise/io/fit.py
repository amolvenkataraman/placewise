"""Garmin FIT activity files into a Track, laps, sessions and the recording device, without dependencies.

Follows the FIT protocol description in the public FIT SDK: a 12- or 14-byte file header, then
records, each a definition message (the layout of a local message number: global message, byte
order, field numbers, sizes and base types) or a data message laid out by the latest definition of
its local number, then a CRC-16 of everything before it. FIT files may be chained back to back.
Only the activity fields in `constants.fit.MESSAGE_FIELDS` are decoded; every other field, message
and developer field is skipped by the size its definition gives, so unknown content never breaks a
read.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from placewise.constants import fit
from placewise.model._base import Model
from placewise.tracks import Track, TrackMeta

from ._fit_decode import FitError as FitError  # re-exported: raised by read_fit
from ._fit_decode import decode


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
    messages = decode(data, check_crc)
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


# --- from raw values to columns and objects ---


def _table(definitions):
    """Columns by field name (float64 with NaN for invalid, or lists of str / None for text) and the
    message times as UTC unix seconds (NaN where a message had none), in file order."""
    used = [d for d in definitions if d.count]
    n = sum(d.count for d in used)
    if not used:
        return {}, np.zeros(0)
    order = np.argsort(np.concatenate([d.seq for d in used]), kind="stable")
    rank = np.empty(n, dtype=np.intp)
    rank[order] = np.arange(n)  # where each definition's rows go in file order
    columns, time, start = {}, np.empty(n), 0
    for d in used:
        where = rank[start : start + d.count]
        start += d.count
        time[where] = np.array(d.times, dtype=np.float64)  # None becomes NaN
        for field, base, values in zip(d.fields, d.bases, d.columns(), strict=True):
            if field.name == "timestamp":
                continue  # already in d.times, alongside compressed-header times
            if field.name not in columns:
                columns[field.name] = [None] * n if field.kind == "string" else np.full(n, np.nan)
            target = columns[field.name]
            if field.kind == "string":
                for i, value in zip(where.tolist(), values.tolist(), strict=True):
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

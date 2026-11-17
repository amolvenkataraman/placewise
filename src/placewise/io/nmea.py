"""NMEA 0183 logs into a Track, from GGA, RMC and GLL sentences.

Sentences sharing a UTC time of day are one fix: position from GGA (else RMC, else GLL), altitude,
satellites and HDOP from GGA, speed and course from RMC. Only RMC carries a date, so it dates every
fix, including those logged before it, and a time of day that jumps back past midnight moves the
date on. Sentences failing their checksum are skipped and counted.
"""

import datetime as dt
import math
import warnings
from functools import reduce

from placewise.constants import nmea
from placewise.constants.speed import METRES_PER_SECOND
from placewise.tracks import TrackMeta

from ._track_common import (
    TrackReadWarning,
    build_track,
    decode_text,
    new_points,
    read_source,
    source_name,
    warn_skipped,
)

_EPOCH_ORDINAL = dt.date(1970, 1, 1).toordinal()
_COLUMNS = ("ele", "accuracy", "speed", "heading", "satellites")


def read_nmea(source, date=None, uere_m=nmea.DEFAULT_UERE_M):
    """A Track from an NMEA log (path, bytes or file object).

    `date` (a datetime.date, the UTC date of the first fix) dates logs with no RMC sentence; without
    either, times are NaN. `accuracy` is HDOP x `uere_m` metres; pass None to leave it out."""
    epochs, bad = _epochs(decode_text(read_source(source)))
    warn_skipped(bad, "sentence(s)", "bad or missing checksum, or malformed fields", "NMEA")
    dates = _epoch_dates(epochs, date)
    points = new_points(_COLUMNS)
    no_fix = 0
    for epoch, day in zip(epochs, dates, strict=True):
        position = _position(epoch)
        if position is None:
            no_fix += 1
            continue
        gga, rmc = epoch.get("GGA") or {}, epoch.get("RMC") or {}
        points["time"].append(
            math.nan if day is None else (day - _EPOCH_ORDINAL) * nmea.SECONDS_PER_DAY + epoch["tod"]
        )
        points["lat"].append(position[0])
        points["lon"].append(position[1])
        points["ele"].append(gga.get("ele", math.nan))
        points["satellites"].append(gga.get("satellites", math.nan))
        hdop = gga.get("hdop", math.nan)
        points["accuracy"].append(math.nan if uere_m is None else hdop * uere_m)
        points["speed"].append(rmc.get("speed", math.nan))
        points["heading"].append(rmc.get("course", math.nan))
    warn_skipped(no_fix, "fix(es)", "no fix: void status, quality 0 or no position", "NMEA")
    if points["time"] and all(d is None for d in dates):
        message = "NMEA: no RMC sentence and no date= given, so times are NaN"
        warnings.warn(TrackReadWarning(message, 0, "no date"), stacklevel=2)
    return build_track(points, None, TrackMeta(source=source_name(source, "nmea")))


def _epochs(text):
    epochs, bad = [], 0
    for line in text.splitlines():
        start = line.find("$")  # loggers often put their own timestamp in front
        if start < 0:
            continue
        fields = _checked_fields(line[start:].strip())
        if fields is None:
            bad += 1
            continue
        talker, kind = fields[0][:2], fields[0][2:]
        if talker not in nmea.TALKER_IDS or kind not in nmea.SENTENCES:
            continue
        try:
            record = _PARSERS[kind](fields[1:])
        except (ValueError, IndexError):
            bad += 1
            continue
        if not epochs or epochs[-1]["tod"] != record["tod"]:
            epochs.append({"tod": record["tod"]})
        epochs[-1].setdefault(kind, record)
    return epochs, bad


def _checked_fields(sentence):
    body, star, checksum = sentence[1:].partition("*")
    if not star or len(checksum) < 2:
        return None
    try:
        expected = int(checksum[:2], 16)
    except ValueError:
        return None
    if reduce(lambda acc, ch: acc ^ ord(ch), body, 0) != expected:
        return None
    return body.split(",")


def _gga(f):
    record = {"tod": _time_of_day(f[0]), "quality": int(f[5] or nmea.NO_FIX_QUALITY)}
    record["position"] = (
        _lat_lon(f[1], f[2], f[3], f[4]) if record["quality"] != nmea.NO_FIX_QUALITY else None
    )
    for key, text in (("satellites", f[6]), ("hdop", f[7]), ("ele", f[8])):
        if text:
            record[key] = float(text)
    return record


def _rmc(f):
    valid = f[1] == nmea.VALID_STATUS and not (len(f) > 11 and f[11] == nmea.INVALID_MODE)
    record = {"tod": _time_of_day(f[0]), "position": _lat_lon(f[2], f[3], f[4], f[5]) if valid else None}
    if f[6]:
        record["speed"] = float(f[6]) * METRES_PER_SECOND["kn"]
    if f[7]:
        record["course"] = float(f[7])
    if f[8]:  # the receiver clock can know the date before there is a fix, so keep it either way
        day, month, year = int(f[8][0:2]), int(f[8][2:4]), int(f[8][4:6])
        year += 1900 if year >= nmea.CENTURY_PIVOT else 2000
        record["date"] = dt.date(year, month, day).toordinal()
    return record


def _gll(f):
    valid = f[5] == nmea.VALID_STATUS and not (len(f) > 6 and f[6] == nmea.INVALID_MODE)
    return {"tod": _time_of_day(f[4]), "position": _lat_lon(f[0], f[1], f[2], f[3]) if valid else None}


_PARSERS = {"GGA": _gga, "RMC": _rmc, "GLL": _gll}


def _time_of_day(text):
    seconds = int(text[0:2]) * 3600 + int(text[2:4]) * 60 + float(text[4:])
    if not 0 <= seconds < nmea.SECONDS_PER_DAY + 1:  # +1 lets a leap second (23:59:60) through
        raise ValueError(f"bad NMEA time {text!r}")
    return seconds


def _lat_lon(lat, ns, lon, ew):
    if not (lat and lon and ns in "NS" and ew in "EW"):
        return None
    return _degrees(lat) * (-1 if ns == "S" else 1), _degrees(lon) * (-1 if ew == "W" else 1)


def _degrees(text):
    # ddmm.mmmm or dddmm.mmmm: the minutes always take the two digits before the point
    dot = text.find(".")
    dot = len(text) if dot < 0 else dot
    degrees, minutes = int(text[: dot - 2]), float(text[dot - 2 :])
    if minutes >= 60:
        raise ValueError(f"bad NMEA coordinate {text!r}")
    return degrees + minutes / 60


def _position(epoch):
    for kind in nmea.SENTENCES:  # GGA, then RMC, then GLL
        record = epoch.get(kind)
        if record and record["position"] is not None:
            return record["position"]
    return None


def _epoch_dates(epochs, date):
    """The date ordinal of each epoch, or None when nothing dates the log."""
    day_index, days, previous = 0, [], None
    for epoch in epochs:
        if previous is not None and epoch["tod"] < previous - nmea.ROLLOVER_JUMP_S:
            day_index += 1
        days.append(day_index)
        previous = epoch["tod"]
    # each RMC date fixes the date of day_index 0; later RMCs win from their own epoch on, so a log
    # that was restarted on another day picks the new date up
    anchors = [
        (e["RMC"]["date"] - d) if "date" in (e.get("RMC") or {}) else None
        for e, d in zip(epochs, days, strict=True)
    ]
    current = next((a for a in anchors if a is not None), None)
    if current is None and date is not None:
        current = date.toordinal()
    if current is None:
        return [None] * len(epochs)
    out = []
    for anchor, d in zip(anchors, days, strict=True):
        current = anchor if anchor is not None else current
        out.append(current + d)
    return out

"""The Track container: columnar, validated, read-only arrays plus segments and metadata.

Columns are float64 numpy arrays of equal length; `time` is UTC unix seconds (float, so sub-second
recordings keep their precision). Operations (clean, measure, resample ...) build new Tracks.
"""

from dataclasses import dataclass
from itertools import pairwise

import numpy as np

from placewise.model._base import Model

REQUIRED_COLUMNS = ("time", "lat", "lon")
OPTIONAL_COLUMNS = (
    "ele",
    "accuracy",
    "speed",
    "heading",
    "hr",
    "cadence",
    "power",
    "temperature",
    "satellites",
)


@dataclass(frozen=True, slots=True)
class TrackMeta(Model):
    name: str | None = None
    activity: str | None = None  # walking, cycling, driving ... as the source states it
    device: str | None = None
    source: str | None = None  # file or importer it came from


class Track:
    """`time`, `lat`, `lon`, any of OPTIONAL_COLUMNS; `segments` are the start index of each
    continuous recording (the first is always 0)."""

    __slots__ = ("_columns", "meta", "segments")

    def __init__(self, time, lat, lon, segments=None, meta=None, **optional):
        if unknown := sorted(set(optional) - set(OPTIONAL_COLUMNS)):
            raise ValueError(f"unknown track column(s) {unknown}; known: {OPTIONAL_COLUMNS}")
        given = {"time": time, "lat": lat, "lon": lon, **{k: v for k, v in optional.items() if v is not None}}
        columns = {}
        for name in REQUIRED_COLUMNS + OPTIONAL_COLUMNS:  # fixed column order, whatever the call order
            if name in given:
                array = np.array(given[name], dtype=np.float64)  # a copy, so callers can't mutate it
                if array.ndim != 1:
                    raise ValueError(f"column {name!r} must be one-dimensional")
                array.flags.writeable = False
                columns[name] = array
        n = len(columns["time"])
        if bad := [k for k, v in columns.items() if len(v) != n]:
            raise ValueError(f"column length mismatch: {bad} differ from time ({n})")
        lat_, lon_ = columns["lat"], columns["lon"]
        if not (np.all(np.isfinite(lat_)) and np.all(np.abs(lat_) <= 90)):
            raise ValueError("latitude must be finite and within ±90")
        if not (np.all(np.isfinite(lon_)) and np.all(np.abs(lon_) <= 180)):
            raise ValueError("longitude must be finite and within ±180")
        self._columns = columns
        self.segments = _check_segments(segments, n)
        self.meta = meta if meta is not None else TrackMeta()

    @classmethod
    def from_columns(cls, columns, segments=None, meta=None):
        columns = dict(columns)
        return cls(columns.pop("time"), columns.pop("lat"), columns.pop("lon"), segments, meta, **columns)

    def __len__(self):
        return len(self._columns["time"])

    def __repr__(self):
        return f"Track({len(self)} points, {len(self.segments)} segments, columns={self.columns})"

    @property
    def columns(self):
        return tuple(self._columns)

    def __getattr__(self, name):
        # time / lat / lon and the optional columns read as attributes; absent optional ones are None
        if name in REQUIRED_COLUMNS or name in OPTIONAL_COLUMNS:
            return self._columns.get(name)
        raise AttributeError(name)

    def __getitem__(self, key):
        """A new Track of the selected points (boolean mask, index array or slice); segment
        boundaries follow the points they started."""
        index = np.arange(len(self))[key]
        segment_of = np.searchsorted(np.asarray(self.segments), np.arange(len(self)), side="right") - 1
        kept = segment_of[index]
        starts = (
            tuple(int(i) for i in np.flatnonzero(np.r_[True, kept[1:] != kept[:-1]])) if len(index) else ()
        )
        return Track.from_columns({k: v[index] for k, v in self._columns.items()}, starts, self.meta)

    def iter_segments(self):
        bounds = (*self.segments, len(self))
        for start, end in pairwise(bounds):
            yield self[start:end]

    def replace(self, **columns):
        """A new Track with some columns swapped (None drops an optional column), same segments
        and meta."""
        return Track.from_columns({**self._columns, **columns}, self.segments or None, self.meta)

    def segment_bounds(self):
        """(start, end) index pairs of each segment, end exclusive."""
        from ._ops import bounds

        return bounds(self)

    # Thin methods over the operation modules, each documented there. Imports are local because
    # those modules import Track, and placewise.io imports this package.

    @classmethod
    def read(cls, path_or_bytes):
        """The first track of a file in any supported format (a path, bytes or a binary file
        object; the format is detected from the content). Files can hold several tracks, and GPX
        routes too: `placewise.io.read_track` returns them all."""
        from placewise.io import read_track

        tracks, fmt = read_track(path_or_bytes)
        if not tracks:
            raise ValueError(f"the {fmt} file has no track")
        return tracks[0]

    def to_gpx(self, path=None):
        """GPX 1.1 text (see `placewise.io.write_gpx`), also written to `path` when given."""
        from placewise.io import write_gpx

        return write_gpx(self, path)

    def to_geojson(self):
        """A GeoJSON Feature dict (see `placewise.io.write_geojson_track`)."""
        from placewise.io import write_geojson_track

        return write_geojson_track(self)

    def clean(self):
        """The usual cleaning pipeline with default settings: sort_and_dedupe -> drop_invalid ->
        remove_spikes -> split_gaps. Call the functions in `placewise.tracks.cleaning` to tune them or
        add filter_accuracy, smooth or thin."""
        from .cleaning import drop_invalid, remove_spikes, sort_and_dedupe, split_gaps

        return split_gaps(remove_spikes(drop_invalid(sort_and_dedupe(self))))

    def smooth(self, **options):
        from .cleaning import smooth

        return smooth(self, **options)

    def thin(self, **options):
        from .cleaning import thin

        return thin(self, **options)

    def stats(self, **options):
        from .metrics import stats

        return stats(self, **options)

    def splits(self, **options):
        from .metrics import splits

        return splits(self, **options)

    def position_at(self, times, **options):
        from .timing import position_at

        return position_at(self, times, **options)

    def resample(self, **options):
        from .timing import resample

        return resample(self, **options)

    def stays(self, **options):
        from .movement import stays

        return stays(self, **options)

    def trips(self, stays=None, **stay_options):
        """Trips between `stays`, found with `stay_options` when not given."""
        from .movement import trips

        return trips(self, self.stays(**stay_options) if stays is None else stays)

    def time_inside(self, shape):
        from .areas import time_inside

        return time_inside(self, shape)

    def crossings(self, features):
        from .areas import crossings

        return crossings(self, features)

    def closest_pass(self, lat, lon):
        from .areas import closest_pass

        return closest_pass(self, lat, lon)

    @property
    def bbox(self):
        from .areas import bbox

        return bbox(self)

    def crop(self, start=None, end=None):
        from .routes import crop

        return crop(self, start, end)

    def split(self, by="segment", **options):
        from .routes import split

        return split(self, by, **options)

    def reverse(self):
        from .routes import reverse

        return reverse(self)


def _check_segments(segments, n):
    if n == 0:
        return ()
    segments = (0,) if segments is None else tuple(int(s) for s in segments)
    if not segments or segments[0] != 0 or any(b <= a for a, b in pairwise(segments)):
        raise ValueError(f"segment starts must begin at 0 and increase: {segments}")
    if segments[-1] >= n:
        raise ValueError(f"segment start {segments[-1]} is beyond the track's {n} points")
    return segments

"""`placewise lookup`: the place at a point, as a readable card or JSON; or a CSV of points.

placewise lookup 43.6426 -79.3871
placewise lookup 43.6426,-79.3871 --json --worldview IN
placewise lookup 43.6 -77.9 --altitude 10000          # "Over Lake Ontario" (else "On ...")
placewise lookup --csv points.csv --out named.csv --lat-column Latitude --lon-column Longitude
"""

import contextlib
import csv
import json
import math
import sys

from placewise.constants import cli as const

from . import _common
from ._common import add_packs_option, card_width, subparser


def add_lookup(commands):
    sub = subparser(commands, "lookup", "the place at a point (reverse geocoding, offline)")
    sub.add_argument("lat", nargs="?", help="latitude, WGS84 degrees (or LAT,LON in one argument)")
    sub.add_argument("lon", nargs="?", help="longitude, WGS84 degrees")
    sub.add_argument("--json", action="store_true", help="the Result as JSON")
    sub.add_argument("--worldview", help="worldview for points in disputed areas (e.g. IN)")
    sub.add_argument("--no-near", action="store_true", help="leave out the places near the point")
    sub.add_argument(
        "--altitude", type=float, metavar="METRES",
        help="metres above sea level (every --csv row): 'Over' water from 100 m above it, else 'On'",
    )  # fmt: skip
    batch = sub.add_argument_group("batch")
    batch.add_argument("--csv", metavar="FILE", help="look up every row of this CSV file instead")
    batch.add_argument("--out", metavar="FILE", help="with --csv: write here (default: standard output)")
    batch.add_argument("--lat-column", default=const.LOOKUP_LAT_COLUMN, help="with --csv (default: lat)")
    batch.add_argument("--lon-column", default=const.LOOKUP_LON_COLUMN, help="with --csv (default: lon)")
    add_packs_option(sub)
    sub.set_defaults(handler=_cmd_lookup)


def _cmd_lookup(args):
    if args.csv:
        if args.lat is not None:
            return _usage(args, "give coordinates or --csv, not both")
        return _batch(args)
    point = _point(args.lat, args.lon)
    if point is None:
        return _usage(args, "expected LAT LON (or LAT,LON) or --csv FILE")
    geocoder = _common.open_geocoder(args)
    result = geocoder.lookup(
        *point, worldview=args.worldview, near=not args.no_near, altitude_m=args.altitude
    )
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(result.card(color=None, width=card_width()))
    return 0


def _batch(args):
    with open(args.csv, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = list(reader.fieldnames or [])
        for column in (args.lat_column, args.lon_column):
            if column not in header:
                raise ValueError(f"{args.csv}: no column {column!r} (columns: {', '.join(header)})")
        rows = list(reader)
    points = [_on_earth(_number_pair(r.get(args.lat_column), r.get(args.lon_column))) for r in rows]
    good = [i for i, p in enumerate(points) if p is not None]
    answers = {}
    if good:
        geocoder = _common.open_geocoder(args)
        for start in range(0, len(good), const.LOOKUP_BATCH):
            chunk = good[start : start + const.LOOKUP_BATCH]
            results = geocoder.lookup_many(
                [points[i][0] for i in chunk],
                [points[i][1] for i in chunk],
                worldview=args.worldview,
                near=False,
                altitude_m=args.altitude,
            )
            answers.update(zip(chunk, results, strict=True))
    fields = header + [c for c in const.LOOKUP_CSV_COLUMNS if c not in header]
    with contextlib.ExitStack() as stack:
        out = (
            stack.enter_context(open(args.out, "w", newline="", encoding="utf-8")) if args.out else sys.stdout
        )
        writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for i, row in enumerate(rows):
            writer.writerow({**row, **_columns(answers.get(i))})
    bad = [i + 1 for i, p in enumerate(points) if p is None]  # data rows, counted from 1
    if bad:
        shown = ", ".join(map(str, bad[: const.BAD_ROWS_SHOWN])) + (
            " ..." if len(bad) > const.BAD_ROWS_SHOWN else ""
        )
        noun = "row" if len(bad) == 1 else "rows"
        print(
            f"placewise: {len(bad)} {noun} without valid coordinates left blank ({noun} {shown})",
            file=sys.stderr,
        )
    return 0


def _columns(result):
    """The answer columns of one Result ("" for every column without one)."""
    if result is None:
        return dict.fromkeys(const.LOOKUP_CSV_COLUMNS, "")
    out = {"label": result.label}
    for field in ("locality", "city", "admin1", "country", "postal"):
        place = getattr(result, field)
        out[field] = place.name if place is not None else ""
    out["tz"] = result.tz or ""
    out["within"] = result.within[0].name if result.within else ""
    out["water"] = result.water.place.name if result.water is not None else ""
    return out


def _point(lat, lon):
    if lat is not None and lon is None and "," in lat:
        lat, lon = lat.split(",", 1)
    return _number_pair(lat, lon)


def _number_pair(lat, lon):
    """(lat, lon) as floats, or None when either isn't a finite number (range is the Geocoder's check)."""
    try:
        pair = (float(lat), float(lon))
    except (TypeError, ValueError):
        return None
    return pair if all(math.isfinite(v) for v in pair) else None


def _on_earth(pair):
    return pair if pair is not None and abs(pair[0]) <= 90 and abs(pair[1]) <= 180 else None


def _usage(args, message):
    args.usage_parser.print_usage(sys.stderr)
    print(f"placewise lookup: error: {message}", file=sys.stderr)
    return 2

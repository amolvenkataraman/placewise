"""`placewise find`: places named by some text, as readable result cards or JSON.

placewise find "Lake Tahoe"
placewise find Paris --country USA
placewise find YYZ --kind airport --json
"""

import json
import sys

from . import _common
from ._common import add_packs_option, card_width, count, subparser


def add_find(commands):
    sub = subparser(commands, "find", "places named by some text (forward search, offline)")
    sub.add_argument("text", help='a name ("Lake Tahoe", "Paris, TX"), code (YYZ, 94105), id or coordinates')
    sub.add_argument("--limit", type=count, default=5, help="results to show (default 5)")
    sub.add_argument(
        "--country", action="append", help="only in this country: US, USA, Canada ... (repeatable)"
    )
    sub.add_argument(
        "--admin1", "--state", dest="admin1", action="append", help="only in this state or province"
    )
    sub.add_argument("--near", type=_lat_lon, metavar="LAT,LON", help="prefer places near this point")
    sub.add_argument("--radius-km", type=float, help="with --near: only places within this distance")
    sub.add_argument("--bbox", type=_bbox, metavar="S,W,N,E", help="only places inside this box")
    sub.add_argument("--within", help='only places inside this place: an id or name ("GTA", "region:gta")')
    sub.add_argument(
        "--kind", action="append", help="only this kind: city, park, water, airport ... (repeatable)"
    )
    sub.add_argument("--loose", action="store_true", help="filters above only push results down")
    sub.add_argument("--prefix", action="store_true", help="match names starting with the text (type-ahead)")
    sub.add_argument("--worldview", help="worldview for places in disputed areas (e.g. IN)")
    sub.add_argument("--geometry", action="store_true", help="with --json: include each place's outline")
    sub.add_argument("--json", action="store_true", help="the Entities as JSON")
    add_packs_option(sub)
    sub.set_defaults(handler=_cmd_find)


def _cmd_find(args):
    geocoder = _common.open_geocoder(args)
    found = geocoder.find(
        args.text,
        limit=args.limit,
        country=args.country,
        admin1=args.admin1,
        near=args.near,
        radius_km=args.radius_km,
        bbox=args.bbox,
        within=args.within,
        kinds=args.kind,
        strict=not args.loose,
        prefix=args.prefix,
        worldview=args.worldview,
        geometry=args.geometry and args.json,
    )
    if args.json:
        print(json.dumps([e.to_dict() for e in found], indent=2, ensure_ascii=False))
        return 0
    if not found:
        print(f"nothing found for {args.text!r}", file=sys.stderr)
        return 1
    width = card_width()
    print(
        "\n\n".join(
            f"{i}. " + e.card(color=None, width=width - len(f"{i}. ")) for i, e in enumerate(found, 1)
        )
    )
    return 0


def _numbers(text, n, what):
    import argparse

    try:
        values = tuple(float(v) for v in text.replace(" ", "").split(","))
    except ValueError:
        values = ()
    if len(values) != n:
        raise argparse.ArgumentTypeError(f"expected {what}, got {text!r}")
    return values


def _lat_lon(text):
    return _numbers(text, 2, "LAT,LON")


def _bbox(text):
    return _numbers(text, 4, "SOUTH,WEST,NORTH,EAST")

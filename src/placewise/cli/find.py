"""`placewise find`: places named by some text, as readable result cards or JSON.

placewise find "Lake Tahoe"
placewise find Paris --country USA
placewise find YYZ --kind airport --json
"""

import json
import sys

from ._common import count, subparser


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
    sub.set_defaults(handler=_cmd_find)


def _cmd_find(args):
    geocoder = _geocoder(args)
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
    sys.stdout.write("\n".join(card(i, e) for i, e in enumerate(found, 1)))
    return 0


def card(n, entity):
    """A few readable lines for one Entity."""
    place = entity.place
    where = ", ".join(x for x in (entity.city, entity.region, entity.country) if x)
    title = f"{n}. {place.name}" + (f"  ({where})" if where else "")
    kind = place.kind.value.replace("_", " ") + (f", tier {place.tier}" if place.tier else "")
    lines = [
        title,
        f"   {kind} · {place.id}" + (f" · score {entity.score:.3f}" if entity.score is not None else ""),
        f"   point {entity.point.lat:.5f}, {entity.point.lon:.5f} · radius {entity.radius_km:.1f} km",
        "   bbox {:.4f}, {:.4f} .. {:.4f}, {:.4f}".format(*entity.bbox.as_tuple()),
    ]
    codes = {k: v for k, v in place.codes.items() if k not in ("iso2", "admin1")}
    if codes:
        lines.append("   codes " + ", ".join(f"{k} {v}" for k, v in codes.items()))
    if place.aliases:
        lines.append("   also called " + ", ".join(place.aliases[:5]))
    if entity.alternates:
        lines.append("   same place in " + ", ".join(p.id for p in entity.alternates[:5]))
    return "\n".join(lines) + "\n"


def _geocoder(args):
    from placewise.config import load_settings
    from placewise.engine import Geocoder
    from placewise.overrides import load_overrides

    data = {}
    if args.data_dir is not None:
        data["data_dir"] = args.data_dir
    if args.index_url is not None:
        data["index_url"] = args.index_url
    if args.offline:
        data["offline"] = True
    settings = load_settings(data=data)
    return Geocoder(settings=settings, overrides=load_overrides(settings=settings))


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

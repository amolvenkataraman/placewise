"""`placewise attribution`: the data sources, licences and credit lines to show."""

import json
import sys

from ._common import subparser


def add_attribution(commands):
    sub = subparser(commands, "attribution", "the data sources, licences and credit lines to show")
    sub.add_argument("--json", action="store_true", help="the source registry as JSON")
    sub.set_defaults(handler=_cmd_attribution)


def _cmd_attribution(args):
    from placewise import attribution

    if args.json:
        sources = {id_: s.to_dict() for id_, s in attribution.load_sources().items()}
        print(json.dumps(sources, indent=2, ensure_ascii=False))
    else:
        sys.stdout.write(attribution.render_markdown())

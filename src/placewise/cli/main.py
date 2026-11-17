"""The `placewise` parser and dispatch: global options, one sub-parser per command group, error and
exit-code handling.

Each top-level command lives in its own module with one `add_<command>` function that builds its
sub-parser and sets a handler; new ones (lookup, find) join `_COMMANDS` the same way.
"""

import argparse
import sys

from placewise import __version__
from placewise.store import StoreError

from ._common import add_global_options, one_line
from .attribution import add_attribution
from .data import add_data
from .serve import add_serve
from .server import add_server


def main(argv=None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:  # argparse exits 2 on bad usage and 0 after --help
        return e.code if isinstance(e.code, int) else 2
    if not hasattr(args, "handler"):
        (args.usage_parser if hasattr(args, "usage_parser") else parser).print_usage(sys.stderr)
        return 2
    try:
        return args.handler(args) or 0
    except (StoreError, OSError, ValueError) as e:
        print(f"placewise: error: {one_line(e)}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("placewise: interrupted", file=sys.stderr)
        return 130


def _build_parser():
    parser = argparse.ArgumentParser(prog="placewise", description="Offline, two-way geocoding.")
    parser.add_argument("--version", action="version", version=f"placewise {__version__}")
    add_global_options(parser)
    commands = parser.add_subparsers(title="commands", metavar="<command>")
    for add in _COMMANDS:
        add(commands)
    return parser


# Top-level commands, in help order.
_COMMANDS = (add_data, add_attribution, add_serve, add_server)

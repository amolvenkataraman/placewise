"""Helpers every command group shares: sub-parsers that accept the global options, the Store the
options describe, one-line error text and argparse value types."""

import argparse

from placewise.model import DataSettings
from placewise.store import Store


def add_global_options(parser, suppress=False):
    # The same options on every sub-parser, defaulting to SUPPRESS there, so they work both before
    # and after the command without the later parser resetting what the earlier one read.
    default = argparse.SUPPRESS if suppress else None
    group = parser.add_argument_group("global options")
    group.add_argument(
        "--data-dir", default=default, help="where packs are kept (default: platform data dir)"
    )
    group.add_argument("--index-url", default=default, help="the pack index to download from")
    group.add_argument(
        "--offline",
        action="store_true",
        default=argparse.SUPPRESS if suppress else False,
        help="never download",
    )


def subparser(commands, name, help_text):
    sub = commands.add_parser(name, help=help_text, description=help_text)
    add_global_options(sub, suppress=True)
    sub.set_defaults(usage_parser=sub)
    return sub


def open_store(args):
    settings = DataSettings(offline=args.offline)
    return Store(args.data_dir, settings, index_url=args.index_url)


def one_line(error):
    return " ".join(str(error).split()) or type(error).__name__


def count(text):
    """argparse type: a whole number, 0 or more."""
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a whole number: {text!r}") from None
    if value < 0:
        raise argparse.ArgumentTypeError("can't be negative")
    return value

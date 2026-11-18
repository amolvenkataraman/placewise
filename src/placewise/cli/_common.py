"""Helpers every command group shares: sub-parsers that accept the global options, the Store and
Geocoder the options describe, card width, one-line error text and argparse value types."""

import argparse
import dataclasses
import shutil

from placewise.config import load_settings
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
    """The Store placewise.toml and the environment describe, with command-line options on top."""
    settings = load_settings().data
    if args.offline:
        settings = dataclasses.replace(settings, offline=True)
    return Store(args.data_dir, settings, index_url=args.index_url)


def add_packs_option(parser):
    parser.add_argument(
        "--packs",
        nargs="+",
        metavar="DIR",
        help="use these packs instead of the installed ones: pack directories or folders of them",
    )


def open_geocoder(args):
    """The Geocoder for a lookup or search command: the --packs given, else the installed packs
    (placewise.toml, the environment and the global options decide where and whether to download)."""
    from placewise.config import load_settings
    from placewise.engine import Geocoder
    from placewise.overrides import load_overrides
    from placewise.store.paths import pack_dirs

    data = {}
    if args.data_dir is not None:
        data["data_dir"] = args.data_dir
    if args.index_url is not None:
        data["index_url"] = args.index_url
    if args.offline:
        data["offline"] = True
    settings = load_settings(data=data)
    packs = pack_dirs(args.packs) if getattr(args, "packs", None) else None
    return Geocoder(packs=packs, settings=settings, overrides=load_overrides(settings=settings))


def card_width():
    """Cards fill the terminal up to their own maximum width."""
    from placewise.constants.display import WIDTH

    return min(WIDTH, shutil.get_terminal_size((WIDTH, 24)).columns)


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

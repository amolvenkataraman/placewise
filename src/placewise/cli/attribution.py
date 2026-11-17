"""`placewise attribution`: the data sources, licences and credit lines to show.

By default only the sources of the installed packs (the current version of each), since those are
what an app using this data dir must credit; `--all` lists the whole source registry.
"""

import json
import sys

from ._common import open_store, subparser

INSTALLED = "the installed data packs"


def add_attribution(commands):
    sub = subparser(commands, "attribution", "the data sources, licences and credit lines to show")
    sub.add_argument(
        "--all", action="store_true", help="every source placewise uses, not just the installed packs'"
    )
    form = sub.add_mutually_exclusive_group()
    form.add_argument("--json", action="store_true", help="the sources' registry entries as JSON")
    form.add_argument("--short", action="store_true", help="one credit line per source")
    sub.set_defaults(handler=_cmd_attribution)


def _cmd_attribution(args):
    from placewise import attribution

    only = None
    if not args.all:
        only = _installed_sources(args, attribution)
        if not only:
            print(
                "no packs installed (placewise data install world); "
                "`placewise attribution --all` lists every source",
                file=sys.stderr,
            )
            return 1
    if args.json:
        sources = attribution.load_sources()
        chosen = sources if only is None else {i: s for i, s in sources.items() if i in set(only)}
        print(json.dumps({i: s.to_dict() for i, s in chosen.items()}, indent=2, ensure_ascii=False))
    elif args.short:
        sys.stdout.write(attribution.render_credits(only=only))
    else:
        subject = None if only is None else INSTALLED
        sys.stdout.write(attribution.render_markdown(only=only, subject=subject))
    return 0


def _installed_sources(args, attribution):
    """The registry source ids the installed packs carry; ids the registry lacks are named on stderr."""
    from placewise.packs import open_pack

    store = open_store(args)
    packs = [open_pack(store.current(name)) for name in store.installed()]
    ids = attribution.pack_sources(packs)
    known = attribution.load_sources()
    if unknown := [i for i in ids if i not in known]:
        print(f"not in placewise's source registry, so not listed: {', '.join(unknown)}", file=sys.stderr)
    return [i for i in ids if i in known]

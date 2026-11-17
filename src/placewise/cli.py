"""The `placewise` command line. Exit codes: 0 ok, 1 error, 2 usage.

Each top-level command lives in one `_add_<command>` function that builds its sub-parser and sets a
handler; `lookup`, `find` and `serve` will join `data` the same way, in _COMMANDS.
"""

import argparse
import json
import sys

from placewise import __version__
from placewise.model import DataSettings
from placewise.store import Store, StoreError


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
        print(f"placewise: error: {_one_line(e)}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("placewise: interrupted", file=sys.stderr)
        return 130


def _build_parser():
    parser = argparse.ArgumentParser(prog="placewise", description="Offline, two-way geocoding.")
    parser.add_argument("--version", action="version", version=f"placewise {__version__}")
    _add_global_options(parser)
    commands = parser.add_subparsers(title="commands", metavar="<command>")
    for add in _COMMANDS:
        add(commands)
    return parser


def _add_global_options(parser, suppress=False):
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


def _subparser(commands, name, help_text):
    sub = commands.add_parser(name, help=help_text, description=help_text)
    _add_global_options(sub, suppress=True)
    sub.set_defaults(usage_parser=sub)
    return sub


def _store(args):
    settings = DataSettings(offline=args.offline)
    return Store(args.data_dir, settings, index_url=args.index_url)


def _one_line(error):
    return " ".join(str(error).split()) or type(error).__name__


# -- placewise data ... ---------------------------------------------------------------------------


def _add_data(commands):
    data = _subparser(commands, "data", "manage downloaded data packs")
    actions = data.add_subparsers(title="data commands", metavar="<action>")

    _subparser(actions, "where", "print the data directory").set_defaults(handler=_cmd_where)
    _subparser(actions, "list", "installed and available packs").set_defaults(handler=_cmd_list)

    install = _subparser(actions, "install", "download and install packs")
    install.add_argument("names", nargs="+", metavar="name")
    install.add_argument("--version", dest="pack_version", help="a specific version (default: newest)")
    install.set_defaults(handler=_cmd_install)

    update = _subparser(actions, "update", "install newer versions (never deletes)")
    update.add_argument("names", nargs="*", metavar="name")
    update.set_defaults(handler=_cmd_update)

    verify = _subparser(actions, "verify", "re-check installed packs against their checksums")
    verify.add_argument("name", nargs="?")
    verify.set_defaults(handler=_cmd_verify)

    prune = _subparser(actions, "prune", "delete old versions, keeping the current and pinned ones")
    prune.add_argument("--keep", type=int, default=1, help="newest versions to keep per pack (default 1)")
    prune.set_defaults(handler=_cmd_prune)

    remove = _subparser(actions, "remove", "delete an installed pack")
    remove.add_argument("name")
    remove.add_argument("--version", dest="pack_version", help="one version (default: all)")
    remove.set_defaults(handler=_cmd_remove)


def _cmd_where(args):
    print(_store(args).data_dir)


def _cmd_list(args):
    _list(_store(args))


def _list(store):
    """Print one line per pack version: installed ones, then what the index offers."""
    installed = store.installed()
    try:
        available = store.available()
    except StoreError as e:
        available = {}
        print(
            f"placewise: warning: pack index unavailable, showing installed packs only: {_one_line(e)}",
            file=sys.stderr,
        )
    pin = store.settings.pin
    rows = []
    for name in sorted(set(installed) | set(available)):
        versions = installed.get(name, [])
        current = pin if pin else (versions[-1] if versions else None)
        offered = available.get(name)
        for version in versions:
            marks = ["installed"]
            if version == current:
                marks.append("current")
            if version == pin:
                marks.append("pinned")
            if offered and offered.version == version:
                marks.append("latest")
            rows.append((name, version, ", ".join(marks)))
        if offered and offered.version not in versions:
            rows.append((name, offered.version, f"available ({_size(offered.size_bytes)})"))
    if not rows:
        print("no packs installed or available")
        return
    width = max(len(r[0]) for r in rows), max(len(r[1]) for r in rows)
    for name, version, marks in rows:
        print(f"{name:<{width[0]}}  {version:<{width[1]}}  {marks}")


def _cmd_install(args):
    store = _store(args)
    progress = _progress_printer() if sys.stderr.isatty() else None
    for name in args.names:
        before = store.installed().get(name, [])
        path = store.install(name, args.pack_version, progress=progress)
        version = path.name[len(name) + 1 :]
        state = "already installed" if version in before else "installed"
        print(f"{name} {version} {state}: {path}")


def _cmd_update(args):
    store = _store(args)
    progress = _progress_printer() if sys.stderr.isatty() else None
    changes = store.update(args.names or None, progress=progress)
    if not changes:
        print("everything is up to date")
    for name, old, new in changes:
        print(f"{name} {old or '(none)'} -> {new}")


def _cmd_verify(args):
    store = _store(args)
    problems = store.verify(args.name)
    for problem in problems:
        print(problem)
    if problems:
        print(
            f"placewise: error: {len(problems)} problem(s); reinstall with placewise data install",
            file=sys.stderr,
        )
        return 1
    count = sum(len(v) for name, v in store.installed().items() if args.name in (None, name))
    print(f"ok: {count} pack version(s) verified")
    return 0


def _cmd_prune(args):
    removed = _store(args).prune(keep=args.keep)
    if not removed:
        print("nothing to prune")
    for name, version in removed:
        print(f"removed {name} {version}")


def _cmd_remove(args):
    for version in _store(args).remove(args.name, args.pack_version):
        print(f"removed {args.name} {version}")


def _size(n):
    if n < 1000:
        return f"{n} B"
    for unit in ("KB", "MB", "GB"):
        n /= 1000
        if n < 1000 or unit == "GB":
            return f"{n:.1f} {unit}"


def _progress_printer():
    def show(done, total):
        percent = 100 * done // total if total else 100
        end = "\n" if done >= total else ""
        print(f"\rdownloading: {percent:3d}% of {_size(total)}", end=end, file=sys.stderr, flush=True)

    return show


# Top-level commands, in help order. Future ones (lookup, find, serve) add an `_add_<name>` here.
def _add_attribution(commands):
    sub = _subparser(commands, "attribution", "the data sources, licences and credit lines to show")
    sub.add_argument("--json", action="store_true", help="the source registry as JSON")
    sub.set_defaults(handler=_cmd_attribution)


def _cmd_attribution(args):
    from placewise import attribution

    if args.json:
        sources = {id_: s.to_dict() for id_, s in attribution.load_sources().items()}
        print(json.dumps(sources, indent=2, ensure_ascii=False))
    else:
        sys.stdout.write(attribution.render_markdown())


_COMMANDS = (_add_data, _add_attribution)


if __name__ == "__main__":
    sys.exit(main())

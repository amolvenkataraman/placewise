"""`placewise data ...`: list, install, update, verify, prune and remove downloaded data packs."""

import sys

from placewise.store import StoreError

from ._common import one_line, open_store, subparser


def add_data(commands):
    data = subparser(commands, "data", "manage downloaded data packs")
    actions = data.add_subparsers(title="data commands", metavar="<action>")

    subparser(actions, "where", "print the data directory").set_defaults(handler=_cmd_where)
    subparser(actions, "list", "installed and available packs").set_defaults(handler=_cmd_list)

    install = subparser(actions, "install", "download and install packs")
    install.add_argument("names", nargs="+", metavar="name")
    install.add_argument("--version", dest="pack_version", help="a specific version (default: newest)")
    install.set_defaults(handler=_cmd_install)

    update = subparser(actions, "update", "install newer versions (never deletes)")
    update.add_argument("names", nargs="*", metavar="name")
    update.set_defaults(handler=_cmd_update)

    verify = subparser(actions, "verify", "re-check installed packs against their checksums")
    verify.add_argument("name", nargs="?")
    verify.set_defaults(handler=_cmd_verify)

    prune = subparser(actions, "prune", "delete old versions, keeping the current and pinned ones")
    prune.add_argument("--keep", type=int, default=1, help="newest versions to keep per pack (default 1)")
    prune.set_defaults(handler=_cmd_prune)

    remove = subparser(actions, "remove", "delete an installed pack")
    remove.add_argument("name")
    remove.add_argument("--version", dest="pack_version", help="one version (default: all)")
    remove.set_defaults(handler=_cmd_remove)


def _cmd_where(args):
    print(open_store(args).data_dir)


def _cmd_list(args):
    _list(open_store(args))


def _list(store):
    """Print one line per pack version: installed ones, then what the index offers."""
    installed = store.installed()
    try:
        available = store.available()
    except StoreError as e:
        available = {}
        print(
            f"placewise: warning: pack index unavailable, showing installed packs only: {one_line(e)}",
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
    store = open_store(args)
    progress = _progress_printer() if sys.stderr.isatty() else None
    for name in args.names:
        before = store.installed().get(name, [])
        path = store.install(name, args.pack_version, progress=progress)
        version = path.name[len(name) + 1 :]
        state = "already installed" if version in before else "installed"
        print(f"{name} {version} {state}: {path}")


def _cmd_update(args):
    store = open_store(args)
    progress = _progress_printer() if sys.stderr.isatty() else None
    changes = store.update(args.names or None, progress=progress)
    if not changes:
        print("everything is up to date")
    for name, old, new in changes:
        print(f"{name} {old or '(none)'} -> {new}")


def _cmd_verify(args):
    store = open_store(args)
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
    removed = open_store(args).prune(keep=args.keep)
    if not removed:
        print("nothing to prune")
    for name, version in removed:
        print(f"removed {name} {version}")


def _cmd_remove(args):
    for version in open_store(args).remove(args.name, args.pack_version):
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

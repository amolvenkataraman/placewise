"""`placewise data ...`: list, install, update, verify, prune and remove downloaded data packs;
`mode` chooses how packs arrive (auto, manual, locked) and `status` shows what's installed, its
size on disk and what auto mode would fetch."""

import sys

from placewise.constants import lookup as lookup_const
from placewise.constants import store as store_const
from placewise.store import StoreError
from placewise.store.ondemand import human_size

from ._common import one_line, open_store, subparser


def add_data(commands):
    data = subparser(commands, "data", "manage downloaded data packs")
    actions = data.add_subparsers(title="data commands", metavar="<action>")

    subparser(actions, "where", "print the data directory").set_defaults(handler=_cmd_where)
    subparser(actions, "list", "installed and available packs").set_defaults(handler=_cmd_list)
    subparser(
        actions, "status", "the data mode, installed packs and their size on disk, what auto mode fetches"
    ).set_defaults(handler=_cmd_status)

    mode = subparser(actions, "mode", "show or set how packs arrive: auto, manual or locked")
    mode.add_argument(
        "mode",
        nargs="?",
        choices=store_const.MODES,
        help="auto: fetch the packs a lookup or search needs; manual: only `data install`; "
        "locked: never download",
    )
    mode.add_argument(
        "--kinds",
        help="the pack kinds auto mode may fetch, comma-separated: "
        f"{','.join(store_const.AUTO_KINDS)} (default: country)",
    )
    mode.set_defaults(handler=_cmd_mode)

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
        had = store.installed()
        path = store.install(name, args.pack_version, progress=progress)
        for extra in sorted(set(store.installed()) - set(had) - {name}):
            print(f"{extra} installed too: {name} requires it")
        version = path.name[len(name) + 1 :]
        state = "already installed" if version in had.get(name, []) else "installed"
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


def _cmd_mode(args):
    from placewise.config import explain_settings, set_setting, user_config_path

    if args.mode is None and args.kinds is None:
        _show_mode(explain_settings(), args)
        return 0
    path = user_config_path()
    if args.kinds is not None:
        kinds = tuple(k.strip() for k in args.kinds.split(",") if k.strip())
        set_setting(path, "data", "auto_packs", kinds)
    if args.mode is not None:
        set_setting(path, "data", "mode", args.mode)
    settings = explain_settings()
    print(f"data mode: {settings['data.mode'][0]} (written to {path})")
    print(f"auto mode fetches: {_kinds(settings['data.auto_packs'][0])}")
    for key in ("data.mode", "data.auto_packs", "data.offline"):
        value, origin = settings[key]
        if origin.startswith("env:") or (key == "data.offline" and value):
            print(f"placewise: warning: {origin.partition(':')[2] or origin} sets {key} = {value!r}, "
                  "which wins over the file", file=sys.stderr)  # fmt: skip
    if getattr(args, "offline", False):
        print("placewise: warning: --offline locks this run whatever the mode", file=sys.stderr)


def _show_mode(settings, args):
    mode, origin = settings["data.mode"]
    offline, offline_origin = settings["data.offline"]
    if offline or getattr(args, "offline", False):
        why = "--offline" if getattr(args, "offline", False) else f"data.offline from {offline_origin}"
        print(f"data mode: locked ({why}; data.mode is {mode})")
    else:
        print(f"data mode: {mode} ({_origin(origin)})")
    kinds, kinds_origin = settings["data.auto_packs"]
    print(f"auto mode fetches: {_kinds(kinds)} ({_origin(kinds_origin)})")


def _origin(origin):
    kind, _, where = origin.partition(":")
    return {"file": f"from {where}", "env": f"from ${where}", "default": "default"}.get(kind, origin)


def _kinds(kinds):
    return ", ".join(f"{k} packs" for k in kinds) if kinds else "nothing beyond the world pack"


def _cmd_status(args):
    store = open_store(args)
    print(f"data mode: {store.mode}; auto mode fetches: {_kinds(store.settings.auto_packs)}")
    if not store.settings.locked:
        try:
            store.fetch_index()
        except StoreError as e:
            print(f"placewise: warning: pack index unavailable: {one_line(e)}", file=sys.stderr)
    coverage = _coverage(store)
    installed = store.installed()
    rows, total = [], 0
    for name, versions in installed.items():
        for version in versions:
            size = store.size_on_disk(name, version)
            total += size
            rows.append((name, version, human_size(size), _covers(coverage.get(name))))
    print(f"data dir: {store.data_dir} ({len(rows)} pack version(s), {human_size(total)} on disk)")
    _table("installed", rows)
    usable = {lookup_const.DEFAULT_PACK, *lookup_const.OPTIONAL_PACKS}  # what lookups read
    fetch = store.plan(everywhere=True, usable=usable)
    available = store.available() if coverage else {}
    _table(
        "auto mode fetches on first use"
        + ("" if store.mode == store_const.MODE_AUTO else f" (mode is {store.mode})"),
        [_offer(n, available[n], coverage[n]) for n in fetch],
    )
    opt_in = [
        n
        for n, cov in sorted(coverage.items())
        if n in usable and n not in installed and n not in fetch and cov.kind != store_const.KIND_BASE
    ]
    _table("opt-in (placewise data install <pack>, or data mode auto --kinds ...)",
           [_offer(n, available[n], coverage[n]) for n in opt_in])  # fmt: skip


def _coverage(store):
    try:
        return store.coverage()
    except StoreError:
        return {}


def _covers(cov):
    if cov is None:
        return ""
    where = "world-wide" if cov.worldwide else ", ".join(cov.covers)
    return f"{cov.kind} ({where})" if where else cov.kind


def _offer(name, info, cov):
    size = f"{human_size(info.size_bytes)} download"
    if cov.installed_bytes:
        size += f", {human_size(cov.installed_bytes)} on disk"
    return name, info.version, size, _covers(cov)


def _table(title, rows):
    print(f"\n{title}:")
    if not rows:
        print("  (none)")
        return
    widths = [max(len(r[i]) for r in rows) for i in range(3)]
    for row in rows:
        print("  " + "  ".join(f"{c:<{w}}" for c, w in zip(row[:3], widths, strict=True)) + f"  {row[3]}")


_size = human_size


def _progress_printer():
    def show(done, total):
        percent = 100 * done // total if total else 100
        end = "\n" if done >= total else ""
        print(f"\rdownloading: {percent:3d}% of {_size(total)}", end=end, file=sys.stderr, flush=True)

    return show

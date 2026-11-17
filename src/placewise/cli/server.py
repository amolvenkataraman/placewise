"""`placewise server keys add | list | revoke`: manage the web server's API keys."""

import json
import sys

from ._common import count, subparser


def add_server(commands):
    from placewise.constants import server as server_const

    server = subparser(commands, "server", "manage the web server's API keys")
    actions = server.add_subparsers(title="server commands", metavar="<action>")
    keys = subparser(actions, "keys", "add, list and revoke API keys")
    key_actions = keys.add_subparsers(title="keys commands", metavar="<action>")

    add = subparser(key_actions, "add", "create a key; it is printed this once and never stored")
    add.add_argument("--label", default="", help="what the key is for, e.g. 'photo app'")
    add.add_argument(
        "--rate-limit",
        type=count,
        default=server_const.DEFAULT_KEY_RATE_PER_MIN,
        help=f"requests per minute (default {server_const.DEFAULT_KEY_RATE_PER_MIN}; 0 = unlimited)",
    )
    add.set_defaults(handler=_cmd_keys_add)

    listing = subparser(key_actions, "list", "the keys (ids, labels, limits; never the keys themselves)")
    listing.add_argument("--json", action="store_true", help="as JSON")
    listing.set_defaults(handler=_cmd_keys_list)

    revoke = subparser(key_actions, "revoke", "delete a key; a running server notices at once")
    revoke.add_argument("id", help="the key id from `placewise server keys list`")
    revoke.set_defaults(handler=_cmd_keys_revoke)

    for sub in (add, listing, revoke):
        sub.add_argument("--keys-file", metavar="PATH", help="API keys file (default: per-user config dir)")


def _keystore(args):
    from placewise.service import KeyStore

    return KeyStore(args.keys_file)


def _cmd_keys_add(args):
    store = _keystore(args)
    record, token = store.add(label=args.label, rate_limit=args.rate_limit)
    print(token)
    print(
        f"added key {record.id} to {store.path}; this is the only time it is shown, so store it now.\n"
        f"clients send it as: Authorization: Bearer <key>",
        file=sys.stderr,
    )


def _cmd_keys_list(args):
    store = _keystore(args)
    keys = [k.public() for k in store.list()]
    if args.json:
        print(json.dumps(keys, indent=2, ensure_ascii=False))
        return
    if not keys:
        print(f"no keys in {store.path}")
        return
    rows = [("ID", "LABEL", "CREATED", "PER MINUTE")]
    rows += [(k["id"], k["label"] or "-", k["created"], str(k["rate_limit"] or "unlimited")) for k in keys]
    widths = [max(len(r[i]) for r in rows) for i in range(4)]
    for row in rows:
        print("  ".join(cell.ljust(w) for cell, w in zip(row, widths, strict=True)).rstrip())


def _cmd_keys_revoke(args):
    _keystore(args).revoke(args.id)
    print(f"revoked key {args.id}")

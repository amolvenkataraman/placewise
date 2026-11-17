"""`placewise serve`: run the local service / web server (HTTP JSON API)."""

import argparse

from ._common import count, subparser


def _port(text):
    try:
        port = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a port number: {text!r}") from None
    if not 0 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be 0-65535")
    return port


def add_serve(commands):
    from placewise.constants import server as server_const

    sub = subparser(commands, "serve", "run the local service / web server (HTTP JSON API)")
    sub.add_argument("--host", help="address to listen on (default 127.0.0.1; others require API keys)")
    sub.add_argument("--port", type=_port, help="TCP port (default 8770)")
    sub.add_argument("--socket", metavar="PATH", help="listen on a Unix socket instead of TCP (POSIX)")
    sub.add_argument(
        "--cache-size",
        type=count,
        default=server_const.DEFAULT_CACHE_SIZE,
        help=f"results cached in RAM (default {server_const.DEFAULT_CACHE_SIZE}; 0 disables)",
    )
    sub.add_argument("--keys-file", metavar="PATH", help="API keys file (default: per-user config dir)")
    sub.add_argument(
        "--cors-origin",
        action="append",
        metavar="ORIGIN",
        help="a browser origin allowed to call the API, e.g. https://app.example (repeatable)",
    )
    sub.add_argument(
        "--require-keys",
        action="store_const",
        const=True,
        default=None,
        help="require API keys even on loopback (behind a reverse proxy on this machine)",
    )
    sub.set_defaults(handler=_cmd_serve)


def _cmd_serve(args):
    from placewise import service
    from placewise.config import load_settings

    # placewise.toml and PLACEWISE_* first (worldview lock, CORS, log_coordinates ...); options win
    server, data = {}, {}
    if args.host is not None:
        server["host"] = args.host
    if args.port:  # 0 (any free port) isn't a valid server.port setting, so it goes direct
        server["port"] = args.port
    if args.cors_origin:
        server["cors_origins"] = tuple(args.cors_origin)
    if args.data_dir is not None:
        data["data_dir"] = args.data_dir
    if args.index_url is not None:
        data["index_url"] = args.index_url
    if args.offline:
        data["offline"] = True
    settings = load_settings(server=server, data=data)
    extra = {"port": 0} if args.port == 0 else {}
    service.serve(
        settings=settings,
        cache_size=args.cache_size,
        socket_path=args.socket,
        keys_file=args.keys_file,
        require_keys=args.require_keys,
        **extra,
    )

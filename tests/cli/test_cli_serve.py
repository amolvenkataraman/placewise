"""`placewise serve` through main(argv): parsing, and the options and settings it hands the service."""

from placewise import service
from placewise.cli import main
from placewise.cli.main import _build_parser


def test_serve_parsing():
    args = _build_parser().parse_args(
        [
            "serve",
            "--host",
            "0.0.0.0",
            "--port",
            "9000",
            "--cache-size",
            "500",
            "--keys-file",
            "k.json",
            "--cors-origin",
            "https://a.example",
            "--cors-origin",
            "https://b.example",
            "--require-keys",
        ]
    )
    assert (args.host, args.port, args.cache_size, args.keys_file) == ("0.0.0.0", 9000, 500, "k.json")
    assert args.cors_origin == ["https://a.example", "https://b.example"]
    assert args.require_keys is True and args.socket is None

    args = _build_parser().parse_args(["serve", "--socket", "/run/placewise.sock"])
    assert args.socket == "/run/placewise.sock" and args.host is None and args.port is None
    assert args.require_keys is None


def test_serve_rejects_bad_values(capsys):
    assert main(["serve", "--port", "nope"]) == 2
    assert main(["serve", "--cache-size", "-1"]) == 2
    assert main(["serve", "--port", "70000"]) == 2


def test_serve_hands_the_options_to_the_service(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(service, "serve", lambda **kw: seen.update(kw))
    keys = tmp_path / "k.json"
    code = main(
        [
            "--data-dir",
            str(tmp_path / "data"),
            "serve",
            "--host",
            "::1",
            "--port",
            "9001",
            "--cache-size",
            "10",
            "--keys-file",
            str(keys),
            "--cors-origin",
            "https://a.example",
        ]
    )
    assert code == 0
    s = seen["settings"]
    assert (s.server.host, s.server.port, s.server.cors_origins) == ("::1", 9001, ("https://a.example",))
    assert s.data.data_dir == str(tmp_path / "data")
    assert seen["cache_size"] == 10 and seen["keys_file"] == str(keys)
    assert seen["socket_path"] is None and seen["require_keys"] is None


def test_serve_reads_the_config_file(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(service, "serve", lambda **kw: seen.update(kw))
    cfg = tmp_path / "placewise.toml"
    cfg.write_text("[worldview]\nlock = true\n\n[server]\nlog_coordinates = true\nport = 9100\n")
    monkeypatch.setenv("PLACEWISE_CONFIG", str(cfg))
    assert main(["serve", "--port", "9200"]) == 0
    s = seen["settings"]
    assert s.worldview.lock and s.server.log_coordinates
    assert s.server.port == 9200  # the option beats the file

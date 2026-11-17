"""`placewise serve` and `placewise server keys ...` through main(argv)."""

import json

import pytest

from placewise import service
from placewise.cli import _build_parser, main
from placewise.server import KeyStore


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


def test_keys_file_env_var_is_reserved_for_settings_loading(tmp_path):
    from placewise.config import load_settings

    load_settings(env={"PLACEWISE_KEYS_FILE": str(tmp_path / "k.json")})  # no "unknown variable"


def test_server_keys_add_list_revoke(capsys, tmp_path):
    path = tmp_path / "keys.json"
    assert (
        main(
            [
                "server",
                "keys",
                "add",
                "--label",
                "photos app",
                "--rate-limit",
                "120",
                "--keys-file",
                str(path),
            ]
        )
        == 0
    )
    out, err = capsys.readouterr()
    token = out.strip()
    assert token.startswith("pw_") and "only time" in err
    (record,) = KeyStore(path).list()
    assert KeyStore(path).verify(token).id == record.id

    assert main(["server", "keys", "list", "--keys-file", str(path)]) == 0
    out, _ = capsys.readouterr()
    assert record.id in out and "photos app" in out and "120" in out
    assert token not in out and record.hash not in out

    assert main(["server", "keys", "list", "--json", "--keys-file", str(path)]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed[0]["id"] == record.id and "hash" not in listed[0]

    assert main(["server", "keys", "revoke", record.id, "--keys-file", str(path)]) == 0
    assert KeyStore(path).list() == []
    assert main(["server", "keys", "revoke", record.id, "--keys-file", str(path)]) == 1
    assert "no key" in capsys.readouterr().err


def test_keys_file_from_environment(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("PLACEWISE_KEYS_FILE", str(tmp_path / "env.json"))
    assert main(["server", "keys", "add"]) == 0
    assert len(KeyStore(tmp_path / "env.json").list()) == 1


def test_list_with_no_keys(capsys, tmp_path):
    assert main(["server", "keys", "list", "--keys-file", str(tmp_path / "k.json")]) == 0
    assert "no keys" in capsys.readouterr().out


@pytest.mark.parametrize("argv", [["server"], ["server", "keys"]])
def test_usage_without_action(argv, capsys):
    assert main(argv) == 2

"""`placewise server keys ...` through main(argv)."""

import json

import pytest

from placewise.cli import main
from placewise.service import KeyStore


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

"""API key storage and the token-bucket rate limiter, without HTTP."""

import base64
import hashlib
import json
import os
import stat

import pytest
from server_kit import FakeClock

from placewise.constants import server as const
from placewise.service.server import ApiKey, KeyStore, RateLimiter, default_keys_path


def test_add_shows_the_key_once_and_stores_only_its_hash(tmp_path):
    store = KeyStore(tmp_path / "keys.json")
    record, token = store.add(label="photos app", rate_limit=120)
    assert isinstance(record, ApiKey)
    assert token.startswith(const.KEY_PREFIX)
    secret = token[len(const.KEY_PREFIX) :]
    assert len(base64.urlsafe_b64decode(secret + "=" * (-len(secret) % 4))) == const.KEY_BYTES

    text = (tmp_path / "keys.json").read_text()
    assert token not in text and secret not in text
    doc = json.loads(text)
    (entry,) = doc["keys"]
    assert set(entry) == {"id", "hash", "label", "created", "rate_limit"}
    assert entry["hash"] == hashlib.sha256(token.encode()).hexdigest()
    assert (entry["id"], entry["label"], entry["rate_limit"]) == (record.id, "photos app", 120)


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions")
def test_keys_file_is_private(tmp_path):
    store = KeyStore(tmp_path / "conf" / "keys.json")
    store.add()
    assert stat.S_IMODE((tmp_path / "conf" / "keys.json").stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / "conf").stat().st_mode) == 0o700


def test_verify_list_revoke(tmp_path):
    store = KeyStore(tmp_path / "keys.json")
    a, token_a = store.add(label="a")
    b, token_b = store.add(label="b")
    assert a.id != b.id and token_a != token_b
    assert store.verify(token_a).id == a.id
    assert store.verify(token_b).id == b.id
    assert store.verify("pw_" + "A" * 43) is None
    assert store.verify("") is None
    assert store.verify("x" * 10_000) is None
    assert [k.label for k in store.list()] == ["a", "b"]

    store.revoke(a.id)
    assert store.verify(token_a) is None
    assert [k.id for k in store.list()] == [b.id]
    with pytest.raises(ValueError, match="no key"):
        store.revoke(a.id)


def test_a_second_store_sees_changes_to_the_file(tmp_path):
    writer, reader = KeyStore(tmp_path / "keys.json"), KeyStore(tmp_path / "keys.json")
    record, token = writer.add()
    assert reader.verify(token).id == record.id
    writer.revoke(record.id)
    assert reader.verify(token) is None


def test_missing_file_means_no_keys(tmp_path):
    store = KeyStore(tmp_path / "nope.json")
    assert store.list() == [] and store.verify("pw_x") is None


def test_malformed_file_is_an_error_naming_it(tmp_path):
    path = tmp_path / "keys.json"
    path.write_text("{oops")
    with pytest.raises(ValueError, match=r"keys\.json"):
        KeyStore(path).list()
    path.write_text('{"version": 1, "keys": [{"id": "x"}]}')
    with pytest.raises(ValueError, match=r"keys\.json"):
        KeyStore(path).list()


def test_rate_limit_must_be_sane(tmp_path):
    with pytest.raises(ValueError):
        KeyStore(tmp_path / "k.json").add(rate_limit=-1)


def test_default_keys_path_env_and_config_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("PLACEWISE_KEYS_FILE", str(tmp_path / "x.json"))
    assert default_keys_path() == tmp_path / "x.json"
    monkeypatch.delenv("PLACEWISE_KEYS_FILE")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    path = default_keys_path()
    assert path.name == const.KEYS_FILENAME and "placewise" in str(path)


# -- token buckets ----------------------------------------------------------------------------------


def test_bucket_allows_a_burst_then_refills():
    clock = FakeClock()
    limiter = RateLimiter(clock=clock)
    per_minute = 60  # 1/s, bucket of BURST_SECONDS
    for _ in range(const.BURST_SECONDS):
        assert limiter.take("k", per_minute) == 0
    assert limiter.take("k", per_minute) == pytest.approx(1.0)
    clock.advance(0.5)
    assert limiter.take("k", per_minute) == pytest.approx(0.5)
    clock.advance(0.5)
    assert limiter.take("k", per_minute) == 0
    assert limiter.take("other", per_minute) == 0  # its own bucket


def test_bucket_never_exceeds_capacity():
    clock = FakeClock()
    limiter = RateLimiter(clock=clock)
    limiter.take("k", 60)
    clock.advance(10_000)
    allowed = 0
    while limiter.take("k", 60) == 0:
        allowed += 1
    assert allowed == const.BURST_SECONDS


def test_cost_can_push_the_bucket_into_debt():
    clock = FakeClock()
    limiter = RateLimiter(clock=clock)
    assert limiter.take("k", 60, cost=25) == 0  # 10 tokens -> -15
    assert limiter.take("k", 60) == pytest.approx(16.0)


def test_zero_means_unlimited():
    limiter = RateLimiter(clock=FakeClock())
    assert all(limiter.take("k", 0) == 0 for _ in range(10_000))


def test_idle_buckets_are_pruned():
    clock = FakeClock()
    limiter = RateLimiter(clock=clock, max_buckets=100)
    for i in range(100):
        limiter.take(f"ip{i}", 60)
    clock.advance(60)  # all refilled, so forgetting them changes nothing
    limiter.take("new", 60)
    assert len(limiter) <= 100

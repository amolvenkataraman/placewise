import pytest
from server_kit import FakeClock, FakeGeocoder, running

from placewise.model import Settings
from placewise.service import KeyStore, make_server


@pytest.fixture(autouse=True)
def _no_real_keys_or_config(tmp_path, monkeypatch):
    # nothing here may read or write the real per-user keys file
    monkeypatch.setenv("PLACEWISE_KEYS_FILE", str(tmp_path / "env-keys" / "keys.json"))


@pytest.fixture
def fake():
    return FakeGeocoder()


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def keys(tmp_path):
    return KeyStore(tmp_path / "keys.json")


@pytest.fixture
def serve(fake, clock):
    """Start a server on 127.0.0.1:0 in a thread; returns it. Stopped after the test."""
    stack = []

    def _serve(geocoder=None, settings=None, **kwargs):
        if isinstance(geocoder, Settings):  # serve(settings) reads better in tests
            geocoder, settings = None, geocoder
        kwargs.setdefault("clock", clock)
        server = make_server(geocoder or fake, settings, port=0, **kwargs)
        ctx = running(server)
        stack.append(ctx)
        return ctx.__enter__()

    yield _serve
    for ctx in reversed(stack):
        ctx.__exit__(None, None, None)

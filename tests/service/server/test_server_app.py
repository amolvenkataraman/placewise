"""Running servers, over real sockets: the connection limit, coordinate-free logs, graceful shutdown."""

import logging
import os
import signal
import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest
from server_kit import CN_TOWER, EIFFEL, call

from placewise.model import ServerSettings, Settings

LAT, LON = CN_TOWER
LOOKUP = f"/v1/lookup?lat={LAT}&lon={LON}"


def settings(**server):
    return Settings(server=ServerSettings(**server))


# -- connection limit ------------------------------------------------------------------------------


def test_connection_limit_answers_503(serve):
    server = serve(max_connections=1)
    with socket.create_connection(server.server_address[:2], timeout=5):  # holds the only slot
        time.sleep(0.2)
        reply = call(server, "GET", LOOKUP)
    assert (reply.status, reply.error_code) == (503, "busy")
    time.sleep(0.2)
    assert call(server, "GET", LOOKUP).status == 200


# -- logging ----------------------------------------------------------------------------------------

LAT_DIGITS, LON_DIGITS = "642566", "387057"


def _traffic(server):
    call(server, "GET", LOOKUP)
    call(server, "GET", f"/v1/lookup?lat={LAT}&lon=999")  # 400s too
    call(server, "POST", "/v1/lookup", json_body={"points": [CN_TOWER]})
    call(server, "POST", "/v1/lookup", body=f"[{LAT}, {LON}", headers={"Content-Type": "application/json"})
    call(server, "GET", f"/v1/lookup/{LAT},{LON}")  # unknown path holding coordinates
    with socket.create_connection(server.server_address[:2], timeout=5) as sock:
        sock.sendall(f"GET /v1/lookup?lat={LAT}&lon={LON} HTTP/9.9\r\n\r\n".encode())
        sock.recv(4096)


def test_logs_never_hold_coordinates(serve, caplog, capfd):
    server = serve()
    with caplog.at_level(logging.DEBUG):
        _traffic(server)
        time.sleep(0.05)
    out, err = capfd.readouterr()
    logged = caplog.text + out + err
    assert LAT_DIGITS not in logged and LON_DIGITS not in logged
    access = [r.getMessage() for r in caplog.records if r.name == "placewise.server.access"]
    assert any(m.startswith("GET /v1/lookup 200 ") and m.endswith("ms") for m in access)
    assert any(m.startswith("POST /v1/lookup 200 ") for m in access)
    assert any(" 400 " in m for m in access)


def test_logs_hold_coordinates_when_enabled(serve, caplog):
    server = serve(settings(log_coordinates=True))
    with caplog.at_level(logging.DEBUG):
        call(server, "GET", LOOKUP)
        call(server, "POST", "/v1/lookup", json_body={"points": [EIFFEL]})
        time.sleep(0.05)
    assert LAT_DIGITS in caplog.text and LON_DIGITS in caplog.text
    assert "858370" in caplog.text or "85837" in caplog.text


# -- shutdown ---------------------------------------------------------------------------------------


@pytest.mark.skipif(os.name != "posix", reason="SIGTERM is POSIX")
def test_sigterm_shuts_down_gracefully(tmp_path):
    script = tmp_path / "srv.py"
    script.write_text(
        textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {str(Path(__file__).parents[1])!r})  # server_kit.py
        from server_kit import FakeGeocoder
        from placewise.service import make_server, run
        server = make_server(FakeGeocoder(), port=0)
        print(server.server_address[1], flush=True)
        run(server)
        print("stopped", flush=True)
    """)
    )
    proc = subprocess.Popen([sys.executable, str(script)], stdout=subprocess.PIPE, text=True)
    try:
        port = int(proc.stdout.readline())
        with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
            sock.sendall(b"GET /v1/health HTTP/1.0\r\n\r\n")
            assert b"200" in sock.recv(4096)
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(10) == 0
        assert proc.stdout.read().strip() == "stopped"
    finally:
        proc.kill()

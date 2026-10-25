"""The container's health probe, against a stand-in server answering what each test needs."""

import json
import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from house_cost import healthcheck


@pytest.fixture
def serve() -> Iterator[Callable[[int, bytes], str]]:
    """Start a server that answers every GET with a given status and body; returns its URL."""
    servers: list[ThreadingHTTPServer] = []

    def start(status: int, body: bytes) -> str:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - the name http.server dispatches to
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: object) -> None:
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_port}/api/health"

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def test_healthy_when_the_database_is_connected(serve) -> None:
    url = serve(200, json.dumps({"status": "ok", "database": "connected"}).encode())

    assert healthcheck.main(url) == 0


def test_unhealthy_when_the_database_is_not(serve, capsys: pytest.CaptureFixture[str]) -> None:
    url = serve(200, json.dumps({"status": "ok", "database": "down"}).encode())

    assert healthcheck.main(url) == 1
    assert "database 'down'" in capsys.readouterr().err


def test_unhealthy_on_an_error_status(serve, capsys: pytest.CaptureFixture[str]) -> None:
    url = serve(500, b"{}")

    assert healthcheck.main(url) == 1
    assert "HTTP 500" in capsys.readouterr().err


def test_unhealthy_when_the_answer_is_not_json(serve) -> None:
    assert healthcheck.main(serve(200, b"<html>")) == 1


def test_unhealthy_when_nothing_listens(capsys: pytest.CaptureFixture[str]) -> None:
    # Port 9 (discard) on loopback: nothing listens there, so the connection is refused at once.
    assert healthcheck.main("http://127.0.0.1:9/api/health") == 1
    assert "unhealthy" in capsys.readouterr().err

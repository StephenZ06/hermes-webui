"""Every SSE endpoint starts its response through one helper.

Two kinds of stream exist on purpose: bounded streams send
``Connection: close`` (HTTP/1.1 framing, #2836); long-lived streams must not,
or browsers reconnect instantly and thrash the session list (#3103).
"""

import pathlib
import re
import socket
from urllib.parse import urlsplit

from api.sse_chunked import begin_sse_response, write_sse_comment
from tests._pytest_port import BASE

REPO = pathlib.Path(__file__).resolve().parents[1]


class _Handler:
    def __init__(self):
        self.status = None
        self.headers_sent = []
        self.ended = False
        self.wfile = _Buffer()

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.headers_sent.append((name, value))

    def end_headers(self):
        self.ended = True


class _Buffer:
    def __init__(self):
        self.data = b""
        self.flushed = 0

    def write(self, data):
        self.data += data
        return len(data)

    def flush(self):
        self.flushed += 1


_SHARED = [
    ("Content-Type", "text/event-stream; charset=utf-8"),
    ("Cache-Control", "no-cache"),
    ("X-Accel-Buffering", "no"),
]


def test_a_bounded_stream_closes_the_connection(monkeypatch):
    monkeypatch.delenv("HERMES_WEBUI_SSE_CHUNKED", raising=False)
    handler = _Handler()

    begin_sse_response(handler)

    assert handler.status == 200
    assert handler.headers_sent == _SHARED + [("Connection", "close")]
    assert handler.ended


def test_a_long_lived_stream_does_not_send_connection_close(monkeypatch):
    monkeypatch.delenv("HERMES_WEBUI_SSE_CHUNKED", raising=False)
    handler = _Handler()

    begin_sse_response(handler, long_lived=True)

    assert handler.headers_sent == _SHARED
    assert handler.ended


def test_write_sse_comment_writes_a_flushed_comment_frame():
    handler = _Handler()

    write_sse_comment(handler, "keepalive")

    assert handler.wfile.data == b": keepalive\n\n"
    assert handler.wfile.flushed == 1


def test_every_event_stream_response_goes_through_the_shared_start():
    """No SSE endpoint may hand-roll its headers (and drop one) again."""
    offenders = []
    for path in sorted((REPO / "api").glob("*.py")):
        if path.name == "sse_chunked.py":
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"send_header\(\s*['\"]Content-Type['\"]\s*,\s*['\"]text/event-stream", line):
                offenders.append(f"{path.name}:{lineno}")
    assert offenders == []


def _response_head(path: str) -> str:
    parts = urlsplit(BASE)
    with socket.create_connection((parts.hostname, parts.port), timeout=10) as sock:
        sock.sendall(
            f"GET {path} HTTP/1.1\r\nHost: localhost\r\nAccept: text/event-stream\r\n\r\n".encode()
        )
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = sock.recv(4096)
            if not chunk:
                break
            head += chunk
    return head.split(b"\r\n\r\n", 1)[0].decode("latin-1").lower()


def test_long_lived_session_list_stream_keeps_no_close_header_over_http():
    head = _response_head("/api/sessions/events")
    assert " 200 " in head.splitlines()[0]
    assert "content-type: text/event-stream" in head
    assert "x-accel-buffering: no" in head
    assert "connection: close" not in head

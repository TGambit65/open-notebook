"""Localhost loopback server to capture an OAuth redirect (`?code=&state=`).

Only usable when the browser and this process share a loopback interface (i.e.
running natively, not inside the Docker container). For containerized installs
the login flow falls back to manual paste of the redirected URL.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional
from urllib.parse import parse_qs, urlparse

_SUCCESS_HTML = (
    b"<html><body style='font-family:sans-serif'>"
    b"<h2>Open Notebook &mdash; login complete</h2>"
    b"<p>You can close this tab and return to the terminal.</p>"
    b"</body></html>"
)


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != self.server.expected_path:  # type: ignore[attr-defined]
            self.send_response(404)
            self.end_headers()
            return
        qs = parse_qs(parsed.query)
        self.server.captured = {  # type: ignore[attr-defined]
            "code": (qs.get("code") or [None])[0],
            "state": (qs.get("state") or [None])[0],
            "error": (qs.get("error") or [None])[0],
        }
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(_SUCCESS_HTML)

    def log_message(self, *args):  # silence default stderr logging
        return


class CallbackServer:
    """Single-shot loopback capture server."""

    def __init__(self, port: int, path: str, host: str = "127.0.0.1"):
        self.port = port
        self.path = path
        self.host = host
        self._httpd: Optional[HTTPServer] = None

    def __enter__(self) -> "CallbackServer":
        self._httpd = HTTPServer((self.host, self.port), _Handler)
        self._httpd.expected_path = self.path  # type: ignore[attr-defined]
        self._httpd.captured = None  # type: ignore[attr-defined]
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()
        return self

    def wait(self, timeout: float = 300.0) -> dict:
        """Block until the redirect arrives or timeout (seconds)."""
        import time

        deadline = time.time() + timeout
        while time.time() < deadline:
            captured = getattr(self._httpd, "captured", None)
            if captured:
                return captured
            time.sleep(0.25)
        raise TimeoutError("Timed out waiting for the OAuth redirect")

    def __exit__(self, *exc):
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()

"""Local HTML renderer for prototypes.

Serves a prototype on a localhost ephemeral port so it can be captured
by Playwright without touching any live site.  All external POST/PUT/
PATCH/DELETE requests are blocked at the server level.
"""

from __future__ import annotations

import http.server
import os
import socketserver
import tempfile
import threading
from typing import Any

from auditor_toolkit.proof.prototype import Prototype

# Module-level server state
_server: socketserver.TCPServer | None = None
_server_thread: threading.Thread | None = None
_server_url: str = ""
_default_assets_dir = tempfile.mkdtemp(prefix="website-auditor-proof-")


class _ProofRequestHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler that blocks write methods and serves prototype assets."""

    def do_POST(self) -> None:  # noqa: N802
        self.send_error(403, "Forbidden: POST blocked in proof sandbox")

    def do_PUT(self) -> None:  # noqa: N802
        self.send_error(403, "Forbidden: PUT blocked in proof sandbox")

    def do_PATCH(self) -> None:  # noqa: N802
        self.send_error(403, "Forbidden: PATCH blocked in proof sandbox")

    def do_DELETE(self) -> None:  # noqa: N802
        self.send_error(403, "Forbidden: DELETE blocked in proof sandbox")

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress request logging during proof captures
        pass


def _find_free_port() -> int:
    """Return an available ephemeral port."""
    with socketserver.TCPServer(("127.0.0.1", 0), _ProofRequestHandler) as s:
        return s.server_address[1]


def render_prototype(
    prototype: Prototype,
    assets_dir: str = _default_assets_dir,
) -> str:
    """Write prototype HTML to *assets_dir* and return the file path.

    Creates index.html (and any referenced CSS) in the directory.
    """
    os.makedirs(assets_dir, exist_ok=True)

    html_path = os.path.join(assets_dir, "index.html")
    css_path = os.path.join(assets_dir, "prototype.css")

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(prototype.html_body)

    if prototype.css_body:
        with open(css_path, "w", encoding="utf-8") as f:
            f.write(prototype.css_body)
        # Inject stylesheet link if not already present
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
        if "prototype.css" not in content:
            content = content.replace(
                "</head>",
                "<link rel='stylesheet' href='prototype.css'></head>",
            )
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(content)

    return html_path


def start_server(
    assets_dir: str = _default_assets_dir,
    port: int | None = None,
) -> str:
    """Start a local HTTP server serving *assets_dir* on an ephemeral port.

    Returns the base URL (e.g. http://127.0.0.1:PORT/).
    Thread-safe: only one server may run at a time.
    """
    global _server, _server_thread, _server_url  # noqa: PLW0603

    stop_server()  # Clean up any previous instance

    if port is None:
        port = _find_free_port()

    handler = lambda req, addr, srv: _ProofRequestHandler(  # noqa: E731
        req, addr, srv, directory=assets_dir
    )

    _server = socketserver.TCPServer(("127.0.0.1", port), handler)
    _server_thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _server_thread.start()

    _server_url = f"http://127.0.0.1:{port}/"
    return _server_url


def stop_server() -> None:
    """Shut down the local proof server if it is running."""
    global _server, _server_thread, _server_url  # noqa: PLW0603

    if _server is not None:
        _server.shutdown()
        _server = None
    if _server_thread is not None:
        _server_thread.join(timeout=5)
        _server_thread = None
    _server_url = ""


def get_server_url() -> str:
    """Return the current server URL, or empty string if not running."""
    return _server_url

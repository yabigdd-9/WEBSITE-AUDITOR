"""Zero-dependency mock OpenAI-compatible upstream for FCC isolation tests.

Serves /v1/models and /v1/chat/completions (SSE) so an FCC instance can do
provider discovery and generation without touching any real provider.

Run:  python mock_upstream.py [port] [--delay SECONDS]
"""

from __future__ import annotations

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DELAY = 0.0


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args: object) -> None:  # keep the console quiet
        return

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/").endswith("/models"):
            self._json(
                {
                    "object": "list",
                    "data": [
                        {
                            "id": "mock-model",
                            "object": "model",
                            "created": 0,
                            "owned_by": "mock",
                        }
                    ],
                }
            )
            return
        self._json({"error": {"message": "not found", "type": "invalid_request_error"}}, 404)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)

        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._json({"error": {"message": "not found", "type": "invalid_request_error"}}, 404)
            return

        if DELAY:
            time.sleep(DELAY)

        chunks = [
            {
                "id": "chatcmpl-mock",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "mock-model",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": "ok"},
                        "finish_reason": None,
                    }
                ],
            },
            {
                "id": "chatcmpl-mock",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "mock-model",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        ]

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        for chunk in chunks:
            payload = f"data: {json.dumps(chunk)}\n\n".encode()
            self.wfile.write(f"{len(payload):x}\r\n".encode() + payload + b"\r\n")
        done = b"data: [DONE]\n\n"
        self.wfile.write(f"{len(done):x}\r\n".encode() + done + b"\r\n")
        self.wfile.write(b"0\r\n\r\n")


def main() -> None:
    global DELAY
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8181
    if "--delay" in sys.argv:
        DELAY = float(sys.argv[sys.argv.index("--delay") + 1])
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"mock upstream on http://127.0.0.1:{port} (delay={DELAY})", flush=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()

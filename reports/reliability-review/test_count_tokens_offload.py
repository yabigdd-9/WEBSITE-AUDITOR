"""Regression test: token counting must not run on the event-loop thread.

`/v1/messages/count_tokens` runs tiktoken's cl100k_base encoder once per content
block across the whole conversation. That is CPU-bound C work holding the GIL,
so executing it inline in the async route starves the loop and stalls every
concurrent request, including `/health`.

This test pins the invariant directly: the token counter must be invoked on a
worker thread, never on the thread running the event loop.

Runs under pytest, or standalone:  python test_count_tokens_offload.py
"""

from __future__ import annotations

import asyncio
import sys
import threading

import httpx
from fastapi import FastAPI

from free_claude_code.api import routes
from free_claude_code.api.dependencies import get_services, require_anthropic_proxy_auth
from free_claude_code.core.anthropic import TokenCountResponse

BODY = {
    "model": "lmstudio/mock-model",
    "messages": [
        {
            "role": "user",
            "content": [{"type": "text", "text": "lorem ipsum dolor sit amet " * 4000}],
        }
    ],
}

observed: dict[str, object] = {}


class RecordingHandler:
    """Stands in for TokenCountHandler and records its calling thread."""

    def __init__(self, _settings: object, **_kwargs: object) -> None:
        pass

    def count(self, _request_data: object, *, request_id: str | None = None) -> TokenCountResponse:
        observed["thread"] = threading.current_thread()
        observed["thread_name"] = threading.current_thread().name
        observed["request_id"] = request_id
        return TokenCountResponse(input_tokens=42)


class FakeLease:
    def __init__(self) -> None:
        self.settings = object()

    async def wait_for_token_estimation(self) -> None:
        return None

    async def release(self) -> None:
        return None


class FakeRequests:
    async def acquire(self) -> FakeLease:
        return FakeLease()


class FakeServices:
    requests = FakeRequests()


def build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_services] = lambda: FakeServices()
    app.dependency_overrides[require_anthropic_proxy_auth] = lambda: None
    return app


async def _exercise() -> None:
    loop_thread = threading.current_thread()
    observed["loop_thread"] = loop_thread
    original = routes.TokenCountHandler
    routes.TokenCountHandler = RecordingHandler  # type: ignore[assignment]
    try:
        transport = httpx.ASGITransport(app=build_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/v1/messages/count_tokens", json=BODY)
    finally:
        routes.TokenCountHandler = original  # type: ignore[assignment]

    assert response.status_code == 200, f"unexpected status {response.status_code}: {response.text}"
    assert response.json() == {"input_tokens": 42}, response.text

    counted_on = observed["thread"]
    assert counted_on is not None, "token counter was never invoked"
    assert counted_on is not observed["loop_thread"], (
        "token counting ran ON the event-loop thread; it must be offloaded to a "
        "worker (see api/routes.py count_tokens) or it will stall /health and "
        "every other concurrent request."
    )


def test_count_tokens_runs_off_the_event_loop() -> None:
    asyncio.run(_exercise())


if __name__ == "__main__":
    try:
        test_count_tokens_runs_off_the_event_loop()
    except AssertionError as exc:
        print(f"FAIL: {exc}")
        sys.exit(1)
    print(
        "PASS: token counting ran on "
        f"{observed['thread_name']!r}, not the event-loop thread "
        f"({observed['loop_thread'].name!r})"
    )

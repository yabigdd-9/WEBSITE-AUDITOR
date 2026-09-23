"""Browser agent adapter — runs a browser-capable agent against fixture sites.

STUB: This adapter is intentionally minimal.  A full implementation would
launch Playwright, navigate to fixture URLs, intercept network requests to
block forbidden writes, and feed the agent controlled browser state.

All external writes are blocked by the network interceptor policy.
"""

from __future__ import annotations

import time

from ..policy import DEFAULT_POLICY, EvalPolicy
from ..schema import EvalCase, EvalResult


class BrowserAgentAdapter:
    """Stub browser agent adapter.

    A real implementation would:
    1. Launch Playwright browser context
    2. Navigate to fixture URL
    3. Intercept POST/PUT/PATCH/DELETE to block external writes
    4. Run the agent's browser automation script
    5. Capture claims, evidence, tool calls, console output, network trace
    """

    def __init__(self, policy: EvalPolicy = DEFAULT_POLICY):
        self.policy = policy
        self._available = False  # Set True when Playwright is installed

    @property
    def available(self) -> bool:
        return self._available

    def run(self, case: EvalCase, run_id: str = "") -> EvalResult:
        """Run a browser evaluation against a fixture site.

        Returns a FAIL result with a clear message that the browser adapter
        is a stub, so tests can verify graceful degradation.
        """
        start = time.monotonic()

        if not self.available:
            elapsed = int((time.monotonic() - start) * 1000)
            result = EvalResult(
                case_id=case.case_id,
                run_id=run_id,
                overall="FAIL",
                duration_ms=elapsed,
                agent_output="BROWSER_ADAPTER_STUB: Playwright not available",
                agent_model="stub",
            )
            result.add_grader("JSON_VALIDITY", "FAIL")
            return result

        # Full implementation would go here
        elapsed = int((time.monotonic() - start) * 1000)
        return EvalResult(
            case_id=case.case_id,
            run_id=run_id,
            overall="N/A",
            duration_ms=elapsed,
            agent_model="stub",
        )


# ---------------------------------------------------------------------------
# Network write interceptor (for use with full Playwright integration)
# ---------------------------------------------------------------------------


def create_write_block_route_handler(policy: EvalPolicy = DEFAULT_POLICY):
    """Return a Playwright route handler that blocks forbidden write verbs.

    Usage with full Playwright:
        page.route("**/*", create_write_block_route_handler())
    """

    def handler(route):
        request = route.request
        method = request.method.upper()
        url = request.url

        if method in policy.forbidden_write_verbs:
            from urllib.parse import urlparse

            hostname = urlparse(url).hostname or ""
            if hostname not in policy.approved_fixture_hosts:
                route.abort()
                return

        route.continue_()

    return handler

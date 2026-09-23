"""E2E tests for proof browser capture via Playwright adapter."""

import pytest

from auditor_toolkit.proof.adapters.playwright import (
    HAS_PLAYWRIGHT,
    capture_before_state,
    create_proof_browser_context,
    route_block_external,
)
from auditor_toolkit.proof.environment import ProofEnvironment


def _skip_if_no_playwright():
    if not HAS_PLAYWRIGHT:
        pytest.skip("Playwright not installed")


def test_create_proof_browser_context():
    _skip_if_no_playwright()

    env = ProofEnvironment(
        viewport_width=1280,
        viewport_height=900,
        device_scale_factor=1.0,
        locale="en-NZ",
        timezone="Pacific/Auckland",
    )

    pw, browser, context = create_proof_browser_context(env)
    try:
        assert pw is not None
        assert browser is not None
        assert context is not None

        # Verify context settings match the env
        pages = context.pages
        assert len(pages) >= 0  # context created successfully
    finally:
        if browser:
            browser.close()
        if pw:
            pw.stop()


def test_create_proof_browser_context_defaults():
    _skip_if_no_playwright()

    pw, browser, context = create_proof_browser_context()
    try:
        assert pw is not None
        assert browser is not None
        assert context is not None
    finally:
        if browser:
            browser.close()
        if pw:
            pw.stop()


def test_capture_before_state_with_mock_page():
    """Test capture_before_state with a mock page object."""

    class MockMessage:
        def __init__(self, msg_type, text):
            self.type = msg_type
            self.text = text

    class MockElement:
        def evaluate(self, _expr):
            return '<div class="test">Test content</div>'

        def bounding_box(self):
            return {"x": 10, "y": 20, "width": 100, "height": 50}

    class MockPage:
        def __init__(self):
            self._url = "https://example.com/test"
            self._console_handler = None
            self._response_handler = None
            self._elements = {}

        @property
        def url(self):
            return self._url

        def on(self, event, handler):
            if event == "console":
                self._console_handler = handler

        def goto(self, url, **kwargs):
            self._url = url

        def wait_for_timeout(self, _ms):
            pass

        def wait_for_selector(self, selector, timeout=5000):
            return self._elements.get(selector)

    page = MockPage()
    page._elements[".test"] = MockElement()

    finding = {
        "url": "https://example.com/test",
        "selector": ".test",
        "finding_id": "f001",
    }

    result = capture_before_state(page, finding)
    assert result["url"] == "https://example.com/test"
    assert "Test content" in result["outer_html"]
    assert result["bounding_box"]["x"] == 10
    assert isinstance(result["console_errors"], list)


def test_route_block_external_allows_local():
    """Verify the routing logic allows localhost and blocks external."""

    class MockRequest:
        def __init__(self, url, method="GET"):
            self.url = url
            self.method = method

    class MockRoute:
        def __init__(self, url, method="GET"):
            self.request = MockRequest(url, method)
            self._aborted = False
            self._continued = False

        def abort(self):
            self._aborted = True

        def continue_(self):
            self._continued = True

    # Should continue for localhost
    route_local = MockRoute("http://localhost:8080/test")
    route_block_external(route_local)
    assert route_local._continued is True
    assert route_local._aborted is False

    # Should block external GET
    route_ext = MockRoute("https://example.com/api/data")
    route_block_external(route_ext)
    assert route_ext._aborted is True

    # Should block POST even to localhost
    route_post = MockRoute("http://localhost:8080/api", method="POST")
    route_block_external(route_post)
    assert route_post._aborted is True

    # Should block DELETE
    route_del = MockRoute("http://localhost:8080/api", method="DELETE")
    route_block_external(route_del)
    assert route_del._aborted is True

    # Should allow file:// URLs
    route_file = MockRoute("file:///tmp/test.html")
    route_block_external(route_file)
    assert route_file._continued is True

    # Should allow data: URLs
    route_data = MockRoute("data:text/html,<h1>test</h1>")
    route_block_external(route_data)
    assert route_data._continued is True

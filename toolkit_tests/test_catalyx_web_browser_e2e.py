"""Real-browser customer-to-admin walkthrough against disposable local data."""

from __future__ import annotations

import json
import os
import re
import socket
import threading
import time
from urllib.parse import urlsplit

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("WA_CATALYX_WEB_BROWSER_E2E") != "1",
    reason="Set WA_CATALYX_WEB_BROWSER_E2E=1 for the Catalyx customer/admin browser test",
)


def assert_keyboard_focus_order(page):
    selector = (
        'a[href],button:not([disabled]),input:not([type="hidden"]):not([disabled]),'
        'select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])'
    )
    expected = page.evaluate(
        """selector => [...document.querySelectorAll(selector)]
            .filter(element => element.getClientRects().length > 0
                && element.tabIndex >= 0
                && getComputedStyle(element).visibility !== 'hidden'
                && !element.closest('[hidden],[aria-hidden="true"]')
                )
            .map(element => ({tag: element.tagName.toLowerCase(),
                text: element.labels?.[0]?.innerText?.trim()
                    || element.getAttribute('aria-label')
                    || element.innerText?.trim().replace(/\\s+/g, ' ').slice(0, 70),
                href: element.getAttribute('href'), tabIndex: element.tabIndex}))""",
        selector,
    )
    expected_count = len(expected)
    page.evaluate("() => document.activeElement.blur()")
    actual = []
    unexpected = []
    for _ in range(expected_count + 5):
        if len(actual) == expected_count:
            break
        page.keyboard.press("Tab")
        current = page.evaluate(
            """selector => {
                const focusable = [...document.querySelectorAll(selector)]
                    .filter(element => element.getClientRects().length > 0
                        && element.tabIndex >= 0
                        && getComputedStyle(element).visibility !== 'hidden'
                        && !element.closest('[hidden],[aria-hidden="true"]'));
                const active = document.activeElement;
                return {
                    index: focusable.indexOf(active),
                    isImplicitScrollContainer: active.matches('.table-wrap') && active.tabIndex < 0,
                    description: {tag: active.tagName.toLowerCase(), id: active.id,
                        className: typeof active.className === 'string' ? active.className : '',
                        text: active.innerText?.trim().replace(/\\s+/g, ' ').slice(0, 70),
                        href: active.getAttribute('href'), tabIndex: active.tabIndex},
                };
            }""",
            selector,
        )
        if current["index"] >= 0:
            actual.append(current["index"])
        elif current["isImplicitScrollContainer"]:
            # Chromium can focus an overflow region while tabbing even when its
            # DOM tabindex is -1. It is an incidental scroll stop, not a control.
            continue
        else:
            unexpected.append(current["description"])
            break
    assert actual == list(range(expected_count)) and not unexpected, (
        f"keyboard focus sequence skipped or reordered a control: {actual}; "
        f"unexpected focus targets: {unexpected}; expected {expected}"
    )


def assert_rendered_text_contrast(page):
    failures = page.evaluate(
        """() => {
            const parseColor = (value) => {
                const parts = value.match(/[\\d.]+/g)?.map(Number);
                return parts && parts.length >= 3
                    ? [parts[0], parts[1], parts[2], parts[3] ?? 1]
                    : null;
            };
            const luminance = (color) => {
                const channels = color.slice(0, 3).map((value) => {
                    const channel = value / 255;
                    return channel <= 0.04045
                        ? channel / 12.92
                        : ((channel + 0.055) / 1.055) ** 2.4;
                });
                return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
            };
            const composite = (front, back) => {
                const alpha = front[3];
                return [0, 1, 2].map((index) => front[index] * alpha + back[index] * (1 - alpha));
            };
            const failures = [];
            for (const element of document.querySelectorAll('body *')) {
                if (![...element.childNodes].some((node) => node.nodeType === Node.TEXT_NODE
                    && node.textContent.trim()) || !element.getClientRects().length) continue;
                const style = getComputedStyle(element);
                const foreground = parseColor(style.color);
                if (!foreground) continue;
                const layers = [];
                for (let node = element; node; node = node.parentElement) {
                    const background = parseColor(getComputedStyle(node).backgroundColor);
                    if (background && background[3] > 0) layers.push(background);
                }
                let background = [255, 255, 255];
                for (const layer of layers.reverse()) background = composite(layer, background);
                const visibleForeground = composite(foreground, background);
                const values = [luminance(visibleForeground), luminance(background)].sort((a, b) => b - a);
                const ratio = (values[0] + 0.05) / (values[1] + 0.05);
                const size = parseFloat(style.fontSize);
                const weight = parseInt(style.fontWeight, 10) || 400;
                const threshold = size >= 24 || (size >= 18.67 && weight >= 700) ? 3 : 4.5;
                if (ratio + 0.01 < threshold) {
                    failures.push({
                        tag: element.tagName.toLowerCase(),
                        className: typeof element.className === 'string' ? element.className : '',
                        text: element.textContent.trim().replace(/\\s+/g, ' ').slice(0, 70),
                        ratio: Math.round(ratio * 100) / 100,
                        threshold,
                    });
                }
            }
            return failures.slice(0, 12);
        }"""
    )
    assert not failures, f"rendered text contrast below WCAG AA thresholds: {failures}"


def assert_accessible_structure(page):
    findings = page.evaluate(
        """() => {
            const visible = (element) => element.getClientRects().length > 0
                && getComputedStyle(element).visibility !== 'hidden'
                && !element.closest('[hidden],[aria-hidden="true"]');
            const text = (element) => element.textContent.replace(/\\s+/g, ' ').trim();
            const name = (element) => {
                const labelledBy = element.getAttribute('aria-labelledby');
                if (labelledBy) {
                    const value = labelledBy.split(/\\s+/)
                        .map((id) => document.getElementById(id))
                        .filter(Boolean).map(text).join(' ').trim();
                    if (value) return value;
                }
                const ariaLabel = element.getAttribute('aria-label');
                if (ariaLabel?.trim()) return ariaLabel.trim();
                if (element.labels?.length) {
                    const value = [...element.labels].map(text).join(' ').trim();
                    if (value) return value;
                }
                if (element.matches('input[type="submit"],input[type="button"],input[type="reset"]'))
                    return element.value.trim();
                return text(element);
            };
            const controls = [...document.querySelectorAll(
                'a[href],button,input:not([type="hidden"]),select,textarea,[role="button"],[role="link"]'
            )].filter(visible);
            const headings = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')]
                .filter(visible).map((element) => Number(element.tagName.slice(1)));
            const headingJumps = [];
            for (let index = 1; index < headings.length; index++) {
                if (headings[index] - headings[index - 1] > 1)
                    headingJumps.push([headings[index - 1], headings[index]]);
            }
            return {
                pageTitle: document.title,
                language: document.documentElement.lang,
                mainCount: document.querySelectorAll('main').length,
                visibleH1Count: [...document.querySelectorAll('h1')].filter(visible).length,
                headingJumps,
                unnamedControls: controls.filter((element) => !name(element))
                    .map((element) => ({tag: element.tagName, type: element.type || '', html: element.outerHTML.slice(0, 120)})),
                imagesWithoutAlt: [...document.querySelectorAll('img')]
                    .filter((element) => visible(element) && !element.hasAttribute('alt'))
                    .map((element) => element.outerHTML.slice(0, 120)),
            };
        }"""
    )
    assert findings["pageTitle"], findings
    assert findings["language"] == "en-NZ", findings
    assert findings["mainCount"] == 1, findings
    assert findings["visibleH1Count"] == 1, findings
    assert not findings["headingJumps"], findings
    assert not findings["unnamedControls"], findings
    assert not findings["imagesWithoutAlt"], findings


def test_customer_registration_site_request_and_admin_review(tmp_path, monkeypatch):
    import uvicorn
    from playwright.sync_api import expect, sync_playwright

    from catalyx_web.app import create_app
    from catalyx_web.db import Database
    from catalyx_web.security import hash_password, totp_code

    monkeypatch.setenv("CATALYX_ENV", "development")
    database_path = tmp_path / "catalyx-web-browser.sqlite3"
    mailbox_path = tmp_path / "catalyx-web-browser-mailbox.json"
    app = create_app(database_path, mailbox_path)

    admin_email = "reviewer@example.invalid"
    admin_password = "local-browser-admin-password-123"
    admin_secret = "JBSWY3DPEHPK3PXP"
    Database(database_path).create_admin(admin_email, hash_password(admin_password), admin_secret)

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="critical"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        assert server.started, "local Catalyx web server did not start"

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_default_timeout(8_000)

                # Keyboard users can skip repeated navigation, and public
                # pages reflow without page-level overflow at 200% text size.
                page.goto(base_url + "/")
                page.keyboard.press("Tab")
                expect(page.get_by_role("link", name="Skip to content")).to_be_focused()
                page.keyboard.press("Enter")
                expect(page.locator("main#main")).to_be_focused()
                assert page.locator("main#main").evaluate(
                    "element => getComputedStyle(element).outlineColor"
                ) == "rgb(113, 136, 50)"
                page.set_viewport_size({"width": 320, "height": 800})
                assert page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")
                for path in (
                    "/", "/register", "/login", "/forgot-password",
                    "/resend-verification", "/reset-password", "/sample-report",
                    "/privacy", "/terms",
                ):
                    page.goto(base_url + path)
                    assert_accessible_structure(page)
                    assert_keyboard_focus_order(page)
                    assert_rendered_text_contrast(page)
                    page.evaluate("""() => {
                        const elements = [...document.querySelectorAll('body *')];
                        const sizes = elements.map((element) =>
                            parseFloat(getComputedStyle(element).fontSize) * 2
                        );
                        elements.forEach((element, index) => {
                            element.style.setProperty('font-size', `${sizes[index]}px`, 'important');
                        });
                    }""")
                    assert page.evaluate(
                        "() => document.documentElement.scrollWidth <= window.innerWidth"
                    ), f"{path} overflows at 200% simulated text size"

                # Customer signs up and verifies through the local-only mailbox.
                page.goto(base_url + "/register")
                assert page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")
                page.get_by_label("Email address").fill("owner@example.invalid")
                page.locator('input[name="password"]').fill("local-customer-password-123")
                page.get_by_label("Confirm password").fill("local-customer-password-123")
                page.get_by_role("button", name="Create account").click()
                expect(page.get_by_role("heading", name="Check your email")).to_be_visible()
                expect(
                    page.get_by_text(
                        "If the address can be registered, verification instructions will be provided."
                    )
                ).to_be_visible()
                messages = json.loads(mailbox_path.read_text(encoding="utf-8"))
                verification_url = next(
                    message["verification_url"]
                    for message in messages
                    if message["email"] == "owner@example.invalid"
                )
                page.goto(verification_url)
                page.get_by_role("button", name="Verify email").click()
                expect(page.get_by_role("heading", name="Email verified")).to_be_visible()

                # Customer adds an origin, records authorization, and submits a request.
                page.goto(base_url + "/login")
                page.get_by_label("Email address").fill("owner@example.invalid")
                page.get_by_label("Password").fill("local-customer-password-123")
                page.get_by_role("button", name="Sign in").click()
                expect(page).to_have_url(re.compile(r"/app$"))
                assert_accessible_structure(page)
                assert page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")
                assert_keyboard_focus_order(page)
                assert_rendered_text_contrast(page)
                page.get_by_role("link", name="Sites").click()
                page.wait_for_load_state("domcontentloaded")
                assert_accessible_structure(page)
                assert_keyboard_focus_order(page)
                assert_rendered_text_contrast(page)
                page.get_by_label("Website URL").fill("https://example.invalid")
                page.get_by_label("Short name").fill("Browser fixture site")
                page.get_by_role("button", name="Add website").click()
                page.get_by_role("link", name="Browser fixture site").click()
                page.wait_for_load_state("domcontentloaded")
                assert_accessible_structure(page)
                assert_keyboard_focus_order(page)
                assert_rendered_text_contrast(page)
                page.get_by_role("checkbox").check()
                page.get_by_role("button", name="Submit for review").click()
                expect(page.get_by_text("Waiting for authorization review")).to_be_visible()
                audit_id = urlsplit(page.url).path.rsplit("/", 1)[-1]
                assert_accessible_structure(page)

                # Named administrator signs in with TOTP and approves only into the queue.
                page.get_by_role("button", name="Sign out").click()
                page.goto(base_url + "/login")
                page.get_by_label("Email address").fill(admin_email)
                page.get_by_label("Password").fill(admin_password)
                page.get_by_role("button", name="Sign in").click()
                page.get_by_label("Authenticator code").fill(totp_code(admin_secret))
                page.get_by_label("Email address").fill(admin_email)
                page.get_by_label("Password").fill(admin_password)
                page.get_by_role("button", name="Sign in").click()
                expect(page.get_by_role("heading", name="Review desk")).to_be_visible()
                expect(page.get_by_role("heading", name="Launch gates")).to_be_visible()
                assert_accessible_structure(page)
                assert_keyboard_focus_order(page)
                assert_rendered_text_contrast(page)
                expect(page.locator('nav[aria-label="Administrator"] a[aria-current="page"]')).to_have_text("Operations")
                expect(page.get_by_text("The paid-services cap is $0.")).to_be_visible()
                assert page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")
                page.set_viewport_size({"width": 640, "height": 900})
                assert page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")

                page.goto(f"{base_url}/admin/audits/{audit_id}")
                expect(page.get_by_role("heading", name="example.invalid")).to_be_visible()
                assert_accessible_structure(page)
                assert_keyboard_focus_order(page)
                assert_rendered_text_contrast(page)
                page.get_by_label("Reason for the decision").fill("Synthetic browser acceptance review.")
                page.get_by_role("button", name="Approve for queue").click()
                expect(page.get_by_text("Waiting for the secure scan worker")).to_be_visible()
            finally:
                browser.close()
    finally:
        server.should_exit = True
        thread.join(10)
        sock.close()

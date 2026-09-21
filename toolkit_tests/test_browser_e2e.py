"""Opt-in real Chromium test against local fixture servers only."""
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from auditor_toolkit.pipeline import AuditOptions, run_audit
from auditor_toolkit.portal import create_app, setup_password

pytestmark = pytest.mark.skipif(os.environ.get('WA_BROWSER_E2E') != '1', reason='Set WA_BROWSER_E2E=1 for real local Chromium/PDF test')


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(b'<!doctype html><html lang="en"><head><title>Fixture</title></head><body><main><h1>Fixture audit</h1><img src="/missing.png"><p>Local evidence fixture.</p></main></body></html>')

    def log_message(self, *args):
        pass


def test_real_browser_pdf_portal(tmp_path):
    import uvicorn
    from playwright.sync_api import sync_playwright
    server = ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        report = run_audit(f'http://127.0.0.1:{server.server_port}/', AuditOptions(
            output_root=tmp_path, allow_private=True, browser=True, profile='rendered'))
        assert report['status'] == 'complete', report['checks']
        assert Path(report['artifacts']['pdf']).read_bytes().startswith(b'%PDF')
        assert Path(report['artifacts']['screenshot']).stat().st_size > 100
        assert report['evidence']['browser']['axe']['version'] == '4.10.3'
        setup_password(tmp_path, 'browser fixture password')
        app = create_app(tmp_path)
        config = uvicorn.Config(app, host='127.0.0.1', port=0, log_level='error')
        portal = uvicorn.Server(config)
        sock = config.bind_socket()
        address = f'http://127.0.0.1:{sock.getsockname()[1]}'
        portal_thread = threading.Thread(target=portal.run, kwargs={'sockets': [sock]}, daemon=True)
        portal_thread.start()
        import time
        for _ in range(100):
            if portal.started:
                break
            time.sleep(.05)
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(address)
                page.get_by_label('Password').fill('browser fixture password')
                page.get_by_role('button', name='Log in').click()
                page.get_by_label('Search sites').fill('127.0.0.1')
                page.get_by_role('button', name='Search', exact=True).click()
                page.get_by_role('link', name='View evidence').click()
                assert page.get_by_role('heading', name='Audit evidence').is_visible()
                with page.expect_download() as download:
                    page.get_by_role('link', name='Download pdf', exact=True).click()
                assert download.value.suggested_filename == 'report.pdf'
                page.goto(address)
                page.get_by_role('button', name='Log out').click()
                page.wait_for_url('**/login')
                assert page.get_by_label('Password').is_visible()
                browser.close()
        finally:
            portal.should_exit = True
            portal_thread.join(10)
            sock.close()
        output = os.environ.get('WA_E2E_OUTPUT')
        if output:
            import shutil
            destination = Path(output) / report['run_id']
            shutil.copytree(Path(report['artifacts']['json']).parent, destination)
            print('Retained fixture artifacts:', destination)
    finally:
        server.shutdown()
        server.server_close()

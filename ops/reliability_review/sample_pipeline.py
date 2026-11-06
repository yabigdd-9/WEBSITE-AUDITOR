"""Loopback-only evidence -> remediation -> demo -> review packet example."""
import hashlib
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from auditor_toolkit.demo import build_demo  # noqa: E402
from auditor_toolkit.packet import build_packet  # noqa: E402
from auditor_toolkit.pipeline import AuditOptions, run_audit  # noqa: E402
from auditor_toolkit.remediation import build_remediation  # noqa: E402


class Fixture(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != '/':
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(b'<!doctype html><html lang="en"><head><title>Synthetic NZ Plumbing</title></head><body><main><h1>Synthetic NZ Plumbing</h1><p>Canterbury fixture, not a real business.</p><img src="/missing.png"><a href="/broken">Request a quote</a></main></body></html>')

    def log_message(self, *args):
        pass


def main():
    output = ROOT / 'reports/reliability-review/sample'
    server = ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        report = run_audit(f'http://127.0.0.1:{server.server_port}/', AuditOptions(
            output_root=output / 'audit', allow_private=True, browser=True,
            deep=True, max_pages=3, max_links=5, timeout=3, ai=False))
        assert report['status'] == 'complete', report['checks']
        screenshot = Path(report['artifacts']['screenshot'])
        assert screenshot.is_file() and screenshot.stat().st_size > 100
        assert report['defects']
        remediation = build_remediation(report, output / 'remediation')
        demo = build_demo(report, remediation, output / 'demo',
                          report_path=report['artifacts']['json'])
        packet = build_packet(report, remediation, demo, None, output / 'packet')
        assert packet['human_approved'] is False and packet['send_enabled'] is False
        assert packet['outreach_eligible'] is False and packet['outbound_sent'] == 0
        queue = ROOT / 'approval/reliability-review/APPROVAL_QUEUE.yaml'
        queue.parent.mkdir(parents=True, exist_ok=True)
        queue.write_text('schema_version: 1\nscope: synthetic_staging_only\nitems:\n'
                         '  - id: reliability-review-synthetic\n'
                         '    status: NOT_SENT_AWAITING_APPROVAL\n'
                         '    human_approved: false\n    send_enabled: false\n'
                         '    recipient: null\n    synthetic: true\n'
                         '    packet: reports/reliability-review/sample/packet/packet.json\n')
        receipt = {'synthetic': True, 'network_scope': 'loopback fixture only',
                   'source_run_id': report['run_id'], 'status': report['status'],
                   'confirmed_fixture_findings': [{'key': f['defect_key'], 'evidence': f.get('observed') or f.get('evidence_summary')} for f in report['defects']],
                   'screenshot': str(screenshot),
                   'screenshot_sha256': hashlib.sha256(screenshot.read_bytes()).hexdigest(),
                   'demo': demo, 'packet': packet, 'queue_path': str(queue),
                   'paid_calls': 0, 'outbound_sent': 0,
                   'inference': 'Potential lost enquiries are a hypothesis, not measured revenue.'}
        (output / 'pipeline-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
        print(json.dumps({'status': report['status'], 'defects': len(report['defects']),
                          'screenshot': str(screenshot), 'queue': str(queue)}))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


if __name__ == '__main__':
    main()

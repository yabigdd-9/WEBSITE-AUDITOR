"""Authenticated ciphertext retrieval; private keys never enter the portal."""

import hashlib
import html
import json
import re
import time
from datetime import datetime

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from scripts.report_archive import EncryptedReportArchive, availability

REPORT_PATH = "/pipeline/reports"


class ReportViews:
    def __init__(self, views, archive):
        self.views = views
        self.archive = archive
        self.downloads = {}

    def reports(self, request: Request, prospect: str = "", offset: int = 0):
        self.views.session(request)
        document = self.views.state()
        if offset < 0 or (prospect and not re.fullmatch(r"[0-9a-f]{64}", prospect)):
            raise HTTPException(400, "Invalid report search")
        audits = {a["audit_id"]: a for a in document.get("audit_runs", [])}
        links = document.get("audit_artifact_links", [])
        ids = {link["artifact_id"] for link in links
               if not prospect or audits[link["audit_id"]]["prospect_id"] == prospect}
        records = [a for key, a in sorted(document.get("report_artifacts", {}).items()) if key in ids]
        cards = "".join(self.report_card(record, links) for record in records[offset:offset + 25])
        body = (
            '<p>Only ciphertext is downloaded. Decrypt on your trusted device; never enter a private key here.</p>'
            '<p>Availability checks the envelope and stored checksum. Authenticated decryption and audit links require owner review.</p>'
            + (cards or '<p>No encrypted reports indexed for this selection.</p>')
        )
        if offset + 25 < len(records):
            body += f'<p><a href="{REPORT_PATH}?offset={offset + 25}&amp;prospect={html.escape(prospect, quote=True)}">Next reports</a></p>'
        return self.views.page("Encrypted audit reports", body)

    def report_card(self, metadata, links):
        identity = metadata["artifact_id"]
        now = time.time()
        status = availability(metadata, self.archive, now=now)
        source_expired = datetime.fromisoformat(metadata["source_expires_at"]).timestamp() <= now
        summary = {
            **metadata, "local_availability": status, "recorded_source_expired": source_expired,
            "audit_links": [link for link in links if link["artifact_id"] == identity],
        }
        source = (
            "https://github.com/yabigdd-9/WEBSITE-AUDITOR/actions/runs/"
            + metadata["source_run_id"] + "/artifacts/" + metadata["source_artifact_id"]
        )
        download = (
            f'<a href="{REPORT_PATH}/{html.escape(identity, quote=True)}/ciphertext">Download encrypted report</a>'
            if status == "AVAILABLE" else '<p>Local download unavailable. Review archive configuration or retention.</p>'
        )
        return ('<article>' + download + '<p><a href="' + html.escape(source, quote=True)
                + '">Recorded GitHub source</a> (availability is not checked online)</p><pre>'
                + html.escape(json.dumps(summary, indent=2)) + '</pre></article>')

    def check_rate(self, key):
        now = time.monotonic()
        self.downloads[key] = [stamp for stamp in self.downloads.get(key, []) if now - stamp < 60]
        if len(self.downloads[key]) >= 10:
            raise HTTPException(429, "Encrypted report download limit reached")
        self.downloads[key].append(now)

    def download(self, identity: str, request: Request):
        key, _ = self.views.session(request)
        self.check_rate(key)
        metadata = self.views.state().get("report_artifacts", {}).get(identity)
        if not re.fullmatch(r"[0-9a-f]{64}", identity) or metadata is None:
            raise HTTPException(404, "Encrypted report unavailable")
        if datetime.fromisoformat(metadata["retain_until"]).timestamp() <= time.time():
            raise HTTPException(410, "Local report retention expired")
        if self.archive is None:
            raise HTTPException(503, "Private encrypted archive is not configured")
        try:
            data = self.archive.read(identity)
            if len(data) != metadata["byte_count"]:
                raise ValueError("Ciphertext size changed")
        except FileNotFoundError:
            raise HTTPException(404, "Encrypted report file unavailable") from None
        except (ValueError, OSError):
            raise HTTPException(409, "Encrypted report integrity check failed") from None
        return Response(
            data, media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{hashlib.sha256(data).hexdigest()}.enc.json"'},
        )


def attach_reports(app, views, archive_root=None):
    archive = EncryptedReportArchive(archive_root) if archive_root is not None else None
    views.report_archive = archive
    reports = ReportViews(views, archive)
    app.add_api_route(REPORT_PATH, reports.reports, methods=["GET"], response_class=HTMLResponse)
    app.add_api_route(REPORT_PATH + "/{identity}/ciphertext", reports.download, methods=["GET"])

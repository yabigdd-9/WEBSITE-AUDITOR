"""Apply an explicit literal patch to an isolated static-site copy and audit it.

The input is read only. This produces local implementation evidence, never a
production-change claim. Source scripts and outbound resources are not supported.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import shutil
import threading
from collections import Counter
from html import escape
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlsplit

from bs4 import BeautifulSoup

from .common import atomic_write_json, atomic_write_text
from .pipeline import AuditOptions, run_audit

_ALLOWED = {
    ".html",
    ".htm",
    ".css",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".ico",
    ".woff",
    ".woff2",
    ".txt",
    ".xml",
}
_MAX_FILES = 200
_MAX_TOTAL = 20_000_000


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _relative(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("A relative static-site path is required")
    path = PurePosixPath(value)
    if path.is_absolute() or any(
        part in {"..", "."} or part.startswith(".") for part in path.parts
    ):
        raise ValueError("Hidden or escaping paths are not allowed")
    return Path(*path.parts)


def _static_html(text):
    soup = BeautifulSoup(text, "html.parser")
    for tag in soup.find_all(True):
        if tag.name in {"iframe", "object", "embed", "base"}:
            raise ValueError("Active frames and base overrides are unsupported")
        if tag.name == "script" and tag.get("type", "").lower() != "application/ld+json":
            raise ValueError("Executable site scripts are unsupported in this local workflow")
        for key, value in tag.attrs.items():
            if key.lower().startswith("on"):
                raise ValueError("Executable inline handlers are unsupported")
            if (
                key.lower() in {"href", "src", "action"}
                and isinstance(value, str)
                and value.strip().lower().startswith("javascript:")
            ):
                raise ValueError("Executable URLs are unsupported")
        if tag.name == "meta" and tag.get("http-equiv", "").lower() == "refresh":
            raise ValueError("Automatic navigation is unsupported")


def _source_files(source):
    files, total = [], 0
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError("Source symlinks are unsupported")
        relative = path.relative_to(source)
        if any(part.startswith(".") for part in relative.parts):
            continue
        if not path.is_file() or path.suffix.lower() not in _ALLOWED:
            continue
        total += path.stat().st_size
        if len(files) >= _MAX_FILES or total > _MAX_TOTAL:
            raise ValueError("Static-site snapshot exceeds the file or byte limit")
        if path.suffix.lower() in {".html", ".htm", ".svg"}:
            _static_html(path.read_text(encoding="utf-8"))
        files.append(relative)
    return files


def _inventory(root):
    return [
        {"path": str(path.relative_to(root)), "sha256": _sha(path), "size": path.stat().st_size}
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def _compare_findings(before, after):
    ranks = {"low": 1, "medium": 2, "high": 3, "critical": 4}

    def groups(report):
        result = {}
        for defect in report["defects"]:
            severity = defect.get("severity")
            if severity not in ranks:
                raise ValueError("Known finding severity required for comparison")
            key = (str(defect.get("defect_key")), str(defect.get("selector") or ""))
            result.setdefault(key, []).append(severity)
        return {key: sorted(values, key=ranks.get, reverse=True) for key, values in result.items()}

    baseline, candidate = groups(before), groups(after)
    removed, added, improved, worsened = Counter(), Counter(), Counter(), Counter()
    for key in sorted(baseline.keys() | candidate.keys()):
        old, new = baseline.get(key, []), candidate.get(key, [])
        for severity in old[len(new) :]:
            removed[(*key, severity)] += 1
        for severity in new[len(old) :]:
            added[(*key, severity)] += 1
        for old_severity, new_severity in zip(old, new):
            if ranks[new_severity] > ranks[old_severity]:
                worsened[(*key, old_severity, new_severity)] += 1
            elif ranks[new_severity] < ranks[old_severity]:
                improved[(*key, old_severity, new_severity)] += 1

    def rows(counter):
        return [
            {"defect_key": key, "selector": selector, "severity": severity, "count": count}
            for (key, selector, severity), count in sorted(counter.items())
        ]

    def transitions(counter):
        return [
            {
                "defect_key": key,
                "selector": selector,
                "before_severity": old,
                "after_severity": new,
                "count": count,
            }
            for (key, selector, old, new), count in sorted(counter.items())
        ]

    return {
        "removed_findings": rows(removed),
        "new_findings": rows(added),
        "improved_findings": transitions(improved),
        "worsened_findings": transitions(worsened),
    }


def build_implementation_demo(source_dir, patch_plan, output_dir, *, entrypoint="index.html"):
    source, output = Path(source_dir).resolve(), Path(output_dir).resolve()
    entry = _relative(entrypoint)
    if entry.suffix.lower() not in {".html", ".htm"}:
        raise ValueError("Entrypoint must be an HTML page")
    if not source.is_dir() or output.exists():
        raise ValueError("An existing source and a new output directory are required")
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("Source and output directories must be separate")
    if not isinstance(patch_plan, dict) or patch_plan.get("schema_version") != 1:
        raise ValueError("Patch plan schema_version 1 is required")
    edits = patch_plan.get("edits")
    if not isinstance(edits, list) or not 1 <= len(edits) <= 30:
        raise ValueError("One to thirty explicit edits are required")
    files = _source_files(source)
    if entry not in files:
        raise ValueError("Entrypoint must be a captured HTML file")
    prepared, seen = {}, set()
    for edit in edits:
        if not isinstance(edit, dict):
            raise ValueError("Malformed patch edit")
        relative = _relative(edit.get("path"))
        if (
            relative in seen
            or relative not in files
            or relative.suffix.lower() not in {".html", ".htm", ".css", ".txt", ".xml", ".svg"}
        ):
            raise ValueError("Each editable text path must exist once in the static snapshot")
        seen.add(relative)
        path = source / relative
        if edit.get("expected_sha256") != _sha(path):
            raise ValueError("Source hash does not match the reviewed patch")
        replacements = edit.get("replacements")
        if not isinstance(replacements, list) or not 1 <= len(replacements) <= 30:
            raise ValueError("Explicit literal replacements are required")
        text = path.read_text(encoding="utf-8")
        for replacement in replacements:
            if not isinstance(replacement, dict):
                raise ValueError("Replacement must be an object")
            old, new, count = (
                replacement.get("old"),
                replacement.get("new"),
                replacement.get("expected_count"),
            )
            if (
                not isinstance(old, str)
                or not old
                or not isinstance(new, str)
                or type(count) is not int
                or not 1 <= count <= 100
            ):
                raise ValueError("Literal replacement and bounded occurrence count are required")
            if text.count(old) != count:
                raise ValueError("Replacement occurrence count does not match the reviewed source")
            text = text.replace(old, new)
        if len(text.encode()) > 2_000_000:
            raise ValueError("Patched file exceeds the byte limit")
        if relative.suffix.lower() in {".html", ".htm", ".svg"}:
            _static_html(text)
        prepared[relative] = text
    source_inventory = [
        {"path": str(relative), "sha256": _sha(source / relative)} for relative in files
    ]
    output.mkdir(parents=True, exist_ok=False)
    before_dir, after_dir = output / "before", output / "after"
    before_dir.mkdir()
    after_dir.mkdir()
    for relative in files:
        for target_root in (before_dir, after_dir):
            target = target_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / relative, target)
    if any(
        _sha(before_dir / item["path"]) != item["sha256"]
        or _sha(after_dir / item["path"]) != item["sha256"]
        for item in source_inventory
    ):
        raise ValueError("Source changed while snapshots were copied")
    patch_text = []
    for relative, text in prepared.items():
        original = (before_dir / relative).read_text(encoding="utf-8")
        atomic_write_text(after_dir / relative, text)
        patch_text.extend(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                text.splitlines(keepends=True),
                fromfile="a/" + str(relative),
                tofile="b/" + str(relative),
            )
        )
    atomic_write_text(output / "implementation.patch", "".join(patch_text))
    atomic_write_json(output / "patch-plan.json", patch_plan)
    root_holder = {"root": before_dir}

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root_holder["root"]), **kwargs)

        def log_message(self, *args):
            pass

        def end_headers(self):
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'none'; object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'",
            )
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            super().end_headers()

        def _host_allowed(self):
            if self.headers.get("Host") != f"127.0.0.1:{server.server_port}":
                self.send_error(403, "Loopback host required")
                return False
            return True

        def do_HEAD(self):
            if self._host_allowed():
                super().do_HEAD()

        def do_GET(self):
            if not self._host_allowed():
                return
            path = urlsplit(self.path).path
            if path == "/robots.txt" and not (root_holder["root"] / "robots.txt").exists():
                body = b"User-agent: *\nAllow: /\n"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            super().do_GET()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/{quote(entry.as_posix(), safe='/')}"
    audit_options = AuditOptions(
        output_root=output / "audits",
        profile="rendered",
        allow_private=True,
        browser=True,
        tls=False,
        ai=False,
        timeout=8,
        max_pages=1,
    )
    manifest = {
        "schema_version": 1,
        "kind": "local_static_implementation",
        "status": "STARTED",
        "source_directory": str(source),
        "source_inventory": source_inventory,
        "entrypoint": str(entry),
        "audit_url": url,
        "audit_profile": "rendered",
        "patch_plan_sha256": _sha(output / "patch-plan.json"),
        "patch_sha256": _sha(output / "implementation.patch"),
        "production_changed": False,
        "external_deploy": False,
        "model_requests": 0,
        "regression_suite_run": False,
        "review_required": True,
        "limitations": [
            "Isolated static copy only; no live customer-site change.",
            "Executable site scripts unsupported; outbound resources blocked by CSP.",
            "Lab findings do not establish legal/accessibility conformance, field performance or revenue.",
            "HTTP and fixed local response headers do not represent production transport configuration.",
        ],
    }
    atomic_write_json(output / "implementation-demo.json", manifest)
    try:
        before = run_audit(url, audit_options)
        root_holder["root"] = after_dir
        after = run_audit(url, audit_options)
        comparison = _compare_findings(before, after)
        unchanged_source = all(
            _sha(source / item["path"]) == item["sha256"] for item in source_inventory
        )
        complete = (
            before["status"] == after["status"] == "complete"
            and before.get("profile") == after.get("profile")
            and before.get("url") == after.get("url")
            and before["coverage"] == after["coverage"]
            and before["coverage"]["passed"] == before["coverage"]["required"]
            and unchanged_source
        )
        improved = (
            complete
            and bool(comparison["removed_findings"] or comparison["improved_findings"])
            and not comparison["new_findings"]
            and not comparison["worsened_findings"]
        )
        manifest.update(
            status="LOCAL_IMPROVEMENT_OBSERVED" if improved else "REVIEW_REQUIRED",
            source_unchanged=unchanged_source,
            before={
                "run_id": before["run_id"],
                "report": before["artifacts"]["json"],
                "coverage": before["coverage"],
                "status": before["status"],
                "defect_count": before["defect_count"],
            },
            after={
                "run_id": after["run_id"],
                "report": after["artifacts"]["json"],
                "coverage": after["coverage"],
                "status": after["status"],
                "defect_count": after["defect_count"],
            },
            **comparison,
            local_improvement_observed=improved,
            before_inventory=_inventory(before_dir),
            after_inventory=_inventory(after_dir),
        )
        for label, report in (("before", before), ("after", after)):
            manifest[label]["report_sha256"] = _sha(report["artifacts"]["json"])
            manifest[label]["screenshots"] = {
                key: report["manifest"][key]
                for key in ("screenshot", "mobile_screenshot")
                if key in report["manifest"]
            }
        summary = (
            "Local improvement observed"
            if improved
            else "Review required: comparison incomplete, new findings or worsened severity"
        )
        screenshots = []
        for label in ("before", "after"):
            record = manifest[label]["screenshots"].get("screenshot")
            if record:
                relative = Path(record["path"]).relative_to(output).as_posix()
                screenshots.append(
                    f'<section><h2>{label.title()}</h2><img src="{escape(relative, quote=True)}" alt="{label.title()} local static page"></section>'
                )
        html = (
            '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Local implemented repair comparison</title><style>body{font:18px/1.6 system-ui;max-width:1200px;margin:32px auto;padding:24px;color:#17302b}img{max-width:100%;height:auto}pre{white-space:pre-wrap}section{border:1px solid #ccd5cf;padding:20px;margin:20px 0}</style></head><body><h1>'
            + summary
            + '</h1><p>Original source preserved. Patch applied only to an isolated local copy. No customer website changed. Review the full reports and remaining findings.</p><p><a href="implementation-demo.json">Comparison evidence</a> · <a href="implementation.patch">Actual patch</a></p><pre>'
            + escape(
                json.dumps(
                    {
                        "removed": manifest["removed_findings"],
                        "new": manifest["new_findings"],
                        "improved": manifest["improved_findings"],
                        "worsened": manifest["worsened_findings"],
                    },
                    indent=2,
                )
            )
            + "</pre>"
            + "".join(screenshots)
            + "</body></html>"
        )
        atomic_write_text(output / "index.html", html)
    except Exception as exc:
        manifest.update(status="INCOMPLETE", error_type=type(exc).__name__)
        raise
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        manifest["local_server_closed"] = True
        atomic_write_json(output / "implementation-demo.json", manifest)
    return manifest

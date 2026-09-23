"""
JavaScript vulnerability detection using local DB.
"""
from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple

from bs4 import BeautifulSoup

from auditor_toolkit.checks import Finding

VULN_DB: List[Tuple[str, str]] = [
    ("jQuery", "1.6.3"),
    ("jQuery", "1.6.2"),
    ("jQuery", "1.6.1"),
    ("jQuery", "1.6.0"),
    ("jQuery", "1.5.2"),
    ("jQuery", "1.5.1"),
    ("jQuery", "1.5.0"),
    ("jQuery", "1.4.4"),
    ("jQuery", "1.4.3"),
    ("jQuery", "1.4.2"),
    ("jQuery", "1.4.1"),
    ("jQuery", "1.4.0"),
    ("jQuery", "1.3.2"),
    ("jQuery", "1.3.1"),
    ("jQuery", "1.3.0"),
]


def _extract_library_and_version(src: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract library name and version from script src URL."""
    patterns = [
        r"([^/]+?)[-_](\d+\.\d+\.\d+(?:\.\d+)?)(?:[.-]min)?\.(?:js)",
        r"([^/]+?)\.(\d+\.\d+\.\d+(?:\.\d+)?)(?:[.-]min)?\.(?:js)",
    ]
    for pattern in patterns:
        match = re.search(pattern, src, re.IGNORECASE)
        if match:
            lib = match.group(1).lower()
            version = match.group(2)
            if "jquery" in lib:
                lib = "jQuery"
            elif "bootstrap" in lib:
                lib = "Bootstrap"
            elif "angular" in lib:
                lib = "Angular"
            elif "vue" in lib:
                lib = "Vue"
            elif "react" in lib:
                lib = "React"
            return lib, version
    return None, None


def detect_js_vulnerabilities(html: str, url: str) -> List[Finding]:
    """Detect JavaScript library vulnerabilities."""
    findings = []
    soup = BeautifulSoup(html, "html.parser")
    scripts = soup.find_all("script", src=True)
    for script in scripts:
        src = script.get("src")
        if not src:
            continue
        lib, version = _extract_library_and_version(src)
        if lib and version:
            for vuln_lib, vuln_version in VULN_DB:
                if lib == vuln_lib and version == vuln_version:
                    findings.append(
                        Finding(
                            defect_key=f"js_vulnerability_{lib.lower()}_{version.replace('.', '_')}",
                        )
                    )
                    break
    return findings


def analyse_html(html: str, url: str, headers: dict) -> tuple[List[Finding], dict[str, Any]]:
    """Analyse HTML for JS vulnerability findings."""
    findings = detect_js_vulnerabilities(html, url)
    return findings, {"js_vulnerabilities_detected": len(findings)}

"""Local security-header grader — the securityheaders.com replacement.

Pure function of response headers the auditor already fetches: no quota, no
dependency, no network. Grades A+..F like the old scanner so reports keep the
same UX, and emits per-header defects in the auditor's ``{defect, impact}``
shape so they slot straight into ``score_defects``.
"""

from __future__ import annotations

GRADE_ORDER = ["A+", "A", "B", "C", "D", "E", "F"]

# header -> (weight, missing_impact, weak_test, weak_impact)
CHECKS = {
    "strict-transport-security": (
        20, "No HSTS — first visit can be downgraded to HTTP",
        lambda v: "max-age" in v.lower() and _max_age(v) >= 15552000,
        "HSTS max-age under 6 months — weak downgrade protection",
    ),
    "content-security-policy": (
        20, "No CSP — XSS has no second line of defence",
        lambda v: "default-src" in v.lower() or "script-src" in v.lower(),
        "CSP present but has no script/default-src directive",
    ),
    "x-frame-options": (
        10, "No X-Frame-Options — page can be iframed (clickjacking)",
        lambda v: v.strip().upper() in ("DENY", "SAMEORIGIN"),
        "X-Frame-Options set to an unrecognised value",
    ),
    "x-content-type-options": (
        10, "No X-Content-Type-Options — MIME-sniffing attacks possible",
        lambda v: v.strip().lower() == "nosniff",
        "X-Content-Type-Options is not 'nosniff'",
    ),
    "referrer-policy": (
        10, "No Referrer-Policy — full URLs may leak to third parties",
        lambda v: v.strip() != "",
        "Referrer-Policy present but empty",
    ),
    "permissions-policy": (
        10, "No Permissions-Policy — browser features left wide open",
        lambda v: v.strip() != "",
        "Permissions-Policy present but empty",
    ),
    "cross-origin-opener-policy": (
        10, "No COOP — cross-origin windows share a browsing context",
        lambda v: v.strip().lower() in ("same-origin", "same-origin-allow-popups"),
        "COOP set to an unrecognised value",
    ),
}

TOTAL_WEIGHT = sum(w for w, *_ in CHECKS.values())


def _max_age(value: str) -> int:
    for part in value.split(";"):
        part = part.strip()
        if part.lower().startswith("max-age="):
            try:
                return int(part.split("=", 1)[1])
            except ValueError:
                return 0
    return 0


def grade_security_headers(headers: dict) -> dict:
    """Grade response headers. Returns grade, score, per-header rows, defects."""
    lowered = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    earned = 0
    rows: list[dict] = []
    defects: list[dict] = []
    for name, (weight, missing_impact, strong, weak_impact) in CHECKS.items():
        value = lowered.get(name)
        if value is None:
            rows.append({"header": name, "status": "missing", "value": None})
            defects.append({"defect": f"Missing {name}", "impact": missing_impact})
        elif strong(value):
            earned += weight
            rows.append({"header": name, "status": "pass", "value": value})
        else:
            earned += weight // 2
            rows.append({"header": name, "status": "weak", "value": value})
            defects.append({"defect": f"Weak {name}", "impact": weak_impact})
    pct = round(100 * earned / TOTAL_WEIGHT)
    if pct >= 95:
        grade = "A+"
    elif pct >= 85:
        grade = "A"
    elif pct >= 70:
        grade = "B"
    elif pct >= 55:
        grade = "C"
    elif pct >= 40:
        grade = "D"
    elif pct >= 25:
        grade = "E"
    else:
        grade = "F"
    return {"grade": grade, "score": pct, "headers": rows, "defects": defects}

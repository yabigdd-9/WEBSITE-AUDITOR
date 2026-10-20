#!/usr/bin/env python3
"""
HERMES_ZERO_TOKEN Demo Blueprint Worker (P2)

Produces review-only demo blueprints from evidence-backed templates.
Writes ONLY to reports/hermes_zero_token/demo_blueprints/ — never sends,
never deploys, never commits pricing without human approval.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from ops.hermes_zero_token.worker_ownership import run_owned_worker  # noqa: E402

BLUEPRINTS_DIR = PROJECT_ROOT / "reports" / "hermes_zero_token" / "demo_blueprints"

os.environ["HERMES_ZERO_TOKEN_MODE"] = "ZERO_LLM"
os.environ["HERMES_ALLOW_HOSTED_LLM"] = "0"
os.environ["HERMES_ALLOW_PAID_FALLBACK"] = "0"
os.environ["WEBSITE_AUDITOR_OUTREACH_SEND"] = "0"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _now_tag():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def get_businesses_with_audit(limit=5):
    """Return businesses with audit evidence (audits table)."""
    conn = __import__("sqlite3").connect(
        f"file:{PROJECT_ROOT / 'database' / 'money_machine.db'}?mode=ro", uri=True
    )
    conn.row_factory = __import__("sqlite3").Row
    rows = conn.execute(
        "SELECT b.id AS business_id, b.name, b.public_website, b.region, "
        "       a.id AS audit_id, a.opportunity_score, a.broken_paths, "
        "       a.automation_opportunities, a.evidence AS audit_evidence, "
        "       a.mobile_quality, a.conversion_quality, a.quote_flow, "
        "       a.booking_flow, a.seo_basics, a.page_speed, a.accessibility "
        "FROM businesses b "
        "JOIN audits a ON a.business_id = b.id "
        "WHERE b.is_dummy = 0 AND b.public_website IS NOT NULL AND b.public_website != '' "
        "ORDER BY a.id DESC, b.id "
        "LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


TEMPLATE = """# Demo Blueprint — {name}

**Generated:** {generated}
**Business:** {name}
**Website:** {url}
**Region:** {region}
**Audit ID:** {audit_id}
**Opportunity Score:** {score}

## Scope

A modernisation proposal for {name}'s public website, based on observed
technical evidence only. No claims are made about revenue, traffic, or
conversion without first-party measurement.

## Observed Technical Indicators

- Mobile quality: {mobile_quality}
- Conversion quality: {conversion_quality}
- Quote flow: {quote_flow}
- Booking flow: {booking_flow}
- SEO basics: {seo_basics}
- Page speed: {page_speed}
- Accessibility: {accessibility}

## Broken Paths

{broken_paths}

## Automation Opportunities

{automation_opportunities}

## Proposed Deliverables

1. **Booking / quote flow audit** — assess friction in existing paths.
2. **Mobile responsiveness review** — verify on common viewports.
3. **Local SEO metadata** — check structured data and meta tags.
4. **Performance baseline** — measure and report, no guarantees of speed.

## Acceptance Criteria

- [ ] Evidence captured and stored with hash + timestamp
- [ ] No fabricated screenshots or findings
- [ ] No outreach sent without human approval
- [ ] Pricing requires explicit Dion approval

## Status

**REVIEW-ONLY. NOT DEPLOYED. NOT SENT.**
"""


def _main():
    BLUEPRINTS_DIR.mkdir(parents=True, exist_ok=True)
    businesses = get_businesses_with_audit(limit=5)
    report = {
        "generated_at": _now(),
        "phase": "P2",
        "blueprints_dir": str(BLUEPRINTS_DIR),
        "production_written": False,
        "outbound_messages_sent": 0,
        "blueprints_created": 0,
        "details": [],
    }

    for biz in businesses:
        bid = biz["business_id"]
        tag = _now_tag()
        path = BLUEPRINTS_DIR / f"business-{bid}-{tag}.md"
        content = TEMPLATE.format(
            name=biz["name"],
            generated=_now(),
            url=biz["public_website"],
            region=biz.get("region") or "NZ",
            audit_id=biz.get("audit_id"),
            score=biz.get("opportunity_score"),
            mobile_quality=biz.get("mobile_quality"),
            conversion_quality=biz.get("conversion_quality"),
            quote_flow=biz.get("quote_flow"),
            booking_flow=biz.get("booking_flow"),
            seo_basics=biz.get("seo_basics"),
            page_speed=biz.get("page_speed"),
            accessibility=biz.get("accessibility"),
            broken_paths=biz.get("broken_paths") or "No broken paths recorded.",
            automation_opportunities=biz.get("automation_opportunities") or "No automation opportunities recorded.",
        )
        path.write_text(content)
        report["blueprints_created"] += 1
        report["details"].append({
            "business_id": bid,
            "name": biz["name"],
            "url": biz["public_website"],
            "audit_id": biz["audit_id"],
            "blueprint_path": str(path),
            "status": "REVIEW_ONLY_NOT_DEPLOYED",
        })

    report_path = BLUEPRINTS_DIR / "demo_blueprint_report.json"
    report_path.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))
    return 0


def main():
    return run_owned_worker(PROJECT_ROOT, 'demo_blueprint', _main)


if __name__ == "__main__":
    sys.exit(main())

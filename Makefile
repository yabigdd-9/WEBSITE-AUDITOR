.PHONY: install test audit crawl remediate dashboard export actions-init actions-demo actions-dry-run actions-status suppressions execute-all-safe

install:
	python3 -m pip install -e ".[dev]"

test:
	python3 -m pytest -q

audit:
	python3 website_auditor.py https://example.co.nz --format json

crawl:
	python3 website_auditor.py https://example.co.nz --profile standard --crawl --max-pages 5 --format json

remediate:
	python3 remediation-engine.py --all --output-dir outputs/remediations

dashboard:
	python3 audit-dashboard.py --output outputs/dashboard.html

export:
	python3 portfolio-export.py --audits-dir audits --output-dir outputs/portfolio --format all

actions-init:
	python3 -m website_auditor.cli actions init

actions-demo:
	python3 -m website_auditor.cli actions demo --domain example.co.nz

actions-dry-run:
	python3 -m website_auditor.cli actions dry-run

actions-status:
	python3 -m website_auditor.cli actions status

suppressions:
	python3 -m website_auditor.cli outreach list

execute-all-safe:
	python3 run_all.py https://example.co.nz

.PHONY: install test actions-init actions-demo actions-dry-run actions-status execute-all-safe

install:
	python3 -m pip install -e ".[dev]"

test:
	python3 -m pytest -q

actions-init:
	python3 -m website_auditor.cli actions init

actions-demo:
	python3 -m website_auditor.cli actions demo --domain example.co.nz

actions-dry-run:
	python3 -m website_auditor.cli actions dry-run

actions-status:
	python3 -m website_auditor.cli actions status

execute-all-safe:
	python3 run_all.py https://example.co.nz

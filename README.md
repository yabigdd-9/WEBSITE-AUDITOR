# WEBSITES/BUISNESSaudits

Evidence-first website and business audits, contact attribution, scoped offers,
and internal approval packets. This is the current project identity of
`yabigdd-9/HERMES_MONEY_ENGINE`; `MoneyMachine` remains a compatibility name.

Start with `reports/CURRENT_STATE.md` for measured results and outstanding gates.
Historical reports retain their original names and dates.

## Local runtime

Use Python 3.11 or newer and the existing pinned requirements. The current installed environment was restored offline from exact existing distribution files after an initial generic-python3 attempt selected incompatible Apple Python 3.9; see the system doctor before creating a fresh environment:

```sh
/absolute/path/to/python3.14 -m venv .venv-email
.venv-email/bin/python -m pip install -r money-machine/requirements-email.txt
./mm --runtime
./mm --help
./mm email-status 5 --json
```

`MM_PYTHON` can select an existing verified interpreter. `MM_ROOT` explicitly
selects an alternative data/output root; it never discovers another database.
The default data root is this checkout. `money-machine/Daily Operator.command`
uses the same launcher, interpreter and data root. Run it with `--runtime` for a
read-only diagnosis. The tracked legacy venv link is historical compatibility;
the new launcher uses the checkout-local environment instead.

Relative `scripts`, `tests`, `migrations`, and `control-plane` aliases restore the
original logical paths after the source was flattened into `money-machine/`.
They all reference the same files; no source or historical evidence is moved.

The database is retained as imported. Existing observation policy and suppression
remain in force. Do not replace it with a historical backup to repair a code path.

## Execution boundary

The local operator does not send or invoke models. Legacy Gmail and SMTP send
entrypoints are held, including self-tests. A CLI flag or generated review cannot
release them. The pilot ends at `HUMAN_APPROVAL_REQUIRED`; production deployment,
outreach, payment, and paid AI remain separate human decisions.

New audit outputs use `WEBSITES/BUISNESSaudits/runs/`. Agent review and automated
checks are not independent human adjudication or contact permission.

`./mm polish-status` shows the dated validation snapshot. To create an internal packet, use `./mm audit-packet --case CASE.json --rendered-review REVIEW.json --output NEW_DIRECTORY`. Browser review must match a captured source; static-only issues cannot qualify a form-label offer.

# Private MoneyMachine opportunity review ledger

The scheduled GitHub cloud auditor already runs without an always-on server. Its public Actions summary contains approved domains and aggregate technical-finding counts. Detailed audit observations and internal drafts are discarded unless the **optional encrypted archive** is configured.

This tool adds an **owner-controlled SQLite history** for decrypted archives. It does NOT place a customer database on public GitHub or silently sync data to a cloud provider.

## What it tracks

- Unique public website domains; each audit run is imported once, even if the same archive is imported again.
- Observed technical findings, their first and latest observation times, and how many distinct runs saw each finding.
- Draft scope notes marked `HUMAN_REVIEW_REQUIRED` with a database check that `sent = 0`.
- A small summary of counts. The terminal does not print individual prospects, findings, contacts, or drafts.

A finding disappearing from a later scan is **not automatically marked resolved**. A review of the actual site and client context would be required to make that claim. This ledger is a private work queue, not a proof of sales or revenue.

## Use it only on a trusted machine

First follow [the encrypted-vault setup](ENCRYPTED_REPORT_VAULT.md). Keep your **private decryption key off GitHub**. Download the encrypted archive from GitHub Actions before its 30-day expiration and decrypt it on your own computer. Never send your private key or decrypted report into this chat.

Create a private directory **outside the public Git checkout**. Example on macOS/Linux:

    mkdir -p "$HOME/moneymachine-private"
    chmod 700 "$HOME/moneymachine-private"

After obtaining a locally decrypted vault JSON file, import it:

    python -m scripts.review_ledger import \
      --input "$HOME/mm-review-decoded.json" \
      --db "$HOME/moneymachine-private/review.sqlite3"

To inspect aggregate progress:

    python -m scripts.review_ledger summary \
      --db "$HOME/moneymachine-private/review.sqlite3"

The database is created with owner-only `0600` permissions. Existing databases with group/other access are refused. The program refuses to put the database inside the repository, even through redirected parent directories. Import uses transactions, bound SQL parameters, size limits, strict status validation, and upsert semantics. Reimporting the same archive or the same scan does not inflate counts.

Keep a separate private backup of `review.sqlite3`; do not upload this plaintext database as a public GitHub Actions artifact or commit it. Do not import into or overwrite your existing `money_machine.db`. This is a separate, smaller review ledger to protect the existing MoneyMachine data and migrations.

## What remains manual

1. Set up the key locally and enable the optional encrypted artifact, if desired.
2. Download and decrypt each archive on your trusted machine.
3. Import it into the ledger with the command above.
4. Independently review findings and scope before any customer-facing steps.

No Oracle server, payment-card validation, paid AI, contact lookup, customer outreach, deployments, payments, or live database edits are involved. The code can be tested free in GitHub Actions using synthetic data. **Unattended private syncing remains unconfigured** until a secure private storage destination and safe credentials are supplied by the owner.

A successful cloud run demonstrates the software path only; it is not a qualified customer or earned revenue.

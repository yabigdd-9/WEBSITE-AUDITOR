# MoneyMachine encrypted review vault (optional)

This repository remains public. Ordinary GitHub Actions artifacts are readable to users with repository read access. Do not upload plaintext prospect reports, drafts, contact records or customer information.

The existing shortlist reports only approved domains and counts. When explicitly configured, the new vault seals a bounded report of observed technical findings and draft scope notes as encrypted ciphertext. The encryption is public-key based, and the owner's private key is never placed on the GitHub runner.

## Setup (on a trusted computer, outside GitHub)

1. Install Python 3.11+ and this repository's optional vault dependency:
   python -m pip install -e '.[vault]'
2. Generate your private key locally, outside the repository:
   python -m scripts.report_vault keygen --private-out "$HOME/mm-vault-private.key"
3. Back up that private key securely. NEVER add it to GitHub, Actions secrets, a public issue, screenshots or chat messages. If it is lost, existing ciphertext is unreadable.
4. Only the command's printed PUBLIC key goes into GitHub repository Settings > Secrets and variables > Actions > Variables as MM_REPORT_PUBLIC_KEY_B64.
5. Once PR #77 is merged, trigger the Cloud Canonical Website Audits workflow manually or wait for its twice-daily best-effort schedule. The workflow uses the public key to encrypt reports and uploads ONLY the encrypted bundle to an artifact. The older MoneyMachine Free Real-Site Shortlist workflow is manual/PR-only.

Without the variable, no reports are archived. The safe no-send scans continue as before.

**Do not generate the private key in a chat, GitHub Actions runner, public repository, or other temporary environment.** Use a trusted device with a supported local Python environment and a secure backup destination. Only publish the public key after verifying the private key is backed up and recoverable.

## Decrypt an owner's archive

Download the run's mm-sealed-review artifact from the GitHub Actions page before it expires. Extract the mm-private-review.enc.json file. On the trusted computer where your private key resides:

    python -m scripts.report_vault decrypt --private-key-file "$HOME/mm-vault-private.key" --input mm-private-review.enc.json --output "$HOME/mm-review-decoded.json"

This creates a local PLAINTEXT report. Do not publish it. The command refuses to overwrite existing output.

## Privacy and cryptography

X25519 ephemeral key agreement, HKDF-SHA256 and AES-256-GCM authenticated encryption are applied to each report archive with a fresh ephemeral key, salt and nonce. The public artifact has no embedded private key. The private key is not needed by cloud runners.

The ciphertext contains only a bounded selection of verified website observations and internal drafts: up to 20 findings per approved site, with short evidence and action strings, plus a scope note capped at 9,000 characters. It excludes full HTML, screenshots, contact searches, payment details and database contents.

The uploaded artifact path is restricted to the runner's temporary directory. Pull requests do not upload even encrypted artifacts. Invalid keys fail closed and never trigger plaintext upload. Customer contact, paid AI, paid providers, site changes, deployments and payments remain disabled.

## Retention and limitations

The workflow sets artifact retention to 30 days. GitHub public-repository artifacts and workflow runs have a maximum retention of 90 days. This is TEMPORARY encrypted storage, not permanent CRM/database storage. Download an archive before it expires or set up a separate private storage destination for durable history.

GitHub Actions artifact storage is subject to platform allowances and possible charges if usage grows. Keep report archives small and do not change to paid services without explicit approval.

An audit finding or scope draft is not proof of customer interest, conversion, revenue or an approved build. All proposals still require human approval.

## Owner-controlled ciphertext archive and index

The optional local archive preserves the existing vault envelope unchanged. It
never accepts private keys or decrypts reports. No hosted archive is configured
by this feature. The owner explicitly creates a dedicated 0700 directory outside
Git checkouts on a trusted device. Existing private pipeline records must already
contain the audit IDs being linked. Download the encrypted GitHub artifact before
its recorded 30-day expiry, extract the envelope, and independently verify its
SHA-256 and association with the recorded audits. Then run:

```sh
python -m scripts.report_archive --database /private/pipeline.sqlite3 \
  --archive-dir /private/sealed --input /private/download.enc.json \
  --expected-sha256 EXPECTED_SHA256 --audit-id RECORDED_AUDIT_ID \
  --source-run-id RUN_ID --source-artifact-id ARTIFACT_ID \
  --created-at CREATION_UTC --source-expires-at SOURCE_EXPIRY_UTC \
  --retain-until LOCAL_EXPIRY_UTC --owner-reviewed --reason 'Verified local association'
```

Use explicit ISO UTC timestamps. Local retention must be in the future and no
more than 365 days from import. Metadata and links are immutable; reimport is
idempotent. The archive permits 1,000 files and 50 MB total, including staging
files. Each envelope is bounded by the existing vault size limit. Publication
uses private files and exclusive content-addressed names; it never overwrites
a different report. No requests or storage provisioning occur.

Launch the existing loopback owner portal with its usual options plus
`--pipeline-db /private/pipeline.sqlite3 --report-archive-root /private/sealed`.
The authenticated Audit reports screen shows availability, recorded source
expiry and audit links, with paginated ciphertext downloads limited to ten per
minute per session. Local expiry blocks download; it does not automatically
delete files. Source URLs are owner-recorded references, not online availability
verification. Partial audit links remain partial and do not qualify findings.

Envelope structure and SHA-256 checks detect malformed or changed copies. They
do not authenticate decrypted content or prove the audit association. Use the
existing trusted-device decryption command above to authenticate/review content.
Never enter the private key in the portal, server configuration or CI.

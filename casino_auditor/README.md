# Casino Auditor — independent product starting point

This is a **full source-code branch copy** of Website Auditor with a separate
casino-operator audit entry point. Original Website Auditor `master` remains
unchanged. This branch is **not yet a separate GitHub repository**.

## Commercial purpose

Offer casino operators a professional audit of their **own, explicitly
authorized** public websites: accessibility, performance, UX, basic
configuration and security hygiene. Provide reproducible findings and scoped
fix proposals; do not imply that the tool finds exploitable vulnerabilities or
guarantees specific regulatory compliance.

## Built now

- All existing Website Auditor source code and its tested audit pipeline.
- `casino_auditor/cli.py`: a thin optional launcher around `wa audit`.
- Dry-run by default, allowlisted root HTTPS domains only.
- A valid operator name, written-authorization reference, explicit limited
  scope and future expiry date are mandatory for every target.
- No access to player accounts, private sessions, payments, wallets or admin.
- No exploit payloads, brute-force, credential enumeration or active
  vulnerability testing; scope is public-site audits only.
- No unauthorized discovery or mass scanning.

## Running a permitted review

First install the original Website Auditor requirements as documented in
`README.md` and verify the `wa` command works.

Create a private `approved-targets.json` with actual independently verified
operator permission (do **not** commit real approval documents or credentials):

```json
{
  "targets": [
    {
      "url": "https://example.com",
      "approved_by": "Operator security lead",
      "authorization_reference": "signed-scope-2026-001",
      "scope": "public-site-audit",
      "expires_utc": "2027-01-01T00:00:00Z"
    }
  ]
}
```

First dry-run:

```sh
python casino_auditor/cli.py --manifest approved-targets.json
```

Only after independently confirming the reference, written permission,
allowed rate/hosts and expiry:

```sh
python casino_auditor/cli.py --manifest approved-targets.json --run --output-dir casino-audit-reports
```

`wa audit` may write its normal artifacts in its configured output location;
the launcher also captures stdout/stderr locally. Review the artifacts
manually before publishing or sending them to the operator.

## Next product work (not yet implemented)

1. Move this branch into its own GitHub repository `CASINO-AUDITOR`, with a
   separate deployment, secrets, billing and product configuration.
2. Add casino-specific checks for accessibility, performance, gameplay
   disclosures, regulatory content, age-related safeguards, privacy and
   user-facing support. Jurisdiction-specific legal interpretation needs
   qualified review and must not be labelled as certified compliance.
3. Generate a client-friendly evidence report, remediation plan, fixed-scope
   quote and tracked acceptance criteria.
4. Add an opt-in client portal and audit history with strong data minimization.
5. Run permissioned end-to-end audits against an operator-owned staging site.
   Only offer active security testing within explicitly written legal scope.

The existing money-machine pipeline remains available in source for later
review, but neither live outbound email nor any automatic casino targeting
is activated. This branch does not run a background server or generate leads.

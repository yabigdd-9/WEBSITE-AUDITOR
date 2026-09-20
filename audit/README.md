# Browser evidence engine

This directory contains the deterministic browser-evidence layer.

Pinned tooling:
- Playwright 1.63.0
- Lighthouse 13.5.0
- @axe-core/playwright 4.13.0

Run locally:

```bash
cd audit
npm install
npx playwright install chromium
node evidence-audit.mjs https://example.com
```

The default output is `evidence/<host>/<timestamp>/`.

This layer captures evidence only. It does not send outreach, approve messages, alter prospect websites, or invent findings.

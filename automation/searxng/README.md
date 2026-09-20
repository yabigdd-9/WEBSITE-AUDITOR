# Local SearXNG for Discovery V2

This service is a local search source for WEBSITE-AUDITOR. It is **not** an outreach
authority. Results are deduplicated and enter MoneyMachine only at
`DISCOVERED`.

## Safety

- Bound to `127.0.0.1:8888` only.
- JSON results only.
- Runtime secret generated into ignored `.env`.
- Cache/data lives on `LLM-USB` by default.
- Image version is pinned.
- No result can directly create an email, approval or send.

## Start

```bash
cd ~/WEBSITE-AUDITOR/automation/searxng
./start.sh
./healthcheck.sh
```

Then test Discovery V2 without writing:

```bash
cd ~/WEBSITE-AUDITOR
./mm discovery-searxng \
  --query "plumber Christchurch" \
  --region Canterbury \
  --dry-run
```

Run without `--dry-run` only when you want the candidates enqueued for the
normal identity/audit pipeline.

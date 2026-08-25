# Demo Factory (scaffold)

A **minimal, runnable scaffold** for the *Low-Touch Demo Factory* SaaS idea from
the HERMES Money Engine ecosystem (economic-os queue task-003).

It does one thing: turns a short product **brief** into a structured **demo
page** (Markdown) containing a hero, value prop, 3 features, and a CTA.

This is intentionally a scaffold — not a finished SaaS. No database, no auth, no
paid APIs, no LLM calls. Generation is a pure local templating function so it
always runs with zero setup.

## What it does

1. Accepts a brief via a web form (name, category, one-liner, optional audience + CTA URL).
2. Generates a structured demo page as Markdown using a local template.
3. Shows the generated demo in the browser (HTML render + raw Markdown, copyable).

## Files

- `demo_factory.py` — core generator. `generate_demo(brief) -> str` returns the
  Markdown demo. Also runnable as a CLI.
- `server.py` — tiny stdlib-only HTTP server exposing the form + result page.
- `README.md` — this file.

## Run it

### Option A — web app (recommended)

```bash
cd demo-factory
python3 server.py            # serves http://127.0.0.1:8000
# open the URL, fill the form, click "Generate demo"
```

Custom port: `python3 server.py --port 9000`

### Option B — CLI (no server)

```bash
python3 demo_factory.py \
  --name "Acme" \
  --category "saas" \
  --one-liner "Close deals while you sleep" \
  --audience "small sales teams"
```

### Verify without a browser

```bash
python3 demo_factory.py --name "Test" --category "saas" --one-liner "Ship faster"
# and/or:
python3 -c "from demo_factory import generate_demo; print(generate_demo({'name':'Test','category':'saas','one_liner':'Ship faster'}))"
```

## Assumptions made (scaffold scope)

- **Local-only templating.** The "generation" is a deterministic Python template,
  not an LLM or paid API. Real product copy would later come from a pluggable
  generator behind the same `generate_demo` interface.
- **Minimal brief schema.** Only name (required), category, one-liner, audience,
  CTA URL. No persistence, no multi-tenant, no accounts.
- **Single-page demo output.** Output is one Markdown doc with hero / value prop /
  exactly 3 features / CTA. Features are template-derived placeholders, not
  researched copy.
- **No storage or queue.** Each request generates on the fly; nothing is saved.
  A production version would drop briefs onto a queue and store results.
- **No tests/deps.** Stdlib only (`http.server`, `argparse`, `urllib`). Python 3.8+.
  CI/build not set up — this is a starting point to validate the concept.

## Out of scope (for a future iteration)

Persistence, auth, multiple demo formats (HTML export, images), an LLM-backed
generator, a job queue, and a real UI/styling pass.

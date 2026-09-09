You are working on MoneyMachine — Dion Lammas's NZ digital modernization operator.

## First step — read the skill
Read /Users/yabigdd/.hermes/skills/business/money-machine/SKILL.md in full. This is the canonical source of truth. Then read its linked references:
- references/outreach-rules.md
- references/verification-delegates.md
- references/db-access.md

## What MoneyMachine is
A local, evidence-based system that identifies NZ small businesses needing digital modernization (booking systems, websites, CRM, automation) and manages the outreach/proposal pipeline. It does NOT send messages or call models on its own. Human-in-the-loop only.

## Pipeline (enforced in SQLite mm_deals table)
DISCOVERED → VERIFIED → AUDITED → QUALIFIED → DRAFT_READY → AWAITING_APPROVAL → APPROVED_TO_SEND → SENT → REPLIED → CALL_OR_DISCOVERY → PROPOSAL_READY → PROPOSAL_SENT → WON / LOST / SUPPRESSED

## Where everything lives
- Root: /Users/yabigdd/Desktop/MoneyMachine/
- Database: /Users/yabigdd/Desktop/MoneyMachine/database/money_machine.db (SQLite)
- CLI: ./mm (run-day, money, learn, price, doctor, email-status, email-find, email-shadow, email-v1, email-rollback, backup)
- Config: config/ (approval_gates.yaml, HERMES_MASTER_OPERATOR.md, HERMES_MONEY_MACHINE_MASTER_PLAN.md)
- Control plane: control-plane/ (scripts, roles, locks, state, config/routing.yaml)
- Prospects: prospects/ (evoke-renovations, heat-force)
- Proposals: proposals/
- Demos: demos/ (booking-quote-calculator.html, enquiry-pilot.html)
- Reports: reports/
- Backups: backups/

## Critical safety rules
1. MoneyMachine does NOT send emails or messages. It prepares drafts for human review.
2. Never manufacture evidence, receipts, or outcomes.
3. VERIFIED_HIGH = supported public business attribution with current mail routing. SMTP/catch-all unknown.
4. Guesses and medium-confidence records cannot enter ready/approval/send workflow.
5. Approval and send recording are separate commands — neither sends anything.
6. Exact content, recipient, and proposal price must remain unchanged once set.
7. Heat Force and Evoke's previous packets are INVALIDATED pending requalification.
8. ATL Heat Pumps, Christchurch Renovations, Butterfield Bathrooms remain SUPPRESSED.
9. Model execution and automatic fallback remain DISABLED for MoneyMachine.
10. All autonomous model adapters are PAUSED. n8n has no production workflows. cron has no scheduled jobs.

## The Offer
Conversion Upgrade Pilot — NZ$750 fixed price. One focused conversion improvement to the existing website. Deposit: NZ$375 to start. Balance: NZ$375 on completion. If the fix is trivial, broaden the scope (trust signals, mobile polish, CTA cleanup) — do NOT drop the price.

## Outreach rules (from references/outreach-rules.md)
- 80–140 words
- One specific, current observation (not a list of weaknesses)
- Low-pressure CTA (offer to share a demo, not to sell)
- No fake urgency, no exaggerated lost-revenue claims
- Verify the contact email is correct before drafting
- Every message must reference specific audit findings for that recipient
- Identical mass blasts trigger spam complaints — personalization is mandatory

## Do-not-contact (6 entries)
Simon Batchelor, Greg/Mobile Hand, Belle Cooper, Taufiq Choudhury, Debbie Vihi, Sangita Devi

## Verification workflow (from references/verification-delegates.md)
When verifying a prospect, dispatch one proofer subagent per business using FILE-BASED prompts (inline JSON schemas in delegate_task fail). Write the prompt to /tmp/PROMPT_proofer_<slug>.txt first, then dispatch the subagent to read it. Results land in /Users/yabigdd/MoneyMachine/reports/PROOFER_<slug>.json.

## Database lock pitfall
The money_machine.db is frequently locked by lingering Python kernel processes. When you get "database is locked": run `lsof <db-path>` to find the holder, `kill -9 <pid>`, then retry. Use `terminal` with sqlite3 CLI directly — do NOT use execute_code for DB writes when the lock persists.

## Prioritization scoring
1. Revenue-loss argument (highest weight) — "your site promises X but X is broken/missing"
2. Ease of visual demonstration — can you show a before/after that makes the value obvious?
3. Contactability — verified email, no suppression history
4. Local relevance — Christchurch/NZ preferred

## Your task
1. Read the MoneyMachine SKILL.md and its references.
2. Run `./mm doctor` and `./mm run-day` to see current status.
3. Review the database schema and current prospects/pipeline state.
4. Identify what Phase 0 (backup) and Phase 1 (auth fix) steps are still pending from EXECUTION_PLAN.md.
5. Propose next actions — but DO NOT send any messages, change CRM stages, or modify approval states without explicit human confirmation.

Start by reading the skill, then report what you find and what you recommend doing next.

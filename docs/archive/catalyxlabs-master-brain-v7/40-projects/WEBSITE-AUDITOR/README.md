---
title: "27. WEBSITE-AUDITOR — CANONICAL PROJECT INTEGRATION"
brain_version: "7.0.0"
canonical_vault: "CatalyxLabs"
source: "DION_LAMMAS_MASTER_BRAIN_V7_OBSIDIAN_WEBSITE_AUDITOR_2026-09-21.md"
status: ACTIVE_CANONICAL_SEGMENT
---

# 27. WEBSITE-AUDITOR — CANONICAL PROJECT INTEGRATION

## 27.1 Identity

```yaml
project:
  name: WEBSITE-AUDITOR
  status: ACTIVE_PRIORITY
  owner: Dion
  canonical_repo: /Users/dd/WEBSITE-AUDITOR
  experimental_repo: /Users/dd/Downloads/WEBSITE-AUDITOR-master
  canonical_plan: WEBSITE_AUDITOR_MASTER_MERGED_PLAN_v32_OBSIDIAN.yaml.md
  plan_version: "32.0"
  cost_policy: ZERO_PAID_MODEL_API_SPEND
  outreach_default: DISABLED
  operator_workspace: Obsidian
```

## 27.2 Purpose

WEBSITE-AUDITOR is the current implementation of the NZ small-business modernization revenue engine.

Its target loop is:

```text
DISCOVER
→ DEDUPE
→ IDENTITY
→ FETCH
→ AUDIT
→ VERIFY CONTACT
→ SCORE
→ SELECT
→ REMEDIATE
→ DEMO
→ SCREENSHOT
→ QUOTE
→ DRAFT
→ QA
→ APPROVAL
→ CONTROLLED ACTION
→ OUTCOME
→ MEASURE
→ LEARN
→ REPEAT
```

## 27.3 Runtime authority

```text
launchd
  ↓
./mm supervisor
  ↓
SQLite leased queue + canonical state
  ↓
WEBSITE-AUDITOR workers
  ↓
artifacts / reports / evidence
  ↓
Obsidian operator workspace
```

Authority order:

1. live repository/database/process state;
2. `./mm` policy and runtime gates;
3. SQLite queue/state;
4. versioned configuration;
5. generated evidence/reports;
6. Obsidian human review notes;
7. historical chat/plan context.

Obsidian is **not** a replacement for SQLite, Git, runtime policy or transport controls.

## 27.4 Obsidian vault mapping

Use the existing vault:

```text
CatalyxLabs/
├── 10 Dashboard/
│   ├── WEBSITE-AUDITOR - Control Centre.md
│   ├── WEBSITE-AUDITOR - Today.md
│   ├── WEBSITE-AUDITOR - Pipeline Status.md
│   ├── WEBSITE-AUDITOR - System Health.md
│   ├── Revenue Pipeline.md
│   ├── Decisions.md
│   ├── Blockers.md
│   └── Waiting On.md
│
├── 40 Projects/
│   └── WEBSITE-AUDITOR/
│       ├── README.md
│       ├── MASTER PLAN.md
│       ├── CURRENT STATE.md
│       ├── CHANGELOG.md
│       ├── ROADMAP.md
│       ├── Leads/
│       ├── Prospects/
│       ├── Audits/
│       ├── Evidence/
│       ├── Demos/
│       ├── Quotes/
│       ├── Outreach Drafts/
│       ├── Experiments/
│       └── Reports/
│
└── 80 Systems/
    └── WEBSITE-AUDITOR/
        ├── Architecture.md
        ├── Runtime.md
        ├── Queue.md
        ├── Providers.md
        ├── Email Verification.md
        ├── Pricing Rules.md
        ├── Approvals.md
        ├── Observability.md
        ├── Backups.md
        ├── Recovery.md
        └── Emergency Stop.md
```

Do not create `WEBSITE-AUDITOR-BRAIN/` as a second vault.

## 27.5 Obsidian sync contract

Runtime → Obsidian:

```text
automatic / read-mostly
```

Suitable generated views:

- health;
- queue depth/age;
- workers;
- provider status;
- errors/DLQ;
- leads;
- prospect packets;
- audit evidence;
- demos;
- quotes;
- approval queue;
- outcomes;
- experiments;
- daily/weekly metrics.

Obsidian → runtime:

```text
explicit gated ./mm command only
```

A note edit or checkbox must never directly:
- send outreach;
- change canonical email verification;
- alter quote arithmetic;
- bypass suppression;
- override duplicate prevention;
- promote code;
- change production database state.

Closing Obsidian must have zero effect on pipeline survival.

---

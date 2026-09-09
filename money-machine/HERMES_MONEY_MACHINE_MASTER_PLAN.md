---
title: "Hermes Money Machine — Master Execution Plan"
version: "2026-09-04"
owner: "Dion"
primary_orchestrator: "Hermes Agent"
objective: "Build a zero-paid-token-first economic operating system that discovers verified demand, sells useful digital improvements, delivers efficiently, and productizes repeated customer pain."
operating_mode: "evidence-first, human-approved external actions"
budget_policy: "Default paid model/API budget = NZD 0"
status: "execution-ready"
---

# HERMES MONEY MACHINE — MASTER EXECUTION PLAN

## 0. Mission

Build a practical, measurable business operating system rather than a swarm of agents that merely generates activity.

The operating sequence is:

**Demand → Evidence → Opportunity Score → Offer → Demo → Human Approval → Outreach → Conversation → Sale → Delivery → Retainer → Productization → Learning**

The system must maximize **expected economic value**, not token usage, task count, number of agents, or number of generated ideas.

The initial commercial wedge is New Zealand small-business digital modernization:
- website/mobile modernization;
- conversion and enquiry improvements;
- quote/booking workflows;
- follow-up automation;
- CRM/customer pipeline setup;
- customer portals and simple internal tools;
- AI-assisted admin where there is a clear ROI case.

Service work produces early cash flow and, more importantly, evidence about repeated customer pain. Repeated pain is then converted into reusable templates, modules, and eventually vertical software products.

---

# 1. Non-Negotiable Operating Rules

1. **NZD 0 paid-model/API default.**
   - Use local inference and free provider tiers first.
   - A paid provider is disabled unless Dion explicitly authorizes it.

2. **No external commercial send without approval.**
   - Agents may research and draft.
   - Sending marketing emails/messages is a separate approval gate.
   - Do not mass-harvest addresses.
   - Store the lawful/permission basis for each commercial contact.

3. **No purchases, contracts, subscriptions, or financial commitments without approval.**

4. **No destructive production action without approval.**
   - No wiping disks.
   - No deleting client/business data.
   - No force-pushing protected branches.
   - No production deploy that cannot be rolled back.

5. **Evidence before build.**
   - No product gets built merely because an agent thinks it sounds good.
   - Every commercial build requires a problem hypothesis and supporting evidence.

6. **Database is source of truth.**
   - Agent memory is useful but is not the canonical ledger.
   - Prospects, decisions, scores, experiments, revenue and next actions belong in structured data.

7. **One creator should not be the only judge.**
   - A model/agent that creates an important result should not be the sole reviewer of that result.

8. **Prefer reversible actions.**
   - Branches, backups, dry runs, local previews and sandboxing are default.

9. **No vanity automation.**
   - Every recurring workflow must map to one of: revenue, sales conversion, delivery time, retention, product discovery, risk reduction or verified learning.

---

# 2. Recommended Agent Stack

## Tier A — Core

### Hermes Agent — Master Economic Orchestrator
Responsibilities:
- maintain the objective;
- triage opportunities;
- delegate specialist work;
- maintain long-lived memory/skills;
- run recurring internal reviews;
- enforce approval gates;
- keep a decision log;
- choose the next highest-value action.

### goose — General Operator / Research Worker
Responsibilities:
- research;
- structured analysis;
- filesystem/terminal work;
- MCP-enabled operations;
- independent second opinion;
- non-coding workflows.

### OpenCode — Primary Builder
Responsibilities:
- frontend;
- backend;
- scripts;
- tests;
- repo audits;
- code repair;
- prototype and demo generation.

## Tier B — Use On Demand

### OpenHands — Heavy Software Engineering Worker
Use only for:
- contained repository-scale builds;
- multi-file engineering work;
- autonomous bug fixing;
- test/fix loops.

### Browser Use — Browser Execution Specialist
Use only where deterministic browser/API access is insufficient.
Avoid using browser automation as the first solution if a stable API/connector exists.

### n8n — Deterministic Workflow Nervous System
Responsibilities:
- schedules;
- webhooks;
- pipeline state changes;
- CRM/event integration;
- notifications;
- deterministic automation around agents.

### Ollama — Local Inference Layer
Best uses on limited hardware:
- classification;
- extraction;
- deduplication;
- tagging;
- short summaries;
- low-risk repetitive processing.

Do not force a weak local model to perform long-horizon autonomous reasoning just to avoid a free cloud call.

---

# 3. Mac Compatibility Strategy

The installer must detect the hardware before installing.

## Apple Silicon (`arm64`)
Preferred:
- Hermes native install;
- goose native;
- OpenCode native;
- OpenHands CLI optional;
- Browser Use optional;
- Ollama optional;
- Docker/n8n optional.

## Intel (`x86_64`)
Important:
- Native Hermes on Intel macOS is currently an unsupported Hermes platform.
- Do not blindly run the native Hermes installer as the default.
- Preferred Hermes path: supported x86_64 Docker image, provided a functioning Docker runtime is available.
- goose has Intel macOS release/build support.
- OpenCode provides macOS Intel downloads and its terminal installer.
- Ollama can run on Intel macOS using CPU, but performance may be limited.
- Homebrew on Intel macOS is now a lower support tier, especially on legacy/OCLP hardware.

## OpenCore / Older Mac rule
Before heavy installation:
- confirm macOS boots reliably;
- confirm internet;
- confirm at least ~30 GB free for a comfortable setup;
- confirm Command Line Tools/Git;
- confirm the Mac does not repeatedly kernel panic/reboot;
- keep heavy local models optional.

The money machine should work even without a large local model.

---

# 4. Free Inference Router

Use a capability router instead of hard-coding one model forever.

```yaml
routing_policy:
  paid_budget_nzd: 0

  cheap_classification:
    primary: local_ollama
    fallbacks:
      - cloudflare_free
      - openrouter_free

  research:
    primary: best_current_free_reasoner
    fallbacks:
      - gemini_free
      - groq_free
      - opencode_free
      - openrouter_free

  deep_reasoning:
    primary: best_current_free_large_model
    fallbacks:
      - gemini_free
      - groq_free
      - opencode_free

  coding:
    primary: opencode_free_or_best_free_coder
    fallbacks:
      - groq_free
      - local_ollama

  judge:
    rule: "Do not use the creator model as the only judge."

  outage:
    action: "Fail over. Do not silently enable a paid model."
```

## Provider Selection Rules

Score providers on:
- current free quota;
- tool-calling reliability;
- model quality;
- latency;
- context length;
- rate limits;
- data handling requirements;
- ease of fallback;
- account requirements.

Provider availability changes frequently. The daily "Free AI Agent Watch" should identify meaningful changes, but the operating stack should not depend on a single temporary promotion.

---

# 5. Canonical Business Database

Create one persistent database named conceptually `money_machine`.

Recommended initial implementation:
- SQLite for the first local version;
- migrate to Postgres/Supabase only when multi-device, hosted or concurrent access is necessary.

Core tables:

## `industries`
- id
- name
- region
- market_notes
- pain_score
- frontend_weakness_score
- backend_pain_score
- ability_to_pay_score
- recurring_revenue_score
- competition_score
- build_ease_score
- total_score
- evidence
- last_reviewed

## `businesses`
- id
- name
- industry_id
- region
- public_website
- source
- discovered_at
- current_status

## `audits`
- business_id
- mobile_quality
- conversion_quality
- quote_flow
- booking_flow
- seo_basics
- trust_signals
- page_speed
- accessibility
- broken_paths
- follow_up_quality
- crm_signal
- automation_opportunities
- evidence
- opportunity_score

## `contacts`
- business_id
- contact_name
- role
- address_or_channel
- source
- contact_permission_basis
- do_not_contact
- last_verified

## `offers`
- business_id
- problem
- proposed_outcome
- implementation_scope
- price_test
- estimated_delivery_effort
- expected_value
- offer_score

## `outreach`
- offer_id
- draft
- approved_by_human
- sent_at
- reply_status
- reply_class
- next_action
- unsubscribe_status

## `projects`
- client
- scope
- repository
- status
- estimated_hours
- actual_hours
- delivery_date
- qa_status

## `revenue`
- project
- quoted
- invoiced
- collected
- recurring_mrr
- costs
- gross_margin

## `experiments`
- hypothesis
- target_segment
- variable
- expected_result
- actual_result
- decision
- lesson

## `product_signals`
- repeated_problem
- count
- customers_affected
- willingness_to_pay_evidence
- build_reusability
- productization_score
- next_test

## `agent_runs`
- task
- agent
- model
- cost
- time
- output_quality
- outcome
- failure_reason

---

# 6. Opportunity Scoring

Every market opportunity receives a 0–100 score.

Example weighted score:

- demonstrated pain: 20
- ability to pay: 15
- ease of identifying prospects: 10
- visible digital weakness: 10
- urgency: 10
- repeatability: 10
- recurring revenue potential: 10
- ease of building: 5
- low competition / weak incumbent solution: 5
- compliance/sales friction: 5

Hard rejection conditions:
- no identifiable buyer;
- no evidence of pain;
- unclear measurable value;
- expensive build before customer validation;
- legal/compliance problem;
- highly commoditized offer with no differentiation;
- ongoing support burden overwhelms likely margin.

---

# 7. Agent Roles and Deliverables

## A. MARKET_SCOUT
Input:
- industry;
- region;
- target business profile.

Output:
- evidence pack;
- common pain;
- current solutions;
- competitor landscape;
- public demand signals;
- likely decision-maker;
- initial opportunity score.

Never output a giant list with no ranking.

## B. BUSINESS_DISCOVERY
Input:
- approved target segment.

Output:
- candidate business records;
- only public business data needed for qualification;
- source/evidence;
- no mass personal-data harvesting.

## C. DIGITAL_AUDITOR
Checks:
- website exists;
- mobile;
- speed;
- broken links;
- clarity of service;
- CTA;
- enquiry path;
- booking;
- quote path;
- online payment relevance;
- trust/reviews;
- SEO basics;
- structured data;
- customer journey;
- repeated manual steps;
- CRM/follow-up indicators;
- opportunities for useful automation.

Output:
- concrete defects;
- screenshots/evidence where appropriate;
- probable business impact;
- opportunity score;
- "do nothing" recommendation when no clear value exists.

## D. OFFER_ARCHITECT
Transforms:
`observed problem → business impact → concrete outcome → scope → price test → proof/demo`.

Avoid generic "AI transformation" language.

## E. DEMO_BUILDER
OpenCode/OpenHands creates:
- isolated prototype;
- no production mutation;
- screenshots;
- before/after comparison;
- short technical scope;
- rollback/deployment plan.

## F. JUDGE
Independent reviewer asks:
- Is the evidence real?
- Is the conclusion overstated?
- Is the proposed fix relevant?
- Is the price plausible?
- Is a demo worth building?
- Is contact appropriate?
- Is the deliverable actually ready?

## G. OUTREACH_DRAFTER
Produces:
- concise personalized message;
- references only verified facts;
- no fake familiarity;
- no fabricated metrics;
- explicit value;
- low-friction next action.

**Sending is human-gated.**

## H. DELIVERY_AGENT
After sale:
- creates branch/workspace;
- task decomposition;
- build;
- tests;
- visual QA;
- accessibility checks;
- security checks;
- performance checks;
- documentation;
- handover;
- backup/rollback.

## I. RETENTION_AGENT
Looks for:
- maintenance;
- analytics;
- conversion improvements;
- content updates;
- automation maintenance;
- workflow support;
- measurable next improvement.

## J. PRODUCT_MINER
Every week:
- cluster repeated problems;
- count frequency;
- measure price acceptance;
- identify reusable components;
- recommend templates/modules/SaaS only when evidence threshold is reached.

---

# 8. Economic Scheduler

Hermes should maintain a ranked queue.

For every candidate task, calculate:

`EV = expected_revenue × probability_of_success × strategic_reuse × recurrence_multiplier`

Then divide by:
- agent effort;
- human effort;
- technical risk;
- sales friction;
- support burden.

Priority:
1. revenue already near closing;
2. existing client retention;
3. qualified prospect with verified pain;
4. reusable delivery improvement;
5. high-evidence market experiment;
6. speculative research.

Speculative idea generation is last.

---

# 9. First Commercial Engine

## NZ Digital Revenue Modernization

Target:
- small service businesses;
- trades;
- local professional services;
- operators with visible customer-journey friction;
- businesses with enough economics to pay for improvement.

Sell outcomes:
- better enquiry conversion;
- faster quote requests;
- automated confirmations;
- booking;
- lead tracking;
- follow-up;
- better mobile experience;
- simpler admin;
- client/customer portal where relevant.

Do not sell "agents" as the product unless the customer actually needs an agent.

### Offer Ladder

#### Entry: Revenue Rescue
- mobile/UX fixes;
- contact/enquiry improvement;
- core conversion cleanup;
- basic measurement.

#### Core: Digital Upgrade
- redesigned conversion flow;
- quote/booking;
- CRM/pipeline;
- automation;
- integration.

#### Recurring: Digital Operator
- monitoring;
- maintenance;
- small improvements;
- workflow upkeep;
- lead/process optimization;
- monthly report.

Price is tested from market evidence. Do not permanently lock pricing before sufficient sales conversations.

---

# 10. Productization Flywheel

Trigger productization when:
- the same pain appears repeatedly;
- multiple customers are willing to pay;
- at least part of the solution is reusable;
- support burden is manageable.

Flow:

`service pain → cluster → reusable component → template → standard product → vertical software`

Do not create SaaS because it is fashionable.

---

# 11. Compliance and Reputation Controls

Before any external commercial message:
1. verify the contact source;
2. store why contact is permissible;
3. check do-not-contact state;
4. check message relevance;
5. identify the sender accurately;
6. provide an appropriate unsubscribe/stop mechanism where required;
7. human approves the send.

Never:
- scrape private contact details;
- bypass platform anti-spam systems;
- fake testimonials;
- fake customer numbers;
- impersonate people;
- claim a site/problem was inspected when it was not;
- send hundreds of identical messages.

High-quality qualification beats volume.

---

# 12. Installation Architecture

Recommended local folder:

```text
~/MoneyMachine/
  README.md
  config/
  data/
  database/
  evidence/
  prospects/
  demos/
  projects/
  experiments/
  reports/
  logs/
  backups/
  scripts/
  exports/
```

Hermes state:
`~/.hermes/`

Do not merge Hermes internal state with business data. Business truth belongs under `~/MoneyMachine` or a dedicated database.

---

# 13. Mac Bootstrap Phases

## Phase M0 — Boot Health
Required:
- Mac can boot reliably;
- network stable;
- correct date/time;
- at least 10 GB free minimum for light setup;
- ~30 GB+ preferred for full setup;
- backup important files.

## Phase M1 — Repair Shell PATH
Use:
```bash
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin:$HOME/.local/bin:$HOME/bin:$PATH"
```

Then verify:
```bash
/usr/bin/uname -m
/usr/bin/sw_vers
/usr/bin/curl --version
/usr/bin/git --version
/bin/bash --version
/bin/zsh --version
```

If `/usr/bin/curl`, `/bin/bash` or `/bin/zsh` are truly absent on a normal macOS install, stop. That indicates a damaged base OS or unusual environment; do not try to fix it by downloading random replacements.

## Phase M2 — Apple Command Line Tools
Check:
```bash
xcode-select -p
git --version
```

If missing:
```bash
xcode-select --install
```

Complete Apple's installer, then rerun the bootstrap.

## Phase M3 — Core Agents
Install:
- goose
- OpenCode

Then verify their binaries before moving on.

## Phase M4 — Hermes
Apple Silicon:
- official native Hermes installer.

Intel:
- do not use native Hermes as the default;
- use Hermes x86_64 Docker image if Docker is working.

## Phase M5 — Optional Agent Tools
- OpenHands
- Browser Use

## Phase M6 — Local Models
Only if macOS and free disk are suitable:
- Ollama;
- begin with a small model;
- never download tens of GB automatically.

## Phase M7 — Workflow Layer
- Docker runtime;
- n8n persistent volume/container;
- do not expose n8n publicly until authentication/networking are deliberately configured.

## Phase M8 — MoneyMachine Workspace
Create directory structure.
Initialize Git for configuration/scripts only.
Do not commit secrets.

---

# 14. Verification Gates

## Gate 1 — System
Pass:
- architecture known;
- macOS known;
- shell tools found;
- Git works;
- disk space known.

## Gate 2 — Agents
At least:
- goose responds to `--help` or version;
- OpenCode responds;
- Hermes works either native or containerized.

## Gate 3 — Model
One zero-paid path completes a normal prompt.

## Gate 4 — Tooling
Agent can:
- read a test file;
- create a file inside `~/MoneyMachine/sandbox`;
- inspect a git repository;
- avoid files outside its allowed test workspace.

## Gate 5 — Browser
Only if needed:
- browser automation doctor passes;
- a harmless public test page can be opened.

## Gate 6 — Workflow
n8n starts on localhost;
- persistent volume survives restart;
- no public internet exposure by default.

## Gate 7 — Business Pipeline
One dummy business can move through:
`discovered → audited → scored → offer drafted → human review`.

Do not begin real outreach before this works.

---

# 15. First 30 Days

## Days 1–3
- stabilize Mac;
- install core;
- verify free inference;
- create MoneyMachine workspace;
- create database;
- define approval gates.

## Days 4–7
Research 20–30 NZ industries.
Score each.
Keep only top 3–5.

Required output:
- evidence;
- score;
- top pain;
- ideal customer profile;
- best entry offer;
- reasons to reject the other industries.

## Week 2
For top industries:
- discover candidate businesses;
- audit;
- score;
- create top 25–50 deeply qualified opportunities;
- make 3–5 reusable demo patterns.

## Week 3
Create a small high-quality outreach batch.
For each candidate:
- evidence;
- personalized problem;
- proposed fix;
- demo if economically justified;
- contact compliance basis;
- draft.
Human approves each external send.

## Week 4
Review:
- positive response rate;
- meetings;
- quotes;
- objections;
- paid work;
- estimated margin;
- agent effort;
- human effort.

Change market/offer/message based on evidence.

---

# 16. Days 31–90

## Month 2 — Delivery Factory
Turn sold jobs into repeatable delivery:
- standard repo template;
- component library;
- QA checklist;
- deployment checklist;
- handover template;
- retainer offer.

Measure:
`lead → close → hours → margin → retention`.

## Month 3 — Product Miner
Cluster customer pain.
Require evidence before productization.

Rank repeated problems:
`frequency × willingness_to_pay × reusability × recurrence ÷ support_cost`.

Build only the highest-scoring reusable solution.

---

# 17. KPI Dashboard

Primary:
- cash collected;
- recurring monthly revenue;
- gross margin;
- qualified opportunities;
- positive replies;
- calls/meetings;
- proposals;
- close rate;
- delivery hours;
- retention.

Secondary:
- opportunity-to-demo rate;
- demo-to-reply lift;
- agent cost;
- agent failure rate;
- average time per audit;
- reusable component count.

Avoid vanity metrics:
- number of prompts;
- number of agents;
- number of generated ideas;
- raw email count;
- lines of code.

---

# 18. Weekly Hermes Review

Every week Hermes should produce:

1. **Revenue**
   - collected;
   - pending;
   - recurring.

2. **Pipeline**
   - best opportunities;
   - bottleneck stage;
   - stale records.

3. **Experiments**
   - what was tested;
   - actual result;
   - keep/change/kill.

4. **Agent quality**
   - failures;
   - hallucinations;
   - repeated manual corrections;
   - provider problems.

5. **Product signals**
   - repeated pain;
   - reusable components;
   - SaaS candidates.

6. **Next 7 days**
   - only highest-EV actions.

---

# 19. Failure Recovery

If an agent install fails:
- do not keep rerunning blindly;
- capture exact command;
- capture exit code;
- capture last 100 log lines;
- verify architecture and OS;
- verify disk;
- verify PATH;
- verify upstream currently supports platform.

If a model fails:
- mark provider unhealthy;
- fall back to next zero-cost provider;
- do not silently enable paid billing.

If an outreach experiment fails:
- inspect targeting;
- inspect evidence quality;
- inspect offer;
- inspect message;
- inspect channel.
Do not conclude "send more" without diagnosis.

If an agent damages a working tree:
- stop;
- preserve logs;
- use git diff/status;
- revert only the agent's changes;
- do not delete unrelated user work.

---

# 20. What ChatGPT Can Execute vs Local Mac Execution

ChatGPT can execute in-chat work such as:
- current web research;
- opportunity research;
- planning;
- drafting;
- file generation;
- analysis of files you provide;
- work through connected apps where a compatible connector exists.

ChatGPT does not automatically obtain shell control of a Mac merely because the Mac is online.

Local Mac actions are executed by:
- you pasting a command;
- the supplied bootstrap script;
- Hermes/goose/OpenCode running locally;
- an explicitly connected/authorized environment.

Therefore this plan separates **decision/orchestration** from **machine execution** instead of pretending remote access exists.

---

# 21. Immediate Execution Order

1. Get Mac online and boot-stable.
2. Download the execution pack.
3. Run:
   `bash ~/Downloads/mac_bootstrap_money_machine.sh preflight`
4. If Command Line Tools are requested, install them and rerun.
5. Run:
   `bash ~/Downloads/mac_bootstrap_money_machine.sh core`
6. Verify goose + OpenCode.
7. Run:
   `bash ~/Downloads/mac_bootstrap_money_machine.sh hermes`
8. Configure one free model path and test one normal conversation.
9. Only then run:
   `bash ~/Downloads/mac_bootstrap_money_machine.sh full`
10. Create the business database.
11. Start industry scoring.
12. Begin with a small, human-reviewed commercial batch.
13. Measure economic results.
14. Productize repeated demand.

---

# 22. Sources Verified 2026-09-04

Official/current sources checked when this plan was generated:

- Hermes docs: https://hermes-agent.nousresearch.com/docs/
- Hermes installation: https://hermes-agent.nousresearch.com/docs/getting-started/installation/
- Hermes platform support: https://hermes-agent.nousresearch.com/docs/getting-started/platform-support
- Hermes Docker: https://hermes-agent.nousresearch.com/docs/user-guide/docker
- goose repository/docs: https://github.com/aaif-goose/goose
- OpenCode docs: https://opencode.ai/docs
- OpenHands docs: https://docs.openhands.dev/openhands/usage/cli/installation
- Browser Use docs: https://docs.browser-use.com/open-source/browser-use-cli
- Ollama macOS docs: https://github.com/ollama/ollama/blob/main/docs/macos.mdx
- n8n repository/docs: https://github.com/n8n-io/n8n
- Homebrew support/install docs: https://docs.brew.sh/Installation

Re-verify commands before major future rebuilds because agent projects and free-provider terms change rapidly.

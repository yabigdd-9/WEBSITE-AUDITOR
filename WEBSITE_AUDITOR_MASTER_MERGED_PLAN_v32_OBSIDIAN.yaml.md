# WEBSITE-AUDITOR MASTER MERGED PLAN
# Agent-ready YAML execution plan
# File: WEBSITE_AUDITOR_MASTER_MERGED_PLAN.yaml.md

```yaml
plan:
  name: "WEBSITE-AUDITOR Master Merged Plan"
  version: "32.0"
  status: "CANONICAL_EXECUTION_PLAN"
  generated_from:
    - "Latest 5 Cline Desktop sessions"
    - "Existing WEBSITE-AUDITOR repository plans"
    - "Current live WEBSITE-AUDITOR goals"
  primary_workspace: "/Users/dd/WEBSITE-AUDITOR"
  experimental_cline_workspace: "/Users/dd/Downloads/WEBSITE-AUDITOR-master"
  execution_mode: "local-first, zero-paid-token, evidence-first, supervised, obsidian-operator-workspace"
  paid_allowed: false
  max_cost_usd: 0
  outreach_default_enabled: false
  destructive_actions_default_allowed: false

objectives:
  primary:
    - "Continuously discover New Zealand businesses with weak or outdated websites."
    - "Verify business identity and contact information before outreach eligibility."
    - "Audit websites using deterministic evidence-first checks."
    - "Prioritize leads by commercial opportunity, not only technical weakness."
    - "Generate remediation plans, previews, demos, screenshots, and deterministic quotes."
    - "Draft personalized outreach backed by real evidence."
    - "Operate continuously with crash recovery, retries, health checks, and bounded resources."
    - "Use local/free models only, with no silent paid fallback."
    - "Continuously improve through measured challenger experiments, never uncontrolled self-modification."
  success_definition:
    - "Pipeline survives restarts without losing queued work."
    - "Every material audit finding has evidence and confidence."
    - "Every contact has provenance and a verification state."
    - "Every quote is deterministic and inspectable."
    - "Every autonomous change is tested before merge."
    - "No paid model/API usage is possible without explicit future policy change."

non_negotiables:
  zero_cost:
    paid_allowed: false
    max_cost_usd: 0
    rules:
      - "Never silently fall back to a paid provider."
      - "When all free providers are unavailable, defer the job."
      - "Prefer deterministic Python over LLM calls."
      - "Local inference is preferred for bulk classification, drafting, and summarization."
  repository_safety:
    rules:
      - "Do not overwrite /Users/dd/WEBSITE-AUDITOR with the Downloads experimental copy."
      - "Do not merge experimental files directly into master."
      - "Create isolated branches/worktrees for implementation."
      - "Back up databases and important outputs before migrations."
      - "Never allow two coding agents to edit the same file concurrently."
  outreach_safety:
    send_enabled: false
    rules:
      - "Do not send outreach unless transport is explicitly enabled."
      - "No guessed email pattern is automatically considered verified."
      - "Catch-all does not equal verified."
      - "NO_VERIFIED_EMAIL is an acceptable final state."
      - "Respect suppression, duplicate prevention, cooldown, bounce, and stop-on-response rules."
  production_change_policy:
    rules:
      - "No autonomous direct-to-master edits."
      - "Every code change must pass tests and quality gates."
      - "No self-improvement change may enter production without measurable improvement."
      - "Human review remains required for high-risk changes."

repository_reconciliation:
  phase_id: "P0"
  priority: "CRITICAL"
  goal: "Create one trustworthy canonical codebase before further upgrades."
  source_of_truth: "/Users/dd/WEBSITE-AUDITOR"
  experimental_source: "/Users/dd/Downloads/WEBSITE-AUDITOR-master"
  branch_to_create: "upgrade/cline-master-merge"
  preserve_first:
    - "SQLite databases"
    - "master opportunity database"
    - "email verification state"
    - "audit outputs"
    - "approval queues"
    - "existing reports"
    - "current configuration"
  inspect_for_selective_port:
    - "DEEP_UPGRADE_RESEARCH.md"
    - "UPGRADE_RESEARCH_2026.md"
    - "UPGRADE_RESEARCH_2026.yaml"
    - "DEEP_UPGRADE_PLAN.md"
    - "IMPLEMENTATION_PLAN.md"
    - "EXECUTION_PLAN.md"
    - "docker-stack.yaml"
    - "upgrade-backlog.yaml"
    - ".gitleaks.toml"
    - "auditor_toolkit/identity.py"
    - "auditor_toolkit/verify.py"
    - "auditor_toolkit/fetch_chain.py"
    - "toolkit_tests/test_p0_upgrades.py"
  rules:
    - "Port only reviewed improvements."
    - "Do not replace working production code with unverified prototypes."
    - "Record each accepted/rejected experimental change in CHANGELOG.md."
  gate:
    - "Canonical repo preserved."
    - "Experimental merge branch created."
    - "No production data loss."
    - "All imported changes are traceable."

phase_1_baseline:
  phase_id: "P1"
  priority: "CRITICAL"
  goal: "Establish a fully reproducible green baseline."
  python:
    target_version: "3.11"
    venv: ".venv"
    requirements_policy: "one source of truth"
  actions:
    - "Repair broken virtual environment references."
    - "Install dependencies from the canonical requirements source."
    - "Remove Python 3.9 assumptions."
    - "Standardize README, CI, local venv, and tooling on Python 3.11."
    - "Run all existing tests."
    - "Record current test failures before modifying behavior."
    - "Fix dependency and import failures."
    - "Remove tracked __pycache__, venvs, and generated state files."
    - "Add .env.example."
    - "Harden .gitignore."
  baseline_metrics:
    tests_total: null
    tests_pass: null
    tests_fail: null
    audit_runtime_seconds: null
    sites_per_hour: null
    email_verified_rate: null
    queue_failures: null
    memory_mb: null
    disk_free_gb: null
  security:
    add:
      - "gitleaks"
      - "pip-audit"
      - "secret scanning in CI"
    rules:
      - "Do not hide security failures with '|| true'."
      - "Any intentionally non-blocking security job must be explicitly labeled informational."
      - "Rotate any exposed credentials before relying on them."
  gate:
    - "Tests green or every remaining failure explicitly documented and accepted."
    - "./mm doctor passes except clearly optional integrations."
    - "Python 3.11 confirmed."
    - "No active secrets committed."
    - "Working tree clean."

phase_2_code_consolidation:
  phase_id: "P2"
  priority: "HIGH"
  goal: "Remove duplicated implementations and establish obvious canonical modules."
  canonical_direction:
    audit_engine: "auditor_toolkit + thin CLI layer"
    cli: "./mm"
  review_for_deprecation:
    - "ultimate_auditor.py"
    - "website_auditor_enhanced.py"
    - "duplicate legacy pipeline paths"
    - "duplicate control-plane implementations"
  documentation:
    canonical_docs:
      - "MASTER_PLAN.md"
      - "MASTER_PLAN.yaml"
      - "CURRENT_STATE.md"
      - "CHANGELOG.md"
    archive_destination: "docs/archive/plans/"
  gate:
    - "One documented canonical audit engine."
    - "One documented operator CLI."
    - "Legacy paths marked deprecated rather than silently deleted."

phase_3_continuous_control_plane:
  phase_id: "P3"
  priority: "CRITICAL"
  goal: "Make the pipeline survive unattended operation."
  architecture:
    queue: "SQLite leased work queue"
    replace_with_redis_now: false
  required_cli:
    - "./mm supervisor start"
    - "./mm supervisor stop"
    - "./mm supervisor restart"
    - "./mm supervisor status"
    - "./mm supervisor health"
    - "./mm supervisor logs"
  features:
    - "PID lock"
    - "single-instance protection"
    - "SIGTERM/SIGINT graceful shutdown"
    - "worker heartbeats"
    - "stale-worker recovery"
    - "job leases"
    - "lease expiry recovery"
    - "bounded retries"
    - "exponential backoff"
    - "jitter"
    - "circuit breakers"
    - "dead-letter queue"
    - "log rotation"
    - "log retention"
    - "disk-space guard"
    - "network availability guard"
    - "health snapshots"
    - "crash recovery"
  worker_types:
    - "DISCOVERY"
    - "IDENTITY"
    - "FETCH"
    - "AUDIT"
    - "CONTACT"
    - "VERIFY"
    - "SCORE"
    - "DEMO"
    - "QUOTE"
    - "DRAFT"
    - "QA"
    - "OUTCOME"
  job_schema:
    required_fields:
      - "job_id"
      - "type"
      - "business_id"
      - "created_at"
      - "lease_owner"
      - "lease_until"
      - "attempt"
      - "max_attempts"
      - "status"
      - "last_error"
      - "evidence_refs"
  acceptance_test:
    - "Start pipeline."
    - "Queue active work."
    - "Force-kill supervisor."
    - "Restart supervisor."
    - "Verify jobs resume from durable state."
    - "Verify no duplicate sends/actions occur."
  gate:
    - "Crash/restart recovery demonstrated."
    - "No lost jobs."
    - "No duplicate leased work."
    - "Health status visible from CLI."

phase_4_audit_engine:
  phase_id: "P4"
  priority: "HIGH"
  goal: "Improve audit accuracy and evidence while keeping browser use efficient."
  keep:
    - "Playwright"
    - "axe-core"
    - "deterministic HTML/SEO checks"
    - "BeautifulSoup"
    - "trafilatura"
    - "HTTP checks"
  add_or_finish:
    - "Lighthouse / Core Web Vitals"
    - "Lychee deterministic broken-link validation"
    - "canonical domain resolution"
    - "security header grading"
    - "robots.txt checks"
    - "sitemap checks"
    - "Schema.org structured data checks"
    - "contact path detection"
    - "booking detection"
    - "quote-form/calculator detection"
    - "mobile/responsive checks"
    - "HTML validation"
    - "SSL/TLS checks"
  canonical_domain:
    library: "tldextract"
    example:
      inputs:
        - "www.foo.co.nz"
        - "https://foo.co.nz/page"
        - "foo.co.nz"
      canonical: "foo.co.nz"
  fetch_chain:
    levels:
      - id: "L1"
        method: "HTTP"
      - id: "L2"
        method: "lightweight JS-capable fetch/browser"
      - id: "L3"
        method: "Playwright"
    rule: "Do not launch Playwright for every website."
  gate:
    - "Audit output remains deterministic for deterministic checks."
    - "Browser fallback only used where cheaper levels fail or JS rendering is required."
    - "Every new check has tests."

phase_5_evidence_first_findings:
  phase_id: "P5"
  priority: "CRITICAL"
  goal: "Make every material finding explainable and auditable."
  finding_schema:
    finding_id: null
    domain: null
    category: null
    issue: null
    severity: null
    confidence: null
    evidence:
      source: null
      selector: null
      observed: null
    business_impact:
      type: null
    remediation:
      action: null
      automation: null
    estimated_effort:
      band: null
  rules:
    - "Never create the score first and explanation second."
    - "Score deductions must be derived from findings."
    - "Material findings require evidence."
    - "Confidence must be stored where uncertainty exists."
  gate:
    - "Every score deduction links back to a finding."
    - "Every finding has evidence or is explicitly marked heuristic."

phase_6_nz_business_discovery:
  phase_id: "P6"
  priority: "HIGH"
  goal: "Continuously discover relevant NZ businesses without duplicate waste."
  discovery_lanes:
    - "NZBN"
    - "SearXNG"
    - "industry directories"
    - "public business directories"
    - "public business websites"
    - "search engines"
    - "permitted OSM-derived sources"
    - "existing lead database"
  business_schema:
    business_id: null
    legal_name: null
    trading_name: null
    nzbn: null
    domain: null
    industry: null
    region: null
    city: null
    source: null
    source_url: null
    confidence: null
    last_seen: null
  early_filters:
    - "duplicate business"
    - "duplicate domain"
    - "same business across subdomains"
    - "dead or inactive company"
    - "directory/listing site"
    - "large corporate outside target market"
  rule: "Deduplicate before expensive audit stages."

phase_7_identity_resolution:
  phase_id: "P7"
  priority: "HIGH"
  goal: "Create reliable links between business, legal identity, website, and email domain."
  relationships:
    - "business ↔ NZBN"
    - "business ↔ legal name"
    - "business ↔ trading name"
    - "business ↔ domain"
    - "business ↔ website"
    - "business ↔ email domain"
    - "business ↔ region"
  confidence_example:
    identity_confidence: 0.94
    signals:
      domain_name_match: true
      website_brand_match: true
      nzbn_match: true
      address_match: false
  rule: "Use weighted evidence and confidence rather than one weak string match."
  gate:
    - "Low-confidence identity does not automatically become outreach eligible."

phase_8_email_finder_v2:
  phase_id: "P8"
  priority: "CRITICAL"
  goal: "Find authentic business contacts with strict provenance."
  stages:
    - "business identity"
    - "canonical domain"
    - "first-party website discovery"
    - "contact/about/team extraction"
    - "visible email extraction"
    - "candidate generation"
    - "DNS"
    - "MX"
    - "disposable-domain check"
    - "optional SMTP evidence"
    - "company/person match"
    - "confidence scoring"
    - "eligibility"
  states:
    - "VERIFIED"
    - "STRONG_EVIDENCE"
    - "CATCH_ALL"
    - "UNVERIFIED"
    - "NO_VERIFIED_EMAIL"
    - "INVALID"
  strict_rules:
    - "Pattern guess != verified."
    - "Catch-all != verified."
    - "MX exists != mailbox verified."
    - "NO_VERIFIED_EMAIL is a valid outcome."
    - "SMTP probing is optional and must not become the single source of truth."
  gate:
    - "Every eligible email has provenance."
    - "Verification state is explicit."
    - "No guessed addresses pass as verified."

phase_9_opportunity_scoring:
  phase_id: "P9"
  priority: "HIGH"
  goal: "Prioritize businesses that are commercially worthwhile, not only technically weak."
  scores:
    technical_score:
      question: "How weak is the current website?"
    opportunity_score:
      question: "How worthwhile is this potential customer?"
  opportunity_inputs:
    - "business activity"
    - "industry"
    - "locality"
    - "service value"
    - "website need"
    - "conversion weakness"
    - "contact confidence"
    - "remediation difficulty"
    - "likely project size"
    - "digital maturity"
    - "evidence confidence"
  conceptual_formula: "need * business_value * contactability * fixability * confidence / delivery_effort"
  rules:
    - "Formula must be deterministic and inspectable."
    - "LLMs may explain the score but must not secretly invent the score."
  gate:
    - "Score calculation can be reproduced from stored inputs."

phase_10_remediation_engine:
  phase_id: "P10"
  priority: "HIGH"
  goal: "Turn findings into real implementation artifacts rather than Markdown-only suggestions."
  automation_classes:
    - "AUTO_SAFE"
    - "AUTO_PREVIEW"
    - "HUMAN_REVIEW"
    - "CLIENT_ACCESS_REQUIRED"
    - "UNSUPPORTED"
  examples:
    missing_meta_description: "AUTO_PREVIEW"
    poor_title: "AUTO_PREVIEW"
    broken_internal_link: "AUTO_PREVIEW"
    missing_hsts: "HUMAN_REVIEW"
    many_html_validation_errors: "HUMAN_REVIEW"
    cms_plugin_vulnerability: "CLIENT_ACCESS_REQUIRED"
  valid_artifacts:
    - "patch"
    - "HTML"
    - "CSS"
    - "configuration snippet"
    - "redirect map"
    - "replacement component"
    - "preview site"
    - "implementation checklist"
  rule: "A Markdown explanation alone is not a completed fix."

phase_11_demo_factory:
  phase_id: "P11"
  priority: "HIGH"
  goal: "Automatically create proof of improvement for strong opportunities."
  flow:
    - "audit"
    - "select high-value fixes"
    - "create local reconstruction/patch"
    - "run tests"
    - "render"
    - "capture before screenshot"
    - "capture after screenshot"
    - "compare"
  measurements:
    - "performance"
    - "accessibility"
    - "broken links"
    - "SEO checks"
    - "mobile rendering"
    - "conversion elements"
  rules:
    - "Never fabricate an improvement."
    - "Before/after claims must have evidence."
  gate:
    - "Demo renders successfully."
    - "QA passes."
    - "Before/after artifact is traceable to the source audit."

phase_12_quote_engine:
  phase_id: "P12"
  priority: "HIGH"
  goal: "Generate deterministic quote bands."
  inputs:
    - "site type"
    - "page count"
    - "number of defects"
    - "difficulty"
    - "CMS"
    - "forms"
    - "booking"
    - "calculator"
    - "SEO repairs"
    - "performance work"
    - "rebuild requirement"
  outputs:
    package: null
    estimated_hours: null
    price_band: null
    confidence: null
    included: []
    excluded: []
    assumptions: []
  package_examples:
    - "Quick Website Rescue"
    - "Technical Repair"
    - "Conversion Upgrade"
    - "Landing Page Rebuild"
    - "Booking Upgrade"
    - "Quote Calculator"
    - "Full Website Modernisation"
  rules:
    - "LLM may explain quote."
    - "LLM must not determine quote."
    - "Pricing must come from versioned rules/tables."

phase_13_prospect_packet:
  phase_id: "P13"
  priority: "HIGH"
  goal: "Create one complete reviewable sales unit per qualified prospect."
  schema:
    business: null
    website: null
    contact: null
    email_confidence: null
    audit_score: null
    opportunity_score: null
    top_problems: []
    before_images: []
    after_images: []
    recommended_package: null
    quote_band: null
    proof: []
    evidence: []
    draft_message: null
    qa_status: null
    approval_status: null
  gate:
    - "No prospect reaches outreach without a complete packet."

phase_14_outreach_engine:
  phase_id: "P14"
  priority: "HIGH"
  goal: "Generate safe, evidence-backed, controlled outreach."
  default:
    send_enabled: false
  flow:
    - "draft"
    - "fact check"
    - "proofer"
    - "compliance check"
    - "duplicate check"
    - "approval policy"
    - "transport"
    - "result tracking"
  controls:
    - "daily cap"
    - "per-domain cap"
    - "cooldown"
    - "suppression list"
    - "unsubscribe handling"
    - "bounce suppression"
    - "duplicate prevention"
    - "reply detection"
    - "stop-on-response"
  rules:
    - "Agents may not bypass transport policy."
    - "Send remains disabled until intentionally enabled."

phase_15_free_model_router:
  phase_id: "P15"
  priority: "HIGH"
  goal: "Use intelligence where needed without overloading the Mac or creating paid spend."
  deterministic_first:
    tasks:
      - "HTTP"
      - "DNS"
      - "MX"
      - "parsing"
      - "scoring"
      - "queue management"
      - "pricing"
      - "deduplication"
      - "rate limiting"
      - "scheduling"
      - "status"
      - "evidence handling"
  local_model_tasks:
    - "classification"
    - "summarization"
    - "drafting"
    - "simple remediation suggestions"
  route:
    - "DETERMINISTIC_CODE"
    - "LOCAL_FREE_MODEL"
    - "FREE_EXTERNAL_ROUTE_1"
    - "FREE_EXTERNAL_ROUTE_2"
    - "DEFER"
  forbidden:
    - "Silent paid fallback."
    - "Running multiple large local models concurrently on 8GB Intel Mac."
    - "Using an LLM for work deterministic code can do reliably."
  config:
    paid_allowed: false
    max_cost_usd: 0
  resource_policy:
    max_large_local_models_concurrent: 0
    preferred_small_local_models_concurrent: 1

phase_16_agent_team:
  phase_id: "P16"
  priority: "HIGH"
  goal: "Use multiple agents without concurrent-edit corruption."
  hierarchy:
    orchestrator: "Hermes"
    roles:
      - "RESEARCHER"
      - "CODER"
      - "OPERATOR"
      - "JUDGE"
      - "PROOFER"
      - "INTEGRATOR"
  coding_rules:
    - "One task per coding agent."
    - "One branch/worktree per coding agent."
    - "Never allow multiple writers to modify the same file concurrently."
    - "Judge reviews evidence/tests, not agent confidence."
    - "Integrator alone merges accepted changes."
  gate:
    - "No shared-file concurrent writes."
    - "All merges have test evidence."

phase_17_observability:
  phase_id: "P17"
  priority: "MEDIUM"
  goal: "Get useful operational visibility without excessive infrastructure."
  start_with:
    - "state/health.json"
    - "state/metrics.jsonl"
    - "state/errors.jsonl"
    - "state/worker-heartbeats/"
    - "state/dead-letter/"
  cli:
    - "./mm health"
    - "./mm status"
    - "./mm metrics"
    - "./mm errors"
    - "./mm queue"
    - "./mm dead-letter"
  business_metrics:
    - "discovered businesses/day"
    - "audited/day"
    - "qualified/day"
    - "verified contacts/day"
    - "demos/day"
    - "drafts/day"
    - "approved/day"
    - "sent/day"
    - "replies"
    - "positive replies"
    - "appointments"
    - "jobs"
    - "revenue"
  system_metrics:
    - "worker crashes"
    - "queue age"
    - "failure rate"
    - "retry rate"
    - "model failures"
    - "browser failures"
  defer_until_needed:
    - "Prometheus"
    - "Grafana"
    - "Loki"
    - "Langfuse"

phase_18_self_improvement:
  phase_id: "P18"
  priority: "MEDIUM"
  goal: "Improve using real measured outcomes without autonomous production drift."
  feedback_capture:
    - "finding accepted/rejected"
    - "email verified/bounced"
    - "prospect approved/rejected"
    - "draft edited"
    - "reply received"
    - "positive reply"
    - "job won"
    - "price accepted"
    - "price rejected"
  golden_dataset: true
  challenger_flow:
    - "propose"
    - "create branch"
    - "test"
    - "evaluate"
    - "shadow run"
    - "compare metrics"
    - "judge"
    - "merge or reject"
  rules:
    - "No direct autonomous modification of production."
    - "No measurable improvement = no merge."
    - "Regressions block promotion."

tool_decisions:
  keep_now:
    gitleaks: "P0/P1"
    python_3_11: "P0/P1"
    tldextract: "P4/P7"
    lychee: "P4"
    playwright: "P4/P11"
    axe_core: "P4/P11"
    lighthouse: "P4"
    nzbn: "P6/P7"
    searxng: "P6"
    sqlite_leased_queue: "P3"
    hermes_supervisor_direction: "P3/P16"
    deterministic_email_consensus: "P8"
    litestream_local_backup: "P3/P17"
    prompt_eval_dataset: "P18"
    obsidian_operator_workspace: "P3/P17/P18"
  benchmark_first:
    crawl4ai: true
    lightpanda: true
  later:
    sqlite_vec: true
    splink: true
    gotenberg: true
  do_not_add_yet:
    redis: true
    dramatiq: true
    celery: true
    minio: true
    twenty_crm: true
    mautic: true
    full_grafana_loki_prometheus_stack: true
    multiple_large_local_llms: true
  optional_with_review:
    reacher:
      reason:
        - "Email verification usefulness."
        - "Must not become single verification authority."
        - "Licensing/deployment implications should be reviewed."


obsidian_operator_workspace:
  priority: "HIGH"
  goal: "Use Obsidian as the human-facing master brain, dashboard, review workspace, and documentation layer without making it a runtime dependency."

  role:
    - "master brain"
    - "operator dashboard"
    - "project documentation"
    - "prospect review interface"
    - "approval review interface"
    - "agent output viewer"
    - "experiment history"
    - "daily/weekly reporting"
    - "runbook and recovery reference"

  authority:
    canonical_runtime_state: false
    canonical_database: false
    canonical_queue: false
    canonical_send_authority: false
    canonical_pricing_authority: false

  runtime_relationship:
    supervisor: "launchd"
    operator_cli: "./mm"
    canonical_queue: "SQLite leased work queue"
    canonical_state: "SQLite + state files"
    agent_orchestrator: "Hermes"
    human_workspace: "Obsidian"

  architecture_flow:
    - "launchd keeps ./mm supervisor alive."
    - "./mm supervisor owns worker lifecycle and recovery."
    - "SQLite owns durable queue and authoritative workflow state."
    - "Workers write reports, prospect packets, metrics, and evidence."
    - "Obsidian reads and presents those outputs for human review."
    - "Obsidian may initiate approved ./mm commands but must not bypass runtime safety gates."

  vault:
    recommended_root: "WEBSITE-AUDITOR-BRAIN"
    folders:
      - "00-DASHBOARD"
      - "01-MASTER-PLAN"
      - "02-LEADS"
      - "03-PROSPECTS"
      - "04-AGENTS"
      - "05-APPROVALS"
      - "06-EXPERIMENTS"
      - "07-REPORTS"
      - "08-RUNBOOK"

    dashboard_files:
      - "00-DASHBOARD/CONTROL-CENTRE.md"
      - "00-DASHBOARD/TODAY.md"
      - "00-DASHBOARD/PIPELINE-STATUS.md"
      - "00-DASHBOARD/SYSTEM-HEALTH.md"

    master_plan_files:
      - "01-MASTER-PLAN/MASTER-PLAN.md"
      - "01-MASTER-PLAN/CURRENT-STATE.md"
      - "01-MASTER-PLAN/CHANGELOG.md"
      - "01-MASTER-PLAN/ROADMAP.md"

    agent_files:
      - "04-AGENTS/HERMES.md"
      - "04-AGENTS/CODER.md"
      - "04-AGENTS/RESEARCHER.md"
      - "04-AGENTS/JUDGE.md"
      - "04-AGENTS/PROOFER.md"
      - "04-AGENTS/INTEGRATOR.md"

    runbook_files:
      - "08-RUNBOOK/RECOVERY.md"
      - "08-RUNBOOK/PROVIDERS.md"
      - "08-RUNBOOK/EMAIL-VERIFICATION.md"
      - "08-RUNBOOK/EMERGENCY-STOP.md"

  generated_views:
    - name: "Pipeline Status"
      source:
        - "state/health.json"
        - "state/metrics.jsonl"
        - "state/errors.jsonl"
    - name: "Execute Now Leads"
      source:
        - "db/MASTER_OPPORTUNITY_DATABASE.csv"
        - "db/master_opportunity_database.json"
    - name: "Prospect Review"
      source:
        - "artifacts/prospects/"
    - name: "Approval Queue"
      source:
        - "approval queue state"
    - name: "Experiments"
      source:
        - "challenger/self-improvement results"
    - name: "Daily Report"
      source:
        - "reports/"
        - "state/metrics.jsonl"

  operator_actions:
    preferred_interface: "./mm"
    examples:
      - "./mm supervisor start"
      - "./mm supervisor stop"
      - "./mm supervisor restart"
      - "./mm supervisor status"
      - "./mm supervisor health"
      - "./mm status"
      - "./mm health"
      - "./mm metrics"
      - "./mm errors"
      - "./mm queue"
      - "./mm dead-letter"

  approval_model:
    rule: "Obsidian displays reviewable approval state, but SQLite/runtime policy remains authoritative."
    allowed:
      - "human marks intent to approve"
      - "operator invokes a gated ./mm approval command"
      - "./mm validates all policy gates before changing canonical state"
    forbidden:
      - "plain Markdown checkbox directly authorizes live outreach"
      - "editing a note bypasses suppression or duplicate checks"
      - "Obsidian state overrides SQLite"

  sync_policy:
    direction:
      runtime_to_obsidian: "automatic/read-mostly"
      obsidian_to_runtime: "explicit gated commands only"
    rule: "Closing Obsidian must never stop WEBSITE-AUDITOR."

  docker_relationship:
    docker_required_for_obsidian: false
    docker_required_for_core_runtime: false
    optional_docker_services:
      - "SearXNG"
    n8n:
      required: false
      install_by_default: false
      status: "REMOVED_FROM_DEFAULT_STACK"
      future_use_only_if:
        - "many external webhook integrations are later required"
        - "a visual workflow editor provides measurable value beyond ./mm"

  implementation:
    - "Create the Obsidian vault structure."
    - "Symlink or export canonical Markdown reports into the vault where safe."
    - "Generate dashboard notes from canonical runtime state."
    - "Keep machine-readable state in SQLite/JSON rather than Markdown."
    - "Add ./mm obsidian-sync command if useful."
    - "Add ./mm obsidian-status command if useful."
    - "Add tests ensuring Obsidian absence does not break the pipeline."
    - "Document recovery when the vault is unavailable."

  gate:
    - "WEBSITE-AUDITOR operates normally with Obsidian closed."
    - "Obsidian dashboards reflect canonical state without becoming canonical state."
    - "No approval can bypass ./mm policy gates."
    - "No n8n dependency exists in the default runtime."
    - "No paid service is required."


exact_execution_order:
  - step: 1
    action: "Reconcile /Users/dd/WEBSITE-AUDITOR with the Cline Downloads experiment."
  - step: 2
    action: "Back up databases, state, and important outputs."
  - step: 3
    action: "Create upgrade/cline-master-merge branch."
  - step: 4
    action: "Standardize Python 3.11 and project venv."
  - step: 5
    action: "Get complete existing test suite green."
  - step: 6
    action: "Rotate/remove exposed secrets."
  - step: 7
    action: "Add gitleaks, dependency audit, and CI security checks."
  - step: 8
    action: "Consolidate auditor implementations."
  - step: 9
    action: "Consolidate planning and operator documentation."
  - step: 10
    action: "Finish supervisor/daemon."
  - step: 11
    action: "Add heartbeats, retry/backoff, DLQ, and log rotation."
  - step: 12
    action: "Prove kill/restart recovery."
  - step: 12.1
    action: "Create Obsidian operator workspace and dashboards as a non-authoritative view over canonical runtime state."
  - step: 13
    action: "Improve canonical business identity."
  - step: 14
    action: "Improve deterministic audit evidence."
  - step: 15
    action: "Add Lighthouse and Lychee."
  - step: 16
    action: "Build multi-source NZ discovery."
  - step: 17
    action: "Upgrade Email Finder V2 verification."
  - step: 18
    action: "Separate technical score from commercial opportunity score."
  - step: 19
    action: "Build remediation automation classifications."
  - step: 20
    action: "Build preview/demo factory."
  - step: 21
    action: "Add before/after evidence capture."
  - step: 22
    action: "Build deterministic quote engine."
  - step: 23
    action: "Build complete prospect packet."
  - step: 24
    action: "Build draft + QA pipeline."
  - step: 25
    action: "Add configurable outreach transport while keeping send disabled by default."
  - step: 26
    action: "Add outcome tracking."
  - step: 27
    action: "Optimize local/free model routing."
  - step: 28
    action: "Create golden evaluation dataset."
  - step: 29
    action: "Add challenger/self-improvement loop."
  - step: 30
    action: "Only then benchmark heavier optional infrastructure."

target_runtime_flow:
  - "discover"
  - "dedupe"
  - "identity"
  - "audit"
  - "verify"
  - "score"
  - "select"
  - "remediate"
  - "demo"
  - "screenshot"
  - "quote"
  - "draft"
  - "review"
  - "approved action"
  - "measure"
  - "learn"
  - "repeat"

final_acceptance_criteria:
  reliability:
    - "Pipeline can run unattended for 24+ hours without manual babysitting."
    - "Crash/restart recovery works."
    - "No duplicate work caused by restart."
    - "Dead-letter items are visible and triageable."
  audit_quality:
    - "Every material finding has evidence."
    - "Scores are derived from findings."
    - "False positives are tracked."
  lead_quality:
    - "Businesses are deduplicated."
    - "Identity confidence is explicit."
    - "Eligible emails have provenance."
  commercial_output:
    - "Qualified prospects can produce demo, before/after proof, quote band, and draft."
    - "Opportunity score is separate from technical weakness."
  cost:
    - "Paid model/API spend remains $0."
    - "No configuration path can silently introduce paid inference."
  safety:
    - "Live outreach is disabled by default."
    - "High-risk changes require review."
    - "No autonomous direct-to-master self-improvement."
  maintainability:
    - "One canonical repo."
    - "One canonical auditor path."
    - "One canonical control plane."
    - "One canonical master plan."
    - "Obsidian is the human-facing operator/master-brain workspace without becoming a runtime dependency."
    - "n8n is not required by the default stack."
```

## Execution instruction for Hermes / Cline / Codex

Execute this plan from `/Users/dd/WEBSITE-AUDITOR`.

Do not overwrite the live repository with `/Users/dd/Downloads/WEBSITE-AUDITOR-master`. Treat the Downloads copy as an experimental source only. Start at `P0` and advance strictly through the gates. Preserve current databases and state before migrations. Keep `paid_allowed=false`, `max_cost_usd=0`, and outreach sending disabled by default. Use Obsidian as the human-facing master brain/operator workspace, while keeping SQLite, `./mm`, and launchd authoritative for runtime state and supervision. Do not install or require n8n in the default stack.

For every implementation phase:

1. Inspect the current repository before editing.
2. Create or use an isolated branch/worktree.
3. Implement the smallest correct change.
4. Add or update tests.
5. Run the relevant focused tests.
6. Run the full regression suite before promotion.
7. Record the result in `CHANGELOG.md` and `CURRENT_STATE.md`.
8. Do not merge regressions.
9. Do not substitute agent confidence for test evidence.
10. Stop and defer any task that would require paid model/API usage.

Obsidian integration rule: dashboards, prospect reviews, approvals, agent outputs, reports, and runbooks may be surfaced in the vault, but editing Markdown must never directly bypass `./mm` gates, SQLite state, suppression rules, duplicate prevention, quote rules, or send controls.

The target is a continuously operating, evidence-first WEBSITE-AUDITOR that discovers, audits, verifies, prioritizes, demonstrates, quotes, drafts, measures, and improves while remaining recoverable, resource-bounded, and $0-paid-token by design.
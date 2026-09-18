#!/usr/bin/env python3
"""Emit engine cartridge YAMLs for the ACTIVE 3, compatible with the
hermes-business-exception-engine 6-agent runtime schema."""
import json, yaml
from pathlib import Path

OUT = Path("/Users/defaultaccount/HERMES_MONEY_ENGINE")
ENG = OUT / "engines"
ENG.mkdir(parents=True, exist_ok=True)
db = {r["engine_id"]: r for r in json.load(open(OUT / "db/master_opportunity_database.json"))}

COMMON_APPROVAL = ["external_communication", "pricing_commitment", "publishing"]

cartridges = {
"website_rescue_lead_engine.yaml": {
    "id": "ACTIVE-1", "name": "Website Rescue Lead Engine",
    "source_engines": ["ME-0462", "ME-0008", "ME-0331", "ME-0380", "ME-0387"],
    "category": "trigger_leads", "automation_tier": "automatable",
    "pricing": {"setup": [149, 799], "monthly": [99, 499], "currency": "NZD",
                "status": "UNAPPROVED — Dion must confirm before any quote"},
    "ideal_customer": "NZ small businesses (Christchurch/Canterbury first) with an outdated, broken or non-mobile website",
    "exact_offer": "Identify objectively observable website defects from public data and deliver a proof-backed mini-audit with a fix offer.",
    "data_inputs": [
        {"name": "prospect_candidates", "type": "csv", "required": True,
         "fields": ["business_name", "website_url", "region", "industry", "source_url"],
         "provenance": "public directories only — NZBN, Google Maps, trade directories"},
        {"name": "detection_methodology", "type": "md", "required": True,
         "path": "outputs/RESEARCH_website_rescue_methodology.md"}],
    "researcher": {"needs_external_data": True,
                   "sources": ["NZBN register", "Google Maps listings", "regional chamber directories",
                               "trade association directories"],
                   "rules": ["public data only", "record source URL for every candidate",
                             "never fabricate a business, defect or metric",
                             "mark confidence on every detected defect"]},
    "delegator": {"thresholds": {"min_defects_to_qualify": 2, "min_qualification_score": 60},
                  "reject_if": ["site rebuilt in last 12 months", "existing agency footer credit",
                                "enterprise/franchise", "business appears defunct"]},
    "executor_1": {"operations": ["detect_defects_from_public_signals", "attach_evidence_artifact",
                                  "score_qualification_0_100", "rank_candidates", "deduplicate"]},
    "executor_2": {"output_template": "website_rescue_mini_audit",
                   "tone": "plain, specific, non-salesy, NZ English",
                   "must_include": ["named defect", "how it was observed", "commercial consequence",
                                    "single clear next step"],
                   "must_not_include": ["invented traffic or revenue numbers", "fake urgency",
                                        "claims of Google partnership", "guaranteed rankings"]},
    "judge": {"min_score": 80,
              "criteria": {"accuracy": 20, "impact": 20, "specificity": 15, "confidence": 15,
                           "actionability": 15, "repeatability": 10, "risk": 5}},
    "proofer": {"extra_checks": ["business name spelled exactly as public listing",
                                 "every defect claim has a verifiable source URL",
                                 "no placeholder tokens remain",
                                 "no price stated unless Dion-approved",
                                 "sender identity + unsubscribe present per UEMA 2007"]},
    "delivery": {"format": "email_draft_plus_audit_pdf", "frequency": "daily_batch",
                 "approval_required": COMMON_APPROVAL,
                 "sender_identity": {"email": "yabigdd@gmail.com", "phone": "02904556680", "signoff": "Dion"}},
    "daily_targets": {"candidates_researched": [60, 100], "qualified": [20, 30],
                      "proof_assets": [20, 30], "sent": 0}},

"reputation_review_engine.yaml": {
    "id": "ACTIVE-2", "name": "Reputation / Unanswered Review Engine",
    "source_engines": ["ME-0007", "ME-0006", "ME-0042", "ME-0392", "ME-0393"],
    "category": "reputation", "automation_tier": "needs_integration",
    "viability_gate": "BLOCKED pending Researcher #2 verdict on lawful review-data access at scale. "
                      "If Google Places/GBP access is closed, substitute ME-0274 Competitor Review "
                      "Velocity Monitor (score 93) or ME-0327 Website Content Freshness Monitor (93).",
    "pricing": {"setup": [149, 499], "monthly": [99, 599], "currency": "NZD",
                "status": "UNAPPROVED — Dion must confirm before any quote"},
    "ideal_customer": "NZ local service businesses with visible unanswered reviews and an active trading presence",
    "exact_offer": "Deliver an honest reputation snapshot showing unanswered reviews, response-rate gap and profile completeness, plus a managed response service.",
    "data_inputs": [
        {"name": "prospect_candidates", "type": "csv", "required": True,
         "fields": ["business_name", "listing_url", "region", "industry", "source_url"]},
        {"name": "detection_methodology", "type": "md", "required": True,
         "path": "outputs/RESEARCH_reputation_engine_methodology.md"}],
    "researcher": {"needs_external_data": True,
                   "rules": ["only lawful access paths confirmed by the methodology file",
                             "no Google Maps scraping if it breaches Terms of Service",
                             "never invent a review, rating or count",
                             "record retrieval method + timestamp per data point"]},
    "delegator": {"thresholds": {"min_unanswered_reviews": 3, "min_qualification_score": 60},
                  "reject_if": ["owner already responds to most reviews", "profile unclaimed and business dormant",
                                "national chain with central marketing"]},
    "executor_1": {"operations": ["compute_owner_response_rate", "count_unanswered_negative",
                                  "measure_review_recency_gap", "profile_completeness_check",
                                  "score_qualification_0_100"]},
    "executor_2": {"output_template": "reputation_snapshot",
                   "tone": "respectful, factual, non-alarmist",
                   "must_not_include": ["implication of Google endorsement or partnership",
                                        "fabricated competitor comparison", "invented review text"]},
    "judge": {"min_score": 80},
    "proofer": {"extra_checks": ["every review statistic traceable to retrieval method",
                                 "no Google trademark misuse", "no fabricated competitor data",
                                 "UEMA 2007 compliance fields present"]},
    "delivery": {"format": "email_draft_plus_snapshot", "frequency": "daily_batch",
                 "approval_required": COMMON_APPROVAL,
                 "sender_identity": {"email": "yabigdd@gmail.com", "phone": "02904556680", "signoff": "Dion"}},
    "daily_targets": {"candidates_researched": [60, 100], "qualified": [20, 30], "sent": 0}},

"catalyx_flooring_lead_engine.yaml": {
    "id": "ACTIVE-3", "name": "CATALYX Flooring Lead Engine",
    "source_engines": ["ME-0001", "ME-0449", "ME-0452", "ME-0453", "ME-0454"],
    "category": "lead_gen", "automation_tier": "automatable",
    "note": "Generic rubric scores ME-0001 at 41/100 because of physical/site-visit cost. "
            "Retained by explicit plan mandate as the CATALYX proving ground.",
    "pricing": {"status": "product pricing owned by Dion — agent never states a flooring price"},
    "ideal_customer": "Christchurch/Canterbury property owners, builders, developers, body corporates, "
                      "facilities managers and insurance repair contractors needing garage/commercial flooring",
    "exact_offer": "Generate qualified, source-cited Canterbury flooring prospects with a reason-for-fit and a prepared approach.",
    "data_inputs": [
        {"name": "catalyx_product_catalogue", "type": "yaml", "required": True,
         "note": "GF-01 Garage Essential, GF-02 series etc. — must come from Dion's real catalogue, never invented"},
        {"name": "prospect_candidates", "type": "csv", "required": True,
         "fields": ["entity_name", "entity_type", "region", "trigger_signal", "source_url"]},
        {"name": "approved_price_bands", "type": "yaml", "required": False,
         "note": "absent = agent must not quote"}],
    "researcher": {"needs_external_data": True,
                   "sources": ["NZBN register", "Canterbury building consent notices (public)",
                               "body corporate / facilities directories", "commercial property listings",
                               "builder and developer directories"],
                   "rules": ["public sources only", "cite source URL per prospect",
                             "never invent a project, consent or contact"]},
    "delegator": {"thresholds": {"min_qualification_score": 60},
                  "reject_if": ["outside Canterbury service area", "residential single-room retail job below viable size",
                                "entity defunct"]},
    "executor_1": {"operations": ["classify_entity_type", "match_to_product_line",
                                  "estimate_indicative_area_band", "score_qualification_0_100"]},
    "executor_2": {"output_template": "flooring_prospect_approach",
                   "must_not_include": ["final pricing", "guaranteed lead times",
                                        "fabricated past project references"]},
    "judge": {"min_score": 80},
    "proofer": {"extra_checks": ["product codes match real CATALYX catalogue",
                                 "no price or lead-time commitment", "entity name and region correct",
                                 "UEMA 2007 compliance fields present"]},
    "delivery": {"format": "prospect_pack_plus_email_draft", "frequency": "daily_batch",
                 "approval_required": COMMON_APPROVAL + ["quote_with_final_pricing"],
                 "sender_identity": {"email": "yabigdd@gmail.com", "phone": "02904556680", "signoff": "Dion"}},
    "daily_targets": {"candidates_researched": [60, 100], "qualified": [20, 30], "sent": 0}},
}

for fn, body in cartridges.items():
    yaml.safe_dump(body, open(ENG / fn, "w"), sort_keys=False, width=100, allow_unicode=True)
    print(f"  engines/{fn}  {(ENG/fn).stat().st_size:,}b")

# sanity: source engine ids must exist in db
missing = [s for c in cartridges.values() for s in c.get("source_engines", []) if s not in db]
print("\nunresolved source engine ids:", missing or "none")
print("cartridges written:", len(cartridges))

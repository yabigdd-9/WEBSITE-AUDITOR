# Money Machine Database Schema

## Core Tables

### businesses
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Canonical business ID |
| name | TEXT | Business name |
| industry_id | INTEGER FK | industries.id |
| region | TEXT | NZ region |
| public_website | TEXT | Website URL |
| is_dummy | INTEGER | 0 = real, 1 = test data |
| current_status | TEXT | Pipeline stage |

### email_policy
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Always 1 (CHECK constraint) |
| mode | TEXT | 'shadow', 'v2', or 'v1_hold' |
| changed_at | TEXT | ISO8601 timestamp |
| acceptance_hash | TEXT | SHA-256 of acceptance.json when promoted to v2 |

### email_release_policy
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Always 1 |
| mode | TEXT | 'v2' or 'POST_DEPLOYMENT_OBSERVATION' |
| verifier_version | TEXT | e.g., 'email-v2.0.1' |

### email_candidates
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| prospect_id | INTEGER FK | businesses.id |
| email | TEXT | Raw email |
| normalized_email | TEXT | Lowercased/validated |
| source_type | TEXT | 'mailto', 'hunter_enrichment', 'legacy', etc. |
| source_url TEXT | |
| source_excerpt | TEXT | JSON context |
| observed_at | TEXT | ISO8601 |
| candidate_method | TEXT | How discovered |
| status | TEXT | CHECK constraint: OBSERVED, CANDIDATE, VERIFIED_HIGH, VERIFIED_MEDIUM, UNVERIFIED, REJECTED, SUPPRESSED |
| legacy_ref | TEXT | UNIQUE — source legacy row |
| created_at | TEXT | |

### email_verifications
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| candidate_id | INTEGER FK | email_candidates.id |
| identity_id | INTEGER FK | email_identity_checks.id |
| syntax_valid | INTEGER | 0 or 1 |
| mx_valid | INTEGER | 0 or 1 |
| smtp_status | TEXT | 'not_probed', 'accepted', 'rejected' |
| catch_all_status | TEXT | 'yes', 'no', 'unknown' |
| disposable | INTEGER | 0 or 1 |
| business_match | INTEGER | 0 or 1 |
| person_match | TEXT | 'not_requested' or bool |
| first_party_observed | INTEGER | 0 or 1 |
| confidence_score | INTEGER | 0-100 |
| confidence_label | TEXT | Same CHECK constraint as candidates |
| rejection_reason | TEXT | '[]' or reasons |
| verifier_version | TEXT | e.g., 'email-v2.0.1' |
| result_json | TEXT | Full result dict |

### email_identity_checks
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| prospect_id | INTEGER FK | |
| checked_at | TEXT | |
| entity_key | TEXT | SHA-256 of identity |
| result_json | TEXT | Full identity dict |
| evidence_hash | TEXT | |

### email_evidence
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| candidate_id | INTEGER FK | |
| evidence_type | TEXT | 'mailto', 'visible_text', 'hunter_source', etc. |
| url TEXT | | Source URL |
| title | TEXT | Page title |
| excerpt | TEXT | Context snippet |
| observed_email | TEXT | Email as seen |
| captured_at | TEXT | |
| evidence_hash | TEXT | SHA-256 of capture |
| capture_path | TEXT | Relative path |
| role | TEXT | Classified role |

### prospect_email_state
| Column | Type | Notes |
|--------|------|-------|
| prospect_id | INTEGER PK FK | |
| best_email_id | INTEGER FK | email_candidates.id |
| best_verification_id | INTEGER FK | email_verifications.id |
| best_email_confidence | INTEGER | |
| email_review_required | INTEGER | Always 1 (CHECK) |
| contact_form_urls | TEXT | JSON array |
| selection_status | TEXT | 'VERIFIED_HIGH' or 'NO_VERIFIED_EMAIL' |
| last_checked | TEXT | |
| identity_id | INTEGER FK | |

### mm_evidence
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| business_id | INTEGER FK | businesses.id |
| url | TEXT | Source URL |
| observation | TEXT | What was observed |
| limitation | TEXT | Known limitations |
| checked_at | TEXT | ISO8601 |

### mm_evidence_meta
| Column | Type | Notes |
|--------|------|-------|
| evidence_id | INTEGER PK FK | mm_evidence.id |
| status TEXT | 'verified','partial','refuted','unverified' |
| method | TEXT | 'exa-retrieval','exa-agent','local review', etc. |
| confidence | REAL | 0-1 (exa-retrieval=0.5, first-party=0.9+) |
| claim_type | TEXT | 'conversion','lead_discovery', etc. |
| commercial_relevance | TEXT | |
| expires_at | TEXT | ISO8601 |
| capture_path | TEXT | Relative path to evidence file |
| capture_hash | TEXT | SHA-256 of capture |
| verified_by | TEXT | 'exa-integration','human', etc. |
| verification_count | INTEGER | |
| Column | Type | Notes |
|--------|------|-------|
| prospect_id | INTEGER PK FK | |
| best_email_id | INTEGER FK | email_candidates.id |
| best_verification_id | INTEGER FK | email_verifications.id |
| best_email_confidence | INTEGER | |
| email_review_required | INTEGER | Always 1 (CHECK) |
| contact_form_urls | TEXT | JSON array |
| selection_status | TEXT | 'VERIFIED_HIGH' or 'NO_VERIFIED_EMAIL' |
| last_checked | TEXT | |
| identity_id | INTEGER FK | |

### hunter_enrichment
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| business_id | INTEGER FK | businesses.id |
| email | TEXT | |
| normalized_email | TEXT | |
| source_type | TEXT | 'hunter_enrichment' |
| source_url | TEXT | First Hunter source URL |
| source_excerpt | TEXT | JSON metadata |
| observed_at | TEXT | |
| candidate_method | TEXT | 'hunter_domain_search' |
| status | TEXT | CHECK: OBSERVED, CANDIDATE, UNVERIFIED (never VERIFIED_HIGH) |
| hunter_confidence | INTEGER | 0-100 |
| hunter_sources | TEXT | JSON array of source URIs |
| hunter_first_name | TEXT | |
| hunter_last_name | TEXT | |
| hunter_position | TEXT | |
| hunter_department | TEXT | |
| created_at | TEXT | |

### mm_suppression
| Column | Type | Notes |
|--------|------|-------|
| address | TEXT PK | Suppressed email |
| reason | TEXT | |
| created_at | TEXT | |

## Views

### email_current_high
Joins email_candidates + email_verifications + email_identity_checks + prospect_email_state to select emails that are:
- confidence_label = 'VERIFIED_HIGH'
- verifier_version = 'email-v2.0.0'
- Checked within 1 day
- DNS checked within 1 day
- No rejection reasons
- Evidence captured within 7 days
- Not suppressed
- Not on hold

## Triggers

All evidence, verification, identity, candidate, and suppression tables have triggers that:
- Block UPDATE and DELETE on evidence/verification/identity/candidates
- Block DELETE on policy tables
- Block shadow mode from reopening once left

Never hand-edit these rows — append new evidence instead.

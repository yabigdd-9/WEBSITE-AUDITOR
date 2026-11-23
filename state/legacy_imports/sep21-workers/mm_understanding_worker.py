"""Understanding worker for Loop B: Decide what to investigate next.

Implements business understanding, evidence memory, and opportunity assessment
to decide what to investigate next in the opportunity lifecycle.
"""

import json
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from mm_core import now, sha, connect
from mm_pipeline import get_loop_for_state, advance, enqueue, transition
from mm_lead_qualifier import qualify_lead
from mm_opportunity_scoring import OpportunityScorer, score_opportunity, is_shortlist_opportunity


def understanding_worker_handler(d, item_row, worker):
    """Decide what to investigate next - Loop B handler.

    Args:
        d: Database connection
        item_row: Pipeline item row
        worker: Worker instance

    Returns:
        Tuple of (next_state, reason, evidence)
    """
    business_id = item_row['business_id']
    payload = json.loads(item_row['payload'] or '{}')
    current_state = item_row['state']

    # Get campaign configuration if available
    campaign_id = payload.get('campaign_id')

    # Construct business understanding based on current state and available evidence
    business_understanding = _construct_business_understanding(d, business_id, campaign_id, current_state)

    # Update payload with understanding findings
    payload.update({
        'understanding_timestamp': now(),
        'business_understanding': business_understanding,
        'campaign_id': campaign_id,
        'last_understanding_state': current_state
    })

    # Score opportunity using 6-component model
    opportunity_score_result = score_opportunity(business_id, campaign_id or "default")

    # Add scoring results to payload
    payload.update({
        'opportunity_score': opportunity_score_result.get('opportunity_score', 0),
        'opportunity_components': opportunity_score_result.get('components', {}),
        'is_shortlist': opportunity_score_result.get('is_shortlist', False),
        'scoring_details': opportunity_score_result
    })

    # Determine next state based on current state and opportunity assessment
    is_shortlist = opportunity_score_result.get('is_shortlist', False)
    score = opportunity_score_result.get('opportunity_score', 0)

    # Additional checks for readiness to proceed
    readiness_checks = _check_readiness_for_next_stage(d, business_id, payload, current_state)

    # Loop B logic: decide what to investigate next based on understanding
    if current_state == 'IDENTITY_PENDING':
        # Moving from identity resolution to audit preparation
        if readiness_checks['ready_for_audit']:
            next_state = 'AUDIT_PENDING'
            reason = f'Identity resolved, ready for audit (score: {score:.1f})'
            evidence = {
                'opportunity_score': score,
                'business_understanding': business_understanding,
                'readiness_checks': readiness_checks,
                'identity_resolved': True
            }
        else:
            next_state = 'NEEDS_REVIEW'
            reason = f'Identity resolution incomplete: {readiness_checks["reason"]}'
            evidence = {
                'business_understanding': business_understanding,
                'readiness_checks': readiness_checks,
                'identity_resolved': False
            }

    elif current_state == 'IDENTITY_RESOLVED':
        # Moving from identity resolved to audit pending
        if readiness_checks['ready_for_audit']:
            next_state = 'AUDIT_PENDING'
            reason = f'Ready for audit based on understanding (score: {score:.1f})'
            evidence = {
                'opportunity_score': score,
                'business_understanding': business_understanding,
                'readiness_checks': readiness_checks,
                'identity_confirmed': True
            }
        else:
            next_state = 'NEEDS_REVIEW'
            reason = f'Not ready for audit: {readiness_checks["reason"]}'
            evidence = {
                'business_understanding': business_understanding,
                'readiness_checks': readiness_checks,
                'identity_confirmed': True
            }

    elif current_state == 'AUDIT_PENDING':
        # Moving from audit pending to audited (triggering audit)
        if readiness_checks['ready_for_audit_execution']:
            next_state = 'AUDITED'
            reason = f'Understanding complete, initiating audit (score: {score:.1f})'
            evidence = {
                'opportunity_score': score,
                'business_understanding': business_understanding,
                'readiness_checks': readiness_checks,
                'audit_triggered': True,
                'audit_focus_areas': _identify_audit_focus_areas(business_understanding, opportunity_score_result)
            }
        else:
            next_state = 'NEEDS_REVIEW'
            reason = f'Not ready to execute audit: {readiness_checks["reason"]}'
            evidence = {
                'business_understanding': business_understanding,
                'readiness_checks': readiness_checks,
                'audit_triggered': False
            }

    elif current_state == 'AUDITED':
        # Moving from audited to qualification pending
        if is_shortlist and readiness_checks['ready_for_qualification']:
            next_state = 'QUALIFICATION_PENDING'
            reason = f'Opportunity shortlisted for qualification (score: {score:.1f})'
            evidence = {
                'opportunity_score': score,
                'opportunity_components': opportunity_score_result.get('components', {}),
                'business_understanding': business_understanding,
                'readiness_checks': readiness_checks,
                'ready_for_qualification': True
            }
        elif readiness_checks['ready_for_qualification']:
            next_state = 'QUALIFIED'
            reason = f'Ready for qualification assessment (score: {score:.1f})'
            evidence = {
                'opportunity_score': score,
                'opportunity_components': opportunity_score_result.get('components', {}),
                'business_understanding': business_understanding,
                'readiness_checks': readiness_checks,
                'needs_qualification': True
            }
        else:
            next_state = 'REJECTED'
            reason = f'Insufficient opportunity or readiness (score: {score:.1f})'
            evidence = {
                'opportunity_score': score,
                'business_understanding': business_understanding,
                'readiness_checks': readiness_checks,
                'rejection_reason': 'low_opportunity_or_not_ready'
            }
    else:
        # Fallback for other states
        next_state = 'NEEDS_REVIEW'
        reason = f'Unexpected state for understanding worker: {current_state}'
        evidence = {
            'business_understanding': business_understanding,
            'unexpected_state': current_state
        }

    return next_state, reason, evidence


def _construct_business_understanding(d, business_id: int, campaign_id: Optional[str], current_state: str) -> Dict:
    """Construct a business understanding profile appropriate for the current state."""
    try:
        with connect() as conn:
            conn.row_factory = conn.Row

            # Get basic business info
            business_row = conn.execute(
                """SELECT b.id, b.name, b.region, b.public_website, b.source,
                          b.discovered_at, b.is_dummy, i.name as industry
                   FROM businesses b
                   LEFT JOIN industries i ON b.industry_id = i.id
                   WHERE b.id = ?""",
                (business_id,)
            ).fetchone()

            if not business_row:
                return {"error": "Unable to retrieve business information"}

            business_info = dict(business_row)

            # Get evidence appropriate for current state
            evidence_rows = _get_evidence_for_state(conn, business_id, current_state)

            # Get pipeline history for context
            pipeline_rows = conn.execute(
                """SELECT state, updated_at, payload
                   FROM pipeline_items
                   WHERE business_id = ?
                   ORDER BY updated_at DESC
                   LIMIT 10""",
                (business_id,)
            ).fetchall()

            # Get contact evidence if available
            contact_rows = conn.execute(
                """SELECT recipient, permission_basis, permission_verified_by,
                          checked_at, capture_path, capture_hash
                   FROM mm_contact_evidence
                   WHERE business_id = ?
                   ORDER BY checked_at DESC
                   LIMIT 5""",
                (business_id,)
            ).fetchall()

            # Construct understanding profile based on current state
            understanding = {
                "business_id": business_id,
                "business_name": business_info.get('name'),
                "industry": business_info.get('industry'),
                "region": business_info.get('region'),
                "website": business_info.get('public_website'),
                "source": business_info.get('source'),
                "discovered_at": business_info.get('discovered_at'),
                "is_dummy": business_info.get('is_dummy'),
                "constructed_at_state": current_state,
                "construction_timestamp": datetime.now(timezone.utc).isoformat()
            }

            # Add state-specific understanding components
            if current_state in ['IDENTITY_PENDING', 'IDENTITY_RESOLVED']:
                understanding.update(_construct_identity_understanding(business_info, evidence_rows))
            elif current_state == 'AUDIT_PENDING':
                understanding.update(_construct_audit_preparation_understanding(business_info, evidence_rows, pipeline_rows))
            elif current_state == 'AUDITED':
                understanding.update(_construct_post_audit_understanding(business_info, evidence_rows, pipeline_rows))

            # Common understanding components
            understanding.update({
                # What the business sells (inferred from evidence)
                "products_services": _infer_products_services(evidence_rows),

                # Who appears to buy it (inferred from evidence)
                "customers": _infer_customers(evidence_rows, business_info),

                # How customers enquire, quote, book, or reorder
                "customer_journey": _infer_customer_journey(evidence_rows, business_info),

                # Existing mechanisms that already work
                "existing_mechanisms": _infer_existing_mechanisms(evidence_rows),

                # Specific observed friction
                "friction_points": _infer_friction_points(evidence_rows),

                # Relevant restrictions and unknowns
                "restrictions": _infer_restrictions(evidence_rows, business_info),
                "unknowns": _identify_unknowns(evidence_rows, pipeline_rows),

                # Evidence quality and freshness
                "evidence_quality": _assess_evidence_quality(evidence_rows, current_state),

                # Understanding confidence and completeness
                "understanding_confidence": _calculate_understanding_confidence(evidence_rows, pipeline_rows, current_state),
                "understanding_completeness": _assess_understanding_completeness(evidence_rows, pipeline_rows, current_state)
            })

            return understanding

    except Exception as e:
        return {"error": f"Failed to construct business understanding: {str(e)}"}


def _get_evidence_for_state(conn, business_id: int, current_state: str) -> List[Dict]:
    """Get evidence appropriate for understanding at current state."""
    if current_state == 'IDENTITY_PENDING':
        # Early stage - basic discovery evidence
        return conn.execute(
            """SELECT id, url, observation, limitation, checked_at, evidence, score
               FROM mm_evidence
               WHERE business_id = ?
               ORDER BY checked_at DESC
               LIMIT 5""",
            (business_id,)
        ).fetchall()
    elif current_state in ['IDENTITY_RESOLVED', 'AUDIT_PENDING']:
        # Moderate stage - more evidence
        return conn.execute(
            """SELECT id, url, observation, limitation, checked_at, evidence, score
               FROM mm_evidence
               WHERE business_id = ?
               ORDER BY checked_at DESC
               LIMIT 10""",
            (business_id,)
        ).fetchall()
    else:  # AUDITED and beyond
        # Later stage - all available evidence
        return conn.execute(
            """SELECT id, url, observation, limitation, checked_at, evidence, score
               FROM mm_evidence
               WHERE business_id = ?
               ORDER BY checked_at DESC""",
            (business_id,)
        ).fetchall()


def _construct_identity_understanding(business_info: Dict, evidence_rows: List[Dict]) -> Dict:
    """Construct understanding components for identity resolution stage."""
    return {
        "identity_resolution": {
            "website_available": bool(business_info.get('public_website')),
            "region_identified": bool(business_info.get('region')),
            "business_name_clear": bool(business_info.get('name') and len(business_info.get('name', '').strip()) > 0),
            "identity_confidence": _calculate_identity_confidence(business_info, evidence_rows)
        }
    }


def _construct_audit_preparation_understanding(business_info: Dict, evidence_rows: List[Dict], pipeline_rows: List[Dict]) -> Dict:
    """Construct understanding components for audit preparation stage."""
    return {
        "audit_preparation": {
            "website_accessible": _assess_website_accessibility(evidence_rows),
            "audit_scope_indicators": _identify_audit_scope_indicators(evidence_rows),
            "pre_audit_findings": _summarize_pre_audit_findings(evidence_rows),
            "audit_readiness_score": _calculate_audit_readiness(evidence_rows, pipeline_rows)
        }
    }


def _construct_post_audit_understanding(business_info: Dict, evidence_rows: List[Dict], pipeline_rows: List[Dict]) -> Dict:
    """Construct understanding components for post-audit stage."""
    return {
        "post_audit_analysis": {
            "audit_completed": _check_if_audit_completed(pipeline_rows),
            "audit_findings_summary": _summarize_audit_findings(evidence_rows, pipeline_rows),
            "opportunity_indicators": _identify_opportunity_indicators_from_audit(evidence_rows, pipeline_rows),
            "post_audit_confidence": _calculate_post_audit_confidence(evidence_rows, pipeline_rows)
        }
    }


def _calculate_identity_confidence(business_info: Dict, evidence_rows: List[Dict]) -> float:
    """Calculate confidence in business identity resolution."""
    score = 0.0
    factors = 0

    # Website availability
    if business_info.get('public_website'):
        score += 0.4
        factors += 1

    # Business name clarity
    name = business_info.get('name', '').strip()
    if name and len(name) > 2 and not name.lower() in ['unknown', 'unnamed', 'test']:
        score += 0.3
        factors += 1

    # Region identification
    if business_info.get('region'):
        score += 0.2
        factors += 1

    # Evidence supporting identity
    identity_evidence = 0
    for evidence in evidence_rows:
        obs = evidence.get('observation', '').lower()
        lim = evidence.get('limitation', '').lower()
        text = f"{obs} {lim}"
        if any(indicator in text for indicator in ['website', 'domain', 'business name', 'company']):
            identity_evidence += 1

    if evidence_rows:
        identity_ratio = min(1.0, identity_evidence / len(evidence_rows))
        score += 0.3 * identity_ratio
        factors += 1

    return score / factors if factors > 0 else 0.0


def _assess_website_accessibility(evidence_rows: List[Dict]) -> str:
    """Assess website accessibility from evidence."""
    for evidence in evidence_rows:
        obs = evidence.get('observation', '').lower()
        lim = evidence.get('limitation', '').lower()
        text = f"{obs} {lim}"

        if 'website accessible' in text or 'site reachable' in text:
            return "accessible"
        elif 'website not accessible' in text or 'site unreachable' in text:
            return "not_accessible"
        elif 'website loading' in text or 'site responding' in text:
            return "loading"

    return "unknown"


def _identify_audit_scope_indicators(evidence_rows: List[Dict]) -> List[str]:
    """Identify indicators that help define audit scope."""
    indicators = []
    audit_scope_terms = ['audit', 'review', 'assessment', 'evaluation', 'analysis', 'examination']

    for evidence in evidence_rows:
        obs = evidence.get('observation', '').lower()
        lim = evidence.get('limitation', '').lower()
        text = f"{obs} {lim}"

        for term in audit_scope_terms:
            if term in text:
                # Extract context around the term
                words = text.split()
                for i, word in enumerate(words):
                    if word == term:
                        start = max(0, i-3)
                        end = min(len(words), i+3)
                        context = " ".join(words[start:end])
                        indicators.append(context)
                        break

    return list(set(indicators))  # Deduplicate


def _summarize_pre_audit_findings(evidence_rows: List[Dict]) -> List[str]:
    """Summarize findings that should be checked during audit."""
    findings = []

    for evidence in evidence_rows:
        obs = evidence.get('observation', '').lower()
        lim = evidence.get('limitation', '').lower()
        text = f"{obs} {lim}"

        # Look for potential issues or areas needing investigation
        issue_indicators = ['problem', 'issue', 'concern', 'question', 'unclear', 'missing', 'absent', 'broken']
        if any(indicator in text for indicator in issue_indicators):
            findings.append(text[:100])  # Limit length

    return findings[:5]  # Return top 5


def _calculate_audit_readiness(evidence_rows: List[Dict], pipeline_rows: List[Dict]) -> float:
    """Calculate readiness for audit execution."""
    if not evidence_rows:
        return 0.0

    score = 0.0
    # Base score for having evidence
    score += 0.3

    # Score for evidence recency
    try:
        now_time = datetime.now(timezone.utc)
        recent_evidence = 0
        for evidence in evidence_rows:
            checked_at_str = evidence.get('checked_at', '')
            if checked_at_str:
                checked_at = datetime.fromisoformat(checked_at_str.replace('Z', '+00:00'))
                days_old = (now_time - checked_at).days
                if days_old <= 30:  # Evidence within last 30 days
                    recent_evidence += 1

        if evidence_rows:
            recency_ratio = recent_evidence / len(evidence_rows)
            score += 0.4 * recency_ratio
    except (ValueError, TypeError):
        pass  # Unable to parse dates

    # Score for evidence completeness
    completeness_indicators = ['complete', 'comprehensive', 'detailed', 'thorough']
    complete_evidence = 0
    for evidence in evidence_rows:
        lim = evidence.get('limitation', '').lower()
        if not any(indicator in lim for indicator in ['incomplete', 'partial', 'limited']):
            complete_evidence += 1

    if evidence_rows:
        completeness_ratio = complete_evidence / len(evidence_rows)
        score += 0.3 * completeness_ratio

    return min(1.0, score)


def _check_if_audit_completed(pipeline_rows: List[Dict]) -> bool:
    """Check if audit has been completed based on pipeline history."""
    audit_states = {'AUDIT_PENDING', 'AUDITED'}
    for pipeline in pipeline_rows:
        if pipeline.get('state') in audit_states:
            return True
    return False


def _summarize_audit_findings(evidence_rows: List[Dict], pipeline_rows: List[Dict]) -> Dict:
    """Summarize audit findings from evidence and pipeline."""
    # In a real implementation, this would parse actual audit results
    # For now, return indicative findings based on evidence

    positive_findings = []
    negative_findings = []

    for evidence in evidence_rows:
        obs = evidence.get('observation', '').lower()
        lim = evidence.get('limitation', '').lower()
        text = f"{obs} {lim}"

        # Simple sentiment analysis
        positive_terms = ['good', 'working', 'effective', 'efficient', 'success', 'pass']
        negative_terms = ['bad', 'broken', 'issue', 'problem', 'fail', 'deficient']

        if any(term in text for term in positive_terms):
            positive_findings.append(text[:80])
        elif any(term in text for term in negative_terms):
            negative_findings.append(text[:80])

    return {
        "positive_findings": positive_findings[:3],
        "negative_findings": negative_findings[:3],
        "findings_count": len(positive_findings) + len(negative_findings)
    }


def _identify_opportunity_indicators_from_audit(evidence_rows: List[Dict], pipeline_rows: List[Dict]) -> List[str]:
    """Identify opportunity indicators from audit findings."""
    indicators = []
    opportunity_terms = ['opportunity', 'improvement', 'potential', 'benefit', 'advantage', 'gain']

    for evidence in evidence_rows:
        obs = evidence.get('observation', '').lower()
        lim = evidence.get('limitation', '').lower()
        text = f"{obs} {lim}"

        if any(term in text for term in opportunity_terms):
            indicators.append(text[:100])

    return list(set(indicators))[:5]  # Deduplicate and limit


def _calculate_post_audit_confidence(evidence_rows: List[Dict], pipeline_rows: List[Dict]) -> float:
    """Calculate confidence after audit completion."""
    if not evidence_rows:
        return 0.0

    # Base confidence from having gone through audit process
    base_confidence = 0.5

    # Boost for evidence quality and quantity
    evidence_score = min(1.0, len(evidence_rows) / 10.0)  # Normalize to max 10 pieces
    base_confidence += 0.3 * evidence_score

    # Boost for positive findings vs negative
    positive_count = 0
    negative_count = 0
    for evidence in evidence_rows:
        obs = evidence.get('observation', '').lower()
        lim = evidence.get('limitation', '').lower()
        text = f"{obs} {lim}"

        if any(term in text for term in ['good', 'effective', 'success', 'working']):
            positive_count += 1
        elif any(term in text for term in ['bad', 'broken', 'issue', 'problem', 'fail']):
            negative_count += 1

    total_findings = positive_count + negative_count
    if total_findings > 0:
        positivity_ratio = positive_count / total_findings
        base_confidence += 0.2 * positivity_ratio

    return min(1.0, base_confidence)


def _infer_products_services(evidence_rows: List[Dict]) -> List[str]:
    """Infer what products/services the business offers from evidence."""
    services = set()

    # Common service indicators in evidence
    service_indicators = {
        'construction': ['building', 'construction', 'renovation', 'remodeling'],
        'plumbing': ['plumbing', 'pipes', 'drainage', 'fixtures'],
        'electrical': ['electrical', 'wiring', 'lighting', 'power'],
        'hvac': ['heating', 'cooling', 'ventilation', 'air conditioning'],
        'saas': ['software', 'application', 'platform', 'service'],
        'retail': ['store', 'shop', 'retail', 'sales'],
        'ecommerce': ['online', 'website', 'store', 'shop']
    }

    for evidence in evidence_rows:
        observation = evidence.get('observation', '').lower()
        limitation = evidence.get('limitation', '').lower()
        evidence_text = f"{observation} {limitation}"

        # Check for explicit service mentions
        for service_category, keywords in service_indicators.items():
            for keyword in keywords:
                if keyword in evidence_text:
                    services.add(service_category)
                    break

        # Check for explicit product/service descriptions
        product_patterns = [
            r"we\s+(?:offer|provide|sell|specialize\s+in)\s+([^,\.]+)",
            r"our\s+(?:products|services)\s+(?:include|are)\s+([^,\.]+)",
            r"specializing\s+in\s+([^,\.]+)",
            r"we\s+focus\s+on\s+([^,\.]+)"
        ]

        for pattern in product_patterns:
            matches = re.findall(pattern, evidence_text)
            for match in matches:
                services.add(match.strip())

    return list(services) if services else ["unspecified"]


def _infer_customers(evidence_rows: List[Dict], business_info: Dict) -> List[str]:
    """Infer who appears to buy from the business from evidence."""
    customers = set()

    # Customer indicators
    customer_indicators = [
        'residential', 'commercial', 'industrial', 'homeowners', 'businesses',
        'contractors', 'developers', 'property managers', 'facilities',
        'households', 'families', 'companies', 'organizations'
    ]

    for evidence in evidence_rows:
        observation = evidence.get('observation', '').lower()
        limitation = evidence.get('limitation', '').lower()
        evidence_text = f"{observation} {limitation}"

        for indicator in customer_indicators:
            if indicator in evidence_text:
                customers.add(indicator)

    # If no specific customers found, infer from business type
    if not customers:
        industry = business_info.get('industry', '').lower()
        if 'construction' in industry or 'plumbing' in industry or 'electrical' in industry:
            customers.add('residential_and_commercial')
        elif 'retail' in industry or 'ecommerce' in industry:
            customers.add('general_consumers')
        elif 'saas' in industry or 'software' in industry:
            customers.add('businesses')
        else:
            customers.add('unspecified')

    return list(customers)


def _infer_customer_journey(evidence_rows: List[Dict], business_info: Dict) -> Dict:
    """Infer how customers enquire, quote, book, or reorder."""
    journey = {
        "enquiry_methods": [],
        "quote_process": [],
        "booking_process": [],
        "reorder_process": [],
        "payment_methods": []
    }

    # Journey indicators
    enquiry_indicators = ['contact form', 'phone', 'email', 'website', 'visit', 'call']
    quote_indicators = ['quote', 'estimate', 'pricing', 'price']
    booking_indicators = ['book', 'schedule', 'appointment', 'reserve']
    reorder_indicators = ['reorder', 'repeat', 'again', 'subscription']
    payment_indicators = ['payment', 'invoice', 'bill', 'pay']

    for evidence in evidence_rows:
        observation = evidence.get('observation', '').lower()
        limitation = evidence.get('limitation', '').lower()
        evidence_text = f"{observation} {limitation}"

        for indicator in enquiry_indicators:
            if indicator in evidence_text:
                journey["enquiry_methods"].append(indicator)

        for indicator in quote_indicators:
            if indicator in evidence_text:
                journey["quote_process"].append(indicator)

        for indicator in booking_indicators:
            if indicator in evidence_text:
                journey["booking_process"].append(indicator)

        for indicator in reorder_indicators:
            if indicator in evidence_text:
                journey["reorder_process"].append(indicator)

        for indicator in payment_indicators:
            if indicator in evidence_text:
                journey["payment_methods"].append(indicator)

    # Deduplicate
    for key in journey:
        journey[key] = list(set(journey[key]))

    return journey


def _infer_existing_mechanisms(evidence_rows: List[Dict]) -> List[str]:
    """Infer what mechanisms already work from evidence."""
    mechanisms = set()

    # Positive indicators of working systems
    positive_indicators = [
        'working', 'functional', 'operational', 'efficient', 'effective',
        'reliable', 'consistent', 'established', 'established', 'running'
    ]

    for evidence in evidence_rows:
        observation = evidence.get('observation', '').lower()
        limitation = evidence.get('limitation', '').lower()
        evidence_text = f"{observation} {limitation}"

        # Look for positive statements about systems
        for indicator in positive_indicators:
            if indicator in evidence_text:
                # Try to extract what is working
                words = evidence_text.split()
                for i, word in enumerate(words):
                    if word == indicator and i > 0:
                        # Look at preceding words for what is working
                        if i >= 2:
                            mechanism = f"{words[i-2]} {words[i-1]} {word}"
                            mechanisms.add(mechanism)
                        elif i >= 1:
                            mechanism = f"{words[i-1]} {word}"
                            mechanisms.add(mechanism)

    return list(mechanisms) if mechanisms else ["none_identified"]


def _infer_friction_points(evidence_rows: List[Dict]) -> List[str]:
    """Infer specific observed friction points from evidence."""
    friction = set()

    # Friction/problem indicators
    friction_indicators = [
        'problem', 'issue', 'challenge', 'difficulty', 'struggle', 'pain point',
        'not working', 'broken', 'slow', 'inefficient', 'manual', 'time-consuming',
        'expensive', 'costly', 'frustrating', 'complicated', 'confusing'
    ]

    for evidence in evidence_rows:
        observation = evidence.get('observation', '').lower()
        limitation = evidence.get('limitation', '').lower()
        evidence_text = f"{observation} {limitation}"

        for indicator in friction_indicators:
            if indicator in evidence_text:
                # Try to extract the friction point
                words = evidence_text.split()
                for i, word in enumerate(words):
                    if word == indicator:
                        # Look at surrounding words for context
                        start = max(0, i-3)
                        end = min(len(words), i+3)
                        context = " ".join(words[start:end])
                        friction.add(context)
                        break

    return list(friction) if friction else ["none_identified"]


def _infer_restrictions(evidence_rows: List[Dict], business_info: Dict) -> List[str]:
    """Infer relevant restrictions from evidence."""
    restrictions = set()

    # Restriction indicators
    restriction_indicators = [
        'restriction', 'limitation', 'constraint', 'limitation', 'cannot',
        'unable', 'limited', 'restricted', 'prohibited', 'not allowed',
        'regulation', 'compliance', 'requirement', 'must', 'have to'
    ]

    for evidence in evidence_rows:
        observation = evidence.get('observation', '').lower()
        limitation = evidence.get('limitation', '').lower()
        evidence_text = f"{observation} {limitation}"

        for indicator in restriction_indicators:
            if indicator in evidence_text:
                restrictions.add(indicator)

    # Add region-based restrictions
    region = business_info.get('region', '').lower()
    if region:
        restrictions.add(f"region_based:{region}")

    return list(restrictions) if restrictions else ["none_identified"]


def _identify_unknowns(evidence_rows: List[Dict], pipeline_rows: List[Dict]) -> List[str]:
    """Identify unknowns based on gaps in evidence and pipeline history."""
    unknowns = set()

    # Common unknown areas in business assessment
    unknown_areas = [
        'pricing_strategy', 'customer_acquisition_cost', 'customer_lifetime_value',
        'market_share', 'competition', 'growth_rate', 'profit_margins',
        'technology_stack', 'team_size', 'funding_status', 'expansion_plans'
    ]

    # Check what we have evidence for
    has_evidence_for = set()
    for evidence in evidence_rows:
        observation = evidence.get('observation', '').lower()
        limitation = evidence.get('limitation', '').lower()
        evidence_text = f"{observation} {limitation}"

        for area in unknown_areas:
            if area.replace('_', ' ') in evidence_text:
                has_evidence_for.add(area)

    # Unknowns are areas we don't have evidence for
    unknowns = set(unknown_areas) - has_evidence_for

    # Add pipeline-based unknowns
    pipeline_states = set()
    for pipeline in pipeline_rows:
        state = pipeline.get('state', '')
        if state:
            pipeline_states.add(state)

    # If we haven't moved beyond discovery, we don't know much about later stages
    if pipeline_states <= {'DISCOVERED'}:
        unknowns.update(['contact_information_verified', 'quoting_process',
                        'customer_feedback', 'service_delivery'])

    return list(unknowns) if unknowns else ["none_identified"]


def _assess_evidence_quality(evidence_rows: List[Dict], current_state: str) -> Dict:
    """Assess the quality and freshness of evidence, adjusted for current state."""
    if not evidence_rows:
        return {"quality": "none", "freshness": "no_evidence", "score": 0.0}

    # Freshness assessment
    freshness_scores = []
    for evidence in evidence_rows:
        try:
            checked_at_str = evidence.get('checked_at', '')
            if checked_at_str:
                checked_at = datetime.fromisoformat(checked_at_str.replace('Z', '+00:00'))
                days_old = (datetime.now(timezone.utc) - checked_at).days

                # Freshness score: 1.0 for today, decaying to 0.0 at 30 days
                if days_old <= 0:
                    freshness = 1.0
                elif days_old >= 30:
                    freshness = 0.0
                else:
                    freshness = 1.0 - (days_old / 30.0)

                freshness_scores.append(freshness)
            else:
                freshness_scores.append(0.2)  # No date available
        except (ValueError, TypeError):
            freshness_scores.append(0.2)  # Unable to parse date

    avg_freshness = sum(freshness_scores) / len(freshness_scores) if freshness_scores else 0.0

    # Quality assessment
    quality_scores = []
    for evidence in evidence_rows:
        limitation = evidence.get('limitation', '').lower()

        # Limitations that reduce quality
        quality_limitations = [
            'incomplete', 'partial', 'estimated', 'approximate',
            'based on', 'according to', 'reportedly', 'allegedly'
        ]

        quality_score = 0.7  # Baseline quality score
        for limitation_indicator in quality_limitations:
            if limitation_indicator in limitation:
                quality_score -= 0.15
                break

        # Check for validation indicators
        validation_indicators = [
            'verified', 'confirmed', 'validated', 'tested',
            'measured', 'observed', 'confirmed', 'checked'
        ]

        for validation_indicator in validation_indicators:
            if validation_indicator in limitation:
                quality_score += 0.15
                break

        quality_score = max(0.1, min(1.0, quality_score))
        quality_scores.append(quality_score)

    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0

    # State-adjusted scoring - later states should have higher quality evidence
    state_multiplier = {
        'IDENTITY_PENDING': 0.8,
        'IDENTITY_RESOLVED': 0.9,
        'AUDIT_PENDING': 0.95,
        'AUDITED': 1.0
    }.get(current_state, 0.8)

    adjusted_quality = avg_quality * state_multiplier
    adjusted_freshness = avg_freshness * state_multiplier

    # Overall evidence assessment
    evidence_score = (adjusted_freshness * 0.4) + (adjusted_quality * 0.6)

    return {
        "quality": "high" if adjusted_quality >= 0.7 else "medium" if adjusted_quality >= 0.4 else "low",
        "freshness": "fresh" if adjusted_freshness >= 0.7 else "recent" if adjusted_freshness >= 0.4 else "stale",
        "score": round(evidence_score, 3),
        "freshness_details": {
            "average_days_old": sum((datetime.now(timezone.utc) -
                                  datetime.fromisoformat(e.get('checked_at', '').replace('Z', '+00:00')).days
                                 for e in evidence_rows if e.get('checked_at')) /
                                 max(len([e for e in evidence_rows if e.get('checked_at')]), 1)) if any(e.get('checked_at') for e in evidence_rows else 0),
            "evidence_count": len(evidence_rows)
        },
        "quality_details": {
            "validation_indicators_found": sum(1 for e in evidence_rows
                                             for v in ['verified', 'confirmed', 'validated', 'tested']
                                             if v in e.get('limitation', '').lower()),
            "limitation_indicators_found": sum(1 for e in evidence_rows
                                             for l in ['incomplete', 'partial', 'estimated', 'approximate']
                                             if l in e.get('limitation', '').lower()),
            "state_multiplier": state_multiplier
        }
    }


def _calculate_understanding_confidence(evidence_rows: List[Dict], pipeline_rows: List[Dict], current_state: str) -> float:
    """Calculate confidence in the understanding constructed."""
    if not evidence_rows:
        return 0.0

    # Base factors for understanding confidence
    factors = []

    # Evidence quantity factor (more evidence = better understanding)
    quantity_score = min(1.0, len(evidence_rows) / 15.0)  # Normalize to expected max
    factors.append(quantity_score * 0.3)

    # Evidence quality factor
    quality_assessment = _assess_evidence_quality(evidence_rows, current_state)
    quality_score = quality_assessment.get('score', 0.0)
    factors.append(quality_score * 0.4)

    # Pipeline progression factor (further along = better contextual understanding)
    pipeline_states = [p.get('state') for p in pipeline_rows if p.get('state')]
    state_order = ['DISCOVERED', 'IDENTITY_PENDING', 'IDENTITY_RESOLVED', 'AUDIT_PENDING', 'AUDITED']
    try:
        current_index = state_order.index(current_state) if current_state in state_order else 0
        max_index = len(state_order) - 1
        progression_score = current_index / max_index if max_index > 0 else 0.0
        factors.append(progression_score * 0.3)
    except (ValueError, IndexError):
        factors.append(0.1)  # Default low score if state not recognized

    return sum(factors)


def _assess_understanding_completeness(evidence_rows: List[Dict], pipeline_rows: List[Dict], current_state: str) -> float:
    """Assess how complete the understanding is for decision making."""
    if not evidence_rows:
        return 0.0

    # Check for key understanding components
    understanding_components = {
        'identity': False,
        'offerings': False,
        'customers': False,
        'operations': False,
        'challenges': False,
        'opportunities': False
    }

    # Analyze evidence for each component
    for evidence in evidence_rows:
        observation = evidence.get('observation', '').lower()
        limitation = evidence.get('limitation', '').lower()
        evidence_text = f"{observation} {limitation}"

        # Identity components
        if any(term in evidence_text for term in ['name', 'business', 'company', 'established']):
            understanding_components['identity'] = True

        # Offerings/components
        if any(term in evidence_text for term in ['offer', 'provide', 'sell', 'service', 'product']):
            understanding_components['offerings'] = True

        # Customer information
        if any(term in evidence_text for term in ['customer', 'client', 'buyer', 'user']):
            understanding_components['customers'] = True

        # Operations/processes
        if any(term in evidence_text for term in ['process', 'system', 'workflow', 'operation']):
            understanding_components['operations'] = True

        # Challenges/problems
        if any(term in evidence_text for term in ['problem', 'issue', 'challenge', 'difficulty']):
            understanding_components['challenges'] = True

        # Opportunities/improvements
        if any(term in evidence_text for term in ['opportunity', 'improve', 'enhance', 'better']):
            understanding_components['opportunities'] = True

    # Calculate completeness score
    completed_components = sum(1 for v in understanding_components.values() if v)
    total_components = len(understanding_components)
    completeness_score = completed_components / total_components if total_components > 0 else 0.0

    # Apply state-appropriate expectations
    state_expectations = {
        'IDENTITY_PENDING': 0.4,  # Expect basic identity and offerings
        'IDENTITY_RESOLVED': 0.6,  # Expect identity, offerings, basic customers
        'AUDIT_PENDING': 0.7,    # Expect most components
        'AUDITED': 0.8           # Expect near-complete understanding
    }

    expected_completeness = state_expectations.get(current_state, 0.5)
    if expected_completeness > 0:
        completeness_ratio = completeness_score / expected_completeness
        return min(1.0, completeness_ratio)  # Cap at 1.0

    return completeness_score


def _check_readiness_for_next_stage(d, business_id: int, payload: Dict, current_state: str) -> Dict:
    """Check readiness to proceed to the next stage based on current state."""
    try:
        with connect() as conn:
            ready = True
            reason = "Ready to proceed"
            checks = {}

            if current_state == 'IDENTITY_PENDING':
                # Check if identity can be resolved
                business_row = conn.execute(
                    "SELECT public_website, name, region FROM businesses WHERE id = ?",
                    (business_id,)
                ).fetchone()

                if business_row:
                    website = business_row['public_website']
                    name = business_row['name']
                    region = business_row['region']

                    has_website = bool(website and website.strip())
                    has_name = bool(name and name.strip())
                    has_region = bool(region and region.strip())

                    checks = {
                        "has_website": has_website,
                        "has_name": has_name,
                        "has_region": has_region,
                        "identity_resolvable": has_website and (has_name or has_region)
                    }

                    if not checks["identity_resolvable"]:
                        ready = False
                        reason = "Insufficient information to resolve business identity"
                    elif not has_website:
                        ready = False
                        reason = "No website available for identity resolution"

            elif current_state == 'IDENTITY_RESOLVED':
                # Check if we have sufficient identity resolution
                # In reality, this would check if we confirmed the identity
                checks = {
                    "identity_confirmed": True  # Placeholder - would check actual confirmation
                }
                # Assume ready if we got to this state

            elif current_state == 'AUDIT_PENDING':
                # Check if ready to execute audit
                website_row = conn.execute(
                    "SELECT public_website FROM businesses WHERE id = ?",
                    (business_id,)
                ).fetchone()

                website = website_row['public_website'] if website_row else None
                checks = {
                    "website_available": bool(website and website.strip()),
                    "audit_executable": bool(website and website.strip())
                }

                if not checks["website_available"]:
                    ready = False
                    reason = "No website available to audit"

            elif current_state == 'AUDITED':
                # Check if audit evidence is sufficient for qualification
                evidence_count = conn.execute(
                    "SELECT COUNT(*) as count FROM mm_evidence WHERE business_id = ?",
                    (business_id,)
                ).fetchone()

                count = evidence_count['count'] if evidence_count else 0
                checks = {
                    "audit_evidence_available": count > 0,
                    "sufficient_evidence": count >= 3  # Require minimum evidence
                }

                if count == 0:
                    ready = False
                    reason = "No audit evidence available"
                elif count < 3:
                    ready = False
                    reason = f"Insufficient audit evidence ({count} pieces, need at least 3)"
            else:
                # Default readiness check
                checks = {"default_check": True}

            return {
                "ready": ready,
                "reason": reason,
                "checks": checks,
                "ready_for_audit": checks.get("audit_executable", False) or checks.get("website_available", False),
                "ready_for_audit_execution": checks.get("audit_executable", False),
                "ready_for_qualification": checks.get("sufficient_evidence", False) or checks.get("audit_evidence_available", False)
            }
    except Exception as e:
        return {
            "ready": False,
            "reason": f"Error checking readiness: {str(e)}",
            "checks": {},
            "ready_for_audit": False,
            "ready_for_audit_execution": False,
            "ready_for_qualification": False
        }


def _identify_audit_focus_areas(business_understanding: Dict, opportunity_score_result: Dict) -> List[str]:
    """Identify specific areas to focus audit on based on understanding and opportunity score."""
    focus_areas = []

    # Add focus areas from friction points
    friction_points = business_understanding.get('friction_points', [])
    if friction_points and friction_points != ['none_identified']:
        focus_areas.extend([f"Investigate friction: {fp}" for fp in friction_points[:2]])

    # Add focus areas from opportunity components that need validation
    components = opportunity_score_result.get('components', {})
    weak_components = [k for k, v in components.items() if v < 60]  # Components below 60/100
    if weak_components:
        focus_areas.extend([f"Validate opportunity component: {comp}" for comp in weak_components[:2]])

    # Add focus areas from unknowns that could affect decision
    unknowns = business_understanding.get('unknowns', [])
    if unknowns and unknowns != ['none_identified']:
        critical_unknowns = [u for u in unknowns if any(term in u.lower() for term in
                          ['pricing', 'decision', 'competition', 'technology'])]
        focus_areas.extend([f"Investigate critical unknown: {uk}" for uk in critical_unknowns[:2]])

    # Default focus areas if none identified
    if not focus_areas:
        focus_areas = [
            "Standard website accessibility audit",
            "Basic contact information verification",
            "Initial service offering confirmation"
        ]

    return focus_areas[:5]  # Limit to top 5


# Register this worker for the understanding states
UNDERSTANDING_WORKER_STATES = ('IDENTITY_PENDING', 'IDENTITY_RESOLVED', 'AUDIT_PENDING', 'AUDITED')

if __name__ == '__main__':
    # Test the understanding worker components
    print("Understanding worker for Loop B loaded successfully")
    print(f"Registered for states: {UNDERSTANDING_WORKER_STATES}")
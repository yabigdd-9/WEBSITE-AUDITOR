"""Discovery worker for Loop A: Discover where useful work exists.

Implements campaign-driven discovery with three complementary angles:
1. Problem-led (reproducible obstacle)
2. Strength-led (existing strength extension)
3. Change-led (new evidence reconsideration)

Works with opportunity recipes and source-quality accounting.
"""

import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from mm_core import now, root, sha
from mm_pipeline import get_loop_for_state, advance, enqueue, transition, RetryableError, PermanentError


def discover_worker_handler(d, item_row, worker):
    """Discover where useful work exists - Loop A handler.

    Args:
        d: Database connection
        item_row: Pipeline item row
        worker: Worker instance

    Returns:
        Tuple of (next_state, reason, evidence)
    """
    business_id = item_row['business_id']
    payload = json.loads(item_row['payload'] or '{}')

    # Get campaign configuration if available
    campaign_id = payload.get('campaign_id')
    campaign_config = _get_campaign_config(d, campaign_id) if campaign_id else _get_default_campaign()

    # Perform discovery based on opportunity recipe
    recipe_id = payload.get('recipe_id') or campaign_config.get('default_recipe')
    discovery_result = _perform_discovery(d, business_id, recipe_id, campaign_config)

    # Update payload with discovery findings
    payload.update({
        'discovery_timestamp': now(),
        'discovery_result': discovery_result,
        'campaign_id': campaign_id,
        'recipe_id': recipe_id
    })

    # Determine next state based on discovery outcome
    if discovery_result.get('should_proceed', False):
        # Move to identity resolution phase
        next_state = 'IDENTITY_PENDING'
        reason = f'Discovered opportunity via {discovery_result.get("angle", "unknown")} angle'
        evidence = {
            'discovery_angle': discovery_result.get('angle'),
            'opportunity_type': discovery_result.get('opportunity_type'),
            'confidence_score': discovery_result.get('confidence_score', 0.0),
            'supported_signals': discovery_result.get('supported_signals', []),
            'evidence_sources': discovery_result.get('evidence_sources', [])
        }
    else:
        # No useful work found - suppress or reject based on reason
        if discovery_result.get('insufficient_evidence', False):
            next_state = 'SUPPRESSED'
            reason = 'Insufficient evidence for meaningful opportunity'
        else:
            next_state = 'REJECTED'
            reason = 'No viable opportunity discovered'

        evidence = {
            'discovery_angle': discovery_result.get('angle'),
            'reason': discovery_result.get('reason', 'No opportunity identified')
        }

    return next_state, reason, evidence


def _get_campaign_config(d, campaign_id: str) -> Dict:
    """Get campaign configuration from database or fixtures."""
    # Try to get from campaign_configs table first
    try:
        row = d.execute(
            "SELECT config FROM campaign_configs WHERE campaign_id = ?",
            (campaign_id,)
        ).fetchone()
        if row and row['config']:
            return json.loads(row['config'])
    except Exception:
        pass  # Fall back to fixture-based config

    # Load from fixture file
    fixture_path = root() / 'money-machine' / 'fixtures' / 'campaigns' / f'{campaign_id}.json'
    if fixture_path.exists():
        with open(fixture_path, 'r') as f:
            return json.load(f)

    return _get_default_campaign()


def _get_default_campaign() -> Dict:
    """Get default campaign configuration."""
    return {
        'campaign_id': 'default',
        'target_region': 'global',
        'business_characteristics': ['has_website', 'local_business'],
        'supported_services': ['website_audit', 'seo_optimization', 'conversion_optimization'],
        'discovery_sources': ['google_search', 'local_directories', 'industry_specific'],
        'opportunity_recipes': ['enquiry_path_repair', 'quote_information', 'repeat_order_assistance'],
        'research_capacity_per_business': 180,  # seconds
        'evidence_freshness_days': 30,
        'default_recipe': 'enquiry_path_repair'
    }


def _perform_discovery(d, business_id: int, recipe_id: str, campaign_config: Dict) -> Dict:
    """Perform discovery using the specified recipe and campaign configuration."""
    # Load opportunity recipe
    recipe = _load_opportunity_recipe(recipe_id)
    if not recipe:
        return {
            'should_proceed': False,
            'reason': f'Unknown opportunity recipe: {recipe_id}',
            'angle': 'unknown',
            'confidence_score': 0.0
        }

    # Get business context
    business_context = _get_business_context(d, business_id)
    if not business_context:
        return {
            'should_proceed': False,
            'reason': 'Unable to retrieve business context',
            'angle': 'unknown',
            'confidence_score': 0.0
        }

    # Apply the three discovery angles
    discovery_angles = [
        ('problem_led', _discover_problem_led),
        ('strength_led', _discover_strength_led),
        ('change_led', _discover_change_led)
    ]

    best_result = None
    best_score = 0.0

    for angle_name, angle_func in discovery_angles:
        try:
            result = angle_func(d, business_id, business_context, recipe, campaign_config)
            score = result.get('confidence_score', 0.0)

            if score > best_score:
                best_score = score
                best_result = result
                best_result['angle'] = angle_name

        except Exception as ex:
            # Log but continue with other angles
            print(f"Discovery angle {angle_name} failed: {ex}")
            continue

    if not best_result or best_score < 0.3:  # Minimum threshold
        return {
            'should_proceed': False,
            'reason': 'No discovery angle produced sufficient confidence',
            'angle': 'none',
            'confidence_score': best_score if best_result else 0.0,
            'evidence_sources': [],
            'supported_signals': []
        }

    # Check if we have sufficient evidence to proceed
    if best_result.get('confidence_score', 0.0) >= 0.6:  # Confidence threshold
        return {
            'should_proceed': True,
            'opportunity_type': best_result.get('opportunity_type'),
            'confidence_score': best_result['confidence_score'],
            'supported_signals': best_result.get('supported_signals', []),
            'evidence_sources': best_result.get('evidence_sources', []),
            'angle': best_result.get('angle'),
            'recipe_id': recipe_id,
            'business_context': business_context
        }
    else:
        return {
            'should_proceed': False,
            'reason': f'Insufficient confidence ({best_score:.2f}) for opportunity pursuit',
            'angle': best_result.get('angle', 'unknown'),
            'confidence_score': best_score,
            'evidence_sources': best_result.get('evidence_sources', []),
            'supported_signals': best_result.get('supported_signals', [])
        }


def _load_opportunity_recipe(recipe_id: str) -> Optional[Dict]:
    """Load opportunity recipe from fixtures."""
    from mm_core import root
    fixture_path = root() / 'money-machine' / 'fixtures' / 'opportunity_recipes' / f'{recipe_id}.json'
    if not fixture_path.exists():
        return None

    try:
        with open(fixture_path, 'r') as f:
            return json.load(f)
    except Exception:
        return None


def _get_business_context(d, business_id: int) -> Optional[Dict]:
    """Get business context from database."""
    try:
        # Get basic business info
        business_row = d.execute(
            "SELECT id, name, website, region, created_at FROM businesses WHERE id = ?",
            (business_id,)
        ).fetchone()

        if not business_row:
            return None

        # Get recent evidence/audits
        evidence_rows = d.execute(
            """SELECT id, url, timestamp, score, details
               FROM evidence
               WHERE business_id = ?
               ORDER BY timestamp DESC
               LIMIT 10""",
            (business_id,)
        ).fetchall()

        # Get previous pipeline items for this business
        pipeline_rows = d.execute(
            """SELECT state, updated_at, payload
               FROM pipeline_items
               WHERE business_id = ?
               ORDER BY updated_at DESC
               LIMIT 5""",
            (business_id,)
        ).fetchall()

        return {
            'business_info': dict(business_row) if business_row else {},
            'recent_evidence': [dict(row) for row in evidence_rows],
            'pipeline_history': [dict(row) for row in pipeline_rows],
            'last_checked': datetime.now(timezone.utc).isoformat()
        }
    except Exception:
        return None


def _discover_problem_led(d, business_id: int, business_context: Dict,
                         recipe: Dict, campaign_config: Dict) -> Dict:
    """Problem-led discovery: Find reproducible obstacles."""
    evidence_sources = []
    supported_signals = []
    confidence_factors = []

    business_info = business_context.get('business_info', {})
    recent_evidence = business_context.get('recent_evidence', [])

    # Check for common problems mentioned in evidence
    problem_indicators = recipe.get('problem_indicators', [])
    for evidence in recent_evidence:
        evidence_sources.append(evidence.get('id'))
        details = evidence.get('details', '')
        url = evidence.get('url', '')

        # Look for problem indicators in evidence details
        for indicator in problem_indicators:
            if indicator.lower() in details.lower() or indicator.lower() in url.lower():
                supported_signals.append({
                    'type': 'problem_indicator',
                    'indicator': indicator,
                    'source': 'evidence',
                    'url': url,
                    'snippet': details[:200] if details else ''
                })
                confidence_factors.append(0.3)  # Each problem indicator adds confidence

    # Check for explicit customer complaints or requests
    complaint_indicators = recipe.get('complaint_indicators', [])
    for evidence in recent_evidence:
        details = evidence.get('details', '').lower()
        for indicator in complaint_indicators:
            if indicator in details:
                supported_signals.append({
                    'type': 'explicit_complaint',
                    'complaint': indicator,
                    'source': 'evidence_feedback'
                })
                confidence_factors.append(0.4)  # Complaints are strong signals

    # Calculate final confidence
    base_confidence = 0.1
    indicator_confidence = min(sum(confidence_factors), 0.8)  # Cap at 0.8 from indicators
    final_confidence = min(base_confidence + indicator_confidence, 1.0)

    return {
        'should_proceed': final_confidence >= 0.6,
        'opportunity_type': recipe.get('opportunity_type', 'general_optimization'),
        'confidence_score': final_confidence,
        'supported_signals': supported_signals,
        'evidence_sources': list(set(evidence_sources)),  # Deduplicate
        'discovery_method': 'problem_led'
    }


def _discover_strength_led(d, business_id: int, business_context: Dict,
                          recipe: Dict, campaign_config: Dict) -> Dict:
    """Strength-led discovery: Extend existing strengths."""
    evidence_sources = []
    supported_signals = []
    confidence_factors = []

    business_info = business_context.get('business_info', {})
    recent_evidence = business_context.get('recent_evidence', [])

    # Look for existing strengths to build upon
    strength_indicators = recipe.get('strength_indicators', [])
    for evidence in recent_evidence:
        evidence_sources.append(evidence.get('id'))
        details = evidence.get('details', '')
        score = evidence.get('score', 0)

        # High scores indicate strengths
        if score >= 0.7:
            for indicator in strength_indicators:
                if indicator.lower() in details.lower():
                    supported_signals.append({
                        'type': 'existing_strength',
                        'strength': indicator,
                        'evidence_score': score,
                        'source': 'high_performing_area'
                    })
                    confidence_factors.append(0.25)

    # Check for expanding service opportunities
    service_expansion_indicators = recipe.get('service_expansion_indicators', [])
    for evidence in recent_evidence:
        details = evidence.get('details', '').lower()
        for indicator in service_expansion_indicators:
            if indicator in details:
                supported_signals.append({
                    'type': 'service_expansion_opportunity',
                    'opportunity': indicator,
                    'source': 'evidence_analysis'
                })
                confidence_factors.append(0.3)

    # Calculate final confidence
    base_confidence = 0.15  # Slightly higher base for strength-led
    indicator_confidence = min(sum(confidence_factors), 0.75)
    final_confidence = min(base_confidence + indicator_confidence, 1.0)

    return {
        'should_proceed': final_confidence >= 0.6,
        'opportunity_type': recipe.get('opportunity_type', 'strength_extension'),
        'confidence_score': final_confidence,
        'supported_signals': supported_signals,
        'evidence_sources': list(set(evidence_sources)),
        'discovery_method': 'strength_led'
    }


def _discover_change_led(d, business_id: int, business_context: Dict,
                        recipe: Dict, campaign_config: Dict) -> Dict:
    """Change-led discovery: Reconsider based on new evidence."""
    evidence_sources = []
    supported_signals = []
    confidence_factors = []

    business_info = business_context.get('business_info', {})
    recent_evidence = business_context.get('recent_evidence', [])
    pipeline_history = business_context.get('pipeline_history', [])

    # Look for recent changes or new information
    change_indicators = recipe.get('change_indicators', [])
    cutoff_time = datetime.now(timezone.utc).timestamp() - (campaign_config.get('evidence_freshness_days', 30) * 86400)

    for evidence in recent_evidence:
        evidence_timestamp = evidence.get('timestamp')
        if evidence_timestamp:
            try:
                # Handle various timestamp formats
                if isinstance(evidence_timestamp, str):
                    ev_time = datetime.fromisoformat(evidence_timestamp.replace('Z', '+00:00')).timestamp()
                else:
                    ev_time = float(evidence_timestamp)

                if ev_time > cutoff_time:  # Recently updated evidence
                    evidence_sources.append(evidence.get('id'))
                    details = evidence.get('details', '')

                    for indicator in change_indicators:
                        if indicator.lower() in details.lower():
                            supported_signals.append({
                                'type': 'recent_change',
                                'change': indicator,
                                'evidence_age_days': (datetime.now(timezone.utc).timestamp() - ev_time) / 86400,
                                'source': 'timely_evidence'
                            })
                            confidence_factors.append(0.35)  # Recent changes are valuable
            except (ValueError, TypeError):
                continue  # Skip unparseable timestamps

    # Check for contradictory evidence that suggests opportunity
    contradiction_indicators = recipe.get('contradiction_indicators', [])
    if len(pipeline_history) >= 2:
        # Compare recent vs historical assessments
        latest_state = pipeline_history[0].get('state') if pipeline_history else None
        if latest_state in ['AUDITED', 'VERIFIED']:  # Previously assessed positively
            for evidence in recent_evidence:
                details = evidence.get('details', '').lower()
                for indicator in contradiction_indicators:
                    if indicator in details:
                        supported_signals.append({
                            'type': 'contradictory_evidence',
                            'contradiction': indicator,
                            'previous_assessment': latest_state,
                            'source': 'evidence_contradiction'
                        })
                        confidence_factors.append(0.4)  # Contradictions after positive assessment are significant

    # Calculate final confidence
    base_confidence = 0.2  # Higher base for change-led (values new information)
    indicator_confidence = min(sum(confidence_factors), 0.7)
    final_confidence = min(base_confidence + indicator_confidence, 1.0)

    return {
        'should_proceed': final_confidence >= 0.6,
        'opportunity_type': recipe.get('opportunity_type', 'change_based_optimization'),
        'confidence_score': final_confidence,
        'supported_signals': supported_signals,
        'evidence_sources': list(set(evidence_sources)),
        'discovery_method': 'change_led'
    }


# Register this worker for the discovery states
DISCOVERY_WORKER_STATES = ('DISCOVERED',)

if __name__ == '__main__':
    # Test the discovery worker components
    print("Discovery worker for Loop A loaded successfully")
    print(f"Registered for states: {DISCOVERY_WORKER_STATES}")
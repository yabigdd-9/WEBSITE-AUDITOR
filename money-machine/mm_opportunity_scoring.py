"""Opportunity scoring using the 6-component model from the plan.

Implements the opportunity scoring system for Loop B:
- Supported problem/explicit request (25 points)
- Evidence-to-solution fit (20 points)
- Business and campaign fit (20 points)
- Bounded delivery feasibility (15 points)
- Evidence quality and freshness (10 points)
- Supported reason to act now (10 points)
"""

import json
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from mm_core import now, sha, connect
from mm_lead_qualifier import qualify_lead, detect_job_signals, detect_budget_signals


class OpportunityScorer:
    """Scores opportunities using the 6-component model."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Path("money_machine.db")

    def score_opportunity(self, business_id: int, campaign_id: str = "default") -> Dict:
        """
        Score an opportunity using the 6-component model.

        Returns:
            Dict with opportunity score (0-100) and component breakdown
        """
        # Get business and campaign context
        business_context = self._get_business_context(business_id)
        campaign_context = self._get_campaign_context(campaign_id)

        if not business_context:
            return self._empty_score("Unable to retrieve business context")

        # Calculate each component
        supported_problem = self._score_supported_problem(business_context, campaign_context)
        evidence_to_solution_fit = self._score_evidence_to_solution_fit(business_context, campaign_context)
        business_and_campaign_fit = self._score_business_and_campaign_fit(business_context, campaign_context)
        bounded_delivery_feasibility = self._score_bounded_delivery_feasibility(business_context, campaign_context)
        evidence_quality_freshness = self._score_evidence_quality_freshness(business_context, campaign_context)
        supported_reason_to_act_now = self._score_supported_reason_to_act_now(business_context, campaign_context)

        # Use the existing 6-component scoring function
        from mm_core import opportunity_score_6_component
        result = opportunity_score_6_component(
            supported_problem=supported_problem,
            evidence_to_solution_fit=evidence_to_solution_fit,
            business_and_campaign_fit=business_and_campaign_fit,
            bounded_delivery_feasibility=bounded_delivery_feasibility,
            evidence_quality_freshness=evidence_quality_freshness,
            supported_reason_to_act_now=supported_reason_to_act_now
        )

        # Add context information
        result.update({
            "business_id": business_id,
            "campaign_id": campaign_id,
            "scored_at": now(),
            "business_context": business_context,
            "campaign_context": campaign_context
        })

        return result

    def _get_business_context(self, business_id: int) -> Optional[Dict]:
        """Get comprehensive business context for scoring."""
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
                    return None

                business_info = dict(business_row)

                # Get recent evidence/audits
                evidence_rows = conn.execute(
                    """SELECT id, url, observation, limitation, checked_at, evidence
                       FROM mm_evidence
                       WHERE business_id = ?
                       ORDER BY checked_at DESC
                       LIMIT 10""",
                    (business_id,)
                ).fetchall()

                # Get pipeline history
                pipeline_rows = conn.execute(
                    """SELECT state, updated_at, payload
                       FROM pipeline_items
                       WHERE business_id = ?
                       ORDER BY updated_at DESC
                       LIMIT 10""",
                    (business_id,)
                ).fetchall()

                # Get contact evidence
                contact_rows = conn.execute(
                    """SELECT recipient, permission_basis, permission_verified_by,
                              checked_at, capture_path, capture_hash
                       FROM mm_contact_evidence
                       WHERE business_id = ?
                       ORDER BY checked_at DESC
                       LIMIT 5""",
                    (business_id,)
                ).fetchall()

                return {
                    "business_info": business_info,
                    "recent_evidence": [dict(row) for row in evidence_rows],
                    "pipeline_history": [dict(row) for row in pipeline_rows],
                    "contact_evidence": [dict(row) for row in contact_rows],
                    "last_checked": datetime.now(timezone.utc).isoformat()
                }
        except Exception as e:
            print(f"Error getting business context: {e}")
            return None

    def _get_campaign_context(self, campaign_id: str) -> Optional[Dict]:
        """Get campaign context for scoring."""
        try:
            with connect() as conn:
                conn.row_factory = conn.Row

                campaign_row = conn.execute(
                    """SELECT campaign_id, name, description, config, target_region,
                              business_characteristics, supported_services, discovery_sources,
                              opportunity_recipes, research_capacity_per_business,
                              evidence_freshness_days, default_recipe
                       FROM campaign_configs
                       WHERE campaign_id = ?""",
                    (campaign_id,)
                ).fetchone()

                if not campaign_row:
                    # Return default campaign
                    return self._get_default_campaign()

                campaign_info = dict(campaign_row)
                # Parse JSON config if present
                if campaign_info.get('config'):
                    try:
                        campaign_info['config'] = json.loads(campaign_info['config'])
                    except json.JSONDecodeError:
                        pass

                return campaign_info
        except Exception as e:
            print(f"Error getting campaign context: {e}")
            return self._get_default_campaign()

    def _get_default_campaign(self) -> Dict:
        """Get default campaign configuration."""
        return {
            'campaign_id': 'default',
            'name': 'General Local Business Optimization',
            'target_region': 'global',
            'business_characteristics': ['has_website', 'local_business', 'customer_facing'],
            'supported_services': ['website_audit', 'seo_optimization', 'conversion_optimization'],
            'discovery_sources': ['google_search', 'local_directories', 'industry_specific'],
            'opportunity_recipes': ['enquiry_path_repair', 'quote_information', 'repeat_order_assistance'],
            'research_capacity_per_business': 180,
            'evidence_freshness_days': 30,
            'default_recipe': 'enquiry_path_repair'
        }

    def _empty_score(self, reason: str) -> Dict:
        """Return an empty score with reason."""
        from mm_core import opportunity_score_6_component
        result = opportunity_score_6_component(
            supported_problem=0.0,
            evidence_to_solution_fit=0.0,
            business_and_campaign_fit=0.0,
            bounded_delivery_feasibility=0.0,
            evidence_quality_freshness=0.0,
            supported_reason_to_act_now=0.0
        )
        result.update({
            "business_id": None,
            "campaign_id": None,
            "scored_at": now(),
            "score_reason": reason,
            "is_shortlist": False
        })
        return result

    # Component scoring methods

    def _score_supported_problem(self, business_context: Dict, campaign_context: Dict) -> float:
        """
        Score supported problem or explicit request (0-1, worth 25 points).

        Evaluates: What problem does the business have that we can solve?
        Is there an explicit request for help?
        """
        business_info = business_context.get('business_info', {})
        recent_evidence = business_context.get('recent_evidence', [])
        pipeline_history = business_context.get('pipeline_history', [])

        score_factors = []

        # Check for explicit requests in evidence
        explicit_request_indicators = [
            "need help with", "looking for", "seeking", "require",
            "want to improve", "need to fix", "requiring assistance",
            "looking for a solution", "seeking help with"
        ]

        for evidence in recent_evidence:
            observation = evidence.get('observation', '').lower()
            limitation = evidence.get('limitation', '').lower()

            for indicator in explicit_request_indicators:
                if indicator in observation or indicator in limitation:
                    score_factors.append(0.9)  # Strong explicit request
                    break

        # Check for business-stated problems
        problem_indicators = [
            "problem", "issue", "challenge", "difficulty", "struggle",
            "not working", "broken", "inefficient", "slow", "difficult"
        ]

        problem_count = 0
        for evidence in recent_evidence:
            observation = evidence.get('observation', '').lower()
            limitation = evidence.get('limitation', '').lower()

            for indicator in problem_indicators:
                if indicator in observation or indicator in limitation:
                    problem_count += 1
                    break

        if problem_count > 0:
            # Normalize problem count to 0-0.7 range
            problem_score = min(0.7, problem_count * 0.15)
            score_factors.append(problem_score)

        # Check for service-specific problems based on campaign
        supported_services = campaign_context.get('supported_services', [])
        if supported_services:
            service_mentions = 0
            for evidence in recent_evidence:
                observation = evidence.get('observation', '').lower()
                for service in supported_services:
                    # Convert service name to checkable terms
                    service_terms = service.replace('_', ' ').split()
                    if any(term in observation for term in service_terms):
                        service_mentions += 1
                        break

            if service_mentions > 0:
                service_score = min(0.6, service_mentions * 0.2)
                score_factors.append(service_score)

        # Check pipeline history for indications of problems
        for pipeline_item in pipeline_history:
            payload = pipeline_item.get('payload', {})
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    payload = {}

            if payload.get('discovery_result', {}).get('should_proceed', False):
                score_factors.append(0.5)  # Previous discovery indicated opportunity

        # Calculate final score
        if not score_factors:
            return 0.1  # Minimal baseline score

        # Weighted average with emphasis on strongest signals
        sorted_factors = sorted(score_factors, reverse=True)
        if len(sorted_factors) == 1:
            final_score = sorted_factors[0]
        else:
            # Give more weight to the strongest signal
            final_score = (sorted_factors[0] * 0.6) + (sum(sorted_factors[1:]) * 0.4 / max(len(sorted_factors)-1, 1))

        return min(1.0, max(0.0, final_score))

    def _score_evidence_to_solution_fit(self, business_context: Dict, campaign_context: Dict) -> float:
        """
        Score evidence-to-solution fit (0-1, worth 20 points).

        Evaluates: How well does our proposed solution fit the observed evidence?
        Does our solution address the actual problems we see?
        """
        business_info = business_context.get('business_info', {})
        recent_evidence = business_context.get('recent_evidence', [])
        supported_services = campaign_context.get('supported_services', [])

        if not recent_evidence or not supported_services:
            return 0.1

        score_factors = []

        # Check how well evidence aligns with supported services
        for evidence in recent_evidence:
            observation = evidence.get('observation', '').lower()
            limitation = evidence.get('limitation', '').lower()
            evidence_text = f"{observation} {limitation}"

            # Check for specific problem-solution alignments
            service_alignments = {
                'website_audit': ['broken', 'error', 'issue', 'problem', 'not working'],
                'seo_optimization': ['traffic', 'visibility', 'search', 'ranking', 'google'],
                'conversion_optimization': ['conversion', 'sale', 'lead', 'form', 'contact'],
                'inquiry_form_optimization': ['contact form', 'inquiry', 'enquiry', 'booking', 'get in touch'],
                'contact_process_improvement': ['response', 'reply', 'contact', 'communication', 'follow up'],
                'local_seo': ['local', 'nearby', 'area', 'region', 'canterbury'],
                'reputation_management': ['review', 'rating', 'feedback', 'reputation', 'testimonial']
            }

            alignment_score = 0.0
            matches = 0

            for service in supported_services:
                if service in service_alignments:
                    problem_indicators = service_alignments[service]
                    for indicator in problem_indicators:
                        if indicator in evidence_text:
                            matches += 1
                            alignment_score += 0.2

            if matches > 0:
                # Normalize to 0-0.8 range per evidence item
                normalized_score = min(0.8, alignment_score)
                score_factors.append(normalized_score)

        # Check for evidence quality indicators
        for evidence in recent_evidence:
            # Fresh evidence gets higher fit score
            try:
                checked_at_str = evidence.get('checked_at', '')
                if checked_at_str:
                    checked_at = datetime.fromisoformat(checked_at_str.replace('Z', '+00:00'))
                    days_old = (datetime.now(timezone.utc) - checked_at).days
                    if days_old <= 7:
                        score_factors.append(0.3)  # Fresh evidence
                    elif days_old <= 30:
                        score_factors.append(0.2)  # Reasonably fresh
                    else:
                        score_factors.append(0.1)  # Stale evidence
            except (ValueError, TypeError):
                score_factors.append(0.1)  # Unable to parse date

        # Calculate final score
        if not score_factors:
            return 0.1

        # Average the scores, weighted by recency
        if len(score_factors) <= 3:
            final_score = sum(score_factors) / len(score_factors)
        else:
            # Weight recent evidence more heavily
            weighted_sum = sum(score * (i + 1) for i, score in enumerate(reversed(score_factors)))
            weight_sum = sum(i + 1 for i in range(len(score_factors)))
            final_score = weighted_sum / weight_sum if weight_sum > 0 else 0.1

        return min(1.0, max(0.0, final_score))

    def _score_business_and_campaign_fit(self, business_context: Dict, campaign_context: Dict) -> float:
        """
        Score business and campaign fit (0-1, worth 20 points).

        Evaluates: How well does the business match our target criteria?
        Does the business fit our campaign's target region, characteristics, etc.?
        """
        business_info = business_context.get('business_info', {})
        target_region = campaign_context.get('target_region', 'global')
        business_characteristics = campaign_context.get('business_characteristics', [])
        region = business_info.get('region', '').lower()

        score_factors = []

        # Region fit
        if target_region.lower() == 'global' or region == target_region.lower():
            score_factors.append(0.8)  # Good region match
        elif target_region.lower() != 'global':
            # Check if region is compatible (e.g., nearby regions)
            compatible_regions = {
                'canterbury': ['marlborough', 'west coast', 'southland', 'otago'],
                'auckland': ['northland', 'waikato', 'bay of plenty']
            }
            if target_region.lower() in compatible_regions:
                if region in compatible_regions[target_region.lower()]:
                    score_factors.append(0.5)  # Compatible region
                else:
                    score_factors.append(0.2)  # Different region
            else:
                score_factors.append(0.3)  # Somewhat different region
        else:
            score_factors.append(0.5)  # Global target, some region fit assumed

        # Business characteristics fit
        business_name = business_info.get('name', '').lower()
        industry = business_info.get('industry', '').lower()
        source = business_info.get('source', '').lower()
        is_dummy = business_info.get('is_dummy', 1)

        # Check against undesirable characteristics
        undesirable_indicators = ['test', 'dummy', 'example', 'fake', 'spam']
        if any(indicator in business_name or indicator in source for indicator in undesirable_indicators):
            score_factors.append(0.1)  # Poor fit due to undesirable characteristics
        elif is_dummy:
            score_factors.append(0.0)  # Dummy businesses get zero fit
        else:
            # Positive characteristics
            positive_indicators = ['ltd', 'limited', 'company', 'corp', 'inc', 'co', 'services', 'solutions']
            positive_count = sum(1 for indicator in positive_indicators if indicator in business_name)
            if positive_count > 0:
                score_factors.append(min(0.7, 0.3 + positive_count * 0.1))
            else:
                score_factors.append(0.4)  # Neutral business characteristics

        # Industry fit with campaign
        # This would be enhanced with specific industry targeting in campaigns
        # For now, give a baseline score for non-empty industry
        if industry and industry not in ['', 'unknown', 'none']:
            score_factors.append(0.6)
        else:
            score_factors.append(0.3)  # Unknown industry

        # Source credibility
        credible_sources = ['google', 'business register', 'official directory', 'industry association']
        source_credibility = 0.3  # Baseline
        for source in credible_sources:
            if source in business_info.get('source', '').lower():
                source_credibility = 0.8
                break
        score_factors.append(source_credibility)

        # Calculate final score
        if not score_factors:
            return 0.1

        final_score = sum(score_factors) / len(score_factors)
        return min(1.0, max(0.0, final_score))

    def _score_bounded_delivery_feasibility(self, business_context: Dict, campaign_context: Dict) -> float:
        """
        Score bounded delivery feasibility (0-1, worth 15 points).

        Evaluates: Can we realistically deliver a solution within bounds?
        Do we have the capability, resources, and constraints understood?
        """
        business_info = business_context.get('business_info', {})
        recent_evidence = business_context.get('recent_evidence', [])
        supported_services = campaign_context.get('supported_services', [])

        score_factors = []

        # Check for complexity indicators that might affect delivery
        complexity_indicators = [
            'complex', 'complicated', 'enterprise', 'large scale', 'multiple',
            'integrated', 'custom', 'legacy', 'outdated', 'years old'
        ]

        complexity_score = 0.5  # Start with neutral feasibility
        for evidence in recent_evidence:
            observation = evidence.get('observation', '').lower()
            limitation = evidence.get('limitation', '').lower()
            evidence_text = f"{observation} {limitation}"

            for indicator in complexity_indicators:
                if indicator in evidence_text:
                    complexity_score -= 0.1  # Reduce feasibility for complexity
                    break

        complexity_score = max(0.1, complexity_score)  # Don't go below 0.1
        score_factors.append(complexity_score)

        # Check for resource availability indicators
        resource_indicators = [
            'budget', 'funding', 'investment', 'resources', 'team', 'staff',
            'capacity', 'ability', 'means', 'option'
        ]

        resource_score = 0.3  # Baseline assumption
        for evidence in recent_evidence:
            observation = evidence.get('observation', '').lower()
            limitation = evidence.get('limitation', '').lower()
            evidence_text = f"{observation} {limitation}"

            for indicator in resource_indicators:
                if indicator in evidence_text:
                    resource_score += 0.15
                    break

        resource_score = min(0.8, resource_score)  # Cap at 0.8
        score_factors.append(resource_score)

        # Check for timeline constraints
        timeline_indicators = [
            'urgent', 'asap', 'quickly', 'immediate', 'soon', 'deadline',
            'timeline', 'schedule', 'by [date]', 'within [timeframe]'
        ]

        timeline_score = 0.6  # Assume reasonable timeline flexibility
        for evidence in recent_evidence:
            observation = evidence.get('observation', '').lower()
            limitation = evidence.get('limitation', '').lower()
            evidence_text = f"{observation} {limitation}"

            for indicator in timeline_indicators:
                if indicator in evidence_text:
                    timeline_score -= 0.1  # Urgent requests reduce feasibility slightly
                    break

        timeline_score = max(0.2, timeline_score)  # Don't go too low
        score_factors.append(timeline_score)

        # Check for technical feasibility based on our capabilities
        # This would be enhanced with specific service feasibility mapping
        technical_feasibility = 0.7  # Assume we can handle most website/business automation
        score_factors.append(technical_feasibility)

        # Calculate final score
        if not score_factors:
            return 0.1

        final_score = sum(score_factors) / len(score_factors)
        return min(1.0, max(0.0, final_score))

    def _score_evidence_quality_freshness(self, business_context: Dict, campaign_context: Dict) -> float:
        """
        Score evidence quality and freshness (0-1, worth 10 points).

        Evaluates: How good is our evidence? How recent is it?
        Is it from reliable sources? Has it been validated?
        """
        recent_evidence = business_context.get('recent_evidence', [])
        pipeline_history = business_context.get('pipeline_history', [])

        if not recent_evidence:
            return 0.1

        score_factors = []

        # Freshness scoring
        freshness_scores = []
        for evidence in recent_evidence:
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

        if freshness_scores:
            avg_freshness = sum(freshness_scores) / len(freshness_scores)
            score_factors.append(avg_freshness)

        # Evidence quality scoring
        quality_scores = []
        for evidence in recent_evidence:
            # Check for evidence metadata that indicates quality
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

        if quality_scores:
            avg_quality = sum(quality_scores) / len(quality_scores)
            score_factors.append(avg_quality)

        # Evidence quantity and diversity
        evidence_count = len(recent_evidence)
        if evidence_count >= 5:
            quantity_score = 0.8
        elif evidence_count >= 3:
            quantity_score = 0.6
        elif evidence_count >= 1:
            quantity_score = 0.4
        else:
            quantity_score = 0.1
        score_factors.append(quantity_score)

        # Pipeline history completeness
        if pipeline_history:
            # More pipeline history suggests better tracking
            history_score = min(0.7, len(pipeline_history) * 0.1)
            score_factors.append(history_score)
        else:
            score_factors.append(0.2)  # No history

        # Calculate final score
        if not score_factors:
            return 0.1

        final_score = sum(score_factors) / len(score_factors)
        return min(1.0, max(0.0, final_score))

    def _score_supported_reason_to_act_now(self, business_context: Dict, campaign_context: Dict) -> float:
        """
        Score supported reason to act now (0-1, worth 10 points).

        Evaluates: Is there a time-sensitive reason to engage now?
        Are there triggers that make this moment opportune?
        """
        business_info = business_context.get('business_info', {})
        recent_evidence = business_context.get('recent_evidence', [])

        score_factors = []

        # Check for temporal triggers and urgency indicators
        temporal_indicators = [
            'recently', 'just', 'lately', 'new', 'newly', 'recent',
            'updated', 'changed', 'modified', 'replaced', 'upgraded'
        ]

        temporal_score = 0.2  # Baseline low urgency
        for evidence in recent_evidence:
            observation = evidence.get('observation', '').lower()
            limitation = evidence.get('limitation', '').lower()
            evidence_text = f"{observation} {limitation}"

            for indicator in temporal_indicators:
                if indicator in evidence_text:
                    temporal_score += 0.15
                    break

        temporal_score = min(0.8, temporal_score)
        score_factors.append(temporal_score)

        # Check for business events or changes
        event_indicators = [
            'launch', 'opening', 'expansion', 'growth', 'new location',
            'new service', 'new product', 'rebranding', 'renovation',
            'move', 'relocation', 'acquisition', 'merger', 'partnership'
        ]

        event_score = 0.3  # Baseline for business events
        for evidence in recent_evidence:
            observation = evidence.get('observation', '').lower()
            limitation = evidence.get('limitation', '').lower()
            evidence_text = f"{observation} {limitation}"

            for indicator in event_indicators:
                if indicator in evidence_text:
                    event_score += 0.2
                    break

        event_score = min(0.8, event_score)
        score_factors.append(event_score)

        # Check for seasonal or cyclical triggers
        seasonal_indicators = [
            'season', 'quarterly', 'annual', 'yearly', 'monthly',
            'q1', 'q2', 'q3', 'q4', 'spring', 'summer', 'autumn', 'winter',
            'holiday', 'christmas', 'new year', 'financial year'
        ]

        seasonal_score = 0.25  # Baseline seasonal awareness
        for evidence in recent_evidence:
            observation = evidence.get('observation', '').lower()
            limitation = evidence.get('limitation', '').lower()
            evidence_text = f"{observation} {limitation}"

            for indicator in seasonal_indicators:
                if indicator in evidence_text:
                    seasonal_score += 0.15
                    break

        seasonal_score = min(0.7, seasonal_score)
        score_factors.append(seasonal_score)

        # Check for competitive or market triggers
        competitive_indicators = [
            'competitor', 'competition', 'market', 'industry trend',
            'new entrant', 'market share', 'competitive', 'vs ', 'versus'
        ]

        competitive_score = 0.3  # Baseline competitive awareness
        for evidence in recent_evidence:
            observation = evidence.get('observation', '').lower()
            limitation = evidence.get('limitation', '').lower()
            evidence_text = f"{observation} {limitation}"

            for indicator in competitive_indicators:
                if indicator in evidence_text:
                    competitive_score += 0.15
                    break

        competitive_score = min(0.8, competitive_score)
        score_factors.append(competitive_score)

        # Check for regulatory or compliance triggers
        compliance_indicators = [
            'compliance', 'regulation', 'standard', 'requirement',
            'must have', 'required by', 'obligation', 'legal',
            'gdpr', 'privacy', 'accessibility', 'wcag'
        ]

        compliance_score = 0.2  # Baseline compliance awareness
        for evidence in recent_evidence:
            observation = evidence.get('observation', '').lower()
            limitation = evidence.get('limitation', '').lower()
            evidence_text = f"{observation} {limitation}"

            for indicator in compliance_indicators:
                if indicator in evidence_text:
                    compliance_score += 0.2
                    break

        compliance_score = min(0.6, compliance_score)
        score_factors.append(compliance_score)

        # Calculate final score
        if not score_factors:
            return 0.1

        final_score = sum(score_factors) / len(score_factors)
        return min(1.0, max(0.0, final_score))


# Convenience functions for external use
def score_opportunity(business_id: int, campaign_id: str = "default") -> Dict:
    """Convenience function to score an opportunity."""
    scorer = OpportunityScorer()
    return scorer.score_opportunity(business_id, campaign_id)


def is_shortlist_opportunity(business_id: int, campaign_id: str = "default") -> bool:
    """Check if an opportunity meets shortlist criteria (score >= 65)."""
    result = score_opportunity(business_id, campaign_id)
    return result.get('is_shortlist', False)


if __name__ == "__main__":
    # Test the opportunity scorer
    print("Opportunity scoring module loaded")
    print("Testing with business ID 1...")

    # This would normally work with actual database connection
    # For now, just show the module is loadable
    scorer = OpportunityScorer()
    print(f"Scorer initialized: {scorer is not None}")
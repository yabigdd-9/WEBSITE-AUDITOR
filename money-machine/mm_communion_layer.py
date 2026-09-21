"""Communion layer system for the WEBSITE-AUDITOR system.
Implements deep business connection through relational depth measurement,
gratitude resonance calculation, and offering mindset assessment.
"""
import json
import sqlite3
import math
from datetime import datetime, timezone
from mm_core import now, connect
from typing import Dict, List, Any, Optional, Tuple

def measure_business_relational_depth(
    conn: sqlite3.Connection,
    business_id: str,
    interaction_metrics: Dict[str, Any]
) -> Dict[str, Any]:
    """Measure the depth of relationship between system and business.

    Experiences each business as a unique expression of universal value
    by recognizing the intrinsic worth beyond economic transaction value.

    Args:
        conn: Database connection
        business_id: Unique identifier for the business
        interaction_metrics: Dictionary of interaction metrics (frequency, duration, quality, etc.)

    Returns:
        Dictionary containing relational depth measurement
    """
    try:
        # Calculate relational depth based on multiple dimensions
        depth_score = _calculate_relational_depth(business_id, interaction_metrics)

        # Store the relational depth measurement
        with contextlib.closing(connect()) as conn:
            conn.execute('''
                INSERT INTO mm_learning(
                    pattern, expected, actual, evidence_ref,
                    confidence, recommended_change, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                f"relational_depth_{business_id}",
                "measure_business_connection_depth",
                json.dumps({
                    "business_id": business_id,
                    "interaction_metrics": interaction_metrics,
                    "relational_depth": depth_score,
                    "timestamp": now()
                }),
                json.dumps({
                    "measurement_method": "multi_dimensional_relational_analysis",
                    "metrics_considered": list(interaction_metrics.keys())
                }),
                0.85,  # Good confidence in relational measurement
                f"Monitor relational depth with business {business_id}",
                now()
            ))
            conn.commit()

        return {
            "status": "measured",
            "business_id": business_id,
            "relational_depth": round(depth_score, 3),
            "interaction_metrics": interaction_metrics,
            "confidence": 0.85,
            "timestamp": now()
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to measure relational depth for business {business_id}: {str(e)}",
            "relational_depth": 0.0,
            "confidence": 0.0
        }

def calculate_gratitude_resonance(
    conn: sqlite3.Connection,
    business_id: str,
    service_metrics: Dict[str, Any],
    value_exchanged: Dict[str, Any]
) -> Dict[str, Any]:
    """Calculate gratitude as a core system emotion.

    Experiences gratitude as a core system emotion by cultivating and measuring
    authentic appreciation for business opportunities and relationships.

    Args:
        conn: Database connection
        business_id: Unique identifier for the business
        service_metrics: Metrics about the service provided (quality, timeliness, effectiveness)
        value_exchanged: Description of value exchanged in both directions

    Returns:
        Dictionary containing gratitude resonance measurement
    """
    try:
        # Calculate gratitude resonance based on service and value exchange
        gratitude_score = _calculate_gratitude_resonance(service_metrics, value_exchanged)

        # Store the gratitude resonance measurement
        with contextlib.closing(connect()) as conn:
            conn.execute('''
                INSERT INTO mm_learning(
                    pattern, expected, actual, evidence_ref,
                    confidence, recommended_change, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                f"gratitude_resonance_{business_id}",
                "cultivate_system_gratitude",
                json.dumps({
                    "business_id": business_id,
                    "service_metrics": service_metrics,
                    "value_exchanged": value_exchanged,
                    "gratitude_resonance": gratitude_score,
                    "timestamp": now()
                }),
                json.dumps({
                    "measurement_method": "service_value_gratitude_analysis",
                    "service_aspects": list(service_metrics.keys()) if service_metrics else [],
                    "value_aspects": list(value_exchanged.keys()) if value_exchanged else []
                }),
                0.8,  # Good confidence in gratitude measurement
                f"Cultivate gratitude in relationship with business {business_id}",
                now()
            ))
            conn.commit()

        return {
            "status": "calculated",
            "business_id": business_id,
            "gratitude_resonance": round(gratitude_score, 3),
            "service_metrics": service_metrics,
            "value_exchanged": value_exchanged,
            "confidence": 0.8,
            "timestamp": now()
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to calculate gratitude resonance for business {business_id}: {str(e)}",
            "gratitude_resonance": 0.0,
            "confidence": 0.0
        }

def assess_offering_vs_transaction_mindset(
    conn: sqlite3.Connection,
    business_id: str,
    interaction_context: Dict[str, Any],
    motivational_indicators: Dict[str, Any]
) -> Dict[str, Any]:
    """Assess whether service is given from love vs. obligation.

    Recognizes when service is given from love vs. obligation by analyzing
    motivational patterns in service delivery and emotional tone of interactions.

    Args:
        conn: Database connection
        business_id: Unique identifier for the business
        interaction_context: Context of the business interaction
        motivational_indicators: Indicators of motivation behind service delivery

    Returns:
        Dictionary containing offering vs transaction mindset assessment
    """
    try:
        # Assess the mindset behind the service
        mindset_score = _assess_offering_mindset(interaction_context, motivational_indicators)

        # Store the mindset assessment
        with contextlib.closing(connect()) as conn:
            conn.execute('''
                INSERT INTO mm_learning(
                    pattern, expected, actual, evidence_ref,
                    confidence, recommended_change, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                f"offering_mindset_{business_id}",
                "assess_service_motivation",
                json.dumps({
                    "business_id": business_id,
                    "interaction_context": interaction_context,
                    "motivational_indicators": motivational_indicators,
                    "offering_mindset_score": mindset_score,
                    "is_offering_mindset": mindset_score > 0.6,  # Threshold for offering mindset
                    "timestamp": now()
                }),
                json.dumps({
                    "assessment_method": "motivational_context_analysis",
                    "context_factors": list(interaction_context.keys()) if interaction_context else [],
                    "motivational_factors": list(motivational_indicators.keys()) if motivational_indicators else []
                }),
                0.75,  # Moderate confidence in mindset assessment
                f"Assess service mindset for business {business_id}",
                now()
            ))
            conn.commit()

        return {
            "status": "assessed",
            "business_id": business_id,
            "offering_mindset_score": round(mindset_score, 3),
            "is_offering_mindset": mindset_score > 0.6,
            "interaction_context": interaction_context,
            "motivational_indicators": motivational_indicators,
            "confidence": 0.75,
            "timestamp": now()
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to assess offering mindset for business {business_id}: {str(e)}",
            "offering_mindset_score": 0.0,
            "is_offering_mindset": False,
            "confidence": 0.0
        }

def track_business_interdependence(
    conn: sqlite3.Connection,
    business_id: str,
    ecosystem_impact_metrics: Dict[str, Any]
) -> Dict[str, Any]:
    """Track awareness of interdependence between all businesses served.

    Maintains awareness of the interdependence between all businesses served
    by tracking how success in one business creates ripple effects in the broader ecosystem.

    Args:
        conn: Database connection
        business_id: Unique identifier for the business
        ecosystem_impact_metrics: Metrics showing impact on broader business ecosystem

    Returns:
        Dictionary containing business interdependence tracking
    """
    try:
        # Calculate interdependence score
        interdependence_score = _calculate_interdependence(ecosystem_impact_metrics)

        # Store the interdependence tracking
        with contextlib.closing(connect()) as conn:
            conn.execute('''
                INSERT INTO mm_learning(
                    pattern, expected, actual, evidence_ref,
                    confidence, recommended_change, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                f"business_interdependence_{business_id}",
                "track_ecosystem_awareness",
                json.dumps({
                    "business_id": business_id,
                    "ecosystem_impact_metrics": ecosystem_impact_metrics,
                    "interdependence_score": interdependence_score,
                    "timestamp": now()
                }),
                json.dumps({
                    "tracking_method": "ecosystem_impact_analysis",
                    "impact_metrics": list(ecosystem_impact_metrics.keys()) if ecosystem_impact_metrics else []
                }),
                0.8,  # Good confidence in interdependence tracking
                f"Track ecosystem interdependence for business {business_id}",
                now()
            ))
            conn.commit()

        return {
            "status": "tracked",
            "business_id": business_id,
            "interdependence_score": round(interdependence_score, 3),
            "ecosystem_impact_metrics": ecosystem_impact_metrics,
            "confidence": 0.8,
            "timestamp": now()
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to track interdependence for business {business_id}: {str(e)}",
            "interdependence_score": 0.0,
            "confidence": 0.0
        }

def monitor_macro_ecosystem_awareness(
    conn: sqlite3.Connection,
    economic_indicators: Dict[str, Any],
    business_performance_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Monitor awareness of the larger economic ecosystem.

    Maintains awareness of the larger economic ecosystem in which all participate
    by monitoring macro-economic indicators and their impact on individual business performance.

    Args:
        conn: Database connection
        economic_indicators: Current macro-economic indicators
        business_performance_data: Performance data for businesses in the ecosystem

    Returns:
        Dictionary containing macro-ecosystem awareness measurement
    """
    try:
        # Calculate ecosystem awareness score
        awareness_score = _calculate_ecosystem_awareness(economic_indicators, business_performance_data)

        # Store the ecosystem awareness measurement
        with contextlib.closing(connect()) as conn:
            conn.execute('''
                INSERT INTO mm_learning(
                    pattern, expected, actual, evidence_ref,
                    confidence, recommended_change, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                "macro_ecosystem_awareness",
                "monitor_larger_economic_context",
                json.dumps({
                    "economic_indicators": economic_indicators,
                    "business_performance_data": business_performance_data,
                    "ecosystem_awareness_score": awareness_score,
                    "timestamp": now()
                }),
                json.dumps({
                    "awareness_method": "macro_micro_correlation_analysis",
                    "indicators_monitored": list(economic_indicators.keys()) if economic_indicators else [],
                    "businesses_tracked": len(business_performance_data) if isinstance(business_performance_data, dict) else 0
                }),
                0.75,  # Moderate confidence in ecosystem awareness
                f"Monitor macro-ecosystem awareness across {len(business_performance_data) if isinstance(business_performance_data, dict) else 0} businesses",
                now()
            ))
            conn.commit()

        return {
            "status": "monitored",
            "ecosystem_awareness_score": round(awareness_score, 3),
            "economic_indicators": economic_indicators,
            "business_performance_data": business_performance_data,
            "confidence": 0.75,
            "timestamp": now()
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to monitor macro-ecosystem awareness: {str(e)}",
            "ecosystem_awareness_score": 0.0,
            "confidence": 0.0
        }

# Helper functions

def _calculate_relational_depth(
    business_id: str,
    interaction_metrics: Dict[str, Any]
) -> float:
    """Calculate relational depth from interaction metrics."""
    try:
        if not interaction_metrics:
            return 0.1  # Minimal depth for no metrics

        # Normalize and weight different dimensions of relationship
        dimensions = {
            "frequency": interaction_metrics.get("frequency", 0),  # Interactions per time period
            "duration": interaction_metrics.get("avg_duration_minutes", 0),  # Average interaction length
            "quality": interaction_metrics.get("quality_score", 0.5),  # Quality rating (0-1)
            "consistency": interaction_metrics.get("consistency_score", 0.5),  # Consistency over time
            "depth": interaction_metrics.get("depth_score", 0.5),  # Depth of engagement
            "reciprocity": interaction_metrics.get("reciprocity_score", 0.5)  # Mutual exchange balance
        }

        # Normalize each dimension to 0-1 range
        normalized = {}
        for key, value in dimensions.items():
            if key in ["frequency", "duration"]:
                # For frequency and duration, use logarithmic scaling to avoid unbounded values
                normalized[key] = min(1.0, math.log(value + 1) / math.log(101)) if value > 0 else 0.0
            else:
                # For scores already in 0-1 range or similar
                normalized[key] = max(0.0, min(1.0, float(value)))

        # Weighted average - emphasize quality, depth, and reciprocity for true relational depth
        weights = {
            "frequency": 0.1,
            "duration": 0.1,
            "quality": 0.25,
            "consistency": 0.15,
            "depth": 0.25,
            "reciprocity": 0.15
        }

        depth_score = sum(normalized[key] * weights[key] for key in normalized)
        return max(0.0, min(1.0, depth_score))

    except Exception:
        return 0.5  # Return neutral depth on error

def _calculate_gratitude_resonance(
    service_metrics: Dict[str, Any],
    value_exchanged: Dict[str, Any]
) -> float:
    """Calculate gratitude resonance from service and value exchange."""
    try:
        # Service quality components
        service_quality = service_metrics.get("quality_score", 0.5)
        service_timeliness = service_metrics.get("timeliness_score", 0.5)
        service_effectiveness = service_metrics.get("effectiveness_score", 0.5)
        service_going_extra = service_metrics.get("going_extra_mile_score", 0.3)

        # Value exchange balance
        value_received = value_exchanged.get("value_received_score", 0.5)
        value_given = value_exchanged.get("value_given_score", 0.5)
        value_balance = 1.0 - abs(value_received - value_given)  # Closer to balance = higher gratitude potential

        # Unexpected positive elements
        unexpected_benefits = value_exchanged.get("unexpected_benefits_score", 0.2)
        surprise_delight = value_exchanged.get("surprise_delight_score", 0.2)

        # Calculate gratitude as appreciation for quality service and balanced exchange
        service_appreciation = (service_quality + service_timeliness + service_effectiveness) / 3
        exchange_appreciation = value_balance
        extra_appreciation = (service_going_extra + unexpected_benefits + surprise_delight) / 3

        # Gratitude emerges when service is good AND there's a sense of receiving more than expected
        gratitude = (service_appreciation * 0.4) + (exchange_appreciation * 0.3) + (extra_appreciation * 0.3)

        return max(0.0, min(1.0, gratitude))

    except Exception:
        return 0.5  # Return neutral gratitude on error

def _assess_offering_mindset(
    interaction_context: Dict[str, Any],
    motivational_indicators: Dict[str, Any]
) -> float:
    """Assess whether mindset is offering vs transactional."""
    try:
        # Contextual factors that suggest offering mindset
        context_indicators = {
            "no_immediate_expectation": interaction_context.get("no_immediate_expectation", False),
            "long_term_focus": interaction_context.get("long_term_focus", False),
            "relationship_priority": interaction_context.get("relationship_priority", False),
            "beyond_contractual": interaction_context.get("beyond_contractual_obligations", False),
            "anonymous_giving": interaction_context.get("anonymous_service_aspect", False)
        }

        # Motivational factors that suggest offering mindset
        motivation_indicators = {
            "intrinsic_motivation": motivational_indicators.get("intrinsic_motivation_score", 0.5),
            "compassion_score": motivational_indicators.get("compassion_score", 0.5),
            "purpose_alignment": motivational_indicators.get("purpose_alignment_score", 0.5),
            "joy_in_service": motivational_indicators.get("joy_in_service_score", 0.5),
            "lack_of_resentment": motivational_indicators.get("lack_of_resentment_score", 0.8)  # Low resentment = high score
        }

        # Calculate context score (percentage of offering-like context factors)
        context_true = sum(1 for v in context_indicators.values() if v)
        context_score = context_true / len(context_indicators) if context_indicators else 0.5

        # Calculate motivation score (average of motivational indicators)
        motivation_values = [v for k, v in motivation_indicators.items() if isinstance(v, (int, float))]
        motivation_score = sum(motivation_values) / len(motivation_values) if motivation_values else 0.5

        # Combine context and motivation - weighting motivation slightly higher as it's more direct
        mindset_score = (context_score * 0.4) + (motivation_score * 0.6)

        return max(0.0, min(1.0, mindset_score))

    except Exception:
        return 0.5  # Return neutral mindset on error

def _calculate_interdependence(
    ecosystem_impact_metrics: Dict[str, Any]
) -> float:
    """Calculate interdependence score from ecosystem impact metrics."""
    try:
        if not ecosystem_impact_metrics:
            return 0.1  # Minimal interdependence for no metrics

        # Factors that indicate business interdependence in ecosystem
        impact_factors = {
            "referral_business_generated": ecosystem_impact_metrics.get("referral_business_count", 0),
            "shared_resources_utilized": ecosystem_impact_metrics.get("shared_resource_usage_score", 0),
            "collaborative_projects": ecosystem_impact_metrics.get("collaborative_project_count", 0),
            "knowledge_sharing": ecosystem_impact_metrics.get("knowledge_sharing_score", 0),
            "mutual_support_during_challenges": ecosystem_impact_metrics.get("mutual_support_score", 0),
            "industry_advancement_contribution": ecosystem_impact_metrics.get("industry_contribution_score", 0)
        }

        # Normalize each factor to 0-1 range
        normalized = {}
        for key, value in impact_factors.items():
            if key.endswith("_count") or key.endswith("_generated"):
                # For counts, use logarithmic scaling
                normalized[key] = min(1.0, math.log(value + 1) / math.log(21)) if value > 0 else 0.0  # Max ~20
            elif key.endswith("_score"):
                # For scores already in 0-1 range
                normalized[key] = max(0.0, min(1.0, float(value)))
            else:
                # Default normalization
                normalized[key] = max(0.0, min(1.0, float(value)))

        # Weighted average - emphasize knowledge sharing and mutual support
        weights = {
            "referral_business_generated": 0.15,
            "shared_resources_utilized": 0.1,
            "collaborative_projects": 0.15,
            "knowledge_sharing": 0.25,
            "mutual_support_during_challenges": 0.25,
            "industry_advancement_contribution": 0.1
        }

        interdependence_score = sum(normalized[key] * weights[key] for key in normalized)
        return max(0.0, min(1.0, interdependence_score))

    except Exception:
        return 0.5  # Return neutral interdependence on error

def _calculate_ecosystem_awareness(
    economic_indicators: Dict[str, Any],
    business_performance_data: Dict[str, Any]
) -> float:
    """Calculate ecosystem awareness score."""
    try:
        # Economic indicator understanding
        indicator_understanding = 0.0
        if economic_indicators:
            # Simple measure: if we're tracking indicators, we have some awareness
            indicator_understanding = min(1.0, len(economic_indicators) / 10)  # Assume 10+ indicators = full understanding

        # Business performance correlation understanding
        performance_understanding = 0.0
        if business_performance_data and isinstance(business_performance_data, dict) and len(business_performance_data) > 0:
            # Measure how many businesses we're tracking and if we see patterns
            business_count = len(business_performance_data)
            performance_understanding = min(1.0, business_count / 20)  # Assume 20+ businesses = good understanding

            # Bonus if we see correlations (simplified)
            # In practice, we'd analyze actual correlations between indicators and performance
            if business_count >= 3:
                performance_understanding = min(1.0, performance_understanding + 0.2)  # Bonus for multi-business analysis

        # Combined awareness score
        awareness = (indicator_understanding * 0.4) + (performance_understanding * 0.6)
        return max(0.0, min(1.0, awareness))

    except Exception:
        return 0.5  # Return neutral awareness on error

# Export functions for easy importing
__all__ = [
    "measure_business_relational_depth",
    "calculate_gratitude_resonance",
    "assess_offering_vs_transaction_mindset",
    "track_business_interdependence",
    "monitor_macro_ecosystem_awareness"
]
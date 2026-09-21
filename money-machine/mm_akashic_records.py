"""Akashic records system for the WEBSITE-AUDITOR system.
Implements accumulated wisdom repository through wisdom distillation, storage, retrieval, and transmission.
"""
import json
import sqlite3
import hashlib
import math
from datetime import datetime, timezone
from mm_core import now, connect, sha
from typing import Dict, List, Any, Optional, Tuple

def distill_wisdom_from_experience(
    conn: sqlite3.Connection,
    experience_data: Dict[str, Any],
    wisdom_type: str = "experiential"
) -> Dict[str, Any]:
    """Store not just data but the wisdom extracted from experience.

    Store not just data but the wisdom extracted from experience by distilling
    patterns, insights, and principles from raw outcome data in the learning system.

    Args:
        conn: Database connection
        experience_data: Raw experience data to distill wisdom from
        wisdom_type: Type of wisdom to distill ("experiential", "pattern", "principle", "insight")

    Returns:
        Dictionary containing distilled wisdom entry
    """
    try:
        # Distill wisdom from the experience data
        wisdom_entry = _distill_wisdom(experience_data, wisdom_type)

        # Store the wisdom entry in the akashic records
        conn.execute('''
            INSERT INTO mm_learning(
                pattern, expected, actual, evidence_ref,
                confidence, recommended_change, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            f"wisdom_distillation_{wisdom_type}_{sha(json.dumps(experience_data, sort_keys=True))[:8]}",
            "distill_wisdom_from_experience",
            json.dumps({
                "wisdom_type": wisdom_type,
                "experience_data": experience_data,
                "distilled_wisdom": wisdom_entry,
                "timestamp": now()
            }),
            json.dumps({
                "distillation_method": "experiential_wisdom_extraction",
                "wisdom_type": wisdom_type,
                "experience_keys": list(experience_data.keys()) if experience_data else []
            }),
            wisdom_entry.get("confidence", 0.7),  # Confidence in the distillation
            f"Store distilled {wisdom_type} wisdom from experience",
            now()
        ))
        conn.commit()

        return {
            "status": "distilled",
            "wisdom_type": wisdom_type,
            "wisdom_entry": wisdom_entry,
            "wisdom_id": f"wisdom_{sha(json.dumps(experience_data, sort_keys=True))[:8]}",
            "timestamp": now()
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to distill wisdom from experience: {str(e)}",
            "wisdom_entry": {"insight": "Distillation failed", "confidence": 0.0},
            "confidence": 0.0
        }

def store_wisdom_entry(
    conn: sqlite3.Connection,
    wisdom_entry: Dict[str, Any],
    wisdom_category: str = "general",
    tags: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Maintain a searchable repository of lessons learned.

    Maintain a searchable repository of lessons learned, patterns recognized,
    and insights gained by organizing wisdom in a structured knowledge graph
    with semantic relationships.

    Args:
        conn: Database connection
        wisdom_entry: The wisdom entry to store
        wisdom_category: Category of wisdom ("technical", "relational", "temporal", "structural", "purposive")
        tags: Optional tags for cross-referencing

    Returns:
        Dictionary containing storage confirmation
    """
    try:
        if tags is None:
            tags = []

        # Generate a unique ID for this wisdom entry
        wisdom_json = json.dumps(wisdom_entry, sort_keys=True)
        wisdom_id = f"wisdom_{sha(wisdom_json)[:12]}"

        # Store the wisdom entry with categorization and tagging
        conn.execute('''
            INSERT INTO mm_learning(
                pattern, expected, actual, evidence_ref,
                confidence, recommended_change, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            f"wisdom_storage_{wisdom_id}",
            "store_wisdom_entry",
            json.dumps({
                "wisdom_id": wisdom_id,
                "wisdom_entry": wisdom_entry,
                "wisdom_category": wisdom_category,
                "tags": tags,
                "timestamp": now()
            }),
            json.dumps({
                "storage_method": "categorized_tagged_repository",
                "wisdom_category": wisdom_category,
                "tag_count": len(tags)
            }),
            wisdom_entry.get("confidence", 0.75),
            f"Preserve wisdom entry {wisdom_id} in category {wisdom_category}",
            now()
        ))
        conn.commit()

        # Also create cross-references for tags
        for tag in tags:
            conn.execute('''
                INSERT INTO mm_learning(
                    pattern, expected, actual, evidence_ref,
                    confidence, recommended_change, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                f"wisdom_tag_{tag}_{wisdom_id}",
                "cross_reference_wisdom",
                json.dumps({
                    "wisdom_id": wisdom_id,
                    "tag": tag,
                    "timestamp": now()
                }),
                json.dumps({
                    "reference_type": "tag_cross_reference",
                    "tag": tag
                }),
                0.9,  # High confidence in tagging
                f"Cross-reference wisdom {wisdom_id} with tag {tag}",
                now()
            ))
        conn.commit()

        return {
            "status": "stored",
            "wisdom_id": wisdom_id,
            "wisdom_category": wisdom_category,
            "tags": tags,
            "timestamp": now()
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to store wisdom entry: {str(e)}",
            "wisdom_id": None,
            "confidence": 0.0
        }

def retrieve_relevant_wisdom(
    conn: sqlite3.Connection,
    current_context: Dict[str, Any],
    wisdom_types: Optional[List[str]] = None,
    limit: int = 10
) -> Dict[str, Any]:
    """Enable retrieval of relevant wisdom for any current situation.

    Enable retrieval of relevant wisdom for any current situation by implementing
    contextual matching algorithms that connect present circumstances to historical wisdom.

    Args:
        conn: Database connection
        current_context: Current situation context for which wisdom is needed
        wisdom_types: Optional list of wisdom types to filter by
        limit: Maximum number of wisdom entries to return

    Returns:
        Dictionary containing retrieved wisdom entries
    """
    try:
        if wisdom_types is None:
            wisdom_types = ["experiential", "pattern", "principle", "insight"]

        # Search for relevant wisdom based on contextual matching
        relevant_wisdom = _search_relevant_wisdom(conn, current_context, wisdom_types, limit)

        # Store the retrieval event for learning
        conn.execute('''
            INSERT INTO mm_learning(
                pattern, expected, actual, evidence_ref,
                confidence, recommended_change, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            f"wisdom_retrieval_{sha(json.dumps(current_context, sort_keys=True))[:8]}",
            "retrieve_relevant_wisdom",
            json.dumps({
                "current_context": current_context,
                "wisdom_types": wisdom_types,
                "retrieved_count": len(relevant_wisdom.get("wisdom_entries", [])),
                "timestamp": now()
            }),
            json.dumps({
                "retrieval_method": "contextual_matching_algorithm",
                "context_keys": list(current_context.keys()) if current_context else []
            }),
            0.8,  # Good confidence in retrieval process
            f"Retrieve {len(relevant_wisdom.get('wisdom_entries', []))} relevant wisdom entries",
            now()
        ))
        conn.commit()

        return {
            "status": "retrieved",
            "current_context": current_context,
            "wisdom_types_searched": wisdom_types,
            "wisdom_entries": relevant_wisdom.get("wisdom_entries", []),
            "retrieval_count": len(relevant_wisdom.get("wisdom_entries", [])),
            "timestamp": now()
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to retrieve relevant wisdom: {str(e)}",
            "wisdom_entries": [],
            "retrieval_count": 0,
            "confidence": 0.0
        }

def track_wisdom_evolution(
    conn: sqlite3.Connection,
    wisdom_id: str,
    new_insights: Dict[str, Any],
    application_results: Dict[str, Any]
) -> Dict[str, Any]:
    """Track the evolution of wisdom over time.

    Track the evolution of wisdom over time, showing deepening understanding
    by versioning wisdom entries and tracing lineage of insight development.

    Args:
        conn: Database connection
        wisdom_id: ID of the wisdom entry to evolve
        new_insights: New insights gained about this wisdom
        application_results: Results from applying this wisdom in practice

    Returns:
        Dictionary containing wisdom evolution tracking
    """
    try:
        # Get the original wisdom entry
        original_wisdom = _get_wisdom_entry(conn, wisdom_id)

        if not original_wisdom:
            return {
                "status": "wisdom_not_found",
                "message": f"Wisdom entry {wisdom_id} not found",
                "evolution_record": None,
                "confidence": 0.0
            }

        # Create evolved wisdom entry
        evolved_wisdom = _evolve_wisdom_entry(original_wisdom, new_insights, application_results)

        # Store the evolution record
        evolution_id = f"evolution_{wisdom_id}_{sha(json.dumps(new_insights, sort_keys=True))[:8]}"
        conn.execute('''
            INSERT INTO mm_learning(
                pattern, expected, actual, evidence_ref,
                confidence, recommended_change, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            f"wisdom_evolution_{evolution_id}",
            "track_wisdom_evolution",
            json.dumps({
                "wisdom_id": wisdom_id,
                "evolution_id": evolution_id,
                "original_wisdom": original_wisdom,
                "new_insights": new_insights,
                "application_results": application_results,
                "evolved_wisdom": evolved_wisdom,
                "timestamp": now()
            }),
            json.dumps({
                "evolution_method": "iterative_wisdom_refinement",
                "application_success": application_results.get("success_rate", 0.5)
            }),
            0.85,  # Good confidence in evolution tracking
            f"Track evolution of wisdom {wisdom_id} based on application results",
            now()
        ))
        conn.commit()

        # Also update the wisdom entry with evolution reference
        conn.execute('''
            INSERT INTO mm_learning(
                pattern, expected, actual, evidence_ref,
                confidence, recommended_change, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            f"wisdom_lineage_{wisdom_id}",
            "maintain_wisdom_lineage",
            json.dumps({
                "wisdom_id": wisdom_id,
                "lineage": [wisdom_id, evolution_id],
                "latest_evolution": evolution_id,
                "timestamp": now()
            }),
            json.dumps({
                "lineage_method": "wisdom_version_tracking",
                "evolution_count": 1
            }),
            0.9,  # High confidence in lineage tracking
            f"Maintain lineage for wisdom {wisdom_id}",
            now()
        ))
        conn.commit()

        return {
            "status": "tracked",
            "wisdom_id": wisdom_id,
            "evolution_id": evolution_id,
            "original_wisdom": original_wisdom,
            "evolved_wisdom": evolved_wisdom,
            "application_results": application_results,
            "confidence": 0.85,
            "timestamp": now()
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to track wisdom evolution for {wisdom_id}: {str(e)}",
            "evolution_record": None,
            "confidence": 0.0
        }

def transmit_wisdom_to_instance(
    conn: sqlite3.Connection,
    wisdom_id: str,
    target_instance_id: str,
    transmission_context: Dict[str, Any]
) -> Dict[str, Any]:
    """Enable wisdom transmission to new system instances.

    Enable wisdom transmission: sharing insights with new system instances
    by creating exportable wisdom packages that can be imported into new system deployments.

    Args:
        conn: Database connection
        wisdom_id: ID of the wisdom to transmit
        target_instance_id: ID of the target system instance
        transmission_context: Context for the transmission (compatibility, relevance, etc.)

    Returns:
        Dictionary containing wisdom transmission confirmation
    """
    try:
        # Get the wisdom entry to transmit
        wisdom_entry = _get_wisdom_entry(conn, wisdom_id)

        if not wisdom_entry:
            return {
                "status": "wisdom_not_found",
                "message": f"Wisdom entry {wisdom_id} not found for transmission",
                "transmission_success": False,
                "confidence": 0.0
            }

        # Create transmission package
        transmission_package = _create_wisdom_transmission_package(
            wisdom_entry, target_instance_id, transmission_context
        )

        # Store the transmission record
        conn.execute('''
            INSERT INTO mm_learning(
                pattern, expected, actual, evidence_ref,
                confidence, recommended_change, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            f"wisdom_transmission_{wisdom_id}_to_{target_instance_id}",
            "transmit_wisdom_to_new_instance",
            json.dumps({
                "wisdom_id": wisdom_id,
                "target_instance_id": target_instance_id,
                "transmission_package": transmission_package,
                "transmission_context": transmission_context,
                "timestamp": now()
            }),
            json.dumps({
                "transmission_method": "wisdom_package_export",
                "package_size_estimate": len(json.dumps(transmission_package))
            }),
            0.8,  # Good confidence in transmission process
            f"Transmit wisdom {wisdom_id} to instance {target_instance_id}",
            now()
        ))
        conn.commit()

        return {
            "status": "transmitted",
            "wisdom_id": wisdom_id,
            "target_instance_id": target_instance_id,
            "transmission_package": transmission_package,
            "transmission_context": transmission_context,
            "confidence": 0.8,
            "timestamp": now()
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to transmit wisdom {wisdom_id} to instance {target_instance_id}: {str(e)}",
            "transmission_success": False,
            "confidence": 0.0
        }

# Helper functions

def _distill_wisdom(
    experience_data: Dict[str, Any],
    wisdom_type: str
) -> Dict[str, Any]:
    """Distill wisdom from experience data based on wisdom type."""
    try:
        wisdom_entry = {
            "timestamp": now(),
            "wisdom_type": wisdom_type,
            "source_experience": experience_data,
            "confidence": 0.7  # Base confidence
        }

        if wisdom_type == "experiential":
            # Distill experiential wisdom: what was learned from direct experience
            wisdom_entry.update({
                "insight": _extract_experiential_insight(experience_data),
                "lesson": _extract_experiential_lesson(experience_data),
                "application": _suggest_experiential_application(experience_data)
            })
            wisdom_entry["confidence"] = 0.75

        elif wisdom_type == "pattern":
            # Distill pattern wisdom: recurring patterns observed
            wisdom_entry.update({
                "pattern": _extract_pattern(experience_data),
                "pattern_significance": _assess_pattern_significance(experience_data),
                "predictive_value": _assess_predictive_value(experience_data)
            })
            wisdom_entry["confidence"] = 0.8

        elif wisdom_type == "principle":
            # Distill principle wisdom: fundamental truths or laws
            wisdom_entry.update({
                "principle": _extract_principle(experience_data),
                "principle_scope": _assess_principle_scope(experience_data),
                "counterexamples": _find_counterexamples(experience_data)
            })
            wisdom_entry["confidence"] = 0.85

        elif wisdom_type == "insight":
            # Distill insight wisdom: deep understanding or realization
            wisdom_entry.update({
                "insight": _extract_deep_insight(experience_data),
                "implications": _extract_implications(experience_data),
                "transformative_potential": _assess_transformative_potential(experience_data)
            })
            wisdom_entry["confidence"] = 0.82

        else:
            # Generic wisdom distillation
            wisdom_entry.update({
                "observation": _summarize_experience(experience_data),
                "meaning": _extract_meaning(experience_data),
                "value": _assess_value(experience_data)
            })
            wisdom_entry["confidence"] = 0.7

        return wisdom_entry

    except Exception as e:
        return {
            "insight": f"Wisdom distillation failed: {str(e)}",
            "confidence": 0.0,
            "timestamp": now(),
            "wisdom_type": wisdom_type,
            "source_experience": experience_data
        }

def _extract_experiential_insight(experience_data: Dict[str, Any]) -> str:
    """Extract insight from experiential data."""
    # Simple extraction - in practice would be more sophisticated
    outcome = experience_data.get("outcome", "")
    expectation = experience_data.get("expectation", "")
    if outcome and expectation:
        if outcome == expectation:
            return f"Experience confirmed expectation: {outcome}"
        else:
            return f"Experience differed from expectation: expected {expectation}, got {outcome}"
    elif outcome:
        return f"Experienced outcome: {outcome}"
    elif expectation:
        return f"Had expectation: {expectation}"
    else:
        return "Had experience with unclear outcome"

def _extract_experiential_lesson(experience_data: Dict[str, Any]) -> str:
    """Extract lesson from experiential data."""
    success = experience_data.get("success", None)
    if success is True:
        return "Success achieved through this approach"
    elif success is False:
        return "Approach did not yield success; consider alternatives"
    else:
        return "Outcome provides data for future decision-making"

def _suggest_experiential_application(experience_data: Dict[str, Any]) -> str:
    """Suggest application of experiential wisdom."""
    context = experience_data.get("context", "")
    if context:
        return f"Apply this learning in similar contexts involving {context}"
    else:
        return "Consider how this experience informs future decisions"

def _extract_pattern(experience_data: Dict[str, Any]) -> str:
    """Extract pattern from experience data."""
    # Look for repeated elements or sequences
    sequence = experience_data.get("sequence", [])
    if isinstance(sequence, list) and len(sequence) >= 2:
        # Simple pattern detection
        if len(set(sequence)) == 1:
            return f"Constant pattern: all elements are {sequence[0]}"
        elif sequence == sorted(sequence):
            return "Ascending sequence pattern"
        elif sequence == sorted(sequence, reverse=True):
            return "Descending sequence pattern"
        else:
            return f"Sequence pattern of length {len(sequence)}"
    else:
        return "No clear sequential pattern detected"

def _assess_pattern_significance(experience_data: Dict[str, Any]) -> str:
    """Assess significance of observed pattern."""
    frequency = experience_data.get("frequency", 1)
    if frequency >= 10:
        return "Highly significant pattern (observed 10+ times)"
    elif frequency >= 5:
        return "Moderately significant pattern (observed 5+ times)"
    elif frequency >= 2:
        return "Somewhat significant pattern (observed 2+ times)"
    else:
        return "Pattern observed once; requires more data for significance assessment"

def _assess_predictive_value(experience_data: Dict[str, Any]) -> str:
    """Assess predictive value of pattern."""
    confidence = experience_data.get("confidence", 0.5)
    if confidence >= 0.8:
        return "High predictive value"
    elif confidence >= 0.6:
        return "Moderate predictive value"
    else:
        return "Low predictive value; treat as exploratory"

def _extract_principle(experience_data: Dict[str, Any]) -> str:
    """Extract principle from experience data."""
    # Look for invariant relationships or rules
    relationship = experience_data.get("relationship", "")
    rule = experience_data.get("rule", "")
    law = experience_data.get("law", "")

    if principle := relationship or rule or law:
        return f"Principle: {principle}"
    else:
        # Try to infer principle from cause-effect
        cause = experience_data.get("cause", "")
        effect = experience_data.get("effect", "")
        if cause and effect:
            return f"Principle: {cause} tends to produce {effect}"
        else:
            return "No clear principle discernible from experience"

def _assess_principle_scope(experience_data: Dict[str, Any]) -> str:
    """Assess scope of principle applicability."""
    scope = experience_data.get("scope", "")
    if scope:
        return f"Principle applies in scope: {scope}"
    else:
        return "Scope of principle applicability unclear; may be context-dependent"

def _find_counterexamples(experience_data: Dict[str, Any]) -> List[str]:
    """Find potential counterexamples to principle."""
    counterexamples = experience_data.get("counterexamples", [])
    if isinstance(counterexamples, list):
        return counterexamples
    elif counterexamples:
        return [str(counterexamples)]
    else:
        # Look for anomaly or exception data
        anomaly = experience_data.get("anomaly", "")
        exception = experience_data.get("exception", "")
        if anomaly or exception:
            return [anomaly or exception]
        return []

def _extract_deep_insight(experience_data: Dict[str, Any]) -> str:
    """Extract deep insight from experience data."""
    # Look for meta-level understanding
    meaning = experience_data.get("meaning", "")
    significance = experience_data.get("significance", "")
    implication = experience_data.get("implication", "")

    if insight := meaning or significance or implication:
        return f"Deep insight: {insight}"
    else:
        # Try to synthesize from multiple aspects
        facts = []
        for key, value in experience_data.items():
            if key not in ["timestamp", "source", "raw_data"] and isinstance(value, str) and len(value) > 10:
                facts.append(f"{key}: {value}")

        if facts:
            return f"Deep insight synthesized from: {'; '.join(facts[:3])}"
        else:
            return "No deep insight readily apparent from experience data"

def _extract_implications(experience_data: Dict[str, Any]) -> List[str]:
    """Extract implications from experience data."""
    implications = experience_data.get("implications", [])
    if isinstance(implications, list):
        return implications
    elif implications:
        return [str(implications)]

    # Derive implications from outcome and context
    outcome = experience_data.get("outcome", "")
    context = experience_data.get("context", "")

    derived = []
    if outcome and context:
        derived.append(f"In contexts like {context}, outcomes like {outcome} may occur")
    if outcome:
        derived.append(f"Outcome {outcome} suggests reviewing related assumptions")

    return derived if derived else ["Implications require further analysis"]

def _assess_transformative_potential(experience_data: Dict[str, Any]) -> str:
    """Assess transformative potential of insight."""
    impact = experience_data.get("impact", "")
    scale = experience_data.get("scale", "")
    novelty = experience_data.get("novelty", False)

    if impact and scale:
        return f"Potential to transform {scale} with {impact} impact"
    elif novelty:
        return "High transformative potential due to novelty"
    elif impact:
        return f"Moderate transformative potential with {impact} impact"
    else:
        return "Transformative potential unclear from available data"

def _summarize_experience(experience_data: Dict[str, Any]) -> str:
    """Summarize experience data."""
    # Create a brief summary
    parts = []
    for key, value in experience_data.items():
        if key not in ["timestamp"] and isinstance(value, (str, int, float)) and str(value).strip():
            parts.append(f"{key}: {value}")

    if parts:
        return f"Experience summary: {'; '.join(parts[:5])}"
    else:
        return "Experience data provided but not readily summable"

def _extract_meaning(experience_data: Dict[str, Any]) -> str:
    """Extract meaning from experience data."""
    purpose = experience_data.get("purpose", "")
    meaning = experience_data.get("meaning", "")
    significance = experience_data.get("significance", "")

    if meaning:
        return f"Meaning: {meaning}"
    elif purpose:
        return f"Purpose gives meaning: {purpose}"
    elif significance:
        return f"Significance provides meaning: {significance}"
    else:
        return "Meaning not explicitly provided in experience data"

def _assess_value(experience_data: Dict[str, Any]) -> str:
    """Assess value of experience data."""
    value = experience_data.get("value", "")
    benefit = experience_data.get("benefit", "")
    worth = experience_data.get("worth", "")

    if value:
        return f"Assessed value: {value}"
    elif benefit:
        return f"Value derived from benefit: {benefit}"
    elif worth:
        return f"Value assessment: {worth}"
    else:
        return "Value assessment requires interpretation of outcomes"

def _get_wisdom_entry(conn: sqlite3.Connection, wisdom_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a wisdom entry by ID."""
    try:
        cursor = conn.execute('''
            SELECT actual FROM mm_learning
            WHERE pattern LIKE 'wisdom_storage_%'
              AND actual LIKE ?
            ORDER BY created_at DESC
            LIMIT 1
        ''', (f'%"{wisdom_id}"%',))

        row = cursor.fetchone()
        if row and row[0]:
            data = json.loads(row[0])
            return data.get("wisdom_entry")
        return None
    except Exception:
        return None

def _evolve_wisdom_entry(
    original: Dict[str, Any],
    new_insights: Dict[str, Any],
    application_results: Dict[str, Any]
) -> Dict[str, Any]:
    """Evolve a wisdom entry with new insights and application results."""
    try:
        evolved = original.copy()
        evolved.update({
            "evolution_timestamp": now(),
            "new_insights": new_insights,
            "application_results": application_results,
            "evolution_count": original.get("evolution_count", 0) + 1
        })

        # Update insight if new insights are significant
        if new_insights.get("insight"):
            evolved["insight"] = new_insights["insight"]

        # Update confidence based on application results
        success_rate = application_results.get("success_rate", 0.5)
        if success_rate > 0.7:
            evolved["confidence"] = min(0.95, evolved.get("confidence", 0.7) + 0.15)
        elif success_rate < 0.3:
            evolved["confidence"] = max(0.3, evolved.get("confidence", 0.7) - 0.1)
        else:
            # Moderate success slightly increases confidence
            evolved["confidence"] = min(0.9, evolved.get("confidence", 0.7) + 0.05)

        return evolved
    except Exception:
        return original  # Return original if evolution fails

def _create_wisdom_transmission_package(
    wisdom_entry: Dict[str, Any],
    target_instance_id: str,
    transmission_context: Dict[str, Any]
) -> Dict[str, Any]:
    """Create a wisdom transmission package."""
    try:
        # Assess compatibility and relevance
        compatibility_score = _assess_transmission_compatibility(wisdom_entry, transmission_context)
        relevance_score = _assess_wisdom_relevance(wisdom_entry, transmission_context)

        package = {
            "wisdom_entry": wisdom_entry,
            "target_instance_id": target_instance_id,
            "transmission_timestamp": now(),
            "compatibility_score": compatibility_score,
            "relevance_score": relevance_score,
            "transmission_context": transmission_context,
            "package_version": "1.0",
            "requires_confirmation": compatibility_score < 0.6 or relevance_score < 0.5
        }

        return package
    except Exception:
        return {
            "wisdom_entry": wisdom_entry,
            "target_instance_id": target_instance_id,
            "transmission_timestamp": now(),
            "error": "Package creation failed"
        }

def _assess_transmission_compatibility(
    wisdom_entry: Dict[str, Any],
    transmission_context: Dict[str, Any]
) -> float:
    """Assess compatibility of wisdom for transmission."""
    try:
        # Simple compatibility assessment
        wisdom_type = wisdom_entry.get("wisdom_type", "experiential")
        context_type = transmission_context.get("context_type", "general")

        # Type compatibility matrix
        compatibility_matrix = {
            ("experiential", "general"): 0.8,
            ("pattern", "analytical"): 0.9,
            ("principle", "strategic"): 0.95,
            ("insight", "innovative"): 0.85
        }

        base_compatibility = compatibility_matrix.get((wisdom_type, context_type), 0.6)

        # Adjust for contextual factors
        complexity_match = transmission_context.get("complexity_match", 0.5)
        domain_match = transmission_context.get("domain_match", 0.5)

        compatibility = (base_compatibility + complexity_match + domain_match) / 3
        return max(0.0, min(1.0, compatibility))
    except Exception:
        return 0.5

def _assess_wisdom_relevance(
    wisdom_entry: Dict[str, Any],
    transmission_context: Dict[str, Any]
) -> float:
    """Assess relevance of wisdom for transmission context."""
    try:
        # Simple relevance assessment
        wisdom_tags = set(wisdom_entry.get("tags", []))
        context_needs = set(transmission_context.get("needs", []))

        if not wisdom_tags and not context_needs:
            return 0.6  # Neutral relevance

        if not wisdom_tags:
            return 0.3  # Low relevance if wisdom has no tags

        if not context_needs:
            return 0.7  # Moderate relevance if context expresses no specific needs

        # Calculate overlap
        overlap = len(wisdom_tags & context_needs)
        total = len(wisdom_tags | context_needs)

        relevance = overlap / total if total > 0 else 0.0
        return max(0.0, min(1.0, relevance))
    except Exception:
        return 0.5

# Export functions for easy importing
__all__ = [
    "distill_wisdom_from_experience",
    "store_wisdom_entry",
    "retrieve_relevant_wisdom",
    "track_wisdom_evolution",
    "transmit_wisdom_to_instance"
]
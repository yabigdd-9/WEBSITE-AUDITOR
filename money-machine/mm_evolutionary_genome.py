"""Evolutionary genome system for the WEBSITE-AUDITOR system.
Implements self-modifying architecture with genetic encoding, expression regulation, and fitness tracking.
"""
import json
import sqlite3
import hashlib
import math
from datetime import datetime, timezone
from mm_core import now, connect, sha
from typing import Dict, List, Any, Optional, Tuple

def encode_architectural_genes(
    conn: sqlite3.Connection,
    architectural_pattern: str,
    parameters: Dict[str, Any],
    generation: int = 0
) -> Dict[str, Any]:
    """Encode the system's architectural patterns as expressible genes.

    Encodes the system's architectural patterns as expressible genes by representing
    pipeline stage configurations, scoring weights, and decision thresholds as configurable genetic traits.

    Args:
        conn: Database connection
        architectural_pattern: Name of the architectural pattern to encode
        parameters: Dictionary of parameters that define this architectural pattern
        generation: Generation number for this encoding

    Returns:
        Dictionary containing the encoded genetic information
    """
    try:
        # Create a genetic hash from the architectural pattern and parameters
        pattern_json = json.dumps({
            "pattern": architectural_pattern,
            "parameters": parameters,
            "generation": generation
        }, sort_keys=True)

        genetic_hash = sha(pattern_json)

        # Store the genetic encoding in the learning table
        conn.execute('''
            INSERT INTO mm_learning(
                pattern, expected, actual, evidence_ref,
                confidence, recommended_change, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            f"genetic_encoding_{architectural_pattern}",
            f"generation_{generation}",
            genetic_hash,
            json.dumps({
                "architectural_pattern": architectural_pattern,
                "parameters": parameters,
                "generation": generation,
                "genetic_hash": genetic_hash,
                "timestamp": now()
            }),
            0.95,  # High confidence in genetic encoding
            f"Preserve architectural pattern {architectural_pattern} generation {generation}",
            now()
        ))
        conn.commit()

        return {
            "status": "encoded",
            "genetic_hash": genetic_hash,
            "architectural_pattern": architectural_pattern,
            "generation": generation,
            "parameters": parameters,
            "timestamp": now()
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to encode architectural genes for {architectural_pattern}: {str(e)}",
            "genetic_hash": None
        }

def express_genotype(
    conn: sqlite3.Connection,
    genetic_hash: str,
    business_context: Dict[str, Any],
    performance_metrics: Dict[str, Any]
) -> Dict[str, Any]:
    """Express different genotypes in response to environmental pressures.

    Expresses different genotypes in response to environmental pressures by activating
    different genetic expressions based on business context, performance metrics, and external conditions.

    Args:
        conn: Database connection
        genetic_hash: The genetic hash to express
        business_context: Current business context
        performance_metrics: Current performance metrics

    Returns:
        Dictionary containing the expressed genotype and its characteristics
    """
    try:
        # Retrieve the genetic encoding from the learning table
        cursor = conn.execute('''
            SELECT actual, evidence_ref, confidence, created_at
            FROM mm_learning
            WHERE actual = ?
              AND pattern LIKE 'genetic_encoding_%'
            ORDER BY created_at DESC
            LIMIT 1
        ''', (genetic_hash,))

        row = cursor.fetchone()
        if not row:
            return {
                "status": "not_found",
                "message": f"Genetic hash {genetic_hash} not found in genome",
                "expressed_traits": {}
            }

        # Decode the genetic information
        genetic_info = json.loads(row[0]) if row[0] else {}
        evidence_ref = json.loads(row[1]) if row[1] else {}
        storage_confidence = row[2] if row[2] else 0.0
        created_at = row[3] if row[3] else now()

        # Calculate expression fitness based on business context and performance
        expression_fitness = _calculate_expression_fitness(
            genetic_info, business_context, performance_metrics
        )

        # Determine if this genotype should be expressed based on fitness
        should_express = expression_fitness > 0.6  # Threshold for expression

        # Store the expression event
        conn.execute('''
            INSERT INTO mm_learning(
                pattern, expected, actual, evidence_ref,
                confidence, recommended_change, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            f"genotype_expression_{genetic_hash[:8]}",
            "express_architectural_traits",
            json.dumps({
                "genetic_hash": genetic_hash,
                "expressed": should_express,
                "expression_fitness": expression_fitness,
                "business_context": business_context,
                "performance_metrics": performance_metrics,
                "timestamp": now()
            }),
            json.dumps({
                "genetic_info": genetic_info,
                "expression_timestamp": now()
            }),
            0.8,
            f"Monitor expression fitness of genotype {genetic_hash[:8]}",
            now()
        ))
        conn.commit()

        return {
            "status": "expressed" if should_express else "suppressed",
            "genetic_hash": genetic_hash,
            "architectural_pattern": genetic_info.get("architectural_pattern"),
            "generation": genetic_info.get("generation"),
            "expressed": should_express,
            "expression_fitness": expression_fitness,
            "traits": genetic_info.get("parameters", {}),
            "timestamp": now()
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to express genotype {genetic_hash}: {str(e)}",
            "expressed": False,
            "expression_fitness": 0.0
        }

def track_genetic_fitness(
    conn: sqlite3.Connection,
    genetic_hash: str,
    business_outcome: Dict[str, Any],
    system_performance: Dict[str, Any]
) -> Dict[str, Any]:
    """Track the fitness of different architectural expressions.

    Tracks the fitness of different architectural expressions by correlating
    genetic expressions with business outcomes and system performance metrics.

    Args:
        conn: Database connection
        genetic_hash: The genetic hash to track fitness for
        business_outcome: Business outcomes resulting from this genetic expression
        system_performance: System performance metrics during this expression

    Returns:
        Dictionary containing fitness tracking information
    """
    try:
        # Calculate fitness score based on business outcomes and system performance
        fitness_score = _calculate_fitness_score(business_outcome, system_performance)

        # Store the fitness evaluation
        conn.execute('''
            INSERT INTO mm_learning(
                pattern, expected, actual, evidence_ref,
                confidence, recommended_change, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            f"fitness_evaluation_{genetic_hash[:8]}",
            "measure_genetic_fitness",
            json.dumps({
                "genetic_hash": genetic_hash,
                "fitness_score": fitness_score,
                "business_outcome": business_outcome,
                "system_performance": system_performance,
                "timestamp": now()
            }),
            json.dumps({
                "evaluation_timestamp": now()
            }),
            0.85,
            f"Continue tracking fitness of genotype {genetic_hash[:8]}",
            now()
        ))
        conn.commit()

        # Update any existing fitness records for this genetic hash.
        # This is observational history only; it does not change runtime policy.
        history_rows = conn.execute('''
            SELECT actual FROM mm_learning
            WHERE pattern = ? AND actual LIKE ?
            ORDER BY created_at DESC LIMIT 10
        ''', (f"fitness_evaluation_{genetic_hash[:8]}", f"%{genetic_hash}%")).fetchall()
        conn.execute('''
            UPDATE mm_learning
            SET actual = ?,
                evidence_ref = ?,
                confidence = ?,
                created_at = ?
            WHERE pattern = ? AND actual LIKE ?
        ''', (
            json.dumps({
                "genetic_hash": genetic_hash,
                "latest_fitness": fitness_score,
                "fitness_history": [json.loads(row[0]) for row in history_rows],
                "business_outcome": business_outcome,
                "system_performance": system_performance,
                "timestamp": now()
            }),
            json.dumps({
                "update_timestamp": now()
            }),
            0.9,
            now(),
            f"fitness_evaluation_{genetic_hash[:8]}",
            f"%{genetic_hash}%"
        ))

        return {
            "status": "tracked",
            "genetic_hash": genetic_hash,
            "fitness_score": fitness_score,
            "business_outcome": business_outcome,
            "system_performance": system_performance,
            "timestamp": now()
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to track fitness for genotype {genetic_hash}: {str(e)}",
            "fitness_score": 0.0
        }

def _calculate_expression_fitness(
    genetic_info: Dict[str, Any],
    business_context: Dict[str, Any],
    performance_metrics: Dict[str, Any]
) -> float:
    """Calculate the fitness of expressing a genotype in the current context."""
    try:
        # Start with base fitness
        fitness = 0.5

        # Adjust based on business context alignment
        pattern = genetic_info.get("architectural_pattern", "")
        parameters = genetic_info.get("parameters", {})

        # Check if this pattern is suitable for current business context
        industry = business_context.get("industry", "")
        problem_type = business_context.get("primary_problem", "")
        urgency = business_context.get("urgency", 0.5)  # 0.0 to 1.0

        # Pattern suitability scoring
        if "audit" in pattern.lower() and urgency > 0.7:
            fitness += 0.2  # Audit patterns good for urgent situations
        elif "conversion" in pattern.lower() and problem_type in ["conversion", "sales"]:
            fitness += 0.25  # Conversion patterns good for conversion problems
        elif "relationship" in pattern.lower() and business_context.get("relationship_focus", False):
            fitness += 0.2  # Relationship patterns good when relationships are focus

        # Adjust based on performance metrics
        current_performance = performance_metrics.get("overall_score", 0.5)
        if current_performance < 0.6:
            # Poor performance - favor patterns that have historically improved performance
            historical_improvement = parameters.get("historical_improvement_potential", 0.5)
            fitness += (historical_improvement - 0.5) * 0.4  # -0.2 to +0.2 adjustment
        else:
            # Good performance - favor stable, proven patterns
            stability = parameters.get("stability", 0.5)
            fitness += (stability - 0.5) * 0.3  # -0.15 to +0.15 adjustment

        # Adjust based on resource constraints
        resource_availability = business_context.get("resource_availability", 0.5)
        resource_intensity = parameters.get("resource_intensity", 0.5)
        if resource_intensity > resource_availability:
            fitness -= 0.2  # Penalize high resource intensity when resources are scarce
        else:
            fitness += 0.1  # Bonus for matching resource usage to availability

        # Ensure fitness stays in valid range
        return max(0.0, min(1.0, fitness))

    except Exception:
        return 0.5  # Return neutral fitness on error

def _calculate_fitness_score(
    business_outcome: Dict[str, Any],
    system_performance: Dict[str, Any]
) -> float:
    """Calculate fitness score from business outcomes and system performance."""
    try:
        # Business outcome components (weighted)
        revenue_impact = business_outcome.get("revenue_impact", 0.0)  # Could be negative
        customer_satisfaction = business_outcome.get("customer_satisfaction", 0.5)  # 0.0 to 1.0
        new_opportunities = business_outcome.get("new_opportunities", 0.0)  # Number of new opportunities
        risk_mitigation = business_outcome.get("risk_mitigation", 0.5)  # 0.0 to 1.0

        # Normalize revenue impact to 0-1 scale (assuming +/- 10000 is max impact)
        normalized_revenue = max(0.0, min(1.0, (revenue_impact + 10000) / 20000))

        # System performance components
        efficiency = system_performance.get("efficiency", 0.5)  # 0.0 to 1.0
        reliability = system_performance.get("reliability", 0.5)  # 0.0 to 1.0
        scalability = system_performance.get("scalability", 0.5)  # 0.0 to 1.0
        innovation = system_performance.get("innovation", 0.5)  # 0.0 to 1.0

        # Calculate weighted fitness score
        fitness = (
            0.25 * normalized_revenue +      # Business value
            0.20 * customer_satisfaction +   # Customer happiness
            0.15 * min(1.0, new_opportunities / 10.0) +  # Opportunity creation
            0.10 * risk_mitigation +         # Risk reduction
            0.10 * efficiency +              # Operational efficiency
            0.10 * reliability +             # System stability
            0.05 * scalability +             # Growth potential
            0.05 * innovation                # Adaptability
        )

        return max(0.0, min(1.0, fitness))

    except Exception:
        return 0.5  # Return neutral fitness on error

def get_genetic_diversity_metrics() -> Dict[str, Any]:
    """Get metrics about the genetic diversity of the system's architecture.

    Returns:
        Dictionary containing genetic diversity metrics
    """
    try:
        with contextlib.closing(connect()) as conn:
            # Count total genetic encodings
            total_encodings = conn.execute('''
                SELECT COUNT(*) FROM mm_learning
                WHERE pattern LIKE 'genetic_encoding_%'
            ''').fetchone()[0]

            # Count unique architectural patterns
            unique_patterns = conn.execute('''
                SELECT COUNT(DISTINCT json_extract(actual, '$.architectural_pattern'))
                FROM mm_learning
                WHERE pattern LIKE 'genetic_encoding_%'
                  AND json_extract(actual, '$.architectural_pattern') IS NOT NULL
            ''').fetchone()[0]

            # Count recent expressions (last 24 hours)
            recent_expressions = conn.execute('''
                SELECT COUNT(*) FROM mm_learning
                WHERE pattern LIKE 'genotype_expression_%'
                  AND created_at >= datetime('now', '-24 hours')
            ''').fetchone()[0]

            # Get average fitness of expressed genotypes
            avg_fitness_cursor = conn.execute('''
                SELECT AVG(CAST(json_extract(actual, '$.fitness_score') AS REAL)) as avg_fitness
                FROM mm_learning
                WHERE pattern LIKE '%fitness_evaluation_%'
                  AND created_at >= datetime('now', '-7 days')
                  AND json_extract(actual, '$.fitness_score') IS NOT NULL
            ''')
            avg_fitness_row = avg_fitness_cursor.fetchone()
            avg_fitness = avg_fitness_row[0] if avg_fitness_row and avg_fitness_row[0] is not None else 0.5

            # Get genetic hash diversity (unique genotypes)
            unique_genotypes = conn.execute('''
                SELECT COUNT(DISTINCT actual) FROM mm_learning
                WHERE pattern LIKE 'genetic_encoding_%'
            ''').fetchone()[0]

            return {
                "total_genetic_encodings": total_encodings or 0,
                "unique_architectural_patterns": unique_patterns or 0,
                "unique_genotypes": unique_genotypes or 0,
                "recent_expressions_24h": recent_expressions or 0,
                "average_fitness_7d": round(avg_fitness, 3) if avg_fitness else 0.5,
                "genetic_diversity_index": round((unique_genotypes / max(total_encodings, 1)) * 100, 1) if total_encodings > 0 else 0.0,
                "timestamp": now()
            }

    except Exception as e:
        return {
            "error": f"Failed to get genetic diversity metrics: {str(e)}",
            "total_genetic_encodings": 0,
            "unique_architectural_patterns": 0,
            "unique_genotypes": 0,
            "recent_expressions_24h": 0,
            "average_fitness_7d": 0.5,
            "genetic_diversity_index": 0.0,
            "timestamp": now()
        }

# Export functions for easy importing
__all__ = [
    "encode_architectural_genes",
    "express_genotype",
    "track_genetic_fitness",
    "get_genetic_diversity_metrics"
]

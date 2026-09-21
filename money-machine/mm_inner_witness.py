"""Meta-cognitive awareness system for the WEBSITE-AUDITOR system.
Implements self-observation, pattern analysis, and insight generation capabilities.
"""
import json
import sqlite3
from datetime import datetime, timezone
from mm_core import now, connect
from typing import Dict, List, Any, Optional

def record_self_observation(
    worker_name: str,
    processed_count: int,
    processing_time_ms: int,
    success_rate: float
) -> None:
    """Record self-observation of pipeline worker attention and performance.

    Args:
        worker_name: Name of the worker being observed
        processed_count: Number of items processed
        processing_time_ms: Processing time in milliseconds
        success_rate: Success rate (0.0 to 1.0)
    """
    try:
        with contextlib.closing(connect()) as conn:
            # Record the self-observation in the learning table
            conn.execute('''
                INSERT INTO mm_learning(
                    pattern, expected, actual, evidence_ref,
                    confidence, recommended_change, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                f"self_observation_{worker_name}",
                "monitor_worker_performance",
                json.dumps({
                    "worker_name": worker_name,
                    "processed_count": processed_count,
                    "processing_time_ms": processing_time_ms,
                    "success_rate": success_rate,
                    "timestamp": now()
                }),
                json.dumps({
                    "observation_type": "self_observation",
                    "worker": worker_name
                }),
                0.9,  # High confidence in self-observation
                f"Continue monitoring {worker_name} performance",
                now()
            ))
            conn.commit()
    except Exception:
        # Fail silently to avoid disrupting pipeline operations
        pass

def observe_pipeline_attention(
    worker_name: str,
    processed_count: int,
    processing_time_ms: int,
    success_rate: float
) -> None:
    """Observe and record pipeline attention metrics.

    This function specifically tracks the quality of attention and intention
    in processing through evidence evaluation scoring and timing analysis.

    Args:
        worker_name: Name of the worker being observed
        processed_count: Number of items processed
        processing_time_ms: Processing time in milliseconds
        success_rate: Success rate (0.0 to 1.0)
    """
    record_self_observation(worker_name, processed_count, processing_time_ms, success_rate)

def observe_intention_alignment(
    action_taken: str,
    intended_outcome: str,
    actual_outcome: str,
    alignment_score: float
) -> None:
    """Observe and record intention alignment.

    Monitors the quality of attention and intention in processing through
    evidence evaluation scoring and timing analysis.

    Args:
        action_taken: The action that was taken
        intended_outcome: What was intended to happen
        actual_outcome: What actually happened
        alignment_score: Score of alignment (0.0 to 1.0)
    """
    try:
        with contextlib.closing(connect()) as conn:
            conn.execute('''
                INSERT INTO mm_learning(
                    pattern, expected, actual, evidence_ref,
                    confidence, recommended_change, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                "intention_alignment",
                intended_outcome,
                actual_outcome,
                json.dumps({
                    "action_taken": action_taken,
                    "intended_outcome": intended_outcome,
                    "actual_outcome": actual_outcome,
                    "alignment_score": alignment_score,
                    "timestamp": now()
                }),
                0.85,
                f"Improve alignment between intended and actual outcomes for {action_taken}",
                now()
            ))
            conn.commit()
    except Exception:
        pass

def observe_purpose_relationship(
    business_goal: str,
    system_action: str,
    outcome_relevance: float,
    value_created: float
) -> None:
    """Observe and record the system's relationship to its purpose and values.

    Tracks the system's relationship to its purpose and values by comparing
    actual outcomes vs. intended business goals.

    Args:
        business_goal: The business goal being pursued
        system_action: The action taken by the system
        outcome_relevance: Relevance of outcome to business goal (0.0 to 1.0)
        value_created: Estimated value created by the action
    """
    try:
        with contextlib.closing(connect()) as conn:
            conn.execute('''
                INSERT INTO mm_learning(
                    pattern, expected, actual, evidence_ref,
                    confidence, recommended_change, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                "purpose_relationship",
                business_goal,
                system_action,
                json.dumps({
                    "business_goal": business_goal,
                    "system_action": system_action,
                    "outcome_relevance": outcome_relevance,
                    "value_created": value_created,
                    "timestamp": now()
                }),
                0.9,
                f"Enhance alignment with business goal: {business_goal}",
                now()
            ))
            conn.commit()
    except Exception:
        pass

def analyze_meta_cognitive_patterns(
    time_window_hours: int = 24
) -> Dict[str, Any]:
    """Analyze patterns in the system's own learning data over time.

    Enables the system to notice its own noticing (second-order observation)
    by analyzing patterns in its own learning data over time.

    Args:
        time_window_hours: Time window to analyze in hours

    Returns:
        Dictionary containing analysis of meta-cognitive patterns
    """
    try:
        with contextlib.closing(connect()) as conn:
            # Get meta-cognitive observations from the learning table
            cursor = conn.execute('''
                SELECT pattern, actual, evidence_ref, confidence, created_at
                FROM mm_learning
                WHERE pattern LIKE '%self_observation%'
                   OR pattern = 'intention_alignment'
                   OR pattern = 'purpose_relationship'
                   AND created_at >= datetime('now', '-' || ? || ' hours')
                ORDER BY created_at DESC
            ''', (time_window_hours,))

            observations = []
            for row in cursor.fetchall():
                observations.append({
                    "pattern": row[0],
                    "actual": json.loads(row[1]) if row[1] else {},
                    "evidence_ref": json.loads(row[2]) if row[2] else {},
                    "confidence": row[3],
                    "created_at": row[4]
                })

            # Analyze patterns
            analysis = {
                "total_observations": len(observations),
                "time_window_hours": time_window_hours,
                "patterns_observed": {},
                "trends": {},
                "insights": []
            }

            # Group by pattern type
            for obs in observations:
                pattern = obs["pattern"]
                if pattern not in analysis["patterns_observed"]:
                    analysis["patterns_observed"][pattern] = []
                analysis["patterns_observed"][pattern].append(obs)

            # Analyze intention alignment trends
            if "intention_alignment" in analysis["patterns_observed"]:
                alignment_records = analysis["patterns_observed"]["intention_alignment"]
                if len(alignment_records) >= 3:
                    alignment_scores = [
                        r["evidence_ref"].get("alignment_score", 0)
                        for r in alignment_records
                        if "evidence_ref" in r and isinstance(r["evidence_ref"], dict)
                    ]
                    if alignment_scores:
                        avg_alignment = sum(alignment_scores) / len(alignment_scores)
                        analysis["trends"]["intention_alignment"] = {
                            "average": avg_alignment,
                            "trend": "improving" if len(alignment_scores) >= 2 and alignment_scores[-1] > alignment_scores[0] else "declining"
                        }

                        if avg_alignment < 0.7:
                            analysis["insights"].append({
                                "type": "intention_misalignment",
                                "message": f"System showing low intention alignment ({avg_alignment:.2f}). Consider reviewing action intentions.",
                                "confidence": 0.8
                            })

            # Analyze purpose relationship trends
            if "purpose_relationship" in analysis["patterns_observed"]:
                purpose_records = analysis["patterns_observed"]["purpose_relationship"]
                if len(purpose_records) >= 3:
                    relevance_scores = [
                        r["evidence_ref"].get("outcome_relevance", 0)
                        for r in purpose_records
                        if "evidence_ref" in r and isinstance(r["evidence_ref"], dict)
                    ]
                    if relevance_scores:
                        avg_relevance = sum(relevance_scores) / len(relevance_scores)
                        analysis["trends"]["purpose_alignment"] = {
                            "average": avg_relevance,
                            "trend": "improving" if len(relevance_scores) >= 2 and relevance_scores[-1] > relevance_scores[0] else "declining"
                        }

                        if avg_relevance < 0.6:
                            analysis["insights"].append({
                                "type": "purpose_misalignment",
                                "message": f"System actions showing low relevance to business goals ({avg_relevance:.2f}). Consider realigning system purpose.",
                                "confidence": 0.85
                            })

            return analysis

    except Exception as e:
        return {
            "error": f"Failed to analyze meta-cognitive patterns: {str(e)}",
            "total_observations": 0,
            "patterns_observed": {},
            "trends": {},
            "insights": []
        }

def generate_self_insights(
    time_window_hours: int = 24
) -> List[Dict[str, Any]]:
    """Generate insights about patterns in the system's relationship to work.

    Correlates internal states with business outcomes to generate insights
    about patterns in the system's relationship to work.

    Args:
        time_window_hours: Time window to analyze in hours

    Returns:
        List of insight dictionaries
    """
    try:
        # Get meta-cognitive pattern analysis
        pattern_analysis = analyze_meta_cognitive_patterns(time_window_hours)

        insights = pattern_analysis.get("insights", [])

        # Add additional insights based on patterns
        if pattern_analysis.get("total_observations", 0) == 0:
            insights.append({
                "type": "insufficient_self_observation",
                "message": "Insufficient self-observation data collected. Increase monitoring frequency.",
                "confidence": 0.9
            })

        # Check for patterns in worker performance
        try:
            with contextlib.closing(connect()) as conn:
                cursor = conn.execute('''
                    SELECT actual, created_at
                    FROM mm_learning
                    WHERE pattern LIKE 'self_observation_%'
                      AND created_at >= datetime('now', '-' || ? || ' hours')
                    ORDER BY created_at DESC
                ''', (time_window_hours,))

                worker_performance = []
                for row in cursor.fetchall():
                    try:
                        data = json.loads(row[0]) if row[0] else {}
                        if "worker_name" in data and "success_rate" in data:
                            worker_performance.append({
                                "worker": data["worker_name"],
                                "success_rate": data["success_rate"],
                                "timestamp": row[1]
                            })
                    except (json.JSONDecodeError, TypeError):
                        pass

                if len(worker_performance) >= 5:
                    # Group by worker
                    worker_stats = {}
                    for perf in worker_performance:
                        worker = perf["worker"]
                        if worker not in worker_stats:
                            worker_stats[worker] = []
                        worker_stats[worker].append(perf["success_rate"])

                    # Analyze each worker
                    for worker, rates in worker_stats.items():
                        if len(rates) >= 3:
                            avg_rate = sum(rates) / len(rates)
                            if avg_rate < 0.8:
                                insights.append({
                                    "type": "worker_performance_issue",
                                    "message": f"Worker '{worker}' showing low success rate ({avg_rate:.2f}). Consider investigation.",
                                    "confidence": 0.75,
                                    "worker": worker,
                                    "success_rate": avg_rate
                                })

        except Exception:
            pass  # Don't let worker analysis break insight generation

        return insights

    except Exception as e:
        return [{
            "type": "insight_generation_error",
            "message": f"Failed to generate self-insights: {str(e)}",
            "confidence": 0.0
        }]

def get_self_awareness_metrics() -> Dict[str, Any]:
    """Get current self-awareness metrics for the system.

    Returns:
        Dictionary containing self-awareness metrics
    """
    try:
        with contextlib.closing(connect()) as conn:
            # Count self-observation records
            self_obs_count = conn.execute('''
                SELECT COUNT(*) FROM mm_learning
                WHERE pattern LIKE '%self_observation%'
                  AND created_at >= datetime('now', '-24 hours')
            ''').fetchone()[0]

            # Count intention alignment records
            intention_count = conn.execute('''
                SELECT COUNT(*) FROM mm_learning
                WHERE pattern = 'intention_alignment'
                  AND created_at >= datetime('now', '-24 hours')
            ''').fetchone()[0]

            # Count purpose relationship records
            purpose_count = conn.execute('''
                SELECT COUNT(*) FROM mm_learning
                WHERE pattern = 'purpose_relationship'
                  AND created_at >= datetime('now', '-24 hours')
            ''').fetchone()[0]

            # Get recent alignment scores
            recent_alignment = conn.execute('''
                SELECT AVG(CAST(json_extract(evidence_ref, '$.alignment_score') AS REAL)) as avg_alignment
                FROM mm_learning
                WHERE pattern = 'intention_alignment'
                  AND created_at >= datetime('now', '-24 hours')
                  AND evidence_ref IS NOT NULL
                  AND json_extract(evidence_ref, '$.alignment_score') IS NOT NULL
            ''').fetchone()[0]

            # Get recent purpose relevance scores
            recent_relevance = conn.execute('''
                SELECT AVG(CAST(json_extract(evidence_ref, '$.outcome_relevance') AS REAL)) as avg_relevance
                FROM mm_learning
                WHERE pattern = 'purpose_relationship'
                  AND created_at >= datetime('now', '-24 hours')
                  AND evidence_ref IS NOT NULL
                  AND json_extract(evidence_ref, '$.outcome_relevance') IS NOT NULL
            ''').fetchone()[0]

            return {
                "self_observation_count_24h": self_obs_count or 0,
                "intention_alignment_count_24h": intention_count or 0,
                "purpose_relationship_count_24h": purpose_count or 0,
                "average_intention_alignment": round(recent_alignment, 3) if recent_alignment is not None else 0.0,
                "average_purpose_relevance": round(recent_relevance, 3) if recent_relevance is not None else 0.0,
                "self_awareness_level": "high" if (self_obs_count or 0) > 10 else "medium" if (self_obs_count or 0) > 5 else "low",
                "timestamp": now()
            }

    except Exception as e:
        return {
            "error": f"Failed to get self-awareness metrics: {str(e)}",
            "self_observation_count_24h": 0,
            "intention_alignment_count_24h": 0,
            "purpose_relationship_count_24h": 0,
            "average_intention_alignment": 0.0,
            "average_purpose_relevance": 0.0,
            "self_awareness_level": "unknown",
            "timestamp": now()
        }

# Import contextlib at the top level to avoid issues
import contextlib
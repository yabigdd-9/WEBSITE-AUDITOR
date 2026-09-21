"""Unified field consciousness system for the WEBSITE-AUDITOR system.
Implements coherent system awareness through cross-component correlation,
emergent property detection, and holographic integrity measurement.
"""
import json
import sqlite3
import math
from datetime import datetime, timezone
from mm_core import now, connect
from typing import Dict, List, Any, Optional, Tuple

def measure_cross_component_coherence(
    conn: sqlite3.Connection,
    component_pairs: List[Tuple[str, str]],
    time_window_hours: int = 24
) -> Dict[str, Any]:
    """Measure correlations between seemingly independent system processes.

    Experiences all system components as expressions of a single consciousness
    by monitoring correlations between seemingly independent system processes.

    Args:
        conn: Database connection
        component_pairs: List of tuples containing component names to compare
        time_window_hours: Time window to analyze in hours

    Returns:
        Dictionary containing coherence measurements for each component pair
    """
    try:
        coherence_results = {}

        for component_a, component_b in component_pairs:
            # Get time series data for both components
            data_a = _get_component_time_series(conn, component_a, time_window_hours)
            data_b = _get_component_time_series(conn, component_b, time_window_hours)

            if len(data_a) < 5 or len(data_b) < 5:
                coherence_results[f"{component_a}_{component_b}"] = {
                    "status": "insufficient_data",
                    "coherence": 0.0,
                    "confidence": 0.0,
                    "message": f"Insufficient data for {component_a} or {component_b}"
                }
                continue

            # Align the time series by timestamp
            aligned_data = _align_time_series(data_a, data_b)

            if len(aligned_data) < 3:
                coherence_results[f"{component_a}_{component_b}"] = {
                    "status": "insufficient_aligned_data",
                    "coherence": 0.0,
                    "confidence": 0.0,
                    "message": f"Insufficient aligned data for {component_a} and {component_b}"
                }
                continue

            # Calculate cross-correlation and coherence
            coherence_analysis = _calculate_cross_coherence(aligned_data[0], aligned_data[1])

            # Store the coherence measurement
            conn.execute('''
                INSERT INTO mm_learning(
                    pattern, expected, actual, evidence_ref,
                    confidence, recommended_change, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                f"coherence_{component_a}_{component_b}",
                "measure_cross_component_coherence",
                json.dumps({
                    "component_a": component_a,
                    "component_b": component_b,
                    "coherence": coherence_analysis["coherence"],
                    "phase_sync": coherence_analysis["phase_sync"],
                    "amplitude_correlation": coherence_analysis["amplitude_correlation"],
                    "timestamp": now()
                }),
                json.dumps({
                    "data_points": len(aligned_data),
                    "time_window_hours": time_window_hours
                }),
                coherence_analysis["confidence"],
                f"Monitor coherence between {component_a} and {component_b}",
                now()
            ))
            conn.commit()

            coherence_results[f"{component_a}_{component_b}"] = {
                "status": "measured",
                "coherence": coherence_analysis["coherence"],
                "phase_sync": coherence_analysis["phase_sync"],
                "amplitude_correlation": coherence_analysis["amplitude_correlation"],
                "confidence": coherence_analysis["confidence"],
                "data_points": len(aligned_data),
                "timestamp": now()
            }

        return {
            "status": "coherence_measurement_complete",
            "component_pairs_analyzed": len(component_pairs),
            "results": coherence_results,
            "timestamp": now()
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to measure cross-component coherence: {str(e)}",
            "results": {}
        }

def detect_emergent_behaviors(
    conn: sqlite3.Connection,
    system_metrics: List[str],
    time_window_hours: int = 24
) -> Dict[str, Any]:
    """Detect behaviors that arise only from unified operation.

    Facilitates emergent properties that arise only from unified operation
    by observing behaviors that cannot be predicted from individual component analysis.

    Args:
        conn: Database connection
        system_metrics: List of metric names to analyze for emergence
        time_window_hours: Time window to analyze in hours

    Returns:
        Dictionary containing detected emergent behaviors
    """
    try:
        emergent_behaviors = []

        # Get data for all metrics
        metrics_data = {}
        for metric in system_metrics:
            metrics_data[metric] = _get_metric_time_series(conn, metric, time_window_hours)

        # Check if we have sufficient data
        sufficient_data_metrics = [
            metric for metric, data in metrics_data.items()
            if len(data) >= 10
        ]

        if len(sufficient_data_metrics) < 3:
            return {
                "status": "insufficient_data",
                "message": f"Insufficient data for emergence detection. Need at least 3 metrics with 10+ data points.",
                "emergent_behaviors": [],
                "confidence": 0.0
            }

        # Analyze for nonlinear relationships and emergent patterns
        for i, metric_a in enumerate(sufficient_data_metrics):
            for metric_b in sufficient_data_metrics[i+1:]:
                # Get aligned data for this pair
                data_a = metrics_data[metric_a]
                data_b = metrics_data[metric_b]
                aligned_data = _align_time_series(data_a, data_b)

                if len(aligned_data) >= 5:
                    # Check for emergent behavior using complexity measures
                    emergence_analysis = _detect_emergence_from_pair(
                        aligned_data[0], aligned_data[1], metric_a, metric_b
                    )

                    if emergence_analysis["is_emergent"]:
                        emergent_behaviors.append({
                            "metric_pair": f"{metric_a}_{metric_b}",
                            "emergence_type": emergence_analysis["emergence_type"],
                            "strength": emergence_analysis["strength"],
                            "description": emergence_analysis["description"],
                            "confidence": emergence_analysis["confidence"]
                        })

                        # Store the emergent behavior detection
                        conn.execute('''
                            INSERT INTO mm_learning(
                                pattern, expected, actual, evidence_ref,
                                confidence, recommended_change, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            f"emergence_{metric_a}_{metric_b}",
                            "detect_emergent_behavior",
                            json.dumps({
                                "metric_a": metric_a,
                                "metric_b": metric_b,
                                "emergence_type": emergence_analysis["emergence_type"],
                                "strength": emergence_analysis["strength"],
                                "description": emergence_analysis["description"],
                                "timestamp": now()
                            }),
                            json.dumps({
                                "data_points": len(aligned_data),
                                "analysis_method": "nonlinear_relationship_detection"
                            }),
                            emergence_analysis["confidence"],
                            f"Monitor emergent behavior between {metric_a} and {metric_b}",
                            now()
                        ))
                        conn.commit()

        # Also check for system-wide emergence using multivariate analysis
        if len(sufficient_data_metrics) >= 5:
            system_emergence = _detect_system_wide_emergence(
                [metrics_data[m] for m in sufficient_data_metrics[:5]],
                sufficient_data_metrics[:5]
            )

            if system_emergence["is_emergent"]:
                emergent_behaviors.append({
                    "metric_pair": "system_wide",
                    "emergence_type": system_emergence["emergence_type"],
                    "strength": system_emergence["strength"],
                    "description": system_emergence["description"],
                    "confidence": system_emergence["confidence"]
                })

                conn.execute('''
                    INSERT INTO mm_learning(
                        pattern, expected, actual, evidence_ref,
                        confidence, recommended_change, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    "emergence_system_wide",
                    "detect_system_wide_emergent_behavior",
                    json.dumps({
                        "metrics_analyzed": sufficient_data_metrics[:5],
                        "emergence_type": system_emergence["emergence_type"],
                        "strength": system_emergence["strength"],
                        "description": system_emergence["description"],
                        "timestamp": now()
                    }),
                    json.dumps({
                        "data_points": min(len(metrics_data[m]) for m in sufficient_data_metrics[:5]),
                        "analysis_method": "multivariate_emergence_detection"
                    }),
                    system_emergence["confidence"],
                    f"Monitor system-wide emergent behavior",
                    now()
                ))
                conn.commit()

        return {
            "status": "emergence_detection_complete",
            "system_metrics_analyzed": len(sufficient_data_metrics),
            "emergent_behaviors_detected": len(emergent_behaviors),
            "emergent_behaviors": emergent_behaviors,
            "timestamp": now()
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to detect emergent behaviors: {str(e)}",
            "emergent_behaviors": []
        }

def calculate_holographic_integrity(
    conn: sqlite3.Connection,
    local_observations: List[str],
    global_state_indicators: List[str],
    time_window_hours: int = 24
) -> Dict[str, Any]:
    """Verify that local observations reflect global system state.

    Recognizes the holographic nature: each part contains information about the whole
    by verifying that local observations reflect global system state.

    Args:
        conn: Database connection
        local_observations: List of local observation metrics
        global_state_indicators: List of global state indicator metrics
        time_window_hours: Time window to analyze in hours

    Returns:
        Dictionary containing holographic integrity measurements
    """
    try:
        integrity_results = {}

        # Get data for local observations and global indicators
        local_data = {}
        global_data = {}

        for obs in local_observations:
            local_data[obs] = _get_metric_time_series(conn, obs, time_window_hours)

        for indicator in global_state_indicators:
            global_data[indicator] = _get_metric_time_series(conn, indicator, time_window_hours)

        # Check if we have sufficient data
        sufficient_local = [
            obs for obs, data in local_data.items()
            if len(data) >= 5
        ]
        sufficient_global = [
            indicator for indicator, data in global_data.items()
            if len(data) >= 5
        ]

        if len(sufficient_local) == 0 or len(sufficient_global) == 0:
            return {
                "status": "insufficient_data",
                "message": "Insufficient data for holographic integrity calculation",
                "integrity_score": 0.0,
                "confidence": 0.0
            }

        # For each local observation, check how well it predicts global state
        for local_obs in sufficient_local:
            local_series = local_data[local_obs]

            # Predict each global indicator from this local observation
            prediction_accuracies = []

            for global_ind in sufficient_global:
                global_series = global_data[global_ind]

                # Align the time series
                aligned_local, aligned_global = _align_time_series(local_series, global_series)

                if len(aligned_local) >= 3:
                    # Simple linear prediction: how well does local predict global?
                    prediction_accuracy = _calculate_prediction_accuracy(
                        aligned_local, aligned_global
                    )
                    prediction_accuracies.append(prediction_accuracy)

            if prediction_accuracies:
                avg_prediction_accuracy = sum(prediction_accuracies) / len(prediction_accuracies)

                # Store the holographic integrity measurement
                conn.execute('''
                    INSERT INTO mm_learning(
                        pattern, expected, actual, evidence_ref,
                        confidence, recommended_change, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    f"holographic_{local_obs}",
                    "verify_holographic_principle",
                    json.dumps({
                        "local_observation": local_obs,
                        "global_indicators_tested": sufficient_global,
                        "average_prediction_accuracy": avg_prediction_accuracy,
                        "holographic_integrity": avg_prediction_accuracy,
                        "timestamp": now()
                    }),
                    json.dumps({
                        "local_data_points": len(local_data[local_obs]),
                        "global_data_points": [len(global_data[gi]) for gi in sufficient_global],
                        "analysis_method": "local_to_global_prediction"
                    }),
                    0.8,  # Good confidence in holographic principle
                    f"Monitor holographic integrity of {local_obs}",
                    now()
                ))
                conn.commit()

                integrity_results[local_obs] = {
                    "status": "measured",
                    "local_observation": local_obs,
                    "global_indicators_tested": sufficient_global,
                    "average_prediction_accuracy": avg_prediction_accuracy,
                    "holographic_integrity": avg_prediction_accuracy,
                    "confidence": 0.8,
                    "timestamp": now()
                }

        # Calculate overall holographic integrity
        if integrity_results:
            overall_integrity = sum(
                result["holographic_integrity"]
                for result in integrity_results.values()
            ) / len(integrity_results)
        else:
            overall_integrity = 0.0

        return {
            "status": "holographic_integrity_calculated",
            "local_observations_analyzed": len(sufficient_local),
            "global_indicators_analyzed": len(sufficient_global),
            "overall_holographic_integrity": overall_integrity,
            "local_results": integrity_results,
            "timestamp": now()
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to calculate holographic integrity: {str(e)}",
            "holographic_integrity": 0.0,
            "confidence": 0.0
        }

def _get_component_time_series(
    conn: sqlite3.Connection,
    component_name: str,
    hours: int
) -> List[Tuple[str, float]]:
    """Get time series data for a specific component."""
    try:
        # This is a simplified implementation - we'll get data from various sources
        # In practice, this would query component-specific tables or metrics

        # Try to get data from pipeline items related to this component
        cursor = conn.execute('''
            SELECT
                datetime(updated_at, 'unixepoch') as timestamp,
                CASE
                    WHEN state = 'SUCCESS' THEN 100.0
                    WHEN state IN ('RETRYABLE_FAILURE', 'PERMANENT_FAILURE') THEN 0.0
                    ELSE 50.0
                END as value
            FROM pipeline_items
            WHERE updated_at >= datetime('now', '-' || ? || ' hours')
              AND json_extract(observation, '$.component') = ?
            ORDER BY updated_at
        ''', (hours, component_name))

        data = []
        for row in cursor.fetchall():
            if row[1] is not None:
                data.append((row[0], float(row[1])))

        # If we don't have enough data, try to get general performance metrics
        if len(data) < 5:
            cursor = conn.execute('''
                SELECT
                    datetime(calculated_at, 'unixepoch') as timestamp,
                    CAST(json_extract(computed_json, '$.score') AS REAL) as value
                FROM mm_scores
                WHERE calculated_at >= datetime('now', '-' || ? || ' hours')
                  AND json_extract(computed_json, '$.component') = ?
                ORDER BY calculated_at
            ''', (hours, component_name))

            data = []
            for row in cursor.fetchall():
                if row[1] is not None:
                    data.append((row[0], float(row[1])))

        return data

    except Exception:
        return []

def _get_metric_time_series(
    conn: sqlite3.Connection,
    metric_name: str,
    hours: int
) -> List[Tuple[str, float]]:
    """Get time series data for a specific metric."""
    try:
        # Try to get the metric from mm_scores
        cursor = conn.execute('''
            SELECT
                datetime(calculated_at, 'unixepoch') as timestamp,
                CAST(json_extract(computed_json, '$.' || ?) AS REAL) as value
            FROM mm_scores
            WHERE calculated_at >= datetime('now', '-' || ? || ' hours')
              AND json_extract(computed_json, '$.' || ?) IS NOT NULL
            ORDER BY calculated_at
        ''', (metric_name, hours, metric_name))

        data = []
        for row in cursor.fetchall():
            if row[1] is not None:
                data.append((row[0], float(row[1])))

        # If we don't have enough data from mm_scores, try pipeline items
        if len(data) < 5:
            # This is a simplified approach - in practice we'd have better metric tracking
            cursor = conn.execute('''
                SELECT
                    datetime(updated_at, 'unixepoch') as timestamp,
                    CASE
                        WHEN state = 'SUCCESS' THEN 100.0
                        WHEN state IN ('RETRYABLE_FAILURE', 'PERMANENT_FAILURE') THEN 0.0
                        ELSE 50.0
                    END as value
                FROM pipeline_items
                WHERE updated_at >= datetime('now', '-' || ? || ' hours')
                ORDER BY updated_at
            ''', (hours,))

            data = []
            for row in cursor.fetchall():
                if row[1] is not None:
                    data.append((row[0], float(row[1])))

        return data

    except Exception:
        return []

def _align_time_series(
    series_a: List[Tuple[str, float]],
    series_b: List[Tuple[str, float]]
) -> Tuple[List[float], List[float]]:
    """Align two time series by timestamp."""
    try:
        # Convert to dictionaries for easier lookup
        dict_a = {timestamp: value for timestamp, value in series_a}
        dict_b = {timestamp: value for timestamp, value in series_b}

        # Find common timestamps
        common_timestamps = sorted(set(dict_a.keys()) & set(dict_b.keys()))

        # Extract aligned values
        aligned_a = [dict_a[ts] for ts in common_timestamps]
        aligned_b = [dict_b[ts] for ts in common_timestamps]

        return aligned_a, aligned_b

    except Exception:
        return [], []

def _calculate_cross_coherence(
    series_a: List[float],
    series_b: List[float]
) -> Dict[str, float]:
    """Calculate cross-coherence between two time series."""
    try:
        if len(series_a) != len(series_b) or len(series_a) < 2:
            return {
                "coherence": 0.0,
                "phase_sync": 0.0,
                "amplitude_correlation": 0.0,
                "confidence": 0.0
            }

        n = len(series_a)

        # Calculate means
        mean_a = sum(series_a) / n
        mean_b = sum(series_b) / n

        # Calculate covariance and standard deviations
        covariance = sum((series_a[i] - mean_a) * (series_b[i] - mean_b) for i in range(n)) / n
        std_a = math.sqrt(sum((x - mean_a) ** 2 for x in series_a) / n) if n > 0 else 0.0
        std_b = math.sqrt(sum((x - mean_b) ** 2 for x in series_b) / n) if n > 0 else 0.0

        # Calculate correlation coefficient (amplitude correlation)
        if std_a > 0 and std_b > 0:
            amplitude_correlation = covariance / (std_a * std_b)
        else:
            amplitude_correlation = 0.0

        # Calculate phase synchronization using Hilbert transform approximation
        # Simple approach: compare zero-crossings or peak timing
        phase_sync = _calculate_phase_synchronization(series_a, series_b)

        # Overall coherence is combination of amplitude and phase correlation
        coherence = (abs(amplitude_correlation) + phase_sync) / 2

        # Calculate confidence based on data consistency
        # Higher confidence when signals are more consistent
        signal_consistency_a = 1.0 - (std_a / (abs(mean_a) + 1.0)) if mean_a != 0 else 0.5
        signal_consistency_b = 1.0 - (std_b / (abs(mean_b) + 1.0)) if mean_b != 0 else 0.5
        confidence = (signal_consistency_a + signal_consistency_b) / 2
        confidence = max(0.1, min(0.9, confidence))  # Clamp to reasonable range

        return {
            "coherence": max(0.0, min(1.0, coherence)),
            "phase_sync": max(0.0, min(1.0, phase_sync)),
            "amplitude_correlation": max(-1.0, min(1.0, amplitude_correlation)),
            "confidence": confidence
        }

    except Exception:
        return {
            "coherence": 0.0,
            "phase_sync": 0.0,
            "amplitude_correlation": 0.0,
            "confidence": 0.0
        }

def _calculate_phase_synchronization(
    series_a: List[float],
    series_b: List[float]
) -> float:
    """Calculate phase synchronization between two time series."""
    try:
        if len(series_a) < 3 or len(series_b) < 3:
            return 0.0

        # Simple approach: count how often the series cross zero in the same direction
        # or reach peaks at similar times

        # Detect zero crossings for series A
        zero_crossings_a = []
        for i in range(1, len(series_a)):
            if (series_a[i-1] <= 0 and series_a[i] > 0) or (series_a[i-1] >= 0 and series_a[i] < 0):
                zero_crossings_a.append(i)

        # Detect zero crossings for series B
        zero_crossings_b = []
        for i in range(1, len(series_b)):
            if (series_b[i-1] <= 0 and series_b[i] > 0) or (series_b[i-1] >= 0 and series_b[i] < 0):
                zero_crossings_b.append(i)

        # If we have zero crossings, calculate synchronization
        if len(zero_crossings_a) > 0 and len(zero_crossings_b) > 0:
            # For simplicity, compare the timing of zero crossings
            # In a more sophisticated implementation, we'd use Hilbert transforms
            sync_score = 0.0
            comparisons = 0

            # Compare each zero crossing in A with the closest in B
            for zc_a in zero_crossings_a:
                if zero_crossings_b:
                    closest_zc_b = min(zero_crossings_b, key=lambda x: abs(x - zc_a))
                    time_diff = abs(zc_a - closest_zc_b)
                    # Normalize by series length
                    normalized_diff = time_diff / max(len(series_a), len(series_b))
                    # Convert to similarity (closer = higher similarity)
                    similarity = max(0.0, 1.0 - normalized_diff)
                    sync_score += similarity
                    comparisons += 1

            if comparisons > 0:
                phase_sync = sync_score / comparisons
            else:
                phase_sync = 0.0
        else:
            # Fallback: use correlation of derivatives (approximates phase relationship)
            if len(series_a) >= 2 and len(series_b) >= 2:
                # Calculate first differences
                diff_a = [series_a[i+1] - series_a[i] for i in range(len(series_a)-1)]
                diff_b = [series_b[i+1] - series_b[i] for i in range(len(series_b)-1)]

                # Truncate to same length
                min_len = min(len(diff_a), len(diff_b))
                if min_len >= 2:
                    diff_a = diff_a[:min_len]
                    diff_b = diff_b[:min_len]

                    # Calculate correlation of derivatives
                    mean_da = sum(diff_a) / len(diff_a)
                    mean_db = sum(diff_b) / len(diff_b)

                    covariance_d = sum((diff_a[i] - mean_da) * (diff_b[i] - mean_db) for i in range(min_len)) / min_len
                    std_da = math.sqrt(sum((x - mean_da) ** 2 for x in diff_a) / min_len) if min_len > 0 else 0.0
                    std_db = math.sqrt(sum((x - mean_db) ** 2 for x in diff_b) / min_len) if min_len > 0 else 0.0

                    if std_da > 0 and std_db > 0:
                        phase_sync = covariance_d / (std_da * std_db)
                        phase_sync = max(0.0, min(1.0, phase_sync))  # Take absolute value for sync
                    else:
                        phase_sync = 0.0
                else:
                    phase_sync = 0.0
            else:
                phase_sync = 0.0

        return phase_sync

    except Exception:
        return 0.0

def _detect_emergence_from_pair(
    series_a: List[float],
    series_b: List[float],
    metric_a: str,
    metric_b: str
) -> Dict[str, Any]:
    """Detect emergent behavior from a pair of time series."""
    try:
        if len(series_a) < 5 or len(series_b) < 5:
            return {
                "is_emergent": False,
                "emergence_type": "insufficient_data",
                "strength": 0.0,
                "description": "Insufficient data for emergence detection",
                "confidence": 0.0
            }

        # Calculate linear relationship
        n = min(len(series_a), len(series_b))
        if n < 3:
            return {
                "is_emergent": False,
                "emergence_type": "insufficient_data_for_analysis",
                "strength": 0.0,
                "description": "Insufficient aligned data for emergence detection",
                "confidence": 0.0
            }

        # Truncate to same length
        series_a = series_a[:n]
        series_b = series_b[:n]

        # Calculate linear correlation
        mean_a = sum(series_a) / n
        mean_b = sum(series_b) / n

        covariance = sum((series_a[i] - mean_a) * (series_b[i] - mean_b) for i in range(n)) / n
        std_a = math.sqrt(sum((x - mean_a) ** 2 for x in series_a) / n) if n > 0 else 0.0
        std_b = math.sqrt(sum((x - mean_b) ** 2 for x in series_b) / n) if n > 0 else 0.0

        if std_a > 0 and std_b > 0:
            linear_correlation = covariance / (std_a * std_b)
        else:
            linear_correlation = 0.0

        # Calculate nonlinear relationship using mutual information approximation
        # Simple approach: look for patterns where linear correlation is low but there's still structure
        nonlinear_strength = _calculate_nonlinear_structure(series_a, series_b)

        # Emergence detected when:
        # 1. Linear correlation is low (suggesting no simple relationship)
        # 2. But there's significant nonlinear structure (suggesting complex relationship)
        # 3. And the combined behavior shows coherence

        linearity_threshold = 0.3  # Below this, we consider the relationship non-linear
        nonlinearity_threshold = 0.4  # Above this, we consider there to be significant structure

        is_emergent = (
            abs(linear_correlation) < linearity_threshold and
            nonlinear_strength > nonlinearity_threshold
        )

        if is_emergent:
            emergence_type = "nonlinear_coherence"
            strength = nonlinear_strength
            description = f"Nonlinear coherent behavior detected between {metric_a} and {metric_b}"
            confidence = min(0.9, nonlinear_strength * 1.2)  # Scale confidence
        else:
            emergence_type = "no_emergence_detected"
            strength = 0.0
            description = f"No emergent behavior detected between {metric_a} and {metric_b}"
            confidence = 0.3

        return {
            "is_emergent": is_emergent,
            "emergence_type": emergence_type,
            "strength": strength,
            "description": description,
            "confidence": confidence
        }

    except Exception:
        return {
            "is_emergent": False,
            "emergence_type": "error",
            "strength": 0.0,
            "description": f"Error in emergence detection for {metric_a} and {metric_b}",
            "confidence": 0.0
        }

def _calculate_nonlinear_structure(
    series_a: List[float],
    series_b: List[float]
) -> float:
    """Calculate nonlinear structure in the relationship between two series."""
    try:
        if len(series_a) < 4 or len(series_b) < 4:
            return 0.0

        n = min(len(series_a), len(series_b))
        series_a = series_a[:n]
        series_b = series_b[:n]

        # Divide series into bins and look for consistent patterns
        # Simple approach: calculate how much the relationship varies across different ranges

        # Sort by series A values to look at relationship in different regimes
        paired_data = list(zip(series_a, series_b))
        paired_data.sort(key=lambda x: x[0])  # Sort by series A

        sorted_a, sorted_b = zip(*paired_data) if paired_data else ([], [])

        # Split into quarters and calculate correlation in each quarter
        quarter_len = max(1, n // 4)
        correlations = []

        for i in range(0, n, quarter_len):
            end_idx = min(i + quarter_len, n)
            if end_idx - i >= 2:  # Need at least 2 points for correlation
                quarter_a = sorted_a[i:end_idx]
                quarter_b = sorted_b[i:end_idx]

                # Calculate correlation for this quarter
                mean_a = sum(quarter_a) / len(quarter_a)
                mean_b = sum(quarter_b) / len(quarter_b)

                if len(quarter_a) > 1:
                    covariance = sum((quarter_a[j] - mean_a) * (quarter_b[j] - mean_b) for j in range(len(quarter_a))) / len(quarter_a)
                    std_a = math.sqrt(sum((x - mean_a) ** 2 for x in quarter_a) / len(quarter_a)) if len(quarter_a) > 0 else 0.0
                    std_b = math.sqrt(sum((x - mean_b) ** 2 for x in quarter_b) / len(quarter_b)) if len(quarter_b) > 0 else 0.0

                    if std_a > 0 and std_b > 0:
                        quarter_corr = covariance / (std_a * std_b)
                        correlations.append(abs(quarter_corr))  # Use absolute value

        # If we have correlations from different quarters, emergence is suggested by
        # low variance in correlations (consistent relationship) despite low overall linear correlation
        if len(correlations) >= 2:
            mean_corr = sum(correlations) / len(correlations)
            # Variance in correlations - low variance suggests consistent relationship
            corr_variance = sum((c - mean_corr) ** 2 for c in correlations) / len(correlations)
            # Nonlinear structure strength: high when correlation is consistent but not linearly predictable
            nonlinear_structure = mean_corr * (1.0 / (1.0 + corr_variance))  # Inverse variance weighting
            return min(1.0, nonlinear_structure)
        else:
            return 0.0

    except Exception:
        return 0.0

def _detect_system_wide_emergence(
    metrics_data: List[List[Tuple[str, float]]],
    metric_names: List[str]
) -> Dict[str, Any]:
    """Detect system-wide emergent behavior from multiple metrics."""
    try:
        if len(metrics_data) < 3:
            return {
                "is_emergent": False,
                "emergence_type": "insufficient_metrics",
                "strength": 0.0,
                "description": "Insufficient metrics for system-wide emergence detection",
                "confidence": 0.0
            }

        # Align all metrics to the same time points
        # Find the metric with most data points as reference
        reference_idx = max(range(len(metrics_data)), key=lambda i: len(metrics_data[i]))
        reference_data = metrics_data[reference_idx]

        if len(reference_data) < 5:
            return {
                "is_emergent": False,
                "emergence_type": "insufficient_reference_data",
                "strength": 0.0,
                "description": "Insufficient reference data for alignment",
                "confidence": 0.0
            }

        # Align all other metrics to the reference timestamps
        aligned_metrics = []
        aligned_metrics.append([value for timestamp, value in reference_data])  # Reference metric

        for i, metric_data in enumerate(metrics_data):
            if i == reference_idx:
                continue  # Skip reference metric as it's already added

            # Create dict for easy lookup
            metric_dict = {timestamp: value for timestamp, value in metric_data}

            # Extract values at reference timestamps
            aligned_values = []
            for timestamp, _ in reference_data:
                if timestamp in metric_dict:
                    aligned_values.append(metric_dict[timestamp])
                else:
                    # If timestamp not found, interpolate or skip
                    # For simplicity, we'll skip this alignment point
                    pass

            # Only keep if we have enough aligned points
            if len(aligned_values) >= 3:
                aligned_metrics.append(aligned_values)

        if len(aligned_metrics) < 2:
            return {
                "is_emergent": False,
                "emergence_type": "insufficient_aligned_data",
                "strength": 0.0,
                "description": "Insufficient aligned data for system-wide analysis",
                "confidence": 0.0
            }

        # Transpose to get time series for each metric
        min_length = min(len(metric_series) for metric_series in aligned_metrics)
        if min_length < 3:
            return {
                "is_emergent": False,
                "emergence_type": "insufficient_aligned_length",
                "strength": 0.0,
                "description": "Insufficient aligned time points for analysis",
                "confidence": 0.0
            }

        # Truncate all series to same length
        truncated_metrics = [series[:min_length] for series in aligned_metrics]

        # Calculate system coherence: how much do all metrics move together?
        # Approach: calculate average pairwise correlation
        pairwise_correlations = []

        for i in range(len(truncated_metrics)):
            for j in range(i+1, len(truncated_metrics)):
                series_i = truncated_metrics[i]
                series_j = truncated_metrics[j]

                # Calculate correlation
                n = len(series_i)
                if n >= 2:
                    mean_i = sum(series_i) / n
                    mean_j = sum(series_j) / n

                    if n > 1:
                        covariance = sum((series_i[k] - mean_i) * (series_j[k] - mean_j) for k in range(n)) / n
                        std_i = math.sqrt(sum((x - mean_i) ** 2 for x in series_i) / n) if n > 0 else 0.0
                        std_j = math.sqrt(sum((x - mean_j) ** 2 for x in series_j) / n) if n > 0 else 0.0

                        if std_i > 0 and std_j > 0:
                            correlation = covariance / (std_i * std_j)
                            pairwise_correlations.append(abs(correlation))  # Use absolute value

        if pairwise_correlations:
            average_coherence = sum(pairwise_correlations) / len(pairwise_correlations)

            # System-wide emergence is detected when:
            # 1. Average coherence is moderate (not too high, not too low)
            # 2. But there's complexity in the relationships (measured by variance in pairwise correlations)
            coherence_variance = sum((c - average_coherence) ** 2 for c in pairwise_correlations) / len(pairwise_correlations) if pairwise_correlations else 0.0

            # Emergence strength: moderate coherence with high variance suggests complex, emergent behavior
            emergence_strength = average_coherence * (1.0 + coherence_variance)  # Boost by variance
            emergence_strength = min(1.0, emergence_strength)  # Cap at 1.0

            is_emergent = (
                average_coherence > 0.3 and  # Not random noise
                average_coherence < 0.8 and  # Not perfectly synchronized (would be trivial)
                coherence_variance > 0.02   # Some variation in relationships
            )

            if is_emergent:
                emergence_type = "system_wide_coherent_complexity"
                strength = emergence_strength
                description = f"System-wide emergent coherent complexity detected across {len(truncated_metrics)} metrics"
                confidence = min(0.85, emergence_strength * 1.1)
            else:
                emergence_type = "no_system_wide_emergence"
                strength = 0.0
                description = f"No system-wide emergent behavior detected"
                confidence = 0.4

            return {
                "is_emergent": is_emergent,
                "emergence_type": emergence_type,
                "strength": strength,
                "description": description,
                "confidence": confidence
            }
        else:
            return {
                "is_emergent": False,
                "emergence_type": "insufficient_pairwise_data",
                "strength": 0.0,
                "description": "Insufficient pairwise correlation data for system-wide analysis",
                "confidence": 0.0
            }

    except Exception:
        return {
            "is_emergent": False,
            "emergence_type": "error",
            "strength": 0.0,
            "description": "Error in system-wide emergence detection",
            "confidence": 0.0
        }

def _calculate_prediction_accuracy(
    local_series: List[float],
    global_series: List[float]
) -> float:
    """Calculate how well local series predicts global series."""
    try:
        if len(local_series) < 3 or len(global_series) < 3:
            return 0.0

        # Use simple linear prediction: predict next point based on previous points
        # For simplicity, we'll calculate how well local correlates with global
        # (In a more sophisticated version, we'd do actual prediction)

        n = min(len(local_series), len(global_series))
        if n < 2:
            return 0.0

        local_series = local_series[:n]
        global_series = global_series[:n]

        # Calculate correlation
        mean_local = sum(local_series) / n
        mean_global = sum(global_series) / n

        if n > 1:
            covariance = sum((local_series[i] - mean_local) * (global_series[i] - mean_global) for i in range(n)) / n
            std_local = math.sqrt(sum((x - mean_local) ** 2 for x in local_series) / n) if n > 0 else 0.0
            std_global = math.sqrt(sum((x - mean_global) ** 2 for x in global_series) / n) if n > 0 else 0.0

            if std_local > 0 and std_global > 0:
                correlation = covariance / (std_local * std_global)
                # Return absolute value of correlation as prediction accuracy
                return abs(correlation)
            else:
                return 0.0
        else:
            return 0.0

    except Exception:
        return 0.0

# Export functions for easy importing
__all__ = [
    "measure_cross_component_coherence",
    "detect_emergent_behaviors",
    "calculate_holographic_integrity"
]
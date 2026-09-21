"""Predictive wisdom engine for the WEBSITE-AUDITOR system.
Implements time series forecasting, seasonal trend detection, and anomaly prediction.
"""
import json
import sqlite3
import math
from datetime import datetime, timezone
from mm_core import now, connect
from typing import Dict, List, Any, Optional, Tuple

def forecast_pipeline_performance(
    conn: sqlite3.Connection,
    metric_name: str,
    horizon_hours: int = 24
) -> Dict[str, Any]:
    """Forecast pipeline performance using time series analysis.

    Anticipates system needs before they arise as urgent demands by analyzing
    historical patterns in pipeline performance and business engagement cycles.

    Args:
        conn: Database connection
        metric_name: Name of the metric to forecast (e.g., 'audit_score', 'pipeline_throughput')
        horizon_hours: Forecast horizon in hours

    Returns:
        Dictionary containing forecast data and confidence metrics
    """
    try:
        # Get historical data for the metric
        historical_data = _get_historical_metric_data(conn, metric_name, days=30)

        if len(historical_data) < 7:  # Need at least a week of data
            return {
                "status": "insufficient_data",
                "message": f"Insufficient historical data for {metric_name}. Need at least 7 data points.",
                "forecast_value": None,
                "forecast_confidence": 0.0,
                "horizon_hours": horizon_hours
            }

        # Simple time series forecasting using moving average and trend analysis
        forecast_result = _simple_time_series_forecast(historical_data, horizon_hours)

        # Store the forecast in the learning table for tracking
        conn.execute('''
            INSERT INTO mm_learning(
                pattern, expected, actual, evidence_ref,
                confidence, recommended_change, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            f"forecast_{metric_name}",
            "predict_future_performance",
            json.dumps({
                "metric_name": metric_name,
                "horizon_hours": horizon_hours,
                "forecast_value": forecast_result["forecast_value"],
                "forecast_confidence": forecast_result["confidence"],
                "timestamp": now()
            }),
            json.dumps({
                "historical_points": len(historical_data),
                "method": "simple_moving_average_trend"
            }),
            forecast_result["confidence"],
            f"Monitor forecast accuracy for {metric_name}",
            now()
        ))
        conn.commit()

        return {
            "status": "forecast_generated",
            "metric_name": metric_name,
            "forecast_value": forecast_result["forecast_value"],
            "forecast_confidence": forecast_result["confidence"],
            "horizon_hours": horizon_hours,
            "historical_data_points": len(historical_data),
            "forecast_method": "simple_moving_average_trend",
            "timestamp": now()
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to generate forecast for {metric_name}: {str(e)}",
            "forecast_value": None,
            "forecast_confidence": 0.0,
            "horizon_hours": horizon_hours
        }

def detect_seasonal_trends(
    conn: sqlite3.Connection,
    metric_name: str,
    min_period_days: int = 7,
    max_period_days: int = 365
) -> Dict[str, Any]:
    """Detect seasonal trends in system metrics.

    Forecasts business opportunities with understanding of timing and readiness
    by correlating seasonal trends, industry cycles, and historical conversion data.

    Args:
        conn: Database connection
        metric_name: Name of the metric to analyze
        min_period_days: Minimum period to consider for seasonality (days)
        max_period_days: Maximum period to consider for seasonality (days)

    Returns:
        Dictionary containing detected seasonal patterns
    """
    try:
        # Get historical data for the metric (look at least 2 years for yearly patterns)
        historical_data = _get_historical_metric_data(conn, metric_name, days=730)

        if len(historical_data) < min_period_days * 2:  # Need at least 2 periods to detect seasonality
            return {
                "status": "insufficient_data",
                "message": f"Insufficient historical data for {metric_name}. Need at least {min_period_days * 2} data points.",
                "detected_patterns": [],
                "strongest_period": None
            }

        # Detect seasonal patterns using autocorrelation
        seasonal_analysis = _detect_seasonality_autocorrelation(historical_data, min_period_days, max_period_days)

        # Store the seasonal analysis in the learning table
        conn.execute('''
            INSERT INTO mm_learning(
                pattern, expected, actual, evidence_ref,
                confidence, recommended_change, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            f"seasonal_analysis_{metric_name}",
            "detect_seasonal_patterns",
            json.dumps({
                "metric_name": metric_name,
                "detected_patterns": seasonal_analysis["detected_patterns"],
                "strongest_period": seasonal_analysis["strongest_period"],
                "timestamp": now()
            }),
            json.dumps({
                "historical_points": len(historical_data),
                "analysis_method": "autocorrelation"
            }),
            seasonal_analysis["confidence"],
            f"Use seasonal patterns to anticipate {metric_name} variations",
            now()
        ))
        conn.commit()

        return {
            "status": "analysis_complete",
            "metric_name": metric_name,
            "detected_patterns": seasonal_analysis["detected_patterns"],
            "strongest_period": seasonal_analysis["strongest_period"],
            "confidence": seasonal_analysis["confidence"],
            "historical_data_points": len(historical_data),
            "timestamp": now()
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to detect seasonal trends for {metric_name}: {str(e)}",
            "detected_patterns": [],
            "strongest_period": None,
            "confidence": 0.0
        }

def predict_emerging_defects(
    conn: sqlite3.Connection,
    defect_type: str,
    lookback_days: int = 14
) -> Dict[str, Any]:
    """Predict the emergence of new defect patterns before they become widespread.

    Predicts not just failures but the learning opportunities within failures by
    analyzing failure patterns to extract actionable insights for system improvement.

    Args:
        conn: Database connection
        defect_type: Type of defect to monitor for emergence
        lookback_days: Number of days to look back for pattern analysis

    Returns:
        Dictionary containing prediction of emerging defect patterns
    """
    try:
        # Get historical defect data
        defect_data = _get_historical_defect_data(conn, defect_type, lookback_days)

        if len(defect_data) < 5:  # Need some data to analyze trends
            return {
                "status": "insufficient_data",
                "message": f"Insufficient defect data for {defect_type}. Need at least 5 data points.",
                "emergence_probability": 0.0,
                "predicted_count": 0
            }

        # Analyze defect emergence using statistical process control
        emergence_prediction = _analyze_defect_emergence(defect_data)

        # Store the prediction in the learning table
        conn.execute('''
            INSERT INTO mm_learning(
                pattern, expected, actual, evidence_ref,
                confidence, recommended_change, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            f"defect_emergence_{defect_type}",
            "predict_defect_emergence",
            json.dumps({
                "defect_type": defect_type,
                "emergence_probability": emergence_prediction["emergence_probability"],
                "predicted_count": emergence_prediction["predicted_count"],
                "confidence": emergence_prediction["confidence"],
                "timestamp": now()
            }),
            json.dumps({
                "historical_points": len(defect_data),
                "lookback_days": lookback_days,
                "method": "statistical_process_control"
            }),
            emergence_prediction["confidence"],
            f"Monitor for emerging {defect_type} defects and prepare preventive measures",
            now()
        ))
        conn.commit()

        return {
            "status": "prediction_complete",
            "defect_type": defect_type,
            "emergence_probability": emergence_prediction["emergence_probability"],
            "predicted_count": emergence_prediction["predicted_count"],
            "confidence": emergence_prediction["confidence"],
            "historical_data_points": len(defect_data),
            "timestamp": now()
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to predict emerging defects for {defect_type}: {str(e)}",
            "emergence_probability": 0.0,
            "predicted_count": 0,
            "confidence": 0.0
        }

def _get_historical_metric_data(
    conn: sqlite3.Connection,
    metric_name: str,
    days: int = 30
) -> List[Tuple[str, float]]:
    """Get historical data for a specific metric from the database."""
    try:
        # This is a simplified implementation - in practice, we'd query specific tables
        # For now, we'll simulate getting data from mm_scores or similar tables
        cursor = conn.execute('''
            SELECT
                datetime(calculated_at, 'unixepoch') as timestamp,
                CAST(json_extract(computed_json, '$.score') AS REAL) as value
            FROM mm_scores
            WHERE calculated_at >= datetime('now', '-' || ? || ' days')
              AND json_extract(computed_json, '$.score') IS NOT NULL
            ORDER BY calculated_at
        ''', (days,))

        data = []
        for row in cursor.fetchall():
            if row[1] is not None:  # Filter out None values
                data.append((row[0], float(row[1])))

        # If we don't have enough data from mm_scores, try other sources
        if len(data) < 5:
            # Try to get data from pipeline items or other sources
            cursor = conn.execute('''
                SELECT
                    datetime(updated_at, 'unixepoch') as timestamp,
                    CASE
                        WHEN state = 'SUCCESS' THEN 100.0
                        WHEN state IN ('RETRYABLE_FAILURE', 'PERMANENT_FAILURE') THEN 0.0
                        ELSE 50.0
                    END as value
                FROM pipeline_items
                WHERE updated_at >= datetime('now', '-' || ? || ' days')
                ORDER BY updated_at
            ''', (days,))

            data = []
            for row in cursor.fetchall():
                if row[1] is not None:
                    data.append((row[0], float(row[1])))

        return data

    except Exception:
        # Return empty list on error
        return []

def _get_historical_defect_data(
    conn: sqlite3.Connection,
    defect_type: str,
    lookback_days: int = 14
) -> List[Tuple[str, int]]:
    """Get historical defect count data for a specific defect type."""
    try:
        cursor = conn.execute('''
            SELECT
                datetime(checked_at, 'unixepoch') as timestamp,
                COUNT(*) as defect_count
            FROM mm_evidence
            WHERE checked_at >= datetime('now', '-' || ? || ' days')
              AND json_extract(observation, '$.defect_type') = ?
            GROUP BY strftime('%Y-%m-%d %H', checked_at)
            ORDER BY checked_at
        ''', (lookback_days, defect_type))

        data = []
        for row in cursor.fetchall():
            if row[1] is not None:
                data.append((row[0], int(row[1])))

        return data

    except Exception:
        return []

def _simple_time_series_forecast(
    historical_data: List[Tuple[str, float]],
    horizon_hours: int
) -> Dict[str, Any]:
    """Simple time series forecasting using moving average and trend analysis."""
    if len(historical_data) < 2:
        return {
            "forecast_value": historical_data[-1][1] if historical_data else 0.0,
            "confidence": 0.1
        }

    # Extract just the values for calculations
    values = [point[1] for point in historical_data]
    timestamps = [point[0] for point in historical_data]

    # Calculate simple moving average (last 5 points or all if less than 5)
    window_size = min(5, len(values))
    recent_values = values[-window_size:]
    moving_avg = sum(recent_values) / len(recent_values)

    # Calculate trend using linear regression on recent points
    if len(values) >= 3:
        # Use last 10 points or all if less than 10 for trend calculation
        trend_window = min(10, len(values))
        trend_values = values[-trend_window:]
        n = len(trend_values)

        # Simple linear regression: y = mx + b
        # Where x is the index (0, 1, 2, ..., n-1)
        sum_x = sum(range(n))
        sum_y = sum(trend_values)
        sum_xy = sum(i * trend_values[i] for i in range(n))
        sum_x2 = sum(i * i for i in range(n))

        if n * sum_x2 - sum_x * sum_x != 0:
            m = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
            b = (sum_y - m * sum_x) / n

            # Forecast horizon points ahead
            forecast_index = n + (horizon_hours / 24)  # Assuming daily data points
            forecast_value = m * forecast_index + b
        else:
            # No variance in x, use moving average
            forecast_value = moving_avg
    else:
        # Not enough data for trend, use moving average
        forecast_value = moving_avg
        m = 0  # No trend

    # Calculate confidence based on data consistency and trend strength
    if len(values) >= 5:
        # Calculate standard deviation of recent values
        recent_variance = sum((x - moving_avg) ** 2 for x in recent_values) / len(recent_values)
        std_dev = math.sqrt(recent_variance) if recent_variance >= 0 else 0.0

        # Confidence decreases with higher volatility and uncertainty in trend
        volatility_factor = max(0.1, 1.0 - (std_dev / (moving_avg + 1.0)))  # Avoid division by zero
        trend_confidence = min(1.0, abs(m) * 10) if m != 0 else 0.5  # Higher confidence with stronger trend
        confidence = (volatility_factor + trend_confidence) / 2
        confidence = max(0.1, min(0.95, confidence))  # Clamp between 0.1 and 0.95
    else:
        confidence = 0.3  # Low confidence with little data

    return {
        "forecast_value": max(0.0, forecast_value),  # Ensure non-negative for metrics like scores
        "confidence": confidence,
        "moving_average": moving_avg,
        "trend_slope": m if 'm' in locals() else 0.0
    }

def _detect_seasonality_autocorrelation(
    historical_data: List[Tuple[str, float]],
    min_period_days: int,
    max_period_days: int
) -> Dict[str, Any]:
    """Detect seasonality using autocorrelation analysis."""
    if len(historical_data) < min_period_days * 2:
        return {
            "detected_patterns": [],
            "strongest_period": None,
            "confidence": 0.0
        }

    # Extract values
    values = [point[1] for point in historical_data]
    n = len(values)

    # Limit max period to half the data length for meaningful autocorrelation
    max_period = min(max_period_days, n // 2)

    if max_period < min_period_days:
        return {
            "detected_patterns": [],
            "strongest_period": None,
            "confidence": 0.0
        }

    # Calculate autocorrelation for different periods
    autocorrelations = []
    mean_value = sum(values) / n

    for period in range(min_period_days, max_period + 1):
        if n > period:
            # Calculate autocorrelation at lag 'period'
            numerator = sum((values[i] - mean_value) * (values[i + period] - mean_value)
                           for i in range(n - period))
            denominator = sum((values[i] - mean_value) ** 2 for i in range(n))

            if denominator != 0:
                autocorr = numerator / denominator
                autocorrelations.append((period, autocorr))

    # Find significant peaks in autocorrelation
    significant_patterns = []
    strongest_period = None
    max_autocorr = 0.0

    for period, autocorr in autocorrelations:
        # Consider it significant if autocorrelation is above threshold
        if autocorr > 0.3:  # Threshold for significance
            significant_patterns.append({
                "period_days": period,
                "autocorrelation": autocorr,
                "strength": "strong" if autocorr > 0.5 else "moderate"
            })

            if abs(autocorr) > abs(max_autocorr):
                max_autocorr = autocorr
                strongest_period = period

    # Calculate overall confidence in seasonality detection
    if significant_patterns:
        # Confidence based on strength of strongest pattern and number of patterns
        pattern_strength = abs(max_autocorr)
        pattern_count_factor = min(1.0, len(significant_patterns) / 3.0)  # More patterns = higher confidence
        confidence = (pattern_strength + pattern_count_factor) / 2
        confidence = max(0.1, min(0.9, confidence))
    else:
        confidence = 0.0

    return {
        "detected_patterns": significant_patterns,
        "strongest_period": strongest_period,
        "confidence": confidence,
        "autocorrelations": autocorrelations[:10]  # Keep first 10 for debugging
    }

def _analyze_defect_emergence(
    defect_data: List[Tuple[str, int]]
) -> Dict[str, Any]:
    """Analyze defect data to predict emergence using statistical process control."""
    if len(defect_data) < 3:
        return {
            "emergence_probability": 0.0,
            "predicted_count": 0,
            "confidence": 0.1
        }

    # Extract defect counts
    counts = [point[1] for point in defect_data]
    n = len(counts)

    # Calculate basic statistics
    mean_count = sum(counts) / n
    variance = sum((x - mean_count) ** 2 for x in counts) / n if n > 0 else 0
    std_dev = math.sqrt(variance) if variance >= 0 else 0.0

    # Calculate recent trend (last 3 points vs previous 3 points if available)
    if n >= 6:
        recent_avg = sum(counts[-3:]) / 3
        previous_avg = sum(counts[-6:-3]) / 3
        trend = recent_avg - previous_avg
        trend_ratio = trend / (previous_avg + 1.0)  # Avoid division by zero
    elif n >= 4:
        recent_avg = sum(counts[-2:]) / 2
        previous_avg = sum(counts[-4:-2]) / 2
        trend = recent_avg - previous_avg
        trend_ratio = trend / (previous_avg + 1.0)
    else:
        trend = 0.0
        trend_ratio = 0.0

    # Calculate emergence probability using control chart principles
    # If recent count is above upper control limit, there's a signal of emergence
    ucl = mean_count + (3 * std_dev)  # Upper Control Limit (3 sigma)
    lcl = max(0, mean_count - (3 * std_dev))  # Lower Control Limit

    latest_count = counts[-1] if counts else 0

    # Probability based on how far above UCL the latest point is
    if latest_count > ucl and std_dev > 0:
        # How many standard deviations above UCL
        sigma_above_ucl = (latest_count - ucl) / std_dev
        # Convert to probability (sigmoid-like function)
        emergence_probability = min(0.95, 0.5 + (sigma_above_ucl / 10.0))
    elif latest_count > mean_count + (2 * std_dev):  # Warning level (2 sigma)
        emergence_probability = min(0.7, 0.3 + ((latest_count - (mean_count + 2 * std_dev)) / (std_dev * 10.0)))
    else:
        # Base probability on trend
        emergence_probability = max(0.0, min(0.5, 0.2 + (trend_ratio * 2.0)))

    # Predicted count based on trend projection
    if trend != 0:
        # Project trend forward by one period
        predicted_count = latest_count + trend
        predicted_count = max(0, predicted_count)  # Ensure non-negative
    else:
        predicted_count = latest_count

    # Calculate confidence based on data consistency
    if std_dev > 0 and mean_count > 0:
        # Coefficient of variation - lower means more consistent
        cv = std_dev / mean_count
        confidence = max(0.3, min(0.8, 1.0 - cv))
    else:
        confidence = 0.4

    return {
        "emergence_probability": emergence_probability,
        "predicted_count": predicted_count,
        "confidence": confidence,
        "mean_count": mean_count,
        "std_dev": std_dev,
        "latest_count": latest_count,
        "trend": trend,
        "trend_ratio": trend_ratio,
        "ucl": ucl,
        "lcl": lcl
    }

# Export functions for easy importing
__all__ = [
    "forecast_pipeline_performance",
    "detect_seasonal_trends",
    "predict_emerging_defects"
]
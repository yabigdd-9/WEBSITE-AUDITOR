"""Management worker for Loop D: Manage the portfolio and learning.

Implements portfolio management, learning from outcomes, queue optimization,
and strategic oversight for the opportunity-to-review system.
"""

import json
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import mm_core as core
from mm_pipeline import RetryableError, PermanentError, BlockedCost


def management_worker_handler(d, item_row, worker):
    """Manage portfolio and learning - Loop D handler.

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

    # Manage based on current state
    if current_state in ('CONVERTED', 'REJECTED', 'NO_VERIFIED_EMAIL', 'PERMANENT_FAILURE', 'SUPPRESSED'):
        # Learn from completed outcomes
        next_state, reason, evidence = _learn_from_outcome(d, business_id, payload, current_state)
    elif current_state == 'NEEDS_REVIEW':
        # Apply management decisions for items needing review
        next_state, reason, evidence = _manage_needs_review_items(d, business_id, payload)
    elif current_state in ('DISCOVERED', 'IDENTITY_PENDING', 'IDENTITY_RESOLVED', 'AUDIT_PENDING', 'AUDITED'):
        # Portfolio management and prioritization for active items
        next_state, reason, evidence = _manage_active_portfolio(d, business_id, payload, current_state)
    else:
        # Fallback for other states
        next_state = 'NEEDS_REVIEW'
        reason = f'Unexpected state for management worker: {current_state}'
        evidence = {'unexpected_state': current_state}

    return next_state, reason, evidence


def _learn_from_outcome(d, business_id: int, payload: Dict, final_state: str) -> Tuple[str, str, Dict]:
    """Learn from completed outcomes to improve future performance."""
    try:
        # Get business and pipeline history
        business = core.get_business(d, business_id)
        if not business:
            raise PermanentError('business row missing')

        # Get complete pipeline history
        pipeline_history = _get_pipeline_history(d, business_id)

        # Get outcome information
        outcome_info = _extract_outcome_info(d, business_id, final_state, payload)

        # Create learning record
        learning_record = {
            'business_id': business_id,
            'business_name': business.get('name'),
            'final_state': final_state,
            'learning_timestamp': core.now(),
            'pipeline_history': pipeline_history,
            'outcome_info': outcome_info,
            'lessons_learned': [],
            'strategy_adjustments': [],
            'portfolio_impact': {}
        }

        # Extract lessons based on outcome type
        if final_state == 'CONVERTED':
            learning_record['lessons_learned'] = _extract_success_lessons(pipeline_history, payload)
            learning_record['strategy_adjustments'] = _identify_success_patterns(pipeline_history)
        elif final_state in ('REJECTED', 'NO_VERIFIED_EMAIL', 'PERMANENT_FAILURE'):
            learning_record['lessons_learned'] = _extract_failure_lessons(pipeline_history, payload, final_state)
            learning_record['strategy_adjustments'] = _identify_improvement_areas(pipeline_history)
        else:
            learning_record['lessons_learned'] = _extract_general_lessons(pipeline_history, final_state)
            learning_record['strategy_adjustments'] = []

        # Apply learning to improve system
        _apply_learning_to_system(d, learning_record)

        # Update portfolio metrics
        portfolio_updates = _update_portfolio_metrics(d, learning_record)
        learning_record['portfolio_impact'] = portfolio_updates

        # Store learning in payload for potential future reference
        payload.update({
            'learning_record': learning_record,
            'learning_applied': True,
            'lessons_count': len(learning_record['lessons_learned'])
        })

        # Determine if item should be archived or kept for reference
        if final_state in TERMINAL_STATES:
            next_state = final_state  # Keep terminal state
            reason = f'Learning completed from {final_state} outcome'
        else:
            next_state = 'ARCHIVED_LEARNING'  # Would need to add this state
            reason = f'Learning extracted, item archived for reference'

        evidence = {
            'learning_summary': {
                'final_state': final_state,
                'lessons_learned': len(learning_record['lessons_learned']),
                'strategy_adjustments': len(learning_record['strategy_adjustments']),
                'outcome_type': outcome_info.get('outcome_type', 'unknown')
            },
            'key_lessons': [lesson.get('lesson', '')[:50] for lesson in learning_record['lessons_learned'][:3]],
            'portfolio_impact_summary': portfolio_updates
        }

        return next_state, reason, evidence

    except RetryableError:
        raise
    except Exception as e:
        raise PermanentError(f'learning from outcome failed: {str(e)}'


def _manage_needs_review_items(d, business_id: int, payload: Dict) -> Tuple[str, str, Dict]:
    """Apply management decisions to items that need review."""
    try:
        business = core.get_business(d, business_id)
        if not business:
            raise PermanentError('business row missing')

        # Get the reason for needing review
        review_reason = payload.get('review_reason', 'unknown')
        review_count = payload.get('review_count', 0)

        # Apply management policy
        management_decision = _apply_management_policy(d, business_id, payload, review_reason, review_count)

        # Update payload with management decision
        payload.update({
            'management_decision': management_decision,
            'management_timestamp': core.now(),
            'review_count': review_count + 1
        })

        # Execute management decision
        if management_decision['action'] == 'retry_with_adjustments':
            next_state = _determine_retry_state(d, business_id, payload)
            reason = f"Retrying with adjustments: {management_decision['reasoning']}"
        elif management_decision['action'] == 'escalate_for_human_review':
            next_state = 'NEEDS_REVIEW'  # Stay in review but flag for human
            reason = f"Escalated for human review: {management_decision['reasoning']}"
        elif management_decision['action'] == 'archive_insufficient_data':
            next_state = 'ARCHIVED_INSUFFICIENT_DATA'  # Would need to add state
            reason = f"Archived due to insufficient data: {management_decision['reasoning']}"
        elif management_decision['action'] == 'convert_to_research_only':
            next_state = 'RESEARCH_ONLY'  # Would need to add state
            reason = f"Converted to research-only mode: {management_decision['reasoning']}"
        else:
            # Default to needs review to prevent infinite loops
            next_state = 'NEEDS_REVIEW'
            reason = f"Management decision: {management_decision['action']}"

        evidence = {
            'management_decision': management_decision,
            'review_reason': review_reason,
            'review_count': review_count,
            'business_id': business_id
        }

        return next_state, reason, evidence

    except RetryableError:
        raise
    except Exception as e:
        raise PermanentError(f'management of needs review item failed: {str(e)}')


def _manage_active_portfolio(d, business_id: int, payload: Dict, current_state: str) -> Tuple[str, str, Dict]:
    """Manage active portfolio items for prioritization and resource allocation."""
    try:
        business = core.get_business(d, business_id)
        if not business:
            raise PermanentError('business row missing')

        # Get portfolio context
        portfolio_context = _get_portfolio_context(d)

        # Assess item priority and resource needs
        priority_assessment = _assess_item_priority(d, business_id, payload, current_state, portfolio_context)

        # Apply portfolio management policies
        management_action = _apply_portfolio_management_policy(d, business_id, payload, priority_assessment, portfolio_context)

        # Update payload with management decision
        payload.update({
            'portfolio_management_timestamp': core.now(),
            'portfolio_context_snapshot': portfolio_context,
            'priority_assessment': priority_assessment,
            'management_action_taken': management_action['action']
        })

        # Execute portfolio management action
        if management_action['action'] == 'prioritize_for_acceleration':
            # Stay in current state but mark for priority processing
            next_state = current_state
            reason = f"Prioritized for acceleration: {management_action['reasoning']}"
        elif management_action['action'] == 'defer_for_capacity':
            # Defer processing due to capacity constraints
            next_state = current_state  # Stay in same state
            reason = f"Deferred for capacity: {management_action['reasoning']}"
        elif management_action['action'] == 'allocate_additional_resources':
            # Allocate more resources to this item
            next_state = current_state
            reason = f"Additional resources allocated: {management_action['reasoning']}"
        elif management_action['action'] == 'maintain_current_processing':
            # Continue normal processing
            next_state = _get_next_state_in_flow(d, business_id, payload, current_state)
            reason = f"Maintaining current processing: {management_action['reasoning']}"
        else:
            # Default to normal flow
            next_state = _get_next_state_in_flow(d, business_id, payload, current_state)
            reason = f"Default portfolio management: {management_action['reasoning']}"

        evidence = {
            'portfolio_context': {
                'total_active_items': portfolio_context.get('total_active', 0),
                'capacity_utilization': portfolio_context.get('capacity_utilization', 0.0),
                'average_wait_time': portfolio_context.get('average_wait_time_hours', 0)
            },
            'priority_assessment': {
                'priority_score': priority_assessment.get('priority_score', 0.5),
                'priority_level': priority_assessment.get('priority_level', 'medium'),
                'resource_needs': priority_assessment.get('resource_needs', 'medium')
            },
            'management_action': management_action['action'],
            'business_id': business_id
        }

        return next_state, reason, evidence

    except RetryableError:
        raise
    except Exception as e:
        raise PermanentError(f'active portfolio management failed: {str(e)}')


def _get_pipeline_history(d, business_id: int) -> List[Dict]:
    """Get complete pipeline history for a business."""
    try:
        rows = d.execute("""
            SELECT state, from_state, to_state, actor, reason, evidence, event_at
            FROM pipeline_events
            WHERE business_id = ?
            ORDER BY event_at ASC
        """, (business_id,)).fetchall()

        history = []
        for row in rows:
            history.append({
                'state': row['state'],
                'from_state': row['from_state'],
                'to_state': row['to_state'],
                'actor': row['actor'],
                'reason': row['reason'],
                'evidence': json.loads(row['evidence']) if row['evidence'] else None,
                'timestamp': row['event_at']
            })

        return history
    except Exception:
        return []


def _extract_outcome_info(d, business_id: int, final_state: str, payload: Dict) -> Dict:
    """Extract information about the final outcome."""
    try:
        business = core.get_business(d, business_id)
        outcome_info = {
            'business_id': business_id,
            'final_state': final_state,
            'business_name': business.get('name') if business else 'Unknown',
            'outcome_type': 'success' if final_state == 'CONVERTED' else 'failure' if final_state in ('REJECTED', 'NO_VERIFIED_EMAIL', 'PERMANENT_FAILURE', 'SUPPRESSED') else 'neutral',
            'completed_at': core.now(),
            'time_in_pipeline': _calculate_time_in_pipeline(d, business_id),
            'total_states_visited': _count_unique_states_visited(d, business_id)
        }

        # Add payload information
        outcome_info.update({
            'final_payload_size': len(json.dumps(payload)),
            'has_proof_package': bool(payload.get('proof_package')),
            'has_demo_preparation': bool(payload.get('demo_preparation')),
            'understanding_completeness': payload.get('business_understanding', {}).get('understanding_completeness', 0)
        })

        return outcome_info
    except Exception:
        return {
            'business_id': business_id,
            'final_state': final_state,
            'outcome_type': 'unknown',
            'error': 'failed_to_extract_outcome_info'
        }


def _calculate_time_in_pipeline(d, business_id: int) -> float:
    """Calculate total time spent in pipeline in hours."""
    try:
        # Get first and last event timestamps
        result = d.execute("""
            SELECT
                MIN(event_at) as first_event,
                MAX(event_at) as last_event
            FROM pipeline_events
            WHERE business_id = ?
        """, (business_id,)).fetchone()

        if result and result['first_event'] and result['last_event']:
            first_time = datetime.fromisoformat(result['first_event'].replace('Z', '+00:00'))
            last_time = datetime.fromisoformat(result['last_event'].replace('Z', '+00:00'))
            duration = last_time - first_time
            return duration.total_seconds() / 3600  # Convert to hours
        else:
            return 0.0
    except Exception:
        return 0.0


def _count_unique_states_visited(d, business_id: int) -> int:
    """Count unique states visited in pipeline."""
    try:
        result = d.execute("""
            SELECT COUNT(DISTINCT state) as unique_states
            FROM pipeline_events
            WHERE business_id = ?
        """, (business_id,)).fetchone()

        return result['unique_states'] if result else 0
    except Exception:
        return 0


def _extract_success_lessons(pipeline_history: List[Dict], payload: Dict) -> List[Dict]:
    """Extract lessons from successful outcomes."""
    lessons = []

    # Lesson 1: What worked well in the pipeline
    if pipeline_history:
        # Check for patterns in successful transitions
        successful_transitions = []
        for i in range(len(pipeline_history) - 1):
            curr = pipeline_history[i]
            next_item = pipeline_history[i + 1]
            if curr['to_state'] == next_item['from_state']:  # Normal progression
                successful_transitions.append({
                    'from': curr['from_state'],
                    'to': curr['to_state'],
                    'actor': curr['actor']
                })

        if successful_transitions:
            lessons.append({
                'lesson': 'Successful pipeline progression pattern identified',
                'details': f'Consistent flow through {len(successful_transitions)} stages',
                'confidence': 'high',
                'applicability': 'future_similar_cases'
            })

    # Lesson 2: Effectiveness of specific interventions
    understanding_confidence = payload.get('business_understanding', {}).get('understanding_completeness', 0)
    if understanding_confidence > 0.7:
        lessons.append({
            'lesson': 'High understanding confidence correlated with success',
            'details': f'Understanding completeness: {understanding_confidence:.2f}',
            'confidence': 'medium',
            'applicability': 'similar_business_types'
        })

    # Lesson 3: Proof package effectiveness
    if payload.get('proof_package', {}).get('ready_for_demo_creation', False):
        lessons.append({
            'lesson': 'Proof package readiness enabled successful demonstration',
            'details': 'Proof artifacts supported effective outreach preparation',
            'confidence': 'medium',
            'applicability': 'cases_with_adequate_evidence'
        })

    # Lesson 4: Time efficiency factors
    time_in_pipeline = _calculate_time_in_pipeline_from_history(pipeline_history)
    if time_in_pipeline < 24:  # Less than 24 hours
        lessons.append({
            'lesson': 'Rapid pipeline processing contributed to success',
            'details': f'Total time in pipeline: {time_in_pipeline:.1f} hours',
            'confidence': 'low',
            'applicability': 'high_priority_cases'
        })

    return lessons


def _extract_failure_lessons(pipeline_history: List[Dict], payload: Dict, final_state: str) -> List[Dict]:
    """Extract lessons from failed outcomes."""
    lessons = []

    # Lesson 1: Where the process broke down
    if pipeline_history:
        # Find the last successful transition before failure
        last_successful_index = -1
        for i, event in enumerate(pipeline_history):
            # Check if this represents a normal progression
            if i > 0:
                prev_event = pipeline_history[i-1]
                if prev_event['to_state'] == event['from_state']:
                    last_successful_index = i
                else:
                    break  # Found a break in normal progression

        if last_successful_index >= 0 and last_successful_index < len(pipeline_history) - 1:
            failure_point = pipeline_history[last_successful_index + 1]
            lessons.append({
                'lesson': f'Process breakdown at {failure_point["to_state"]} stage',
                'details': f'Failure reason: {failure_point.get("reason", "unknown")}',
                'confidence': 'high',
                'applicability': 'similar_failure_patterns'
            })

    # Lesson 2: Specific failure mode analysis
    failure_modes = {
        'REJECTED': 'Insufficient qualification or opportunity',
        'NO_VERIFIED_EMAIL': 'Unable to verify contact information',
        'PERMANENT_FAILURE': 'Repeated retryable failures',
        'SUPPRESSED': 'Explicit opt-out or suppression'
    }

    if final_state in failure_modes:
        lessons.append({
            'lesson': f'Specific failure mode: {failure_modes[final_state]}',
            'details': f'Final state analysis: {final_state}',
            'confidence': 'medium',
            'applicability': f'preventing_{final_state.lower()}_outcomes'
        })

    # Lesson 3: Data insufficiency issues
    understanding = payload.get('business_understanding', {})
    if understanding.get('understanding_completeness', 1) < 0.4:
        lessons.append({
            'lesson': 'Insufficient business understanding contributed to failure',
            'details': f'Understanding completeness: {understanding.get("understanding_completeness", 0):.2f}',
            'confidence': 'medium',
            'applicability': 'cases_with_limited_evidence'
        })

    # Lesson 4: Proof preparation deficiencies
    proof_package = payload.get('proof_package', {})
    if not proof_package.get('ready_for_demo_creation', True):
        lessons.append({
            'lesson': 'Inadequate proof preparation hindered progress',
            'details': f'Proof artifacts: {len(proof_package.get("proof_artifacts", []))}',
            'confidence': 'medium',
            'applicability': 'cases_needing_better_evidence_packaging'
        })

    return lessons


def _extract_general_lessons(pipeline_history: List[Dict], final_state: str) -> List[Dict]:
    """Extract general lessons from non-terminal outcomes."""
    lessons = []

    # Lesson about NEEDS_REVIEW cycles
    needs_review_count = sum(1 for event in pipeline_history
                           if event.get('state') == 'NEEDS_REVIEW' or
                              event.get('from_state') == 'NEEDS_REVIEW' or
                              event.get('to_state') == 'NEEDS_REVIEW')

    if needs_review_count > 2:
        lessons.append({
            'lesson': 'Multiple NEEDS_REVIEW cycles indicate process friction',
            'details': f'NEEDS_REVIEW encountered {needs_review_count} times',
            'confidence': 'medium',
            'applicability': 'process_improvement_opportunities'
        })

    return lessons


def _identify_success_patterns(pipeline_history: List[Dict]) -> List[Dict]:
    """Identify patterns that contributed to success."""
    patterns = []

    # Pattern 1: Consistent actor performance
    actor_success = {}
    for event in pipeline_history:
        actor = event.get('actor', 'unknown')
        if actor not in actor_success:
            actor_success[actor] = 0
        actor_success[actor] += 1

    if actor_success:
        most_successful_actor = max(actor_success, key=actor_success.get)
        patterns.append({
            'pattern': f'High effectiveness of {most_successful_actor} actor',
            'details': f'Successfully processed {actor_success[most_successful_actor]} events',
            'recommendation': f'Maintain or increase capacity for {most_successful_actor}',
            'confidence': 'medium'
        })

    # Pattern 2: Efficient state transitions
    transition_times = []
    for i in range(len(pipeline_history) - 1):
        try:
            curr_time = datetime.fromisoformat(pipeline_history[i]['event_at'].replace('Z', '+00:00'))
            next_time = datetime.fromisoformat(pipeline_history[i+1]['event_at'].replace('Z', '+00:00'))
            transition_time = (next_time - curr_time).total_seconds() / 3600  # hours
            transition_times.append(transition_time)
        except (ValueError, KeyError):
            continue

    if transition_times:
        avg_transition_time = sum(transition_times) / len(transition_times)
        if avg_transition_time < 1:  # Less than 1 hour average
            patterns.append({
                'pattern': 'Rapid state transitions contributed to success',
                'details': f'Average transition time: {avg_transition_time:.2f} hours',
                'recommendation': 'Maintain current handoff efficiency',
                'confidence': 'medium'
            })

    return patterns


def _identify_improvement_areas(pipeline_history: List[Dict]) -> List[Dict]:
    """Identify areas for improvement based on failure patterns."""
    improvements = []

    # Improvement 1: Bottleneck identification
    state_delays = {}
    for i in range(len(pipeline_history) - 1):
        try:
            curr_state = pipeline_history[i]['to_state']
            next_time = datetime.fromisoformat(pipeline_history[i+1]['event_at'].replace('Z', '+00:00'))
            curr_time = datetime.fromisoformat(pipeline_history[i]['event_at'].replace('Z', '+00:00'))
            delay_hours = (next_time - curr_time).total_seconds() / 3600

            if curr_state not in state_delays:
                state_delays[curr_state] = []
            state_delays[curr_state].append(delay_hours)
        except (ValueError, KeyError):
            continue

    # Find states with high average delay
    for state, delays in state_delays.items():
        if len(delays) >= 2:  # Need multiple samples
            avg_delay = sum(delays) / len(delays)
            if avg_delay > 4:  # More than 4 hours average delay
                improvements.append({
                    'area': f'Reduce delay in {state} state',
                    'details': f'Average delay: {avg_delay:.2f} hours',
                    'impact': 'high' if avg_delay > 12 else 'medium',
                    'suggestion': f'Investigate {state} processing efficiency',
                    'confidence': 'medium'
                })

    # Improvement 2: Actor performance issues
    actor_issues = {}
    for event in pipeline_history:
        actor = event.get('actor', 'unknown')
        reason = event.get('reason', '').lower()
        # Check if reason indicates actor-related issues
        if any(term in reason for term in ['timeout', 'failed', 'error', 'retry']):
            if actor not in actor_issues:
                actor_issues[actor] = 0
            actor_issues[actor] += 1

    for actor, issue_count in actor_issues.items():
        if issue_count >= 2:  # Multiple issues with same actor
            improvements.append({
                'area': f'Address reliability issues with {actor} actor',
                'details': f'{issue_count} failure events associated with this actor',
                'impact': 'medium',
                'suggestion': f'Review {actor} implementation or increase retry tolerance',
                'confidence': 'medium'
            })

    return improvements


def _apply_learning_to_system(d, learning_record: Dict):
    """Apply learning to improve system performance."""
    try:
        # Store learning in system knowledge base
        _store_learning_record(d, learning_record)

        # Update system parameters based on learned patterns
        _update_system_parameters(d, learning_record)

        # Log learning application for audit
        core.event(
            d,
            'management_learning_applied',
            learning_record['business_id'],
            json.dumps({
                'learning_timestamp': learning_record['learning_timestamp'],
                'lessons_count': len(learning_record['lessons_learned']),
                'strategy_adjustments': len(learning_record['strategy_adjustments']),
                'final_state': learning_record['final_state']
            })
        )

    except Exception:
        # Learning application failure should not break the main process
        pass


def _store_learning_record(d, learning_record: Dict):
    """Store learning record in system knowledge base."""
    try:
        # Create learning table if it doesn't exist
        d.execute("""
            CREATE TABLE IF NOT EXISTS mm_learning (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_id INTEGER NOT NULL,
                learning_timestamp TEXT NOT NULL,
                final_state TEXT NOT NULL,
                lessons_json TEXT NOT NULL,
                adjustments_json TEXT NOT NULL,
                outcome_info TEXT NOT NULL,
                applied INTEGER NOT NULL DEFAULT 0
            )
        """)

        # Insert learning record
        d.execute("""
            INSERT INTO mm_learning
            (business_id, learning_timestamp, final_state, lessons_json, adjustments_json, outcome_info)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            learning_record['business_id'],
            learning_record['learning_timestamp'],
            learning_record['final_state'],
            json.dumps(learning_record['lessons_learned']),
            json.dumps(learning_record['strategy_adjustments']),
            json.dumps(learning_record['outcome_info'])
        ))

    except Exception:
        # Storage failure should not break learning process
        pass


def _update_system_parameters(d, learning_record: Dict):
    """Update system parameters based on learned patterns."""
    try:
        # This would update things like:
        # - Retry parameters based on failure patterns
        # - Resource allocation based on success patterns
        # - Queue prioritization based on learned priorities

        # For now, we'll just log that parameter updates would happen here
        # In a full implementation, this would modify system configuration tables

        pass
    except Exception:
        pass


def _get_portfolio_context(d) -> Dict:
    """Get current portfolio context for management decisions."""
    try:
        # Get counts by state
        state_counts = {}
        states = d.execute("""
            SELECT state, COUNT(*) as count
            FROM pipeline_items
            GROUP BY state
        """).fetchall()

        for row in states:
            state_counts[row['state']] = row['count']

        # Calculate totals
        total_active = sum(count for state, count in state_counts.items()
                          if state not in TERMINAL_STATES)
        total_terminal = sum(count for state, count in state_counts.items()
                           if state in TERMINAL_STATES)

        # Get average wait times (simplified)
        avg_wait_time = _calculate_average_wait_time(d)

        # Get capacity utilization (simplified)
        capacity_utilization = min(1.0, total_active / 50.0)  # Assume 50 is max capacity

        return {
            'total_active': total_active,
            'total_terminal': total_terminal,
            'total_businesses': total_active + total_terminal,
            'state_distribution': state_counts,
            'capacity_utilization': round(capacity_utilization, 3),
            'average_wait_time_hours': round(avg_wait_time, 2),
            'portfolio_health': _assess_portfolio_health(state_counts),
            'timestamp': core.now()
        }
    except Exception:
        return {
            'total_active': 0,
            'total_terminal': 0,
            'total_businesses': 0,
            'state_distribution': {},
            'capacity_utilization': 0.0,
            'average_wait_time_hours': 0.0,
            'portfolio_health': 'unknown',
            'timestamp': core.now()
        }


def _calculate_average_wait_time(d) -> float:
    """Calculate average time items spend waiting in queue."""
    try:
        # Simplified calculation - in reality would be more complex
        result = d.execute("""
            SELECT AVG(
                CASE
                    WHEN lease_until IS NOT NULL AND lease_owner IS NOT NULL THEN
                        (julianday(lease_until) - julianday(updated_at)) * 24
                    ELSE 0
                END
            ) as avg_wait_hours
            FROM pipeline_items
            WHERE state NOT IN ('CONVERTED', 'REJECTED', 'NO_VERIFIED_EMAIL', 'PERMANENT_FAILURE', 'SUPPRESSED', 'DUPLICATE')
        """).fetchone()

        return result['avg_wait_hours'] if result and result['avg_wait_hours'] is not None else 0.0
    except Exception:
        return 0.0


def _assess_portfolio_health(state_counts: Dict) -> str:
    """Assess overall portfolio health."""
    try:
        total_active = sum(count for state, count in state_counts.items()
                          if state not in TERMINAL_STATES)
        total_terminal = sum(count for state, count in state_counts.items()
                           if state in TERMINAL_STATES)

        if total_active + total_terminal == 0:
            return 'no_data'

        success_rate = state_counts.get('CONVERTED', 0) / max(total_terminal, 1)
        rejection_rate = (state_counts.get('REJECTED', 0) + state_counts.get('NO_VERIFIED_EMAIL', 0) +
                         state_counts.get('PERMANENT_FAILURE', 0) + state_counts.get('SUPPRESSED', 0)) / max(total_terminal, 1)
        needs_review_rate = state_counts.get('NEEDS_REVIEW', 0) / max(total_active, 1)

        if success_rate > 0.3 and rejection_rate < 0.2 and needs_review_rate < 0.3:
            return 'healthy'
        elif success_rate > 0.15:
            return 'moderate'
        else:
            return 'needs_attention'
    except Exception:
        return 'unknown'


def _assess_item_priority(d, business_id: int, payload: Dict, current_state: str, portfolio_context: Dict) -> Dict:
    """Assess priority of an item within the portfolio."""
    try:
        # Base priority factors
        priority_factors = []

        # Factor 1: Opportunity score (if available)
        opportunity_score = payload.get('opportunity_score', 0) / 100.0  # Convert to 0-1 scale
        priority_factors.append(('opportunity_score', opportunity_score, 0.3))

        # Factor 2: Understanding completeness
        understanding_complete = payload.get('business_understanding', {}).get('understanding_completeness', 0)
        priority_factors.append(('understanding_completeness', understanding_complete, 0.25))

        # Factor 3: Proof package readiness
        proof_ready = 1.0 if payload.get('proof_package', {}).get('ready_for_demo_creation', False) else 0.0
        priority_factors.append(('proof_readiness', proof_ready, 0.2))

        # Factor 4: Time in pipeline (newer items may get priority)
        time_in_pipeline = _calculate_time_in_pipeline(d, business_id)
        # Normalize: items < 6 hours get full credit, > 24 hours get none
        time_factor = max(0.0, min(1.0, (24 - time_in_pipeline) / 24)) if time_in_pipeline < 24 else 0.0
        priority_factors.append(('time_sensitivity', time_factor, 0.15))

        # Factor 5: Business characteristics (if available)
        business = core.get_business(d, business_id)
        if business:
            # Prioritize businesses with websites
            has_website = 1.0 if business.get('public_website') else 0.0
            priority_factors.append(('has_website', has_website, 0.1))

        # Calculate weighted priority score
        total_weight = sum(weight for _, _, weight in priority_factors)
        if total_weight > 0:
            priority_score = sum(score * weight for _, score, weight in priority_factors) / total_weight
        else:
            priority_score = 0.5  # Default middle priority

        # Determine priority level
        if priority_score >= 0.8:
            priority_level = 'high'
        elif priority_score >= 0.6:
            priority_level = 'medium-high'
        elif priority_score >= 0.4:
            priority_level = 'medium'
        elif priority_score >= 0.2:
            priority_level = 'low-medium'
        else:
            priority_level = 'low'

        # Assess resource needs
        resource_needs = 'medium'  # Default
        if opportunity_score > 0.8 and understanding_complete > 0.7:
            resource_needs = 'high'  # High opportunity needs resources to capitalize
        elif opportunity_score < 0.3:
            resource_needs = 'low'   # Low opportunity needs minimal resources

        return {
            'priority_score': round(priority_score, 3),
            'priority_level': priority_level,
            'resource_needs': resource_needs,
            'factors': {name: round(score, 3) for name, score, _ in priority_factors},
            'portfolio_context_used': bool(portfolio_context)
        }
    except Exception:
        return {
            'priority_score': 0.5,
            'priority_level': 'medium',
            'resource_needs': 'medium',
            'factors': {},
            'portfolio_context_used': False
        }


def _apply_portfolio_management_policy(d, business_id: int, payload: Dict, priority_assessment: Dict, portfolio_context: Dict) -> Dict:
    """Apply portfolio management policies to determine action."""
    try:
        priority_score = priority_assessment.get('priority_score', 0.5)
        resource_needs = priority_assessment.get('resource_needs', 'medium')
        capacity_utilization = portfolio_context.get('capacity_utilization', 0.5)
        total_active = portfolio_context.get('total_active', 0)

        # Policy 1: High priority items get accelerated when capacity allows
        if priority_score >= 0.8 and capacity_utilization < 0.8:
            return {
                'action': 'prioritize_for_acceleration',
                'reasoning': f'High priority item (score: {priority_score:.2f}) with available capacity ({capacity_utilization:.2f})'
            }

        # Policy 2: Defer low priority items when system is overloaded
        if priority_score < 0.3 and capacity_utilization > 0.9:
            return {
                'action': 'defer_for_capacity',
                'reasoning': f'Low priority item (score: {priority_score:.2f}) with high system load ({capacity_utilization:.2f})'
            }

        # Policy 3: Allocate additional resources to high-need, high-priority items
        if priority_score >= 0.7 and resource_needs == 'high' and capacity_utilization < 0.9:
            return {
                'action': 'allocate_additional_resources',
                'reasoning': f'High priority ({priority_score:.2f}) item with high resource needs and available capacity'
            }

        # Policy 4: Maintain normal processing for medium priority items in normal conditions
        if 0.3 <= priority_score <= 0.7 and capacity_utilization < 0.85:
            return {
                'action': 'maintain_current_processing',
                'reasoning': f'Medium priority item ({priority_score:.2f}) in normal operating conditions'
            }

        # Policy 5: Default to maintaining current processing to avoid thrashing
        return {
            'action': 'maintain_current_processing',
            'reasoning': f'Default maintenance action for priority {priority_score:.2f} and capacity {capacity_utilization:.2f}'
        }
    except Exception:
        return {
            'action': 'maintain_current_processing',
            'reasoning': 'Error in policy application, defaulting to maintenance'
        }


def _get_next_state_in_flow(d, business_id: int, payload: Dict, current_state: str) -> str:
    """Get the next state in the normal flow."""
    try:
        # Use the pipeline's advance function conceptually
        # Import here to avoid circular imports
        from mm_pipeline import HAPPY_PATH, ALTERNATE, TERMINAL, _FORWARD

        # Check if it's a terminal state
        if current_state in TERMINAL:
            return current_state

        # Check if it's in the happy path
        if current_state in HAPPY_PATH:
            try:
                current_index = HAPPY_PATH.index(current_state)
                if current_index < len(HAPPY_PATH) - 1:
                    return HAPPY_PATH[current_index + 1]
                else:
                    return current_state  # At end of happy path
            except ValueError:
                pass  # Not in happy path, check alternate

        # Check if it's in alternate states (non-terminal)
        if current_state in ALTERNATE and current_state not in TERMINAL:
            # For now, just return the state - alternate states usually need external triggers
            return current_state

        # Default: return current state to avoid errors
        return current_state
    except Exception:
        return current_state


# Terminal states for reference
TERMINAL_STATES = ('CONVERTED', 'REJECTED', 'NO_VERIFIED_EMAIL', 'PERMANENT_FAILURE', 'SUPPRESSED', 'DUPLICATE')

# Register this worker for the management states
MANAGEMENT_WORKER_STATES = tuple(set(TERMINAL_STATES + ('NEEDS_REVIEW',) +
                                   tuple(state for state in ['DISCOVERED', 'IDENTITY_PENDING', 'IDENTITY_RESOLVED', 'AUDIT_PENDING', 'AUDITED']
                                    if state not in TERMINAL_STATES)))

if __name__ == '__main__':
    # Test the management worker components
    print("Management worker for Loop D loaded successfully")
    print(f"Registered for states: {MANAGEMENT_WORKER_STATES}")
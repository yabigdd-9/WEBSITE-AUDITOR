"""Preparation worker for Loop C: Prepare useful proof.

Implements proof preparation, demonstration creation, and evidence packaging
to prepare useful proof for human review and outreach.
"""

import json
import base64
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import mm_core as core
from mm_pipeline import RetryableError, PermanentError, BlockedCost


def preparation_worker_handler(d, item_row, worker):
    """Prepare useful proof - Loop C handler.

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

    # Prepare useful proof based on current state
    if current_state == 'REMEDIATION_PENDING':
        # Prepare proof from audit/remediation findings
        next_state, reason, evidence = _prepare_proof_from_remediation(d, business_id, payload)
    elif current_state == 'DEMO_PENDING':
        # Prepare demonstration artifacts
        next_state, reason, evidence = _prepare_demonstration_artifacts(d, business_id, payload)
    elif current_state == 'QA_PENDING':
        # Final proof preparation and packaging
        next_state, reason, evidence = _finalize_proof_package(d, business_id, payload)
    else:
        # Fallback - should not reach here with proper worker registration
        next_state = 'NEEDS_REVIEW'
        reason = f'Unexpected state for preparation worker: {current_state}'
        evidence = {'unexpected_state': current_state}

    return next_state, reason, evidence


def _prepare_proof_from_remediation(d, business_id: int, payload: Dict) -> Tuple[str, str, Dict]:
    """Prepare proof materials from remediation findings."""
    try:
        # Get business information
        business = core.get_business(d, business_id)
        if not business:
            raise PermanentError('business row missing')

        # Get latest audit/evidence
        evidence_rows = core.get_evidence(d, business_id, limit=10)
        if not evidence_rows:
            raise RetryableError('no evidence available for proof preparation')

        # Get any remediation-specific data
        remediation_data = _get_remediation_data(d, business_id)

        # Prepare proof package
        proof_package = {
            'business_id': business_id,
            'business_name': business.get('name'),
            'preparation_timestamp': core.now(),
            'proof_type': 'remediation_based',
            'audit_summary': _summarize_audit_findings(evidence_rows),
            'key_findings': _extract_key_findings(evidence_rows),
            'remediation_opportunities': _identify_remediation_opportunities(evidence_rows, remediation_data),
            'proof_artifacts': [],
            'evidence_quality': _assess_overall_evidence_quality(evidence_rows),
            'ready_for_demo_creation': False
        }

        # Generate specific proof artifacts
        artifacts = _generate_proof_artifacts(business, evidence_rows, remediation_data)
        proof_package['proof_artifacts'] = artifacts

        # Check if we have sufficient artifacts to create a demonstration
        if len(artifacts) >= 2:  # Need at least 2 artifacts for meaningful demo
            proof_package['ready_for_demo_creation'] = True

        # Store proof package in payload for next stages
        payload.update({
            'proof_package': proof_package,
            'proof_prepared': True,
            'artifacts_count': len(artifacts)
        })

        # Determine next state based on preparation success
        if proof_package['ready_for_demo_creation']:
            next_state = 'DEMO_PENDING'
            reason = f'Proof prepared successfully with {len(artifacts)} artifacts, ready for demo creation'
        else:
            next_state = 'REMEDIATION_PENDING'  # Stay in same state to retry
            reason = f'Insufficient proof artifacts ({len(artifacts)}), need more evidence or remediation data'

        evidence = {
            'proof_package_summary': {
                'artifacts_created': len(artifacts),
                'proof_type': proof_package['proof_type'],
                'ready_for_demo': proof_package['ready_for_demo_creation'],
                'evidence_quality_score': proof_package['evidence_quality']['score']
            },
            'artifacts': [artifact.get('name', 'unnamed') for artifact in artifacts[:3]]  # First 3 for brevity
        }

        return next_state, reason, evidence

    except RetryableError:
        raise
    except Exception as e:
        raise PermanentError(f'proof preparation failed: {str(e)}')


def _prepare_demonstration_artifacts(d, business_id: int, payload: Dict) -> Tuple[str, str, Dict]:
    """Prepare demonstration artifacts from proof package."""
    try:
        # Get the proof package from previous stage
        proof_package = payload.get('proof_package', {})
        if not proof_package:
            raise RetryableError('no proof package available for demonstration preparation')

        business = core.get_business(d, business_id)
        if not business:
            raise PermanentError('business row missing')

        # Prepare demonstration based on proof package
        demo_preparation = {
            'business_id': business_id,
            'demo_preparation_timestamp': core.now(),
            'demo_type': 'interactive_audit_review',
            'based_on_proof_package': True,
            'demo_components': [],
            'demo_ready': False,
            'estimated_preparation_time': 0
        }

        # Generate demonstration components from proof artifacts
        proof_artifacts = proof_package.get('proof_artifacts', [])
        demo_components = _create_demo_components(proof_artifacts, business)
        demo_preparation['demo_components'] = demo_components

        # Calculate estimated preparation time
        demo_preparation['estimated_preparation_time'] = sum(
            comp.get('estimated_time_minutes', 5) for comp in demo_components
        )

        # Check if demo is ready to be created
        if len(demo_components) >= 2:
            demo_preparation['demo_ready'] = True

        # Update payload
        payload.update({
            'demo_preparation': demo_preparation,
            'demo_ready': demo_preparation['demo_ready'],
            'demo_components_count': len(demo_components)
        })

        # Determine next state
        if demo_preparation['demo_ready']:
            next_state = 'DEMO_READY'
            reason = f'Demonstration prepared with {len(demo_components)} components, ready for assembly'
        else:
            next_state = 'DEMO_PENDING'  # Stay to retry
            reason = f'Insufficient demo components ({len(demo_components)}), need more proof preparation'

        evidence = {
            'demo_preparation_summary': {
                'components_prepared': len(demo_components),
                'demo_ready': demo_preparation['demo_ready'],
                'estimated_time_minutes': demo_preparation['estimated_preparation_time']
            },
            'component_types': [comp.get('type', 'unknown') for comp in demo_components[:3]]
        }

        return next_state, reason, evidence

    except RetryableError:
        raise
    except Exception as e:
        raise PermanentError(f'demo preparation failed: {str(e)}')


def _finalize_proof_package(d, business_id: int, payload: Dict) -> Tuple[str, str, Dict]:
    """Finalize proof package and prepare for outreach."""
    try:
        business = core.get_business(d, business_id)
        if not business:
            raise PermanentError('business row missing')

        # Collect all preparation data
        proof_package = payload.get('proof_package', {})
        demo_preparation = payload.get('demo_preparation', {})
        understanding = payload.get('business_understanding', {})
        opportunity_score = payload.get('opportunity_score', 0)

        # Create final proof package for human review
        final_proof_package = {
            'business_id': business_id,
            'business_name': business.get('name'),
            'finalization_timestamp': core.now(),
            'proof_package': proof_package,
            'demo_preparation': demo_preparation,
            'business_understanding': understanding,
            'opportunity_score': opportunity_score,
            'review_readiness': _assess_review_readiness(proof_package, demo_preparation, understanding),
            'package_version': '1.0',
            'ready_for_human_review': False
        }

        # Determine if package is ready for human review
        review_readiness = final_proof_package['review_readiness']
        if review_readiness['overall_score'] >= 0.7:  # 70% readiness threshold
            final_proof_package['ready_for_human_review'] = True
            next_state = 'OUTREACH_PENDING'
            reason = f'Proof package ready for human review (readiness: {review_readiness["overall_score"]:.2f})'
        else:
            next_state = 'QA_PENDING'  # Stay to improve preparation
            reason = f'Proof package needs improvement (readiness: {review_readiness["overall_score"]:.2f})'

        evidence = {
            'final_package_summary': {
                'ready_for_human_review': final_proof_package['ready_for_human_review'],
                'review_readiness_score': review_readiness['overall_score'],
                'proof_artifacts_count': len(proof_package.get('proof_artifacts', [])),
                'demo_components_count': len(demo_preparation.get('demo_components', []))
            },
            'readiness_breakdown': review_readiness
        }

        # Update payload with final package
        payload.update({
            'final_proof_package': final_proof_package,
            'proof_package_finalized': True,
            'ready_for_human_review': final_proof_package['ready_for_human_review']
        })

        return next_state, reason, evidence

    except RetryableError:
        raise
    except Exception as e:
        raise PermanentError(f'proof finalization failed: {str(e)}')


def _get_remediation_data(d, business_id: int) -> Dict:
    """Get remediation-specific data if available."""
    try:
        # Look for remediation rows or specific remediation evidence
        remediation_rows = d.execute("""
            SELECT * FROM mm_remediation
            WHERE business_id = ?
            ORDER BY created_at DESC LIMIT 5
        """, (business_id,)).fetchall()

        remediation_data = {
            'remediation_count': len(remediation_rows),
            'remediation_items': [dict(row) for row in remediation_rows] if remediation_rows else [],
            'has_remediation_plan': len(remediation_rows) > 0
        }

        return remediation_data
    except Exception:
        # If remediation table doesn't exist or other error, return empty data
        return {
            'remediation_count': 0,
            'remediation_items': [],
            'has_remediation_plan': False
        }


def _summarize_audit_findings(evidence_rows: List[Dict]) -> Dict:
    """Summarize audit findings from evidence rows."""
    if not evidence_rows:
        return {'total_findings': 0, 'severity_distribution': {}, 'categories': []}

    findings_by_severity = {'high': 0, 'medium': 0, 'low': 0, 'info': 0}
    categories = set()
    total_findings = 0

    for evidence in evidence_rows:
        # Try to extract findings from evidence
        observation = evidence.get('observation', '').lower()
        limitation = evidence.get('limitation', '').lower()
        evidence_text = f"{observation} {limitation}"

        # Simple severity detection
        if any(term in evidence_text for term in ['critical', 'severe', 'serious', 'major']):
            findings_by_severity['high'] += 1
        elif any(term in evidence_text for term in ['moderate', 'medium']):
            findings_by_severity['medium'] += 1
        elif any(term in evidence_text for term in ['minor', 'minimal', 'low']):
            findings_by_severity['low'] += 1
        else:
            findings_by_severity['info'] += 1

        # Try to categorize
        if 'accessibility' in evidence_text or 'a11y' in evidence_text:
            categories.add('accessibility')
        if 'performance' in evidence_text or 'speed' in evidence_text or 'load' in evidence_text:
            categories.add('performance')
        if 'seo' in evidence_text or 'search' in evidence_text or 'ranking' in evidence_text:
            categories.add('seo')
        if 'security' in evidence_text or 'vulnerability' in evidence_text or 'ssl' in evidence_text:
            categories.add('security')
        if 'mobile' in evidence_text or 'responsive' in evidence_text:
            categories.add('mobile_experience')

        total_findings += 1

    return {
        'total_findings': total_findings,
        'severity_distribution': findings_by_severity,
        'categories': list(categories),
        'findings_density': total_findings / max(len(evidence_rows), 1)
    }


def _extract_key_findings(evidence_rows: List[Dict]) -> List[Dict]:
    """Extract key findings suitable for proof materials."""
    key_findings = []

    for evidence in evidence_rows[:5]:  # Limit to top 5 for brevity
        observation = evidence.get('observation', '')
        limitation = evidence.get('limitation', '')
        score = evidence.get('score', 0)

        # Create a finding entry
        finding = {
            'id': evidence.get('id'),
            'observation': observation[:200] if observation else '',
            'limitation': limitation[:200] if limitation else '',
            'score': score,
            'impact_level': _determine_impact_level(score, limitation),
            'remediation_potential': _assess_remediation_potential(observation, limitation)
        }

        key_findings.append(finding)

    return key_findings


def _determine_impact_level(score: int, limitation: str) -> str:
    """Determine impact level based on score and limitation."""
    if score >= 80:
        return 'high'
    elif score >= 60:
        return 'medium'
    elif score >= 40:
        return 'low'
    else:
        return 'minimal'


def _assess_remediation_potential(observation: str, limitation: str) -> str:
    """Assess how easy/hard it would be to remediate this finding."""
    text = f"{observation} {limitation}".lower()

    # Easy to fix indicators
    easy_indicators = ['missing', 'add', 'include', 'update', 'change', 'fix']
    # Medium difficulty indicators
    medium_indicators = ['improve', 'enhance', 'optimize', 'restructure']
    # Hard indicators
    hard_indicators = ['rebuild', 'redevelop', 'migrate', 'replace', 'overhaul']

    if any(indicator in text for indicator in hard_indicators):
        return 'hard'
    elif any(indicator in text for indicator in medium_indicators):
        return 'medium'
    elif any(indicator in text for indicator in easy_indicators):
        return 'easy'
    else:
        return 'unknown'


def _identify_remediation_opportunities(evidence_rows: List[Dict], remediation_data: Dict) -> List[Dict]:
    """Identify specific remediation opportunities from evidence."""
    opportunities = []

    # From evidence rows
    for evidence in evidence_rows:
        observation = evidence.get('observation', '').lower()
        limitation = evidence.get('limitation', '').lower()
        evidence_text = f"{observation} {limitation}"

        # Look for clear remediation opportunities
        if any(term in evidence_text for term in ['should', 'could', 'would benefit', 'recommended', 'suggested']):
            opportunity = {
                'type': 'evidence_based_suggestion',
                'description': evidence_text[:150],
                'source_evidence_id': evidence.get('id'),
                'estimated_effort': _estimate_remediation_effort(evidence_text),
                'potential_impact': _estimate_impact_from_evidence(evidence_text)
            }
            opportunities.append(opportunity)

    # From remediation data if available
    if remediation_data.get('has_remediation_plan'):
        for rem_item in remediation_data.get('remediation_items', []):
            opportunity = {
                'type': 'remediation_plan_item',
                'description': str(rem_item.get('description', ''))[:150],
                'source': 'remediation_plan',
                'estimated_effort': rem_item.get('estimated_effort', 'unknown'),
                'potential_impact': rem_item.get('potential_impact', 'unknown')
            }
            opportunities.append(opportunity)

    return opportunities[:5]  # Limit to top 5


def _estimate_remediation_effort(text: str) -> str:
    """Estimate remediation effort from text description."""
    text_lower = text.lower()
    if any(term in text_lower for term in ['quick', 'simple', 'easy', 'minor', 'trivial']):
        return 'low'
    elif any(term in text_lower for term in ['moderate', 'medium', 'standard']):
        return 'medium'
    elif any(term in text_lower for term in ['complex', 'difficult', 'hard', 'major', 'significant']):
        return 'high'
    else:
        return 'medium'  # Default


def _estimate_impact_from_evidence(text: str) -> str:
    """Estimate potential impact from evidence text."""
    text_lower = text.lower()
    if any(term in text_lower for term in ['critical', 'major', 'significant', 'substantial', 'dramatic']):
        return 'high'
    elif any(term in text_lower for term in ['moderate', 'medium', 'noticeable']):
        return 'medium'
    elif any(term in text_lower for term in ['minor', 'minimal', 'slight']):
        return 'low'
    else:
        return 'medium'  # Default


def _generate_proof_artifacts(business: Dict, evidence_rows: List[Dict], remediation_data: Dict) -> List[Dict]:
    """Generate specific proof artifacts from evidence and remediation data."""
    artifacts = []

    # Artifact 1: Executive Summary
    exec_summary = _create_executive_summary(business, evidence_rows, remediation_data)
    if exec_summary:
        artifacts.append(exec_summary)

    # Artifact 2: Key Findings Visualization
    key_findings_viz = _create_key_findings_visualization(evidence_rows)
    if key_findings_viz:
        artifacts.append(key_findings_viz)

    # Artifact 3: Remediation Roadmap
    if remediation_data.get('has_remediation_plan'):
        remediation_roadmap = _create_remediation_roadmap(remediation_data)
        if remediation_roadmap:
            artifacts.append(remediation_roadmap)

    # Artifact 4: Opportunity Assessment
    opportunity_assessment = _create_opportunity_assessment(business, evidence_rows)
    if opportunity_assessment:
        artifacts.append(opportunity_assessment)

    # Artifact 5: Evidence Traceability Matrix
    evidence_matrix = _create_evidence_traceability_matrix(evidence_rows)
    if evidence_matrix:
        artifacts.append(evidence_matrix)

    return artifacts


def _create_executive_summary(business: Dict, evidence_rows: List[Dict], remediation_data: Dict) -> Optional[Dict]:
    """Create executive summary proof artifact."""
    try:
        business_name = business.get('name', 'Unknown Business')
        evidence_count = len(evidence_rows)
        findings_summary = _summarize_audit_findings(evidence_rows)

        summary_text = f"""
EXECUTIVE SUMMARY - {business_name}

Overview:
- Business: {business_name}
- Website: {business.get('public_website', 'Not provided')}
- Region: {business.get('region', 'Not provided')}
- Audit Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}

Audit Scope:
- Total evidence points reviewed: {evidence_count}
- Findings categories: {', '.join(findings_summary.get('categories', ['None'])) or 'None identified'}

Key Results:
- Total findings identified: {findings_summary.get('total_findings', 0)}
- High priority issues: {findings_summary.get('severity_distribution', {}).get('high', 0)}
- Medium priority issues: {findings_summary.get('severity_distribution', {}).get('medium', 0)}
- Low priority issues: {findings_summary.get('severity_distribution', {}).get('low', 0)}

Opportunity Assessment:
- Remediation opportunities identified: {len(remediation_data.get('remediation_items', [])) if remediation_data.get('has_remediation_plan') else 0}
- Estimated business impact: {_estimate_business_impact_from_findings(findings_summary)}

Next Steps:
- Review detailed findings in attached reports
- Prioritize remediation based on impact and effort
- Schedule follow-up audit to verify improvements
        """.strip()

        return {
            'name': 'executive_summary',
            'type': 'document',
            'format': 'text',
            'content': summary_text,
            'estimated_time_minutes': 5,
            'proof_value': 'high'  # Executive summary has high proof value for decision makers
        }
    except Exception:
        return None


def _create_key_findings_visualization(evidence_rows: List[Dict]) -> Optional[Dict]:
    """Create key findings visualization proof artifact."""
    try:
        key_findings = _extract_key_findings(evidence_rows)
        if not key_findings:
            return None

        # Create a simple textual visualization
        viz_lines = ["KEY FINDINGS VISUALIZATION", "=" * 50, ""]

        for i, finding in enumerate(key_findings[:10], 1):  # Top 10 findings
            impact = finding.get('impact_level', 'unknown')
            obs = finding.get('observation', 'No observation')[:100]
            lim = finding.get('limitation', 'No limitation')[:100]

            viz_lines.append(f"{i:2d}. [{impact.upper()}] {obs}")
            if lim and lim != 'No limitation':
                viz_lines.append(f"    Limitation: {lim}")
            viz_lines.append("")

        viz_content = "\n".join(viz_lines)

        return {
            'name': 'key_findings_visualization',
            'type': 'document',
            'format': 'text',
            'content': viz_content,
            'estimated_time_minutes': 10,
            'proof_value': 'medium'
        }
    except Exception:
        return None


def _create_remediation_roadmap(remediation_data: Dict) -> Optional[Dict]:
    """Create remediation roadmap proof artifact."""
    try:
        remediation_items = remediation_data.get('remediation_items', [])
        if not remediation_items:
            return None

        roadmap_lines = [
            "REMEDIATION ROADMAP",
            "=" * 50,
            "",
            f"Total remediation items: {len(remediation_items)}",
            "",
            "Prioritized Remediation Plan:",
            ""
        ]

        # Sort by potential impact and effort (high impact, low effort first)
        sorted_items = sorted(
            remediation_items,
            key=lambda x: (
                {'high': 3, 'medium': 2, 'low': 1}.get(str(x.get('potential_impact', 'medium')).lower(), 2),
                -{'high': 3, 'medium': 2, 'low': 1}.get(str(x.get('estimated_effort', 'medium')).lower(), 2)
            ),
            reverse=True
        )

        for i, item in enumerate(sorted_items[:10], 1):  # Top 10 items
            desc = str(item.get('description', 'No description'))[:100]
            impact = str(item.get('potential_impact', 'medium')).lower()
            effort = str(item.get('estimated_effort', 'medium')).lower()

            roadmap_lines.append(f"{i:2d}. {desc}")
            roadmap_lines.append(f"    Impact: {impact.capitalize()} | Effort: {effort.capitalize()}")
            roadmap_lines.append("")

        roadmap_content = "\n".join(roadmap_lines)

        return {
            'name': 'remediation_roadmap',
            'type': 'document',
            'format': 'text',
            'content': roadmap_content,
            'estimated_time_minutes': 15,
            'proof_value': 'high'  # Roadmap has high proof value as it shows actionable plan
        }
    except Exception:
        return None


def _create_opportunity_assessment(business: Dict, evidence_rows: List[Dict]) -> Optional[Dict]:
    """Create opportunity assessment proof artifact."""
    try:
        business_name = business.get('name', 'Unknown Business')
        findings_summary = _summarize_audit_findings(evidence_rows)

        # Calculate opportunity score based on findings
        high_severity = findings_summary.get('severity_distribution', {}).get('high', 0)
        total_findings = findings_summary.get('total_findings', 0)

        # More findings = more opportunity (to fix them)
        opportunity_density = min(1.0, total_findings / 10.0) if total_findings > 0 else 0
        severity_factor = min(1.0, high_severity / 5.0) if high_severity > 0 else 0.3

        opportunity_score = (opportunity_density * 0.6) + (severity_factor * 0.4)

        assessment_lines = [
            "OPPORTUNITY ASSESSMENT",
            "=" * 50,
            "",
            f"Business: {business_name}",
            f"Assessment Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
            "",
            "FINDINGS-BASED OPPORTUNITY SCORE: {opportunity_score:.2f}/1.00",
            "",
            "Assessment Factors:",
            f"- Total findings identified: {total_findings}",
            f"- High severity findings: {high_severity}",
            f"- Findings density score: {opportunity_density:.2f}",
            f"- Severity concentration factor: {severity_factor:.2f}",
            "",
            "Interpretation:",
            _interpret_opportunity_score(opportunity_score),
            "",
            "Recommended Actions:",
            "1. Address high severity findings immediately",
            "2. Develop systematic approach for medium findings",
            "3. Establish monitoring for low severity items",
            "4. Consider preventive measures to avoid recurrence"
        ]

        assessment_content = "\n".join(assessment_lines)

        return {
            'name': 'opportunity_assessment',
            'type': 'document',
            'format': 'text',
            'content': assessment_content,
            'estimated_time_minutes': 8,
            'proof_value': 'medium'
        }
    except Exception:
        return None


def _interpret_opportunity_score(score: float) -> str:
    """Interpret opportunity score for human readers."""
    if score >= 0.8:
        return "High opportunity: Significant issues identified that, when resolved, could substantially improve business performance."
    elif score >= 0.6:
        return "Medium-High opportunity: Notable findings present that warrant investment in improvements."
    elif score >= 0.4:
        return "Medium opportunity: Moderate issues found that suggest room for improvement."
    elif score >= 0.2:
        return "Low-Medium opportunity: Minor issues identified with limited improvement potential."
    else:
        return "Low opportunity: Few or minor issues found indicating relatively good current state."


def _create_evidence_traceability_matrix(evidence_rows: List[Dict]) -> Optional[Dict]:
    """Create evidence traceability matrix proof artifact."""
    try:
        if not evidence_rows:
            return None

        matrix_lines = [
            "EVIDENCE TRACEABILITY MATRIX",
            "=" * 60,
            "",
            "Evidence ID | URL/Source | Type | Score | Status",
            "-" * 60
        ]

        for evidence in evidence_rows[:15]:  # Limit to 15 for readability
            evidence_id = str(evidence.get('id', 'N/A'))
            url = evidence.get('url', 'N/A')[:30]
            # Determine type from URL or observation
            obs = evidence.get('observation', '').lower()
            if 'ajax' in obs or 'api' in obs:
                ev_type = 'Technical'
            elif 'content' in obs or 'text' in obs:
                ev_type = 'Content'
            elif 'performance' in obs or 'speed' in obs:
                ev_type = 'Performance'
            else:
                ev_type = 'General'
            score = str(evidence.get('score', 'N/A'))
            status = 'Collected'

            matrix_lines.append(f"{evidence_id:>10} | {url:<30} | {ev_type:<10} | {score:>5} | {status}")

        matrix_content = "\n".join(matrix_lines)

        return {
            'name': 'evidence_traceability_matrix',
            'type': 'document',
            'format': 'text',
            'content': matrix_content,
            'estimated_time_minutes': 12,
            'proof_value': 'medium'
        }
    except Exception:
        return None


def _assess_overall_evidence_quality(evidence_rows: List[Dict]) -> Dict:
    """Assess overall quality of evidence collection."""
    if not evidence_rows:
        return {'score': 0.0, 'level': 'none', 'details': {}}

    # Simple quality assessment based on evidence attributes
    quality_scores = []
    for evidence in evidence_rows:
        limitation = evidence.get('limitation', '').lower()
        score = evidence.get('score', 0)

        # Quality factors
        quality = 0.5  # Base quality

        # Penalty for limitations
        if 'incomplete' in limitation or 'partial' in limitation:
            quality -= 0.2
        if 'estimated' in limitation or 'approximate' in limitation:
            quality -= 0.15

        # Bonus for validation indicators
        if 'verified' in limitation or 'confirmed' in limitation:
            quality += 0.2
        if 'tested' in limitation or 'measured' in limitation:
            quality += 0.15

        # Score-based quality (higher evidence score = better quality)
        if score >= 80:
            quality += 0.2
        elif score >= 60:
            quality += 0.1
        elif score < 40:
            quality -= 0.1

        quality = max(0.0, min(1.0, quality))  # Clamp to 0-1
        quality_scores.append(quality)

    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0

    return {
        'score': round(avg_quality, 3),
        'level': 'high' if avg_quality >= 0.7 else 'medium' if avg_quality >= 0.4 else 'low',
        'details': {
            'evidence_count': len(evidence_rows),
            'quality_scores': [round(q, 3) for q in quality_scores],
            'assessment_method': 'limitation_and_score_based'
        }
    }


def _assess_review_readiness(proof_package: Dict, demo_preparation: Dict, understanding: Dict) -> Dict:
    """Assess readiness of proof package for human review."""
    scores = []
    details = {}

    # Proof package readiness (0-1)
    proof_ready = 0.0
    if proof_package:
        artifact_count = len(proof_package.get('proof_artifacts', []))
        proof_ready = min(1.0, artifact_count / 3.0)  # Expect at least 3 artifacts
        details['proof_artifacts'] = artifact_count
        details['proof_package_complete'] = proof_package.get('ready_for_demo_creation', False)

    scores.append(proof_ready * 0.4)  # 40% weight

    # Demo preparation readiness (0-1)
    demo_ready = 0.0
    if demo_preparation:
        component_count = len(demo_preparation.get('demo_components', []))
        demo_ready = min(1.0, component_count / 2.0)  # Expect at least 2 components
        details['demo_components'] = component_count
        details['demo_ready'] = demo_preparation.get('demo_ready', False)

    scores.append(demo_ready * 0.3)  # 30% weight

    # Understanding completeness (0-1)
    understanding_complete = 0.0
    if understanding:
        # Use understanding confidence if available, otherwise estimate
        understanding_complete = understanding.get('understanding_confidence', 0.5)
        if understanding_complete == 0.0:  # Fallback if not calculated
            understanding_complete = 0.6  # Reasonable default
        details['understanding_confidence'] = understanding_complete

    scores.append(understanding_complete * 0.2)  # 20% weight

    # Opportunity score alignment (0-1)
    opportunity_aligned = 0.0
    opportunity_score = understanding.get('opportunity_score', 0) / 100.0  # Convert to 0-1 scale
    # Higher opportunity score should align with better preparation
    opportunity_aligned = opportunity_score  # Direct mapping
    details['opportunity_score'] = opportunity_score

    scores.append(opportunity_aligned * 0.1)  # 10% weight

    overall_score = sum(scores)

    return {
        'overall_score': round(overall_score, 3),
        'ready_for_review': overall_score >= 0.7,
        'component_scores': {
            'proof_package': round(scores[0] / 0.4, 3) if len(scores) > 0 else 0.0,
            'demo_preparation': round(scores[1] / 0.3, 3) if len(scores) > 1 else 0.0,
            'understanding': round(scores[2] / 0.2, 3) if len(scores) > 2 else 0.0,
            'opportunity_alignment': round(scores[3] / 0.1, 3) if len(scores) > 3 else 0.0
        },
        'details': details,
        'threshold': 0.7,
        'assessment_timestamp': core.now()
    }


def _estimate_business_impact_from_findings(findings_summary: Dict) -> str:
    """Estimate business impact from findings summary."""
    high_count = findings_summary.get('severity_distribution', {}).get('high', 0)
    total_count = findings_summary.get('total_findings', 0)

    if high_count >= 3:
        return 'High - Critical issues requiring immediate attention'
    elif high_count >= 1:
        return 'Medium-High - Significant issues with notable impact potential'
    elif total_count >= 5:
        return 'Medium - Multiple issues suggesting systemic improvement opportunities'
    elif total_count >= 2:
        return 'Low-Medium - Minor issues with limited individual impact'
    else:
        return 'Low - Few or minor issues found'


# Register this worker for the preparation states
PREPARATION_WORKER_STATES = ('REMEDIATION_PENDING', 'DEMO_PENDING', 'QA_PENDING')

if __name__ == '__main__':
    # Test the preparation worker components
    print("Preparation worker for Loop C loaded successfully")
    print(f"Registered for states: {PREPARATION_WORKER_STATES}")
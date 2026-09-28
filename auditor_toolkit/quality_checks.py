"""Quality checking system for generated drafts.

This module provides functions to validate and score generated drafts
against quality criteria to ensure they meet standards for specificity,
actionability, and professionalism.
"""

import re
from typing import Any, Dict


def check_outreach_draft_quality(draft_text: str, evidence_brief: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Check the quality of an outreach draft.

    Args:
        draft_text: The generated outreach draft text
        evidence_brief: Optional evidence brief for reference checking

    Returns:
        Dictionary with quality scores and feedback
    """
    if not draft_text or not isinstance(draft_text, str):
        return {
            "overall_score": 0,
            "passed": False,
            "feedback": "Draft is empty or not a string",
            "checks": {}
        }

    # Initialize scores
    scores = {
        "has_cta": 0,
        "uses_evidence": 0,
        "appropriate_length": 0,
        "no_unverified_claims": 0,
        "specificity": 0,
        "professional_tone": 0
    }

    feedback_parts = []

    # Check 1: Contains a clear, low-pressure call-to-action
    cta_patterns = [
        r'would it be useful to discuss',
        r'would you like me to share',
        r'could we schedule',
        r'would you be open to a quick conversation',
        r"let me know if you'd like to discuss",
        r'happy to provide more details if interested',
        r'would you like to learn more',
        r'should we explore this further'
    ]

    has_cta = any(re.search(pattern, draft_text.lower()) for pattern in cta_patterns)
    scores["has_cta"] = 2 if has_cta else 0
    if not has_cta:
        feedback_parts.append("Missing clear, low-pressure call-to-action")

    # Check 2: Uses concrete evidence from the brief
    if evidence_brief:
        # Check for specific findings or data points
        key_findings = evidence_brief.get("evidence", {}).get("key_findings", [])
        talking_points = evidence_brief.get("talking_points", {}).get("evidence_phrases", [])

        # Simple check: look for specific terms that might come from evidence
        evidence_indicators = [
            "critical", "high priority", "medium priority", "issue", "problem",
            "defect", "error", "warning", "missing", "broken", "expired"
        ]

        # Check if draft mentions any specific findings
        draft_lower = draft_text.lower()
        evidence_mentioned = any(
            finding.get("finding", "").lower() in draft_lower
            for finding in key_findings[:3]  # Check top 3 findings
        )

        # Or check for evidence phrases
        evidence_phrase_used = any(
            phrase.lower() in draft_lower
            for phrase in talking_points[:3]  # Check top 3 phrases
        )

        # Or check for general evidence indicators
        evidence_indicators_found = any(
            indicator in draft_lower
            for indicator in evidence_indicators
        )

        uses_evidence = evidence_mentioned or evidence_phrase_used or evidence_indicators_found
        scores["uses_evidence"] = 2 if uses_evidence else 0
        if not uses_evidence:
            feedback_parts.append("Could use more specific evidence from the audit")
    else:
        # Without evidence brief, do a basic check
        scores["uses_evidence"] = 1  # Neutral score

    # Check 3: Appropriate length (short and specific)
    word_count = len(draft_text.split())
    if 20 <= word_count <= 120:
        scores["appropriate_length"] = 2
    elif word_count < 20:
        scores["appropriate_length"] = 0
        feedback_parts.append("Draft is too short - add more specific details")
    else:
        scores["appropriate_length"] = 0
        feedback_parts.append("Draft is too long - aim for more conciseness")

    # Check 4: No unverified claims or measured revenue losses
    unverified_patterns = [
        r'costing you.*\$',
        r'lost.*revenue',
        r'costing you.*per month',
        r"you're losing",
        r'costing you.*dollars',
        r'revenue loss',
        r'lost sales',
        r'financial impact',
        r'\$\d+',  # Dollar amounts
    ]

    has_unverified_claims = any(
        re.search(pattern, draft_text.lower(), re.IGNORECASE)
        for pattern in unverified_patterns
    )

    scores["no_unverified_claims"] = 2 if not has_unverified_claims else 0
    if has_unverified_claims:
        feedback_parts.append("Avoid making unverified financial claims or specifying dollar amounts")

    # Check 5: Specificity (not too generic)
    generic_phrases = [
        r'your website',
        r'your online presence',
        r'your business',
        r'improve your website',
        r'enhance your site',
        r'better website',
        r'website issues',
        r'online presence'
    ]

    # Count generic phrases - too many indicates lack of specificity
    generic_count = sum(
        len(re.findall(phrase, draft_text.lower()))
        for phrase in generic_phrases
    )

    # Allow up to 2 generic phrases, penalize more
    if generic_count <= 2:
        scores["specificity"] = 2
    elif generic_count <= 4:
        scores["specificity"] = 1
        feedback_parts.append("Consider making the draft more specific to the actual findings")
    else:
        scores["specificity"] = 0
        feedback_parts.append("Draft is too generic - reference specific audit findings")

    # Check 6: Professional tone
    unprofessional_patterns = [
        r'!!',  # Multiple exclamations
        r'!!!',
        r'\$\$\$',  # Multiple dollar signs
        r'act now',
        r'limited time',
        r"don't miss out",
        r'urgent.*action',
        r'hurry',
        r'act fast'
    ]

    has_unprofessional = any(
        re.search(pattern, draft_text.lower(), re.IGNORECASE)
        for pattern in unprofessional_patterns
    )

    # Also check for excessive capitalization (not counting normal sentence starts)
    words = draft_text.split()
    if words:
        caps_words = [w for w in words if w.isupper() and len(w) > 2]
        excessive_caps = len(caps_words) > len(words) * 0.3  # More than 30% caps words
    else:
        excessive_caps = False

    if not has_unprofessional and not excessive_caps:
        scores["professional_tone"] = 2
    elif has_unprofessional or excessive_caps:
        scores["professional_tone"] = 0
        if has_unprofessional:
            feedback_parts.append("Avoid unprofessional language or high-pressure tactics")
        if excessive_caps:
            feedback_parts.append("Avoid excessive use of capital letters")

    # Calculate overall score (0-12 possible)
    total_score = sum(scores.values())
    max_possible = 12

    # Determine if passed (threshold: 8/12 or ~67%)
    passed = total_score >= 8

    # Generate feedback
    if passed:
        feedback = "Good quality outreach draft"
        if feedback_parts:
            feedback += ". Consider: " + "; ".join(feedback_parts)
    else:
        feedback = "Draft needs improvement: " + "; ".join(feedback_parts)

    return {
        "overall_score": total_score,
        "max_possible": max_possible,
        "percentage": round((total_score / max_possible) * 100),
        "passed": passed,
        "feedback": feedback,
        "checks": scores,
        "word_count": word_count
    }


def check_metadata_draft_quality(draft_text: str) -> Dict[str, Any]:
    """Check quality of metadata draft (title and meta description)."""
    if not draft_text or not isinstance(draft_text, str):
        return {
            "overall_score": 0,
            "passed": False,
            "feedback": "Draft is empty or not a string",
            "checks": {}
        }

    scores = {
        "has_title": 0,
        "has_description": 0,
        "appropriate_length": 0,
        "relevant_content": 0
    }

    feedback_parts = []

    # Expect format like "Title: [title]\nDescription: [description]" or similar
    lines = draft_text.strip().split('\n')

    has_title = any('title:' in line.lower() for line in lines)
    has_description = any('description:' in line.lower() for line in lines)

    scores["has_title"] = 2 if has_title else 0
    scores["has_description"] = 2 if has_description else 0

    if not has_title:
        feedback_parts.append("Missing title")
    if not has_description:
        feedback_parts.append("Missing meta description")

    # Check length - title should be ~50-60 chars, description ~150-160 chars
    # This is approximate since we don't know the exact format
    total_chars = len(draft_text)
    if 30 <= total_chars <= 300:
        scores["appropriate_length"] = 2
    elif total_chars < 30:
        scores["appropriate_length"] = 0
        feedback_parts.append("Draft too short for title and description")
    else:
        scores["appropriate_length"] = 0
        feedback_parts.append("Draft may be too long")

    # Check for relevant content (should mention website, SEO, etc.)
    relevant_indicators = ['website', 'site', 'page', 'seo', 'search', 'title', 'description']
    has_relevant = any(indicator in draft_text.lower() for indicator in relevant_indicators)

    scores["relevant_content"] = 2 if has_relevant else 0
    if not has_relevant:
        feedback_parts.append("Draft should reference website or SEO elements")

    total_score = sum(scores.values())
    max_possible = 8
    passed = total_score >= 5  # ~63%

    if passed:
        feedback = "Metadata draft looks good"
        if feedback_parts:
            feedback += ". Consider: " + "; ".join(feedback_parts)
    else:
        feedback = "Metadata draft needs improvement: " + "; ".join(feedback_parts)

    return {
        "overall_score": total_score,
        "max_possible": max_possible,
        "percentage": round((total_score / max_possible) * 100),
        "passed": passed,
        "feedback": feedback,
        "checks": scores
    }


def check_content_expansion_draft_quality(draft_text: str) -> Dict[str, Any]:
    """Check quality of content expansion draft."""
    if not draft_text or not isinstance(draft_text, str):
        return {
            "overall_score": 0,
            "passed": False,
            "feedback": "Draft is empty or not a string",
            "checks": {}
        }

    scores = {
        "addresses_gaps": 0,
        "specific_suggestions": 0,
        "appropriate_length": 0,
        "actionable": 0
    }

    feedback_parts = []

    word_count = len(draft_text.split())

    # Check for specific suggestions
    suggestion_indicators = [
        'consider adding', 'you could', 'recommend', 'suggest',
        'try implementing', 'it would be beneficial to',
        'consider creating', 'you might want to'
    ]

    has_suggestions = any(
        indicator in draft_text.lower()
        for indicator in suggestion_indicators
    )

    scores["specific_suggestions"] = 2 if has_suggestions else 0
    if not has_suggestions:
        feedback_parts.append("Include specific, actionable suggestions")

    # Check for addressing gaps/opportunities
    gap_indicators = [
        'missing', 'lacking', 'opportunity', 'could improve',
        'consider', 'add', 'include', 'implement', 'enhance'
    ]

    addresses_gaps = any(
        indicator in draft_text.lower()
        for indicator in gap_indicators
    )

    scores["addresses_gaps"] = 2 if addresses_gaps else 0
    if not addresses_gaps:
        feedback_parts.append("Clearly identify content gaps or opportunities")

    # Check length
    if 50 <= word_count <= 200:
        scores["appropriate_length"] = 2
    elif word_count < 50:
        scores["appropriate_length"] = 0
        feedback_parts.append("Draft too short - provide more detailed suggestions")
    else:
        scores["appropriate_length"] = 0
        feedback_parts.append("Draft may be too long - aim for conciseness")

    # Check if actionable (contains verbs like add, create, implement, etc.)
    action_verbs = ['add', 'create', 'implement', 'include', 'improve', 'enhance', 'optimize']
    has_action = any(verb in draft_text.lower() for verb in action_verbs)

    scores["actionable"] = 2 if has_action else 0
    if not has_action:
        feedback_parts.append("Make suggestions more actionable with clear verbs")

    total_score = sum(scores.values())
    max_possible = 8
    passed = total_score >= 5

    if passed:
        feedback = "Content expansion draft is good"
        if feedback_parts:
            feedback += ". Consider: " + "; ".join(feedback_parts)
    else:
        feedback = "Content expansion draft needs improvement: " + "; ".join(feedback_parts)

    return {
        "overall_score": total_score,
        "max_possible": max_possible,
        "percentage": round((total_score / max_possible) * 100),
        "passed": passed,
        "feedback": feedback,
        "checks": scores,
        "word_count": word_count
    }


def check_bilingual_draft_quality(draft_text: str) -> Dict[str, Any]:
    """Check quality of bilingual draft (English and te reo Māori)."""
    if not draft_text or not isinstance(draft_text, str):
        return {
            "overall_score": 0,
            "passed": False,
            "feedback": "Draft is empty or not a string",
            "checks": {}
        }

    scores = {
        "has_english": 0,
        "has_maori": 0,
        "appropriate_length": 0,
        "notes_review_needed": 0
    }

    feedback_parts = []

    # Check for both languages (simple heuristic)
    has_english = len([c for c in draft_text if c.isalpha() and ord(c) < 128]) > 10
    # Very basic check for Māori characters - this is simplistic
    has_maori_indicators = any(
        char in draft_text for char in ['ā', 'ē', 'ī', 'ō', 'ū', 'Ā', 'Ē', 'Ī', 'Ō', 'Ū']
    ) or 'māori' in draft_text.lower() or 'te reo' in draft_text.lower()

    scores["has_english"] = 2 if has_english else 0
    scores["has_maori"] = 2 if has_maori_indicators else 0

    if not has_english:
        feedback_parts.append("Missing English content")
    if not has_maori_indicators:
        feedback_parts.append("Missing te reo Māori content or indicators")

    # Check length
    word_count = len(draft_text.split())
    if 30 <= word_count <= 250:
        scores["appropriate_length"] = 2
    elif word_count < 30:
        scores["appropriate_length"] = 0
        feedback_parts.append("Draft too short")
    else:
        scores["appropriate_length"] = 0
        feedback_parts.append("Draft may be too long")

    # Check for note about review needed
    needs_review = any(
        phrase in draft_text.lower()
        for phrase in [
            'requires review', 'needs review', 'should be reviewed',
            'fluent editorial review', 'expert review', 'review by'
        ]
    )

    scores["notes_review_needed"] = 2 if needs_review else 0
    if not needs_review:
        feedback_parts.append("Should note that Māori content requires fluent editorial review")

    total_score = sum(scores.values())
    max_possible = 8
    passed = total_score >= 5

    if passed:
        feedback = "Bilingual draft looks good"
        if feedback_parts:
            feedback += ". Consider: " + "; ".join(feedback_parts)
    else:
        feedback = "Bilingual draft needs improvement: " + "; ".join(feedback_parts)

    return {
        "overall_score": total_score,
        "max_possible": max_possible,
        "percentage": round((total_score / max_possible) * 100),
        "passed": passed,
        "feedback": feedback,
        "checks": scores,
        "word_count": len(draft_text.split())
    }


def check_platform_fix_draft_quality(draft_text: str) -> Dict[str, Any]:
    """Check quality of platform/CMS fix draft."""
    if not draft_text or not isinstance(draft_text, str):
        return {
            "overall_score": 0,
            "passed": False,
            "feedback": "Draft is empty or not a string",
            "checks": {}
        }

    scores = {
        "specific_platform": 0,
        "clear_steps": 0,
        "appropriate_length": 0,
        "actionable": 0
    }

    feedback_parts = []

    word_count = len(draft_text.split())

    # Check for specific platform/CMS mentions
    platform_indicators = [
        'wordpress', 'wp', 'joomla', 'drupal', 'shopify', 'magento',
        'squarespace', 'wix', 'webflow', 'ghost', 'craftcms',
        'concrete5', 'modx', 'textpattern', ' cms ', 'platform'
    ]

    has_platform = any(
        indicator in draft_text.lower()
        for indicator in platform_indicators
    )

    scores["specific_platform"] = 2 if has_platform else 0
    if not has_platform:
        feedback_parts.append("Consider mentioning specific CMS/platform if known")

    # Check for clear steps or implementation guidance
    step_indicators = [
        'step', 'first', 'second', 'then', 'next', 'finally',
        'to fix', 'how to', 'you can', 'simply', 'easily',
        'add', 'install', 'configure', 'update', 'modify'
    ]

    has_steps = any(
        indicator in draft_text.lower()
        for indicator in step_indicators
    )

    scores["clear_steps"] = 2 if has_steps else 0
    if not has_steps:
        feedback_parts.append("Include clearer implementation steps or guidance")

    # Check length
    if 40 <= word_count <= 180:
        scores["appropriate_length"] = 2
    elif word_count < 40:
        scores["appropriate_length"] = 0
        feedback_parts.append("Draft too short - provide more details")
    else:
        scores["appropriate_length"] = 0
        feedback_parts.append("Draft may be too long")

    # Check if actionable
    action_verbs = ['add', 'install', 'update', 'modify', 'change', 'fix', 'implement']
    has_action = any(verb in draft_text.lower() for verb in action_verbs)

    scores["actionable"] = 2 if has_action else 0
    if not has_action:
        feedback_parts.append("Make the fix more actionable with clear verbs")

    total_score = sum(scores.values())
    max_possible = 8
    passed = total_score >= 5

    if passed:
        feedback = "Platform fix draft is good"
        if feedback_parts:
            feedback += ". Consider: " + "; ".join(feedback_parts)
    else:
        feedback = "Platform fix draft needs improvement: " + "; ".join(feedback_parts)

    return {
        "overall_score": total_score,
        "max_possible": max_possible,
        "percentage": round((total_score / max_possible) * 100),
        "passed": passed,
        "feedback": feedback,
        "checks": scores,
        "word_count": word_count
    }


def run_quality_checks(drafts: Dict[str, Any], evidence_brief: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Run quality checks on all draft types.

    Args:
        drafts: Dictionary of drafts by type (from ai_worker.py)
        evidence_brief: Optional evidence brief for reference checking

    Returns:
        Dictionary with quality results for each draft type and overall assessment
    """
    results = {}

    # Check each draft type with appropriate validator
    if "metadata" in drafts:
        results["metadata"] = check_metadata_draft_quality(drafts["metadata"].get("text", ""))

    if "platform_fix" in drafts:
        results["platform_fix"] = check_platform_fix_draft_quality(drafts["platform_fix"].get("text", ""))

    if "outreach" in drafts:
        results["outreach"] = check_outreach_draft_quality(
            drafts["outreach"].get("text", ""),
            evidence_brief
        )

    if "content_expansion" in drafts:
        results["content_expansion"] = check_content_expansion_draft_quality(
            drafts["content_expansion"].get("text", "")
        )

    if "bilingual" in drafts:
        results["bilingual"] = check_bilingual_draft_quality(drafts["bilingual"].get("text", ""))

    # Calculate overall results
    passed_count = sum(1 for result in results.values() if result.get("passed", False))
    total_count = len(results)

    overall_passed = passed_count == total_count if total_count > 0 else False

    # Generate summary feedback
    if overall_passed:
        overall_feedback = f"All {total_count} drafts passed quality checks"
    else:
        failed_types = [k for k, v in results.items() if not v.get("passed", False)]
        overall_feedback = f"{passed_count}/{total_count} drafts passed. Failed: {', '.join(failed_types)}"

    return {
        "individual_results": results,
        "overall_passed": overall_passed,
        "passed_count": passed_count,
        "total_count": total_count,
        "feedback": overall_feedback
    }


if __name__ == "__main__":
    # Simple test
    sample_evidence_brief = {
        "metadata": {"health_score": 65, "total_defects": 3},
        "summary": {"overall_assessment": "Poor website with significant issues"},
        "evidence": {
            "key_findings": [
                {"finding": "No mobile viewport tag", "check": "no_mobile_viewport", "severity": "critical"},
                {"finding": "SSL certificate expired", "check": "ssl_expired", "severity": "critical"}
            ]
        },
        "talking_points": {
            "evidence_phrases": [
                "I noticed your website lacks a mobile viewport tag",
                "Your SSL certificate has expired"
            ]
        }
    }

    sample_drafts = {
        "outreach": {"text": "I noticed critical issues on your website that could be costing you business. Would it be useful to discuss these findings?"},
        "metadata": {"text": "Title: Improved Website Performance\nDescription: Learn how to fix critical website issues"},
        "platform_fix": {"text": "To fix the missing viewport issue in WordPress: Add <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"> to your theme's header.php file."},
        "content_expansion": {"text": "Consider adding a mobile-friendly section to your homepage that highlights your services. This would improve user experience for mobile visitors."},
        "bilingual": {"text": "English: I noticed critical issues on your website that need attention.\nMāori: Kua kite ahau i ngā take kritiko i tō tītoketanga tāhiko e hiahiatia ana i te tiakitanga.\nNote: Māori content requires fluent editorial review."}
    }

    results = run_quality_checks(sample_drafts, sample_evidence_brief)
    print("Quality Check Results:")
    print(f"Overall: {results['feedback']}")
    print(f"Passed: {results['overall_passed']}")
    for draft_type, result in results["individual_results"].items():
        print(f"{draft_type}: {result['feedback']} (Score: {result.get('overall_score', 0)}/{result.get('max_possible', 0)})")

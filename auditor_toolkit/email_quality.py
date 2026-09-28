"""Email quality validation for ensuring specific, compelling, and compliant outreach."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class QualityIssue:
    """Represents a quality issue found in an email draft."""
    issue_type: str  # 'blocking' or 'stylistic'
    category: str    # e.g., 'personalization', 'offer_clarity', 'call_to_action'
    message: str     # Human-readable description of the issue
    suggestion: str  # Suggested fix or improvement
    severity: str    # 'low', 'medium', 'high' - for styling issues only


@dataclass
class EmailQualityReport:
    """Results of email quality validation."""
    passed: bool
    blocking_issues: List[QualityIssue]
    stylistic_issues: List[QualityIssue]
    score: float  # 0-100, higher is better
    reviewed_at: datetime
    email_version: str = "email-quality-v1"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "passed": self.passed,
            "blocking_issues": [issue.__dict__ for issue in self.blocking_issues],
            "stylistic_issues": [issue.__dict__ for issue in self.stylistic_issues],
            "score": self.score,
            "reviewed_at": self.reviewed_at.isoformat(),
            "email_version": self.email_version
        }


class EmailQualityChecker:
    """Validates email drafts for quality, specificity, and compliance."""

    def __init__(self):
        # Words/phrases that indicate generic or unsupported claims
        self.generic_phrases = {
            "great website", "nice site", "love your", "impressive",
            "professional looking", "well done", "awesome", "fantastic",
            "amazing", "excellent", "outstanding", "superb"
        }

        # Words/phrases that indicate artificial urgency or pressure
        self.urgency_phrases = {
            "limited time", "act now", "don't miss out", "hurry",
            "expires soon", "last chance", "final offer", "closing soon",
            "time is running out", "don't delay", "immediate action"
        }

        # Words/phrases that indicate unsupported revenue claims
        self.revenue_claims = {
            "increase revenue", "boost sales", "double your", "triple your",
            "more customers", "more leads", "more business", "more profit",
            "more money", "more income", "more conversions", "more sales"
        }

        # Required opt-out phrases (at least one should be present)
        self.opt_out_phrases = {
            "unsubscribe", "opt out", "stop receiving", "remove me",
            "do not contact", "no further emails", "no more messages"
        }

        # Generic salutations to avoid
        self.generic_salutations = {
            "dear sir/madam", "to whom it may concern", "dear business owner",
            "hello there", "hi there", "greetings"
        }

    def validate_email(
        self,
        email_body: str,
        email_subject: str = "",
        evidence_brief: Optional[Dict[str, Any]] = None
    ) -> EmailQualityReport:
        """
        Validate an email draft for quality and compliance.

        Args:
            email_body: The body of the email to validate
            email_subject: The subject line of the email
            evidence_brief: Optional evidence brief to validate against

        Returns:
            EmailQualityReport with validation results
        """
        blocking_issues = []
        stylistic_issues = []

        # Combine subject and body for analysis
        full_text = f"{email_subject}\n\n{email_body}".lower()

        # 1. Check for supported personalization (blocking if missing)
        personalization_issues = self._check_personalization(email_body, email_subject, evidence_brief)
        blocking_issues.extend(personalization_issues)

        # 2. Check for clear primary offer (blocking if missing or unclear)
        offer_issues = self._check_offer_clarity(email_body, email_subject)
        blocking_issues.extend(offer_issues)

        # 3. Check for principal question or call to action (blocking if missing)
        cta_issues = self._check_call_to_action(email_body, email_subject)
        blocking_issues.extend(cta_issues)

        # 4. Check for complete sender information (blocking if incomplete)
        sender_issues = self._check_sender_identity(email_body, email_subject)
        blocking_issues.extend(sender_issues)

        # 5. Check for unfilled placeholders (blocking if found)
        placeholder_issues = self._check_unfilled_placeholders(email_body, email_subject)
        blocking_issues.extend(placeholder_issues)

        # 6. Check for unsupported claims or invented proof (blocking if found)
        claim_issues = self._check_unsupported_claims(full_text)
        blocking_issues.extend(claim_issues)

        # 7. Check for misleading reply subjects (stylistic)
        subject_issues = self._check_reply_subject(email_subject)
        stylistic_issues.extend(subject_issues)

        # 8. Check for repetitive or generic language (stylistic)
        language_issues = self._check_generic_language(full_text)
        stylistic_issues.extend(language_issues)

        # 9. Check for excessive length (stylistic)
        length_issues = self._check_excessive_length(email_body)
        stylistic_issues.extend(length_issues)

        # 10. Check for proper opt-out wording (blocking if missing for commercial email)
        opt_out_issues = self._check_opt_out_wording(email_body)
        blocking_issues.extend(opt_out_issues)

        # Calculate overall score (0-100)
        blocking_count = len(blocking_issues)
        stylistic_count = len(stylistic_issues)

        # Base score: 100 minus penalties
        score = 100.0
        score -= blocking_count * 15  # Each blocking issue costs 15 points
        score -= stylistic_count * 5   # Each stylistic issue costs 5 points
        score = max(0.0, score)        # Don't go below 0

        # Email passes if no blocking issues
        passed = blocking_count == 0

        return EmailQualityReport(
            passed=passed,
            blocking_issues=blocking_issues,
            stylistic_issues=stylistic_issues,
            score=score,
            reviewed_at=datetime.now()
        )

    def _check_personalization(
        self,
        body: str,
        subject: str,
        evidence_brief: Optional[Dict[str, Any]]
    ) -> List[QualityIssue]:
        """Check for supported personalization."""
        issues = []
        combined = f"{subject} {body}".lower()

        # Check for business name mention
        if evidence_brief and "business_name" in evidence_brief:
            business_name = evidence_brief["business_name"].lower()
            if business_name not in combined:
                issues.append(QualityIssue(
                    issue_type="blocking",
                    category="personalization",
                    message="Email does not mention the business name",
                    suggestion=f"Include the business name '{evidence_brief['business_name']}' to show this is not a generic template",
                    severity="high"
                ))
        else:
            # Even without evidence brief, check for any specific personalization
            personalization_indicators = [
                "your website", "your business", "your company",
                "i noticed on your site", "when i visited",
                "based on my review of", "during my analysis"
            ]
            has_personalization = any(indicator in combined for indicator in personalization_indicators)
            if not has_personalization:
                issues.append(QualityIssue(
                    issue_type="blocking",
                    category="personalization",
                    message="Email lacks specific personalization - appears to be a generic template",
                    suggestion="Add specific reference to the recipient's website, business, or recent observation",
                    severity="high"
                ))

        return issues

    def _check_offer_clarity(
        self,
        body: str,
        subject: str
    ) -> List[QualityIssue]:
        """Check for clear primary offer."""
        issues = []
        combined = f"{subject} {body}".lower()

        # Count how many different services/offers are mentioned
        service_indicators = [
            "audit", "consultation", "analysis", "review", "assessment",
            "optimization", "improvement", "fix", "redesign", "development",
            "marketing", "seo", "social media", "content", "design",
            "development", "programming", "coding", "training", "support"
        ]

        mentioned_services = [service for service in service_indicators if service in combined]

        if len(mentioned_services) == 0:
            issues.append(QualityIssue(
                issue_type="blocking",
                category="offer_clarity",
                message="No clear service or offer mentioned in email",
                suggestion="Clearly state what specific service you are offering to help the business",
                severity="high"
            ))
        elif len(mentioned_services) > 3:
            issues.append(QualityIssue(
                issue_type="stylistic",
                category="offer_clarity",
                message=f"Too many services mentioned ({len(mentioned_services)}): {', '.join(mentioned_services[:5])}...",
                suggestion="Focus on one primary service offering to avoid overwhelming the recipient",
                severity="medium"
            ))

        return issues

    def _check_call_to_action(
        self,
        body: str,
        subject: str
    ) -> List[QualityIssue]:
        """Check for principal question or call to action."""
        issues = []
        combined = f"{subject} {body}".lower()

        # Check for clear next step/request
        cta_indicators = [
            "reply", "respond", "answer", "write back", "get in touch",
            "call me", "phone me", "text me", "email me back",
            "let me know", "tell me what you think", "what do you think",
            "thoughts?", "opinion?", "feedback?", "available for a call",
            "free to chat", "schedule a call", "book a meeting",
            "yes/no", "interested?", "would you like", "could we",
            "shall we", "can i send", "may i share"
        ]

        has_cta = any(indicator in combined for indicator in cta_indicators)

        if not has_cta:
            issues.append(QualityIssue(
                issue_type="blocking",
                category="call_to_action",
                message="Email lacks a clear call to action or question for the recipient",
                suggestion="End with a clear, low-pressure next step like asking for their thoughts or availability for a brief chat",
                severity="high"
            ))

        return issues

    def _check_sender_identity(
        self,
        body: str,
        subject: str
    ) -> List[QualityIssue]:
        """Check for complete sender identity."""
        issues = []
        combined = f"{subject} {body}".lower()

        # Check for sender name or business
        name_indicators = [
            "i am", "this is", "my name is", "from ",
            "at ", "with ", "representing ",
            "best regards", "sincerely", "cheers", "thanks",
            "regards", "warmly"
        ]

        has_sender_closure = any(indicator in combined for indicator in name_indicators)

        if not has_sender_closure:
            issues.append(QualityIssue(
                issue_type="blocking",
                category="sender_identity",
                message="Email lacks clear sender identification or closing",
                suggestion="End with your name, business name, and contact information",
                severity="medium"
            ))

        # Check for contact information
        contact_indicators = [
            "@", "phone", "call", "text", "website",
            "contact", "reach", "get in touch"
        ]

        has_contact_info = any(indicator in combined for indicator in contact_indicators)

        if not has_contact_info:
            issues.append(QualityIssue(
                issue_type="stylistic",
                category="sender_identity",
                message="Email lacks clear contact information for follow-up",
                suggestion="Include at least one way to contact you (email, phone, website)",
                severity="low"
            ))

        return issues

    def _check_unfilled_placeholders(
        self,
        body: str,
        subject: str
    ) -> List[QualityIssue]:
        """Check for unfilled template placeholders."""
        issues = []
        combined = f"{subject} {body}"

        # Common placeholder patterns
        placeholder_patterns = [
            r"\{[^}]+\}",           # {placeholder}
            r"\[[^\]]+\]",          # [placeholder]
            r"<[^>]+>",             # <placeholder>
            r"_[^_]+_",             # _placeholder_
            r"\*{2}[^\*]+\*{2}",    # **placeholder**
            r"/{2}[^/]+/{2}",       # //placeholder//
            r"your\s+\w+\s+here",   # your [something] here
            r"insert\s+\w+",        # insert [something]
            r"todo:",               # todo:
            r"fixme:",              # fixme:
            r"xxx+",                # xxx or xxxx
            r"[^\w]test[^\w]",      # test as standalone word
            r"[^\w]example[^\w]"    # example as standalone word
        ]

        for pattern in placeholder_patterns:
            matches = re.findall(pattern, combined, re.IGNORECASE)
            if matches:
                issues.append(QualityIssue(
                    issue_type="blocking",
                    category="placeholders",
                    message=f"Unfilled template placeholder found: '{matches[0]}'",
                    suggestion="Replace all placeholders with actual personalized content before sending",
                    severity="high"
                ))
                break  # Only report first instance to avoid spam

        return issues

    def _check_unsupported_claims(self, text: str) -> List[QualityIssue]:
        """Check for unsupported claims or invented proof."""
        issues = []

        # Check for generic praise
        for phrase in self.generic_phrases:
            if phrase in text:
                issues.append(QualityIssue(
                    issue_type="blocking",
                    category="claims",
                    message=f"Contains generic, unsupported praise: '{phrase}'",
                    suggestion="Replace with specific observation from your audit or research",
                    severity="high"
                ))
                break  # Only report first instance

        # Check for artificial urgency
        for phrase in self.urgency_phrases:
            if phrase in text:
                issues.append(QualityIssue(
                    issue_type="blocking",
                    category="claims",
                    message=f"Contains artificial urgency: '{phrase}'",
                    suggestion="Remove time pressure - let the recipient decide their own timeline",
                    severity="high"
                ))
                break

        # Check for unsupported revenue/business claims
        for phrase in self.revenue_claims:
            if phrase in text:
                issues.append(QualityIssue(
                    issue_type="blocking",
                    category="claims",
                    message=f"Contains unsupported business outcome claim: '{phrase}'",
                    suggestion="Focus on specific, observable improvements you can actually deliver",
                    severity="high"
                ))
                break

        # Check for specific invented metrics
        metric_patterns = [
            r"\d+%\s+increase",           # "25% increase"
            r"\d+%\s+more",               # "50% more"
            r"\d+x\s+growth",             # "2x growth"
            r"double\s+your\s+\w+",       # "double your traffic"
            r"triple\s+your\s+\w+",       # "triple your sales"
            r"increase\s+by\s+\d+%",      # "increase by 30%"
            r"boost\s+by\s+\d+%",         # "boost by 40%"
            r"improve\s+by\s+\d+%",       # "improve by 25%"
        ]

        for pattern in metric_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                issues.append(QualityIssue(
                    issue_type="blocking",
                    category="claims",
                    message="Contains specific, unsupported metric improvement claim",
                    suggestion="Remove unverified metrics or replace with observations from your actual audit",
                    severity="high"
                ))
                break

        return issues

    def _check_reply_subject(self, subject: str) -> List[QualityIssue]:
        """Check for misleading reply subjects (for follow-ups)."""
        issues = []
        subject_lower = subject.lower().strip()

        # Check if this looks like a reply but has misleading subject
        reply_indicators = ["re:", "aw:", "fw:", "fwd:"]
        is_reply_format = any(subject_lower.startswith(indicator) for indicator in reply_indicators)

        if is_reply_format:
            # Check if the actual content after RE: is misleading
            actual_subject = subject_lower
            for indicator in reply_indicators:
                if actual_subject.startswith(indicator):
                    actual_subject = actual_subject[len(indicator):].strip()
                    break

            # Check if it's trying to restart a conversation misleadingly
            misleading_starts = [
                "checking in", "following up", "just wanted to",
                "i hope youre well", "hope youre doing well",
                "quick question", "brief question"
            ]

            if any(actual_subject.startswith(misleading) for misleading in misleading_starts):
                issues.append(QualityIssue(
                    issue_type="stylistic",
                    category="reply_subject",
                    message=f"Reply subject may be misleading: '{subject}'",
                    suggestion="If this is a genuine reply, keep the original subject. If starting new conversation, use clear subject line",
                    severity="medium"
                ))

        return issues

    def _check_generic_language(self, text: str) -> List[QualityIssue]:
        """Check for repetitive or generic language."""
        issues = []

        # Check for overused business jargon
        buzzwords = {
            "leverage", "synergy", "paradigm shift", "disrupt", "disruptive",
            "game changer", "cutting edge", "state of the art", "best in class",
            "next generation", "innovative", "revolutionary", "transformative",
            "holistic approach", "turnkey solution", "end to end", "seamless",
            "frictionless", "pain point", "value add", "value added",
            "win win", "win-win", "low hanging fruit", "move the needle"
        }

        found_buzzwords = [word for word in buzzwords if word in text]
        if len(found_buzzwords) >= 3:
            issues.append(QualityIssue(
                issue_type="stylistic",
                category="language",
                message=f"Contains excessive business jargon: {', '.join(found_buzzwords[:5])}",
                suggestion="Use plain, direct language instead of buzzwords",
                severity="medium"
            ))

        # Check for repeated sentences or phrases (simple check)
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip().lower() for s in sentences if s.strip()]

        # Look for exact duplicates
        seen = set()
        duplicates = []
        for sentence in sentences:
            if sentence in seen and len(sentence) > 10:  # Ignore very short sentences
                duplicates.append(sentence)
            else:
                seen.add(sentence)

        if duplicates:
            issues.append(QualityIssue(
                issue_type="stylistic",
                category="language",
                message="Contains repetitive sentences or phrases",
                suggestion="Vary your language and avoid repeating the same exact phrases",
                severity="low"
            ))

        return issues

    def _check_excessive_length(self, body: str) -> List[QualityIssue]:
        """Check for excessive length."""
        issues = []

        # Count words
        word_count = len(body.split())

        # Different thresholds for different contexts
        if word_count > 200:
            issues.append(QualityIssue(
                issue_type="stylistic",
                category="length",
                message=f"Email is very long ({word_count} words)",
                suggestion="Consider shortening to respect recipient's time - aim for under 150 words",
                severity="medium"
            ))
        elif word_count > 150:
            issues.append(QualityIssue(
                issue_type="stylistic",
                category="length",
                message=f"Email is on the longer side ({word_count} words)",
                suggestion="Could be shortened for better readability - ideal range is 70-130 words for first contact",
                severity="low"
            ))

        return issues

    def _check_opt_out_wording(self, body: str) -> List[QualityIssue]:
        """Check for proper opt-out wording (required for commercial emails)."""
        issues = []
        text_lower = body.lower()

        # Check if this looks like a commercial/marketing email
        commercial_indicators = [
            "offer", "service", "help", "improve", "increase", "boost",
            "audit", "consultation", "proposal", "quote", "price",
            "cost", "fee", "payment", "invoice", "bill",
            "business", "company", "website", "online", "digital"
        ]

        is_commercial = any(indicator in text_lower for indicator in commercial_indicators)

        if is_commercial:
            # Check for opt-out mechanism
            has_opt_out = any(phrase in text_lower for phrase in self.opt_out_phrases)

            if not has_opt_out:
                issues.append(QualityIssue(
                    issue_type="blocking",
                    category="opt_out",
                    message="Commercial email lacks clear opt-out mechanism",
                    suggestion="Include a clear way to opt out, such as 'Reply with \"unsubscribe\" to stop receiving emails'",
                    severity="high"
                ))

        return issues


# Convenience function for easy usage
def validate_email_quality(
    email_body: str,
    email_subject: str = "",
    evidence_brief: Optional[Dict[str, Any]] = None
) -> EmailQualityReport:
    """
    Validate email quality with default checker.

    Args:
        email_body: The body of the email to validate
        email_subject: The subject line of the email
        evidence_brief: Optional evidence brief to validate against

    Returns:
        EmailQualityReport with validation results
    """
    checker = EmailQualityChecker()
    return checker.validate_email(email_body, email_subject, evidence_brief)


# Example usage and testing
if __name__ == "__main__":
    # Example of a good email
    good_email = """
    Hi Sarah,

    I was reviewing bubblyplumbing.co.nz and noticed that your contact form requires users to
    specify whether they need residential or commercial service before they can submit an inquiry.

    This extra step might be causing some potential customers to abandon the inquiry process,
    especially those who are unsure which category they fall into or who have mixed needs.

    A simple improvement would be to make the service type selection optional, or to add a
    "Both residential and commercial" option, or to route all inquiries to a central team that
    can triage them internally.

    I help NZ plumbing businesses optimize their inquiry flow to capture more leads.
    If you'd like to see a quick audit of your current contact form effectiveness,
    I'd be happy to share what I found - no obligation.

    Best regards,
    Mike Johnson
    NZ Plumbing Optimization Co
    mike@nzplumbingopt.co.nz
    021 123 4567
    Reply "unsubscribe" to opt out
    """

    # Example of a problematic email
    bad_email = """
    Dear Business Owner,

    I noticed your website is great and has lots of potential! I can help you increase your
    revenue by 50% and get more customers! My amazing SEO services will boost your sales
    and triple your online visibility! This is a limited time offer - act now!

    We offer website design, SEO optimization, social media marketing, content creation,
    email marketing, PPC advertising, and conversion rate optimization!

    Let me know if you're interested in learning more about how we can help your business grow!

    Best regards,
    Marketing Expert
    """

    print("=== Testing Good Email ===")
    good_report = validate_email_quality(good_email, "Quick question about your contact form")
    print(f"Passed: {good_report.passed}")
    print(f"Score: {good_report.score:.1f}/100")
    print(f"Blocking Issues: {len(good_report.blocking_issues)}")
    print(f"Stylistic Issues: {len(good_report.stylistic_issues)}")

    if good_report.blocking_issues:
        print("\nBlocking Issues:")
        for issue in good_report.blocking_issues:
            print(f"  - [{issue.category}] {issue.message}")

    if good_report.stylistic_issues:
        print("\nStylistic Issues:")
        for issue in good_report.stylistic_issues:
            print(f"  - [{issue.category}] {issue.message}")

    print("\n" + "="*50 + "\n")

    print("=== Testing Bad Email ===")
    bad_report = validate_email_quality(bad_email, "AMAZING LIMITED TIME OFFER!!!")
    print(f"Passed: {bad_report.passed}")
    print(f"Score: {bad_report.score:.1f}/100")
    print(f"Blocking Issues: {len(bad_report.blocking_issues)}")
    print(f"Stylistic Issues: {len(bad_report.stylistic_issues)}")

    if bad_report.blocking_issues:
        print("\nBlocking Issues:")
        for issue in bad_report.blocking_issues:
            print(f"  - [{issue.category}] {issue.message}")

    if bad_report.stylistic_issues:
        print("\nStylistic Issues:")
        for issue in bad_report.stylistic_issues:
            print(f"  - [{issue.category}] {issue.message}")

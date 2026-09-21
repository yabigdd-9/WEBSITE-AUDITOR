#!/usr/bin/env python3
"""
Demonstration of how the improvements work together.
This shows the flow from audit → evidence brief → email generation → quality check.
"""

from auditor_toolkit.evidence_brief import create_evidence_birth_from_audit, explain_opportunity_score
from auditor_toolkit.email_quality import validate_email_quality

def demo_improvement_flow():
    """Demonstrate the complete improvement flow."""

    print("🚀 Website Auditor Improvement Demo")
    print("=" * 50)

    # Step 1: Simulate an audit result (what we would get from website_auditor.py)
    print("\n📋 STEP 1: Website Audit Result")
    print("-" * 30)
    audit_result = {
        "url": "https://bubblyplumbing.co.nz",
        "domain": "bubblyplumbing.co.nz",
        "score": 42,
        "status": "complete",
        "defects": [
            {
                "defect": "Contact form requires service type selection",
                "impact": "Extra step may cause potential customers to abandon inquiry process",
                "severity": "medium"
            },
            {
                "defect": "No clear CTA above the fold",
                "impact": "Visitors may not know what action to take next",
                "severity": "low"
            },
            {
                "defect": "Missing meta description",
                "impact": "Lower click-through rate from search results",
                "severity": "low"
            }
        ]
    }

    print(f"Domain: {audit_result['domain']}")
    print(f"Score: {audit_result['score']}/100")
    print(f"Defects Found: {len(audit_result['defects'])}")
    for defect in audit_result['defects']:
        print(f"  • {defect['defect']} ({defect['severity']})")

    # Step 2: Generate structured evidence brief
    print("\n📝 STEP 2: Structured Evidence Brief Generation")
    print("-" * 45)

    sender_info = {
        "identity": "Mike Johnson - NZ Plumbing Optimization Co",
        "offer": "Free inquiry flow audit and optimization consultation"
    }

    evidence_brief = create_evidence_birth_from_audit(
        business_name="Bubbly Plumbing Ltd",
        domain="bubblyplumbing.co.nz",
        audit_result=audit_result,
        sender_info=sender_info,
        service_offered="Plumbing business inquiry optimization"
    )

    print(f"Business: {evidence_brief.business_name}")
    print(f"Observation: {evidence_brief.observation}")
    print(f"Evidence Confidence: {evidence_brief.evidence_confidence} ({evidence_brief.get_confidence_level()})")
    print(f"Recommendation: {evidence_brief.recommended_improvement}")
    print(f"Sender: {evidence_brief.sender_identity}")
    print(f"Offer: {evidence_brief.supported_offer}")

    # Step 3: Generate email based on evidence brief (simulated)
    print("\n✉️  STEP 3: Email Generation Based on Evidence Brief")
    print("-" * 50)

    # This would normally come from ai_writer.py using the evidence_brief
    generated_email = """Hi Bubbly Plumbing Ltd,

I was reviewing bubblyplumbing.co.nz and noticed that your contact form requires users to
specify whether they need residential or commercial service before they can submit an inquiry.

This extra step might be causing some potential customers to abandon the inquiry process,
especially those who are unsure which category they fall into or who have mixed needs.

A simple improvement would be to make the service type selection optional - allowing all
visitors to submit inquiries without this initial filtering step.

I specialize in helping NZ plumbing businesses optimize their online inquiry forms to
capture more legitimate service requests.

If you'd like me to share what I found during my quick review of your contact form,
I'd be happy to send over my notes - no obligation or sales pitch.

Best regards,
Mike Johnson
NZ Plumbing Optimization Co
mike@nzplumbingopt.co.nz
021 123 4567
Reply "unsubscribe" to opt out of future emails"""

    generated_subject = "Quick question about your contact form flow"

    print(f"Subject: {generated_subject}")
    print("Email Preview:")
    print("-" * 30)
    print(generated_email.strip())

    # Step 4: Quality check the generated email
    print("\n🔍 STEP 4: Email Quality Validation")
    print("-" * 35)

    quality_report = validate_email_quality(
        email_body=generated_email,
        email_subject=generated_subject,
        evidence_brief=evidence_brief.to_dict()
    )

    print(f"✅ Quality Check Passed: {quality_report.passed}")
    print(f"📊 Quality Score: {quality_report.score:.1f}/100")

    if quality_report.blocking_issues:
        print("\n🚫 Blocking Issues (must fix before sending):")
        for issue in quality_report.blocking_issues:
            print(f"  • [{issue.category}] {issue.message}")
            print(f"    💡 Suggestion: {issue.suggestion}")

    if quality_report.stylistic_issues:
        print("\n⚠️  Stylistic Issues (consider improving):")
        for issue in quality_report.stylistic_issues:
            print(f"  • [{issue.category}] {issue.message}")
            print(f"    💡 Suggestion: {issue.suggestion}")

    if not quality_report.blocking_issues and not quality_report.stylistic_issues:
        print("\n🎉 Email passes all quality checks! Ready to send.")

    # Step 5: Show opportunity score explanation
    print("\n📈 STEP 5: Opportunity Score Explanation")
    print("-" * 38)

    # Simulate opportunity components that would come from the P9 scoring
    opportunity_components = {
        "need": 0.7,           # Clear contact form issue affecting conversions
        "business_value": 0.6, # Plumbing business likely has good ability to pay
        "contactability": 0.8, # We have contact info from website/form
        "fixability": 0.9,     # This is a relatively simple UI/UX fix
        "confidence": 0.85,    # Good evidence from audit + clear observation
        "effort": 0.2          # Very low effort to implement the fix
    }

    explanation = explain_opportunity_score(opportunity_components)
    print(explanation)

    print("\n" + "=" * 50)
    print("✨ Improvement Flow Complete!")
    print("   Audit → Evidence Brief → Personalized Email → Quality Checked")
    print("=" * 50)

if __name__ == "__main__":
    demo_improvement_flow()
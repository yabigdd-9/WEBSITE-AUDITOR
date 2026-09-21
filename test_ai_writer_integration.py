#!/usr/bin/env python3
"""
Test script for AI Writer evidence brief integration
"""

from ai_writer import generate_email_from_evidence_brief, generate_email_subject_from_evidence_brief

def test_ai_writer_integration():
    """Test that AI writer can generate emails from evidence briefs"""

    print("🧪 Testing AI Writer Evidence Brief Integration")
    print("=" * 50)

    # Sample evidence brief (similar to what would come from pipeline)
    evidence_brief = {
        "business_name": "Bubbly Plumbing Ltd",
        "relevant_service": "Plumbing business inquiry optimization",
        "source_url": "https://bubblyplumbing.co.nz",
        "capture_date": "2026-09-22T14:30:22+12:00",
        "observation": "Contact form requires service type selection - Extra step may cause potential customers to abandon inquiry process",
        "evidence_confidence": 0.95,
        "evidence_limitations": ["Audit based on public website analysis only"],
        "recommended_improvement": "Make the service type selection optional - allowing all visitors to submit inquiries without this initial filtering step",
        "existing_customer_requests": [],
        "sender_identity": "Mike Johnson - NZ Plumbing Optimization Co",
        "supported_offer": "Free inquiry flow audit and optimization consultation",
        "contact_history": [],
        "excluded_topics": [],
        "brief_version": "evidence-brief-v1",
        "generated_at": "2026-09-22T14:30:22+12:00"
    }

    print("\n📋 Input Evidence Brief:")
    print(f"   Business: {evidence_brief['business_name']}")
    print(f"   Observation: {evidence_brief['observation']}")
    print(f"   Recommendation: {evidence_brief['recommended_improvement']}")

    print("\n📧 Generating email subject...")
    subject = generate_email_subject_from_evidence_brief(evidence_brief)
    print(f"   Subject: {subject}")

    print("\n📝 Generating email body...")
    email_body = generate_email_from_evidence_brief(evidence_brief, "first_contact")
    print(f"   Email Body:\n{email_body}")

    print("\n" + "=" * 50)
    print("✅ AI Writer integration test completed successfully!")
    print("📧 The AI writer can now generate personalized emails from evidence briefs")

    return True

if __name__ == "__main__":
    success = test_ai_writer_integration()
    exit(0 if success else 1)
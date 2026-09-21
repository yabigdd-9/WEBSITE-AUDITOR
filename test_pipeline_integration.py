#!/usr/bin/env python3
"""
Test script to verify evidence brief integration in pipeline.py
"""

from auditor_toolkit.pipeline import run_audit, AuditOptions
from auditor_toolkit.evidence_brief import EvidenceBrief
import json

def test_evidence_brief_integration():
    """Test that evidence brief is generated and included in audit report."""

    # Create a simple test audit options
    opts = AuditOptions(
        max_pages=2,
        max_depth=1,
        ai=False,  # Disable AI for faster testing
        cache=False,
        output_root=Path("./test_output")
    )

    # Run audit on a simple test site
    # Using a known test site that should work
    test_url = "https://httpbin.org/html"  # Simple test endpoint

    try:
        print(f"Running audit on {test_url}...")
        report = run_audit(test_url, opts)

        # Check if evidence brief was generated
        if "evidence_brief" in report:
            print("✅ Evidence brief found in audit report")
            evidence_brief = report["evidence_brief"]
            print(f"   Business: {evidence_brief.get('business_name', 'N/A')}")
            print(f"   Observation: {evidence_brief.get('observation', 'N/A')[:100]}...")
            print(f"   Confidence: {evidence_brief.get('evidence_confidence', 'N/A')}")

            # Verify it's a valid EvidenceBrief structure
            required_fields = ['business_name', 'observation', 'evidence_confidence', 'recommended_improvement']
            missing_fields = [field for field in required_fields if field not in evidence_brief]

            if not missing_fields:
                print("✅ Evidence brief contains all required fields")
                return True
            else:
                print(f"❌ Evidence brief missing fields: {missing_fields}")
                return False
        else:
            print("❌ Evidence brief not found in audit report")
            print(f"   Available keys: {list(report.keys())}")
            return False

    except Exception as e:
        print(f"❌ Error running audit: {e}")
        return False

if __name__ == "__main__":
    from pathlib import Path
    success = test_evidence_brief_integration()
    if success:
        print("\n🎉 Integration test passed!")
    else:
        print("\n💥 Integration test failed!")
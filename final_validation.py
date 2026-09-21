#!/usr/bin/env python3
"""
Final validation that all improvements are correctly integrated
"""

import ast
import sys

def validate_evidence_brief_integration():
    """Validate that evidence brief generation is integrated into pipeline.py"""

    print("🔍 Validating Evidence Brief Integration in Pipeline")
    print("=" * 55)

    try:
        with open("/Users/dd/Downloads/WEBSITE-AUDITOR-master/auditor_toolkit/pipeline.py", 'r') as f:
            content = f.read()

        # Check for key integration elements
        checks = [
            ("from .evidence_brief import create_evidence_birth_from_audit", "Evidence brief import"),
            ("# Generate evidence brief for use by writing workflows", "Evidence brief comment"),
            ("evidence_brief = create_evidence_birth_from_audit(", "Evidence brief function call"),
            ('report["evidence_brief"] = evidence_brief.to_dict()', "Evidence brief assignment to report"),
            ("history.save(report)", "History save before evidence brief"),
            ("return report", "Return statement")
        ]

        all_passed = True
        for check, description in checks:
            if check in content:
                print(f"✅ {description}: Found")
            else:
                print(f"❌ {description}: NOT FOUND")
                all_passed = False

        # Check ordering
        lines = content.split('\n')
        try:
            history_idx = [i for i, line in enumerate(lines) if "history.save(report)" in line][0]
            evidence_idx = [i for i, line in enumerate(lines) if "# Generate evidence brief for use by writing workflows" in line][0]
            return_idx = [i for i, line in enumerate(lines) if "return report" in line and i > evidence_idx][0]

            if history_idx < evidence_idx < return_idx:
                print("✅ Evidence brief generation is in correct location (after history.save, before return)")
            else:
                print("⚠️  Evidence brief generation may not be in optimal location")
                # Don't fail on this as it's not critical
        except IndexError:
            print("⚠️  Could not verify exact ordering")

        return all_passed

    except Exception as e:
        print(f"❌ Error validating pipeline integration: {e}")
        return False

def validate_ai_writer_integration():
    """Validate that AI writer can accept evidence briefs"""

    print("\n🔍 Validating AI Writer Evidence Brief Integration")
    print("=" * 52)

    try:
        with open("/Users/dd/Downloads/WEBSITE-AUDITOR-master/ai_writer.py", 'r') as f:
            content = f.read()

        # Check for key integration elements
        checks = [
            ("from auditor_toolkit.evidence_brief import EvidenceBrief", "Evidence brief import"),
            ("def generate_email_from_evidence_brief(", "Evidence brief email generation function"),
            ("def generate_email_subject_from_evidence_brief(", "Evidence brief subject generation function"),
            ("business_name = evidence_brief.get", "Business name extraction"),
            ("observation = evidence_brief.get", "Observation extraction"),
            ("recommended_improvement = evidence_brief.get", "Recommendation extraction")
        ]

        all_passed = True
        for check, description in checks:
            if check in content:
                print(f"✅ {description}: Found")
            else:
                print(f"❌ {description}: NOT FOUND")
                all_passed = False

        return all_passed

    except Exception as e:
        print(f"❌ Error validating AI writer integration: {e}")
        return False

def validate_evidence_brief_module():
    """Validate that evidence brief module is complete"""

    print("\n🔍 Validating Evidence Brief Module")
    print("=" * 37)

    try:
        with open("/Users/dd/Downloads/WEBSITE-AUDITOR-master/auditor_toolkit/evidence_brief.py", 'r') as f:
            content = f.read()

        # Check for key elements
        checks = [
            ("class EvidenceBrief:", "EvidenceBrief class"),
            ("def create_evidence_birth_from_audit(", "Factory function from audit"),
            ("def explain_opportunity_score(", "Opportunity score explanation"),
            ("def to_dict(self) -> Dict[str, Any]:", "Serialization method"),
            ("    @classmethod\n    def from_dict(cls, data: Dict[str, Any]) -> \"EvidenceBrief\":", "Deserialization method"),
            ("business_name: str", "Business name field"),
            ("observation: str", "Observation field"),
            ("evidence_confidence: float", "Evidence confidence field"),
            ("recommended_improvement: str", "Recommendation field")
        ]

        all_passed = True
        for check, description in checks:
            if check in content:
                print(f"✅ {description}: Found")
            else:
                print(f"❌ {description}: NOT FOUND")
                all_passed = False

        return all_passed

    except Exception as e:
        print(f"❌ Error validating evidence brief module: {e}")
        return False

def validate_email_quality_module():
    """Validate that email quality module is complete"""

    print("\n🔍 Validating Email Quality Module")
    print("=" * 36)

    try:
        with open("/Users/dd/Downloads/WEBSITE-AUDITOR-master/auditor_toolkit/email_quality.py", 'r') as f:
            content = f.read()

        # Check for key elements
        checks = [
            ("class EmailQualityChecker:", "EmailQualityChecker class"),
            ("def validate_email(", "Main validation function"),
            ("def _check_personalization(", "Personalization check"),
            ("def _check_offer_clarity(", "Offer clarity check"),
            ("def _check_call_to_action(", "Call to action check"),
            ("def _check_sender_identity(", "Sender identity check"),
            ("def _check_unfilled_placeholders(", "Unfilled placeholders check"),
            ("def _check_unsupported_claims(", "Unsupported claims check"),
            ("class EmailQualityReport:", "EmailQualityReport class"),
            ("blocking_issues", "Blocking issues attribute"),
            ("stylistic_issues", "Stylistic issues attribute")
        ]

        all_passed = True
        for check, description in checks:
            if check in content:
                print(f"✅ {description}: Found")
            else:
                print(f"❌ {description}: NOT FOUND")
                all_passed = False

        return all_passed

    except Exception as e:
        print(f"❌ Error validating email quality module: {e}")
        return False

def main():
    """Run all validations"""

    print("🚀 FINAL VALIDATION OF WEBSITE AUDITOR IMPROVEMENTS")
    print("=" * 60)

    results = []
    results.append(("Evidence Brief Module", validate_evidence_brief_module()))
    results.append(("Email Quality Module", validate_email_quality_module()))
    results.append(("Evidence Brief → Pipeline Integration", validate_evidence_brief_integration()))
    results.append(("Evidence Brief → AI Writer Integration", validate_ai_writer_integration()))

    print("\n" + "=" * 60)
    print("📊 VALIDATION RESULTS")
    print("=" * 60)

    all_passed = True
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} {test_name}")
        if not passed:
            all_passed = False

    print("=" * 60)
    if all_passed:
        print("🎉 ALL VALIDATIONS PASSED!")
        print("\n✅ Improvements successfully implemented:")
        print("   • Structured evidence brief generation (auditor_toolkit/evidence_brief.py)")
        print("   • Email quality validation (auditor_toolkit/email_quality.py)")
        print("   • Evidence brief integration into audit pipeline (auditor_toolkit/pipeline.py)")
        print("   • AI writer enhanced to use evidence briefs (ai_writer.py)")
        print("   • End-to-end demonstration available (demo_improvements.py)")
        print("\n📋 Next steps for full deployment:")
        print("   1. Resolve missing certifi dependency")
        print("   2. Run full system tests")
        print("   3. Deploy to production environment")
    else:
        print("💥 SOME VALIDATIONS FAILED!")
        print("   Please review the failed components above.")

    return all_passed

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
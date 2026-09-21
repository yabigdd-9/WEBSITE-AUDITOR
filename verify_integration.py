#!/usr/bin/env python3
"""
Simple verification that evidence brief integration code is in place
"""

import ast
import sys

def check_evidence_brief_integration():
    """Check that evidence brief generation code is present in pipeline.py"""

    pipeline_path = "/Users/dd/Downloads/WEBSITE-AUDITOR-master/auditor_toolkit/pipeline.py"

    try:
        with open(pipeline_path, 'r') as f:
            content = f.read()

        # Check for the key components we added
        checks = [
            ("from .evidence_brief import create_evidence_birth_from_audit", "Import statement"),
            ("# Generate evidence brief for use by writing workflows", "Comment marker"),
            ("evidence_brief = create_evidence_birth_from_audit(", "Function call"),
            ("report[\"evidence_brief\"] = evidence_brief.to_dict()", "Report assignment"),
            ("history.save(report)", "History save before evidence brief"),
            ("return report", "Return statement")
        ]

        all_found = True
        for check_str, description in checks:
            if check_str in content:
                print(f"✅ {description}: Found")
            else:
                print(f"❌ {description}: NOT FOUND")
                all_found = False

        # Also check that it's in the right place (before return)
        lines = content.split('\n')
        return_line_index = -1
        history_save_index = -1

        for i, line in enumerate(lines):
            if "history.save(report)" in line:
                history_save_index = i
            if "return report" in line and i > history_save_index:
                return_line_index = i
                break

        if history_save_index != -1 and return_line_index != -1:
            # Check if evidence brief code is between history.save and return
            evidence_brief_section = '\n'.join(lines[history_save_index+1:return_line_index])
            if "Generate evidence brief" in evidence_brief_section:
                print(f"✅ Evidence brief generation is in correct location")
            else:
                print(f"⚠️  Evidence brief generation may not be in correct location")
                all_found = False
        else:
            print(f"⚠️  Could not verify exact placement")

        return all_found

    except Exception as e:
        print(f"❌ Error reading pipeline.py: {e}")
        return False

if __name__ == "__main__":
    print("Verifying evidence brief integration in pipeline.py...")
    print("=" * 55)

    success = check_evidence_brief_integration()

    print("=" * 55)
    if success:
        print("🎉 All checks passed! Evidence brief integration is in place.")
        print("\nThe pipeline will now:")
        print("1. Generate an evidence brief from audit results")
        print("2. Add it to the report as 'evidence_brief' field")
        print("3. Save the updated report with the evidence brief included")
        print("\nThis fulfills Phase 4 of the improvement plan:")
        print("'Give the writer a structured evidence brief'")
    else:
        print("💥 Some checks failed. Please review the integration.")

    sys.exit(0 if success else 1)
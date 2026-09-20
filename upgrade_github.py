"""GitHub connector upgrade: full PR workflow."""
WORKFLOW = """
1. Detect defect → generate patch
2. Create branch: auto-fix/{defect-id}
3. Apply patch to branch
4. Run local tests (if available)
5. Push branch
6. Open PR with:
   - Title: fix(category): description
   - Body: evidence JSON + before/after
   - Labels: auto-fix, needs-review
   - Assignee: repo owner
7. Wait for CI to pass
8. If approved → merge
9. Re-audit to verify fix
"""
print(WORKFLOW)
print("\n✅ Set GITHUB_TOKEN env var to enable real PR creation.")

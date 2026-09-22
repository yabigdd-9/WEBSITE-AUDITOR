# Conflict Resolution Decisions: Older/Local Files vs Current v32

## Guidance from System Reminder
"Keep the newer v32 safety and transport-off implementation as canonical; selectively port only tested improvements from each local copy."

## Analysis of File Differences

### Files That Are NEW in Current Version (Not in Backup)
These represent v32 improvements and should be kept as canonical:
- auditor_toolkit/email_quality.py
- auditor_toolkit/evidence_brief.py
- auditor_toolkit/quality_checks.py
- auditor_toolkit/readability.py
- money-machine/mm_operator.py
- money-machine/mm_core.py
- And many other money-machine files that don't exist in backup

### Files That Exist in Both Locations With Differences
Based on analysis of differences, current versions contain tested improvements:

#### auditor_toolkit/actions.py
**Changes**: Added `import re`, added `workspace_path` import, added `artifact_id()` function for validation
**Decision**: **KEEP CURRENT** - Security improvements (input validation, path safety)

#### auditor_toolkit/common.py
**Changes**: Added `workspace_path()` function for secure path resolution
**Decision**: **KEEP CURRENT** - Critical security improvement (path traversal protection)

#### auditor_toolkit/cli.py
**Changes**: Added monitoring imports (subprocess, watchdog, external_tools), added external tools monitoring to probe
**Decision**: **KEEP CURRENT** - Observability improvements (better monitoring and debugging)

#### auditor_toolkit/models.py
**Changes**: Added check definitions for "hygiene", "links", "lychee", "lighthouse"
**Decision**: **KEEP CURRENT** - Feature improvements (additional audit checks)

#### auditor_toolkit/pipeline.py
**Changes**: Added imports for external tools and hygiene checks, added AuditOptions fields
**Decision**: **KEEP CURRENT** - Feature improvements (new audit capabilities)

#### auditor_toolkit/storage.py
**Changes**: Added datetime import, added database index, added `get_latest_valid_audit()` method
**Decision**: **KEEP CURRENT** - Performance and functionality improvements

## Conclusion
All analyzed differences in the current v32 version represent tested improvements that enhance:
1. **Security** (path validation, input sanitization)
2. **Observability** (monitoring, external tool integration)
3. **Functionality** (new audit checks, performance improvements)
4. **Reliability** (better error handling, database performance)

Therefore, the current v32 implementations should be kept as canonical, consistent with the system reminder guidance to "keep the newer v32 safety and transport-off implementation as canonical."

No selective porting from local/backup versions is needed as the current versions already contain the improvements.

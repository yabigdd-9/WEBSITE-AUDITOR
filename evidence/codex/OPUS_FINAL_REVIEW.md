# Independent review of Opus's final daemon correction

Reviewed commit: `d61306bcc997fd63f26e26bd31ff09296b4fe38c`.
It follows corrective code commit `f12a83c7f028f52fca6d4b5c5e9c5d0495aeb586`
and handoff update `891f88f467a47713322c5cc32ed28046bcaeef6e`.

The original `5f461d43` startup inversion was independently reproduced in two
isolated cases. The corrected implementation then passed five independent
cases: live PID denied, dead PID recovered, PermissionError denied, malformed
PID recovered and missing PID file accepted. Both review receipts are retained.

The final isolation commit redirects LOG_DIR to tmp_path and restores original
SIGTERM/SIGINT handlers after each test. Exact committed daemon/package/test
bytes were copied into `work/codex-r00/opus-final-isolation`; no Opus files were
edited or tests executed in its worktree. All seven committed regression cases
passed in 0.57 seconds (1.020 seconds including the review harness).

The independent harness checked original process signal handlers before and
after pytest and confirmed exact identity restoration. It also confirmed that
the copied source hashes did not change. This is stronger than the named
signal-restoration test's in-test function-identity assertion alone.

Evidence: `opus-final-review.json`, `opus-final-tests.xml`,
`opus-final-tests.log`, `opus-correction-review.json`, `opus-daemon-review.json`.

## Integration disposition

No remaining failure was observed in this bounded correction/isolation scope.
Never integrate the original `5f461d43` change without its correction. The full
chain still needs integrator review and impacted tests after sequential
integration; this seven-case run does not validate the full Opus branch or
the seventeen-file a365d6b1 candidate.

SupervisorDaemon.start() still has a non-atomic PID-check/write window. The
live CLI uses its separate PIDFile mechanism; do not claim the standalone
method provides atomic concurrency protection. No service activation follows
from this review.

At the final local check, Opus had new uncommitted edits to
`money-machine/mm_pipeline.py` and `money-machine/test_pipeline.py`. These are
explicitly excluded from this review and were preserved untouched.

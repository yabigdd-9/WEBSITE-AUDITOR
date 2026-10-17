# Authorized controlled integration completed

Human operator explicitly authorized integration of ec86481c after fresh verified preservation, handling only registry/email-adapter overlaps and leaving the shared supervisor stopped.

Shared integration/v44-local-machine-convergence fast-forwarded from e68873c509431f7132c754e2aeaee99fc9eb858e to ec86481ccd6c674c6dfee8d7856d71d97581d08f. No merge commit or cherry-picks. A fresh mode-0700 private preservation directory contains mode-0600 archive, manifest and binary patches. All 248 dirty files verified against the archive before mutation. Both source overlaps were reviewed byte-for-byte and their originals preserved before adopting candidate versions. Registry bytes matched candidate already; email adapter differed solely by lint annotations.

Post-integration verification: 31 targeted tests passed in 16.88s (20.664s process receipt), covering registry, foreign-entry adapter imports and bootstrap. Used disposable MM_ROOT, synthetic fixture repositories, scrubbed environment and existing interpreter. No package installation or live DB validation. The earlier full-suite receipts certify source 923c14e5; subsequent ec86481c is evidence-only.

After focused tests, all five other modified files and 241 untracked files still match backup hashes and modes. Both adopted source files match integrated HEAD. Opus SHA unchanged at dfc5dc39. Shared launchd job remains absent/unloaded. No service restart, deployment, push, soak, provider routing/configuration change or outreach occurred. Other shared dirty data remains outside application acceptance.

Private full preservation and command receipts remain under work/codex-r00/integration-ec86481c/ and are not published. New evidence here is Codex-only and does not move the shared branch again.

Next gate: design and approve full A10 scheduler/process identity and continuous-observation contract, or explicitly approve a separate runtime activation. Startup-only verification and local green suites do not establish live-runtime, financial-admission, release or soak acceptance. No additional module ownership is inferred.

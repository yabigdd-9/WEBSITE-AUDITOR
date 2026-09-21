# Hermes delegated coding rules

When this repository is opened through Cline directly or through the Hermes Cline bridge:

- Work only inside this repository unless the user explicitly names another path.
- Keep live outreach and email sending disabled. Drafting is allowed; sending is not.
- Do not purchase services, deploy, push to Git remotes, rotate credentials, or change external accounts.
- Never print, commit, or copy secrets from `.env`, keychains, credential stores, or API configuration.
- Do not run destructive commands such as `git reset --hard`, `git clean`, broad `rm`, or `sudo`.
- Preserve existing work. Inspect `git status` and `git diff` before editing.
- Prefer targeted, reversible changes and keep generated/runtime data out of commits.
- Run the smallest relevant local tests first, then broader tests when practical.
- If a task can change outreach eligibility, pricing, approval gates, or send behaviour, keep the existing human-approval requirement intact.
- Finish each delegated task with the files changed, tests run/results, and any unresolved blocker.

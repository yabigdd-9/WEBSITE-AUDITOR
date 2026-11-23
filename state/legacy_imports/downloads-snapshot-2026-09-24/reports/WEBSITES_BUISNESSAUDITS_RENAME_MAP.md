# WEBSITES/BUISNESSaudits — rename map

No bulk rename or workspace relocation was performed. GitHub name HERMES_MONEY_ENGINE remains the repository identity. WEBSITES/BUISNESSaudits is the current display name and nested namespace. MoneyMachine is preserved where compatibility or historical evidence requires it.

| Reference | Classification | Action | Rollback |
|---|---|---|---|
| README, current reports, CLI description and daily dashboard title | Safe current display identity | Use WEBSITES/BUISNESSaudits | Reverse repair patch |
| scripts, tests, migrations, control-plane | Compatibility required | Relative links to money-machine | Reverse patch; source remains |
| config/email_finder.json and approval/blocklist source | Compatibility required | Relative links to existing files | Reverse patch |
| money-machine/.venv-email | Historical tracked link | Retained; new mm selects root venv | Existing link unchanged |
| Desktop/mm and local bin/mm | Stale/missing launcher | Target authoritative local checkout | Guarded local rollback |
| Desktop MoneyMachine Hermes / hermes-moneymachine | Stale launcher | Resolve current checkout; bounded probe/smoke, no interactive paid launch | Guarded local rollback |
| ~/MoneyMachine and Desktop/MoneyMachine | Stale historical roots | No tree moved or overwritten | No move to reverse |
| External-volume MoneyMachine | Separate historical checkout | Read-only fixture/runtime source; not canonical | Unchanged |
| Historical plans, reports, prompts and legacy jobs | History/compatibility or unvalidated legacy entrypoints | Retain exact content; README designates current operator | No change |

[Exact reference inventory](rename-reference-inventory.csv) contains 299 references with file, line, exact text, classification, action and rollback. Legacy jobs with hard-coded paths are not certified active launch paths. Use the current root mm. Their preservation is explicit; this run does not claim every historical script is operational.

New run outputs are file-only and isolated from the existing CRM. No database, archive, or historical report was renamed.

Evidence is in the sibling outputs/evidence directory. All times in evidence are UTC; this run occurred 13 September 2026 in Pacific/Auckland.

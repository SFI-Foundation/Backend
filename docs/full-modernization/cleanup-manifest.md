# Backend hygiene audit

No runtime, schema, authentication, catalog, PDF or migration changes.

| Original path | Purpose | Decision / evidence | Replacement | Tests | Risk |
|---|---|---|---|---|---|
| `instance/.DS_Store` | macOS Finder metadata | Remove tracked binary. No application, test, Docker or deployment references; initial-commit platform artifact. Not a database or backup. | None; `.DS_Store` ignored | 84 backend tests, 22 isolated account tests, 18 config/PDF tests; unchanged runtime | Low |
| `.gitignore` repeated `.env.*`/exception pair | Secret exclusion | Consolidate duplicate pair; first `.env.*` rule and `!.env.example` preserved. Ignore generated `/backend.log` and Finder metadata. | Same file | `git check-ignore` for secret/env/log/metadata paths | Low |

## Retained candidates

- `backend.log` (tracked): contains private-looking identity/credential markers. Contents were not copied into reports or PRs. Retained for a separate confidential owner review, consistent with the requested sensitive-file rule. Ignore rule prevents new untracked logs but does not untrack this historical file. Do not publish or casually delete log contents; the owner must determine exposure, retention, rotation and any history-remediation requirement. No claim that markers are active credentials.
- `instance/backup/data.json`, existing uploads and any local databases: potentially real historical/customer information. Retained without mutation or publication of contents.
- `scripts/old/*`, database restore/migration scripts: historical database and migration knowledge; prior security documentation names these files. Not executed.
- Social-media tooling, templates, datasets and non-SFI endpoints: existing inherited API/route consumers. Removing them requires an approved product/deprecation review.
- Catalog JSON copies: frontend/backend deployment inputs, not redundant runtime files. Retained canonical data.
- Original checkout's feedback changes, log/metadata deletions and environment edits: preserved as found. All hygiene edits occur in this separate worktree.

Full tracked metadata inventory and exact duplicate groups are recorded alongside this manifest. A duplicate hash alone does not prove safe removal. Tests use disposable synthetic SQLite data and never use the original checkout's `.env`, database or uploads. MySQL-only tests are explicitly skipped where no disposable MySQL instance is provisioned.

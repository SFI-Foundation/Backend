# Account settings verification — 18 November 2026

Baseline: `a850ce8` (origin/main). The companion frontend builds on merged PR #35.
The original backend checkout's unrelated feedback/configuration edits and data
were preserved; this branch was implemented in a separate worktree.

| Check | Result | Evidence |
| --- | --- | --- |
| SQLite account/profile/settings suite | VERIFIED | `python testing/test_sfi_profile.py`: 22 passed |
| MySQL 8.4 account/profile/settings suite | VERIFIED | Same 22 tests against a freshly named localhost disposable schema |
| Process restart persistence | VERIFIED | A new backend Python process reopens the same DB and reads the stored settings |
| `.env`/driver/host/port/database/username loading | VERIFIED | `python testing/test_sfi_settings_config.py`: 2 passed; generated private `.env` in source copy, separate cwd and environment override |
| Additive migration | VERIFIED | Repeat without modifying users, password hashes or roles; refuse populated-table downgrade |
| Authorization and validation | VERIFIED | 401 guest, 403 unapproved Origin/privileged actions, 400 identity/role/unknown/malformed values, 415 non-JSON, 413 request bound, rollback on SQL failure |
| Cross-device writes | VERIFIED | Two authenticated clients; DB record inspection; reverse update and 409 stale revision |
| Browser/account integration | VERIFIED | Companion frontend evidence uses real Chromium cookies → Flask HTTP → isolated SQLite records; member/admin profile editing and account isolation |
| General regressions | PARTIALLY VERIFIED | 77 run: 74 passed; 3 independent opt-in catalog MySQL tests skipped |
| Disposable customer demo startup | VERIFIED | `--demo` starts real Flask on 8865 and returns 23 synthetic catalog entries, then stops |
| Production setup/deployment | BLOCKED | Requires operator-approved production DB/network, secrets, migration/backup plan and domain/cookie deployment verification; none was modified |

SQLite is the documented local fallback; authenticated MySQL is required in
production. MySQL port/name now use `DB_PORT` and `DB_NAME`. No SQLite result is
presented as MySQL verification. The MySQL QA container has no production volume,
uses generated private credentials, and contains only synthetic test data.

Settings are a new table, independent of existing profile and onboarding data.
The only endpoint is current-account `/api/sfi/settings`; the request cannot
choose another user. JSON values are allowlisted and bounded at 16 KiB; existing
cookie/token authentication and exact-origin CORS policies remain in force. No
per-user rate limiter was added because this API follows the app's existing
conventions. No notification subscriptions, credentials or privileged roles enter
the settings record.

See README for exact setup/test commands, migration/rollback and troubleshooting.
The frontend's `docs/customer-preferences-demo.md` provides the customer sequence;
`docs/teacher-deployment-preferences-verification.md` contains the combined report,
language coverage, responsive/theme/accessibility evidence and screenshots.

Manufacturer is an optional self-reported interest, never an authorization role.
Existing catalog PDF approval/invalidation and gear moderation tests remain covered.
Real camera downloads, physical phones, production hosts and other browser engines
are not asserted as verified.

Companion draft: [Frontend #39](https://github.com/SFI-Foundation/Frontend/pull/39). Backend draft: [#47](https://github.com/SFI-Foundation/Backend/pull/47). Both target main with auto-merge disabled. Fresh revalidation repeated the SQLite, MySQL, configuration, regression and disposable-demo checks above. The final frontend browser run passed 286 theme/responsive checks and 13 axe scans; its report separately discloses a pre-existing failing legacy chatbot Sass audit. No production deployment was performed.

# Selective Backend upstream synchronization — 2026-11-18

Origin repository: `SFI-Foundation/Backend`. Origin base: `6014c0d59687934505223b0c8079aae3fdbc45ab`.
Upstream repository: `Open-Coding-Society/flask`. Audited tip: `e09d1e7dfc9620a8e70578fffd44ce66cdfc1f05`.
Prior upstream integration/merge base: `b58c2f6f1259424e06c9cfa840df7c2c93b925b9`. New reachable upstream commits: **115**, including merges.
Branch: `chore/selective-upstream-sync-backend` from the pinned `origin/main`.

[Every upstream file decision](classification.tsv) was recorded before integration: 117 paths including intermediate changes; classes {'D': 83, 'C': 30, 'B': 4}. Endpoint counts use no rename detection (a rename is a separate delete/add). Historical shared ancestors were selectively merged previously, so ancestry alone never authorizes template replacement.

## Imported/adapted changes

- `api/analytics.py`: adapt upstream `451653370f4f4fe6229cd55f7377630237eda2e5`; add the existing `token_required()` to received-issue-comment analytics. Signed-in calls now receive their own account's data rather than an unset-identity error; anonymous callers receive 401.
- `main.py`: adapt `c5a1a91fe107ab6212efff6ac025cfa19f480c8f`; check `is_authenticated` before the existing SFI `Admin` role check on `PUT /update_user/<uid>`. Existing non-admin 403 and admin update/missing-user behavior stay intact.
- `api/python_exec_api.py`, `api/javascript_exec_api.py`: adapt the login-guard portion of `7f0122f3a57929b5d102f4b3e890d60a894b8f9d` using SFI's existing session/Bearer/cookie decorator. Keep local subprocess executors and existing successful response/empty-input behavior. Unauthorized requests cannot create execution temp files or reach the subprocess.
- `tests/test_selective_upstream_security.py`: seven behavioral regressions using memory databases, synthetic accounts, stubbed GitHub responses and stubbed execution. Checks include distinct caller identities and all three existing API auth methods.

## Excluded, deferred and already present

OCS school/guest/mentor accounts, domain signup, role policies/RBAC, account schema/password changes, presence/RFID, classroom/AI/grade demos, generic database init/restore/upgrade/removal scripts, Spring preference migration, upstream configuration/default passwords and templates are excluded. The absent upstream runner service and its debug-setting hunk are not introduced. GitHub analytics pagination/trimester work is deferred beyond the single guard fix. Broad JSON-object validation is deferred to a separate SFI API-contract review.

SFI already provides exact-origin credentialed CORS, fail-closed production-secret validation and account preference persistence with revision protection. These equivalent or stronger implementations remain authoritative. Existing dedicated catalog/onboarding/settings migrations remain additive and repeatable. No upstream account policies are copied into SFI's decorator.

## Validation against the same baseline

| Check | Baseline | Proposed branches |
|---|---|---|
| Backend `unittest discover -s tests -v`, isolated SQLite | 77 tests, 3 MySQL-only skips, pass | 84 tests, same 3 skips, pass |
| Isolated profile/auth/onboarding/preferences regression | 22 pass | 22 pass |
| Config and PDF-ingestion `testing/test_sfi_*.py` | 18, 1 intentional direct-run profile skip, pass | Same, pass |
| Disposable MySQL 8.4 account/preferences regression | 22 pass | 22 pass |
| Disposable MySQL catalog migration/import/concurrency | 3 pass | 3 pass |
| New guard regression tests against original code | Reproduce errors/failures | 7 pass; final test isolates each session/Bearer/cookie identity |
| Frontend `npm test` | 5 script files pass | Same, pass |
| New upstream DOCX regressions against original code | Reproduce failures | 5 pass |
| Frontend phase1 tests | Pass | Pass |
| Full production Jekyll build | Pass | Pass |
| Public artifact / assets / search-index suite | 7 pass | 7 pass |
| Scoped Sass and redesign/photography checks | Pass | Pass |
| Internal links/assets | 15 pages, 489 targets pass | Same, pass |
| Paired Chromium integration, real Flask HTTP and disposable DB | Pass | Pass |
| Responsive layout widths | 1440, 1024, 768, 390, 320 px pass | Same, pass |
| Browser theme checks | 286 cases | Same, pass |
| Accessibility / Spanish localization | 13 routes, zero violations / untranslated known strings | Same |
| Browser JavaScript errors | Zero | Zero |
| Flask route map | Recorded | Identical |
| Generated output preservation | 2,110 files | Identical paths; only feed build timestamp and CSS-map temporary paths differ |

## Preservation and data safety

All SFI-specific route handlers, schemas, migrations, catalogs, canonical reconciliation/deduplication, PDF verification/approval/revocation, role/group policies, account/profile/onboarding/preferences, English/Spanish data contracts and production validation remain unchanged. Existing gear tracking/reviewer moderation, research boundaries, chat/PDF-summary APIs and other retained features are also preserved.

All frontend runtime JavaScript, content/pages, navigation, layouts, includes, Sass, images/data, localization resources, themes, dependencies, API configuration, custom domain and workflows match the pinned origin base. No classroom pages or assets are added. The two generated builds have no added/removed paths; all HTML and runtime assets are byte-identical. Only the feed's build timestamp and a CSS source map's temporary remote-theme paths differ, verified by normalization.

The original backend checkout remains on main with its pre-existing `.env.example`/`.gitignore` edits, deleted tracked log/DS_Store files and untracked feedback files intact. The original frontend checkout stays on main and clean. All initial tracked/untracked file hashes plus `.env` hashes match; original HEADs/statuses are unchanged. Existing worktrees are retained. Real/customer data and production databases were never used by the applications or tests. Tests use memory SQLite, temporary source copies and newly created explicitly named localhost MySQL QA schemas. Private data remains local; no contents enter these commits.

## Security, configuration and limitations

- No dependency or deployment changes. Existing ignored `Gemfile.lock` and installed dependencies were reused for local builds; no new lockfile is committed.
- Existing SQLAlchemy relationship and datetime deprecation warnings remain. Existing Jekyll Sass/post-link and duplicate classroom-destination warnings match baseline; the SFI output remains unchanged.
- Initial sandbox runs failed on remote-theme DNS, nested Bundler process permissions and the browser's Unix socket. Matching reruns with the required execution access passed. One redesign invocation lacked its required built-site argument; the corrected baseline/proposed invocations passed. These were environment/invocation failures, not product regressions.
- Browser tests block external services and use disposable synthetic records. Official public PDF download/network availability and production credentials/data were not exercised. PDF approval/rejection/revocation and unapproved-link restrictions are covered by regression tests; the browser verifies unapproved actions remain unavailable.
- Authentication now gates the legacy code runners. Their existing subprocess isolation is unchanged and is not a complete sandbox; evaluate stronger isolation separately. No OCS account expiry/activation semantics are imposed on SFI.
- This is a selective audit through the recorded tips, not an ancestry merge or acceptance of every commit. Next sync must read this classification and the named source commits, inspect remaining changes, and avoid replaying these hunks. Merge bases intentionally remain the earlier recorded integration points.

## File-by-file final diff review

Each changed file was reviewed against the pinned origin base. No SFI functionality was removed.

| File | Why needed | What changed | SFI impact/removal | Dependency/configuration/security risk | Verification |
|---|---|---|---|---|---|
| api/analytics.py | Missing identity initialization caused errors | Add one existing auth decorator | Existing account analytics only; no SFI removal | Tightens access; no dependencies | Anonymous/invalid tokens; session/Bearer/cookie; distinct account IDs |
| main.py | Anonymous update dereferenced missing role | 401 before existing Admin check | Admin behavior retained; no routes removed | No auth model/config change | 401,403, admin update/404 |
| api/python_exec_api.py | Existing execution route lacked login gate | Import and apply existing decorator | Executor and response contract retained | Tightens access; executor isolation unchanged | Denied before file/execution; authenticated output/blank body |
| api/javascript_exec_api.py | Same missing execution login gate | Import and apply existing decorator | Executor and response contract retained | Same as Python executor | Same as Python executor |
| tests/test_selective_upstream_security.py | Prevent guard regressions | Seven isolated behavior tests | No runtime change | Memory DB; execution/GitHub stubbed | Pass; original code fails |
| docs/upstream-sync/2026-11-18/classification.tsv | Prevent duplicate/risky future imports | Complete pre-integration A/B/C/D decisions and blob evidence | Documentation only; no SFI removal | No private data or credentials | Compared inventory to Git history and endpoints |
| docs/upstream-sync/2026-11-18/README.md | Make selective patch reviewable | Source pins, decisions, verification and preservation receipt | Documentation only; no SFI removal | No runtime/config changes; docs excluded from site | Reviewed against logs and final diff |

# Phase 1 final branch reconciliation — 2026-11-11

This coordinated review consolidates specification search, safe import and public UI cleanup. It is not approved for production deployment.

## Git evidence and preservation

The final branch in each repository is `feature/sfi-phase1-final-review`.

| Repository | Current SFI main / merge base | Accepted UI-cleanup ancestor |
|---|---|---|
| Backend | `146179056ea57910accc79d098fa8434211b019c` | `27bdbd2b5380f03a4efbd9fa3a7f501d8696537a` |
| Frontend | `3273784f303993d3a535d62b41debc69786cff12` | `f425cbacb37cae03e46b15199818a3a3f0c4f74a` |

`git worktree list`, status, tracking configuration, merge-base, graph logs and branch containment show linear ancestry: initial Phase 1 → repairs → public cleanup → UI cleanup. Neither branch is parallel, conflicting, or an equivalent patch series needing cherry-picks. Both final branches retain those commits unchanged. The only final follow-up is scoped backend lint/format maintenance plus this verification record. Import regex aliases/dictionary syntax and UTC spelling are equivalent; ORM registration imports are explicitly retained, and subprocess failure assertions use `check=False`.

Remote SFI main was verified before reconciliation. The existing frontend origin points to a personal fork; its cached main matches SFI main exactly. Publication targets only the SFI organization repositories using explicit URLs. Original main references, existing branches, the original dirty backend worktree and all pre-existing local changes are preserved. No reset, rebase, force-push, merge or deployment is part of this work.

## Executed verification

| Check | Final result |
|---|---|
| Backend `unittest discover -s tests -v`, SQLite and dedicated disposable MySQL 8.4 schema | 58 passed, zero skips |
| Backend configuration tests | 7 passed |
| Standalone PDF-ingestion tests | 7 passed |
| Isolated full-app authentication/profile tests | 13 passed |
| Frontend profile, gear, search, reminder and public artifact tests | 38 passed, zero skips |
| Rendered authentication / gear integrations with real Flask and disposable SQLite | 7 / 1 passed; WSGI pipe transport where sandbox sockets are unavailable |
| Production Jekyll build, scoped Sass, API configuration and demo gate checks | Passed |
| Actual production build with development demo overlay | Rejected as expected |
| Ruff check and format on 15 catalog/security/CLI/regression files | Passed |
| Changed Python/JavaScript/Ruby syntax and Git whitespace | Passed |
| Chromium against real localhost servers, without mocked application requests | 13 groups passed |

Initial socket/theme/browser sandbox restrictions were resolved through execution approvals. An initial browser run reached the optional demo before that server finished building; it was rerun after readiness. Broad lint diagnostics were corrected and backend regressions rerun. Initial failures are not counted as passes. Jekyll retains inherited duplicate-route/post-link and Sass warnings; SQLAlchemy emits legacy deprecation warnings.

The real-source importer parsed 220 observations into 108 identities with no conflicting source fields. On a separate copied disposable database, migration and dry-run succeeded; two applies returned zero inserts, zero updates, 108 unchanged. Strict dry-run returned 1 as expected for unresolved source/document conditions. This is a safety assertion, not an accepted import failure. Post-maintenance repeat import also leaves 108 unchanged. MySQL regressions cover additive migration, Unicode, rollback, archive/restore relationships and concurrent canonical creation.

## Browser evidence and manual review

The production-like frontend runs at `http://localhost:4000/sfi-specs/`, with the final backend at `http://localhost:8605/api/sfi/health`. An explicit development preview is available at `http://localhost:4100/sfi-manufacturer-demo/`; the same route on port 4000 returns 404.

Chromium used 1440×1000 and 390×844. Verified: keyboard/Enter search for 16.1, independent 20.1/1 and 20.1/2 searches, product keywords, every category, all 111 canonical identities across six pages without duplicates, previous-page navigation, official verified PDF opening (200 with PDF bytes), restricted unverified links, wrapped labels/cards, public navigation and no car diagram, classifier controls, ML accuracy card or manufacturer navigation. CORS, anonymous/member/admin authorization, password login and logout passed over localhost HTTP. Demo intervals start off, its five records are fictional, and it sends no notification requests. No page exceptions, unexpected console errors or failed requests remained; intentional 401/404 checks and the sandbox favicon 404 are recorded.

Evidence is Git-ignored under `qa-evidence/final-review-20261111/` in the frontend worktree. Twenty capture entries produce 19 unique PNGs because the initial desktop overview is captured twice. Every PNG was opened and visually inspected. The screenshots cover desktop/mobile overview, controls/navigation, three exact searches, All categories, unavailable PDF cards, blocked demo, a verified PDF action and the opted-in fictional demo. No screenshots, local PDF rendering, private source documents or local QA reports are committed or uploaded.

Original and copied review catalog row hashes remain unchanged for `sfi_specs`, `sfi_spec_chunks` and `sfi_catalog_entries`. The reviewed snapshot has 111 canonical results: 63 verified current, 16 rejected, 29 needing review, 3 not checked. These preserved evidence states are not a fresh revalidation of every public PDF.

## PR scope and security

Changed-file manifests were reviewed against current SFI main, including renames/deletions, size and content checks. No added/modified PDF, ZIP, DOCX, database, model binary, screenshot, private source bundle, real environment file, cache or build output is proposed. Four inherited tracked backend databases and the inherited frontend environment file are deleted from current source. No newly introduced large binary is included. Outgoing commits were scanned for provider credentials and secret assignments without printing values; the only assignment candidates are deliberate incorrect-password test literals. Generated output passes the known-exposed-value and provider-pattern checks. These heuristic checks do not certify all inherited history or legacy functionality.

Historical exposure still requires credential-owner review of `GAMIFY_API_KEY`, `GEMINI_API_KEY`, `VITE_GEMINI_API_KEY`, provider `API_KEY` values, `ADMIN_PASSWORD`, `DEFAULT_PASSWORD`, `MIRAGE_PASSWORD`, `SECRET_KEY`, `rds_password`, `DB_PASSWORD` and related account/session credentials. No active-status probes, rotation or historical rewriting occurred. See backend `docs/sfi-public-security.md` for owner actions and bounded audit scope.

## Release blockers and coordinated rollout

- Jennifer/SFI must resolve 17 public PDF revision/effective-date/catalog discrepancies. Keep them restricted. The shared 20.1 PDF must not be approved automatically.
- Eight category assignments remain unconfirmed: 11.1, 20.1/1, 20.1/2, 21.1, 22.1, 3.2, 8.1 and 9.1. Keep the explicit category-review state.
- Credential owners must assess historical exposure and revoke/rotate any active credentials. Removal from current source is not evidence of rotation.
- Production requires coordinated review, configuration and HTTPS/cookie/CORS validation, database backups, writer coordination, migration planning and SFI approval.

After approval, back up the target database and establish a tested recovery point; apply the additive metadata migration and reviewed import against explicit target configuration, then validate backend API compatibility before enabling the corresponding frontend. Revalidate document evidence near release and keep demos/research off. MySQL DDL is not transactional; do not treat rollback as a SQL transaction around DDL.

Rollback should use ordinary revert commits and the previous reviewed frontend/backend pair. Retain the additive metadata table and legacy rows; never drop user data automatically. Restore a verified database backup only under an owner-approved recovery plan if data recovery is required. Preserve security fixes in any rollback. This draft review grants no merge or deployment approval.

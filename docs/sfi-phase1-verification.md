# Phase 1 verification

Executed locally using isolated databases and synthetic fixtures. No production
service or real user/manufacturer records were used. Exact command paths used the
existing Backend `venv/bin/python`; `PYTHON_DOTENV_DISABLED=1` was set.

| Check | Outcome |
| --- | --- |
| Before: `python -m unittest discover -s tests -v` | 10 passed |
| Before: config + PDF ingestion modules | 14 run, 2 mapper errors documented in audit |
| Before: Frontend `npm test` | Both existing script suites passed |
| Final: `python -m unittest discover -s tests -v` | 34 passed |
| Final: `python -m unittest testing.test_sfi_config testing.test_sfi_pdf_ingest -v` | 14 passed |
| `python testing/test_sfi_profile.py` (its disposable-copy harness) | 13 passed |
| Frontend `npm test` | Both existing script suites passed |
| Frontend `npm run test:phase1` | Both new suites passed; 8 Phase 1 cases also executed directly with Node |
| `npm run test:styles -- /tmp/sfi-phase1-site` | Scoped Sass compiled; existing gear/admin checks passed |
| `bundle exec jekyll build --disable-disk-cache --destination /tmp/sfi-phase1-site` | Passed; existing unrelated duplicate routes/post-tag warnings |
| Ruff critical-error lint (`E9,F63,F7,F82`) on changed catalog Python | Passed |
| Ruff format check on eight new Python files | Passed |
| Python compileall / Node `--check` / inline-script compilation | Passed |
| Additive migration on new isolated SQLite + preservation fixtures | Passed; repeat safe, backup generated |
| Actual source import, then repeated apply | 106 metadata records; final repeat 0 inserted, 0 updated, 106 unchanged |
| Actual `--strict` dry-run | Expected rejection for unresolved documents/categories; no writes |
| Public official PDF HTTP/content/revision audit | 80 checked; 63 current, 17 review exceptions |
| Chromium desktop + 390 px mobile, real Flask API + SQLite | Passed; no page JavaScript errors |
| `git diff --check` | Passed before commits; final check repeated at delivery |

The Phase 1 unit/integration fixtures cover PDF/DOCX parser accuracy and Word run
boundaries and explicit line breaks, explicit technical bulletins, unsafe ZIP paths/symlinks/bombs/duplicate
names, conflicts and rating variants, missing/incorrect/old PDFs, literal SQL
punctuation, exact/case/whitespace/synonym search, name-vs-category ranking,
category overlap, deduplication, pagination errors, API legacy fields,
authorization, duplicate writes, manual metadata edits, no-op upserts, user/row
preservation, rollback and additive migration. DOM tests cover accessible labels,
keyboard form behavior, busy/empty/error/retry states, stale response protection,
unsafe URLs/content escaping, demo isolation, date editing and disabled intervals.
Calendar tests cover leap years, month ends, DST, timezone-midnight boundaries,
inclusive threshold/expiry days and the first overdue day.

Browser story: search input → existing `/api/sfi/specs/search` → isolated SQLite
legacy rows and metadata → canonical paginated response → cards and verified URL.
Chromium verified exact 16.1, a current official PDF link, clearing, total 109,
next-page boundaries, no-match state, no horizontal overflow at 390 px, five
fictional demo records, demo search, and independently disabling six-month notices.
Screenshots and full runtime/import logs remain under `/tmp/sfi-phase1-*` outside
Git. Browser driver and missing runtime libraries were installed only under /tmp.

No project-wide lint/formatter configuration exists. Ruff was installed into a
temporary environment; no Python/JS test framework or runtime dependency changed.
The profile test must run directly; importing it via unittest module discovery
intentionally raises SkipTest. Its direct isolated run passed. Browser checks
covered this feature, not every unrelated route in the large existing site.

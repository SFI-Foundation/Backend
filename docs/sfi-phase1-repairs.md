# Phase 1 repairs and localhost acceptance

Verdict: **PASS WITH CONDITIONS**. The implementation findings and regressions
are repaired, automated checks pass, and the actual localhost application passed
browser and visual acceptance. Production release still requires resolution or
explicit review of source/PDF/category exceptions and the previously documented
credential/deployment concerns. This verdict does not approve deployment.

QA date: 2026-11-10 Pacific (2026-11-11 UTC). No push, merge, deployment, private
source upload, production database access, or real notification occurred.

## A. Repair results

| Finding | Repair and regression evidence |
| --- | --- |
| H1 | Full-number grammar accepts slash qualifiers; 20.1/1 and 20.1/2 retain distinct age/rating identities and explicitly share the 20.1 PDF. Both source lists parse 110 rows. Malformed specification-looking rows block import with source/page/table/row references. Identifier/parser regressions exercise both qualifiers, source references and shared PDFs. |
| H2 | Public states are not_checked, verified_current, rejected, temporarily_unavailable and needs_review. Confirmed wrong identity/revision/bytes and 404/410 reject; network failures are temporary. Explicit negative results revoke prior approval, even without a timestamp. Historical evidence stays private. Repeated imports cannot revive rejected documents through equal revision strings. Transition, repeat-import, CLI persistence and API tests cover this. |
| H3 | Both CLI entry points use sys.exit(main()). Subprocess tests execute real entry points and assert successful and unsuccessful process codes. Import strict/parser failures and validator timeouts/mismatches return nonzero. |
| M1 | Validated normalized comparisons prevent unchanged saves and product-only edits from invalidating PDFs. Actual identity, revision, effective-date or spec-PDF changes invalidate. Full canonical groups rename together. Unit cases cover all fields and repeated saves; browser saves a verified 16.1 unchanged. |
| M2 | Delete explicitly archives the complete canonical identity; it does not delete duplicate rows or related evidence. Exact identity confirmation is required. Authorized archived listing and restore are exposed in the existing admin UI. Restore requires fresh document review. Single-row and multiple-row cases, related chunks, repeat imports and MySQL integrity are tested. |
| M3 | Every reminder checkbox and numeric input has an individual explicit label. Bounds/help/errors are associated, invalid fields expose aria-invalid, disabled notices disable their numeric field, and keyboard focus is visible. Chromium checks label association, Tab order, focus outlines and accessibility names. No notifications are sent. |
| M4 | Admin bodies must be nonempty JSON objects, supported fields must be strings, lengths are bounded, required values cannot normalize to blanks, and complete specification grammar is checked before SQL binding. Arrays/null/objects/numbers/booleans/oversized values/invalid identifiers return 400; duplicates return 409; auth remains 401/403. |
| Search race | Input immediately invalidates in-flight results during debounce. Explicit/category loads cancel pending timers; pagination is disabled while a new input is pending. Delayed-response DOM regressions and real rapid-typing browser checks pass. |
| Concurrent creation | A unique canonical metadata key is reserved in the same transaction as the legacy insert. MySQL synchronized creators and simultaneous browser HTTP requests yield one 201 and one 409. Failed transactions roll back. No destructive uniqueness migration touches legacy duplicates. |
| Resource bounds | Directory traversal stops at the file/member limit; cumulative expanded bytes across archives are bounded. Per-file, compression, XML and PDF page limits remain; PDF page caches are closed and list hashes computed once. Synthetic regressions cover aggregate limits. |
| Browser findings | Fixed 240px-tall mobile search input, duplicate description text, fixed-nav anchor positioning, dashboard/reminder alignment, select labels, and cached 410 responses after restore. Catalog responses use Cache-Control: no-store, also preventing stale PDF actions. |
| Broader regression | Existing gear UI used PUT /review while backend exposed PATCH /status. Added a validated compatibility route reusing permission checks; corrected the isolated bridge fixture's synthetic permission-group initialization. Real browser admin approval/rejection and persisted notes pass. |

No unresolved implementation defect was found in the tested Phase 1 stories.
Missing source documents, revision discrepancies and category ownership remain
review conditions; none are represented as approved current documents.

Changed backend files:

- `api/sfi_spec.py`
- `catalog.py`
- `catalog_admin.py`
- `catalog_import.py`
- `catalog_links.py`
- `model/sfi_spec.py`
- `scripts/import_sfi_catalog.py`
- `scripts/validate_sfi_links.py`
- `scripts/phase1_local.py`
- `tests/test_phase1_repairs.py`
- `tests/test_phase1_mysql.py`
- `api/user_gear.py`
- `tests/test_user_gear_review.py`
- `testing/test_sfi_profile.py`
- `README.md`
- `docs/sfi-phase1.md`
- `docs/sfi-phase1-import-results.md`
- `docs/sfi-phase1-link-validation.json`
- `docs/sfi-phase1-verification.md`
- `docs/sfi-phase1-repairs.md`

Changed frontend files:

- `.gitignore`
- `_sass/sfi/pages/_specs.scss`
- `assets/js/sfi/manufacturer-demo.js`
- `assets/js/sfi/spec-search.js`
- `docs/sfi-phase1.md`
- `navigation/sfi-manufacturer-demo.md`
- `navigation/sfi-specs.md`
- `scripts/test-sfi-api-config.mjs`
- `scripts/test-sfi-manufacturer-demo.mjs`
- `scripts/test-sfi-phase1-browser.cjs`
- `scripts/test-sfi-spec-search.mjs`

## B. Data integrity

| Measure | Corrected count |
| --- | ---: |
| PDF specification-list rows | 110 |
| DOCX specification-list rows | 110 |
| Combined observations | 220 |
| Distinct source identities | 108 |
| Confirmation/variant observations beyond unique identities | 112 |
| Source conflicts | 0 |
| Local PDFs inspected | 80 |
| Source identities with local PDF matches | 79 |
| Source identities without local PDF matches | 29 |
| Unmatched local PDFs | 2 |
| Existing public legacy rows retained | 140 |
| Rows after actual import, before synthetic QA additions | 148 |
| Canonical public identities, including legacy-only entries | 111 |
| Fresh metadata inserts | 108 |
| Repeated SQLite and MySQL import inserts / updates / unchanged | 0 / 0 / 108 |
| Official public URLs checked live | 80 |
| Public URLs verified current | 63 |
| Public URLs requiring review | 17 |

The 20.1 PDF is a local match for two distinct identities. Its revision remains
mismatched; neither qualifier has a current PDF action. Only 36.1 and 36.2 remain
unmatched archive PDFs. Source identities have 63 verified, 16 rejected and 29
needs-review public document states. URL counts differ because of shared and
unlisted documents. Eight new identities retain explicit category-review labels.
Detailed private provenance remains only in local /tmp import reports; it is not
copied here. The committed JSON audit contains public URLs and public evidence.

## C. Automated checks and exact commands

Backend working directory: `/home/ruhaanb622/sfi-foundation/phase1/Backend`.
The existing environment was used without modifying the original worktree:

```bash
export SFI_QA_PYTHON=/home/ruhaanb622/sfi-foundation/SFI-Backend/venv/bin/python
PYTHON_DOTENV_DISABLED=1 SFI_QA_MYSQL_URI=mysql+pymysql://root@127.0.0.1:13367/sfi_phase1_qa \
  "$SFI_QA_PYTHON" -m unittest discover -s tests -v
PYTHON_DOTENV_DISABLED=1 "$SFI_QA_PYTHON" -m unittest testing.test_sfi_config testing.test_sfi_pdf_ingest -v
PYTHON_DOTENV_DISABLED=1 "$SFI_QA_PYTHON" testing/test_sfi_profile.py
```

Results: **51/51**, **14/14**, and **13/13** passed, with zero skipped in the final
combined backend run. Baseline discovery was 34/34 before repairs. The first
attempt with system Python failed because Flask was absent; using the repository's
existing environment resolved that setup error. Tests use disposable databases.

Frontend working directory: `/home/ruhaanb622/sfi-foundation/phase1/Frontend`.

```bash
npm test
npm run test:phase1
node --test --test-isolation=none scripts/test-sfi-profile.mjs scripts/test-sfi-gear.mjs scripts/test-sfi-spec-search.mjs scripts/test-sfi-manufacturer-demo.mjs
node scripts/test-sfi-integration.mjs /home/ruhaanb622/sfi-foundation/SFI-Backend/venv/bin/python /home/ruhaanb622/sfi-foundation/phase1/Backend /tmp/sfi-phase1-repair-preview
node scripts/test-sfi-gear-integration.mjs /home/ruhaanb622/sfi-foundation/SFI-Backend/venv/bin/python /home/ruhaanb622/sfi-foundation/phase1/Backend
BUNDLE_PATH=/tmp/sfi-phase1-gems bundle exec jekyll build --disable-disk-cache --destination /tmp/sfi-phase1-repair-build
npm run test:styles -- /tmp/sfi-phase1-repair-build
node scripts/test-sfi-api-config.mjs /tmp/sfi-phase1-repair-build
```

Both npm commands pass their two script suites. Direct execution reports **34
individual cases passed** (including 12 Phase 1 cases). Profile/auth integration
passes **7/7**; gear integration passes **1/1**. The bridge suites transparently
report WSGI-over-pipes when sandbox sockets are prohibited; actual HTTP/browser
acceptance was performed separately. The earlier gear integration failure led to
the compatibility/fixture repairs above; its final rerun passes. The earlier
root-baseurl config assertion was corrected to support explicit SFI_BASEURL while
retaining the production default. Final production-baseurl checks pass.

Full build and Sass pass. Jekyll retains pre-existing duplicate-route and post-tag
warnings outside these features. Ruff critical-error checks (E9,F63,F7,F82),
format checks on the ten catalog/repair Python files, Python compile checks,
changed JavaScript syntax/inline-script checks and git diff --check pass. Existing
legacy formatting outside touched lines was preserved. Formatter command:

```bash
/tmp/sfi-phase1-quality/bin/ruff format --check --config "format.quote-style='single'" catalog.py catalog_admin.py catalog_import.py catalog_links.py api/sfi_spec.py scripts/import_sfi_catalog.py scripts/validate_sfi_links.py scripts/phase1_local.py tests/test_phase1_repairs.py tests/test_phase1_mysql.py
```

Actual source CLI commands also ran with explicit private-source paths and the
disposable SQLite URI: dry-run, apply with live public-link validation, repeated
apply and strict dry-run. Strict returned **1 as expected** for unresolved review
conditions; repeated apply returned 0 with 108 unchanged. Detailed local logs are
`/tmp/sfi-repair-*.log`; detailed import reports are `/tmp/sfi-repair-*-report.json`.
No failed final regression or build check remains.

Exact actual-source invocations from Backend (reports stay outside Git):

```bash
PYTHON_DOTENV_DISABLED=1 "$SFI_QA_PYTHON" scripts/import_sfi_catalog.py --source-dir /home/ruhaanb622/sfi-foundation/sfi-private-data --apply --database sqlite:////tmp/sfi-phase1-repair-local.db --validate-links --report /tmp/sfi-repair-verified-import-report.json
PYTHON_DOTENV_DISABLED=1 "$SFI_QA_PYTHON" scripts/import_sfi_catalog.py --source-dir /home/ruhaanb622/sfi-foundation/sfi-private-data --apply --database sqlite:////tmp/sfi-phase1-repair-local.db --report /tmp/sfi-repair-repeat-import-report.json
PYTHON_DOTENV_DISABLED=1 "$SFI_QA_PYTHON" scripts/import_sfi_catalog.py --source-dir /home/ruhaanb622/sfi-foundation/sfi-private-data --strict --report /tmp/sfi-repair-strict-import-report.json
PYTHON_DOTENV_DISABLED=1 "$SFI_QA_PYTHON" /tmp/sfi-repair-mysql-import.py
```

The strict command exits 1 by design for review conditions. The disposable MySQL
actual-import harness refuses a nonempty schema rather than overwriting a prior
run. The container was created with:

```bash
docker run --detach --name sfi-phase1-repair-mysql --publish 127.0.0.1:13367:3306 --env MYSQL_ALLOW_EMPTY_PASSWORD=yes --env MYSQL_DATABASE=sfi_phase1_qa mysql:8.4
```

This is an isolated local QA database, not an application database configuration.
No production secrets were supplied.

## D. Running localhost and visual evidence

Both actual services started successfully. Backend has no Makefile; its documented
focused launcher was used. Frontend Makefile was inspected. Its broad `serve` and
`dev` targets clean/convert/watch unrelated content, so the documented equivalent
Jekyll serve command was used directly with temporary output. The existing gems
are in /tmp/sfi-phase1-gems; bundle check confirms dependencies are satisfied.

Backend:

```bash
cd /home/ruhaanb622/sfi-foundation/phase1/Backend
PYTHON_DOTENV_DISABLED=1 ../../SFI-Backend/venv/bin/python scripts/phase1_local.py \
  --database sqlite:////tmp/sfi-phase1-repair-local.db --port 8605 --demo-accounts
```

Frontend, in a second terminal:

```bash
cd /home/ruhaanb622/sfi-foundation/phase1/Frontend
BUNDLE_PATH=/tmp/sfi-phase1-gems bundle exec jekyll serve \
  --host 127.0.0.1 --port 4000 --baseurl "" \
  --destination /tmp/sfi-phase1-repair-preview
```

These services are left running for inspection; do not launch another instance
on occupied ports. If restarting, stop the current instances first. The prepared
SQLite file is disposable and contains only public catalog metadata and fictional
QA accounts. To reproduce in a fresh file, run the same launcher with `--prepare
--demo-accounts`, then the documented additive migration/import using that file's
explicit URI. Preparation refuses existing files.

Open:

- http://localhost:4000/sfi-specs/
- http://localhost:4000/sfi-manufacturer-demo/
- http://localhost:8605/api/sfi/health
- http://localhost:8605/local-demo/ to select a fictional admin/member role.
- http://localhost:4000/admin/ for the existing gear portal after synthetic admin login.

Use **localhost consistently** for cookies. The backend binds only loopback.
The real browser exercises credentialed CORS and actual API responses, including
OPTIONS; no frontend API requests are intercepted/mocked. The classifier is
intentionally Offline in this focused sandbox. No production service is selected.

Chromium command used:

```bash
LD_LIBRARY_PATH=/tmp/sfi-phase1-browser-libs/root/usr/lib/x86_64-linux-gnu \
PLAYWRIGHT_MODULE=/tmp/sfi-phase1-browser/node_modules/playwright \
CHROME_PATH=/home/ruhaanb622/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome \
SFI_QA_PYTHON=/home/ruhaanb622/sfi-foundation/SFI-Backend/venv/bin/python \
SFI_QA_NEGATIVE_HELPER=/tmp/sfi-repair-negative-validation.py \
node scripts/test-sfi-phase1-browser.cjs
```

The helper drives the real standalone validator with an explicit synthetic wrong-
document transport fixture, persists its result to the QA SQLite file, then the
running API/browser verifies rejection and removal of the action. Original local
verification evidence is restored after that QA experiment. Archive experiments
similarly restore only their QA snapshot. There is no production mutation.

**16 browser groups passed**: exact 16.1/20.1/1/20.1/2, product/mixed-case/partial
search, empty browsing, all 111 identities and duplicate-free pagination, rapid
typing, live verified PDF in a new tab (rendered and reviewed), unverified/missing
PDFs, negative revalidation, compact mobile input/no overflow, anonymous/member
write denial, malformed inputs, real UI add/unchanged verified save/edit,
canonical archive/restore for one/two legacy rows, concurrent HTTP creation,
existing gear approval/rejection, five fictional manufacturers/search/filters,
and reminder accessibility/validation/disable/expiry/reset with no messages sent.

No page JavaScript exceptions occurred. Console HTTP errors correspond to deliberate
401/403/400/409/410 negative cases, plus the QA login page's harmless missing
`http://localhost:8605/favicon.ico`. There were no unexpected application API 404s
or 5xx responses. Ten ERR_ABORTED requests were navigation/preflight cancellations;
completed critical flows were asserted. No reminder POST requests occurred.

All **19 actual screenshot images** were opened and visually reviewed, not merely
checked for existence. Initial defects were corrected and replaced with final
screenshots: mobile height, anchor placement, repeated descriptions and controls/
card alignment. Final layouts have readable text/statuses, visible keyboard focus,
usable controls, wrapping labels and no horizontal overflow at 390px. Long pages
scroll vertically as expected.

Evidence is Git-ignored under
`/home/ruhaanb622/sfi-foundation/phase1/Frontend/qa-evidence/`, accessible through
`/home/ruhaanb622/sfi-foundation/phase1/qa-evidence/` (a local symlink). Ignore
behavior was checked with git check-ignore. `browser-results.json` holds check,
viewport, console and network results; screenshots are not committed.

| Screenshot | Viewport | Visual review |
| --- | --- | --- |
| `01-spec-desktop.png` | 1440×1000 | Reviewed |
| `01-spec-desktop-search.png` | 1440×1000 | Reviewed |
| `03-search-16.1.png` | 1440×1000 | Reviewed |
| `04-search-20.1-1.png` | 1440×1000 | Reviewed |
| `05-search-20.1-2.png` | 1440×1000 | Reviewed |
| `06-all-categories.png` | 1440×1000 | Reviewed |
| `07-verified-pdf-action.png` | 1440×1000 | Reviewed |
| `07-opened-verified-pdf.png` | 1440×1000 | Reviewed |
| `08-unverified-pdf.png` | 1440×1000 | Reviewed |
| `08-negative-revalidation.png` | 1440×1000 | Reviewed |
| `02-spec-mobile.png` | 390×844 | Reviewed |
| `11-input-validation.png` | 1440×1000 | Reviewed |
| `12-admin-canonical-management.png` | 1440×1000 | Reviewed |
| `13-existing-gear-review.png` | 1440×1000 | Reviewed |
| `09-manufacturer-dashboard.png` | 1440×1000 | Reviewed |
| `11-reminder-validation.png` | 1440×1000 | Reviewed |
| `10-reminder-settings.png` | 1440×1000 | Reviewed |
| `09-manufacturer-mobile.png` | 390×844 | Reviewed |
| `10-reminder-mobile.png` | 390×844 | Reviewed |

## E. Git safety

Both repositories remain on **feature/sfi-phase1-spec-search**. Initial clean
Phase 1 commits were Backend 17429135b276691440af8616e648cff175552e29 and Frontend
4128d04138a92aa2aa25c060b0577f0e4322e4f0. Repair implementation commits:

- Backend catalog/document/admin repairs: 32cf5b4.
- Backend existing gear-client compatibility: 2b17c5bbcc6395083f917c94d4a2d1eb1d42ef5e.
- Frontend UI/browser regression repairs: 77915a71106e82a215ac3da54fab129290d221bc.
- The subsequent backend documentation commit contains this final report and public audit.

Local main refs were checked before and after work and remain:

- Backend: 23981acd4dff77dc587a3d2eba9ca01367ae0643.
- Frontend: a22a2f296abc07790060efb7933a91066b2274af.

The original backend's unrelated dirty files and original frontend were preserved.
Only the Phase 1 worktrees were edited. No reset, force push, merge, push, deployment
or upload was performed. New tracked files were audited: no private source PDF,
DOCX/ZIP, database, screenshot, cache, model binary or credential file was added.
Existing tracked private/runtime concerns were not rewritten or removed.

## F. Release conditions

Implementation and localhost visual acceptance pass. Production readiness remains
conditional on SFI's review of the 20.1 discrepancy and other 17 public-URL review
exceptions, the 29 source identities without local matches, and category review
for eight identities. Keep those actions suppressed until approved evidence is
available. The full catalog's preserved legacy-only identities are not endorsements.

MySQL 8.4 was actually tested in the disposable container
`sfi-phase1-repair-mysql`, bound only to 127.0.0.1:13367; production credentials
were never used. Additive/repeated migration, Unicode, rollback, constraints,
transactions, canonical identity, legacy relations and actual full imports passed.
The separate actual-import schema retained all 140 legacy rows and yielded 148
rows/111 identities, with a no-op second import. This does not replace backup,
restore, credential review and deployment checks on the eventual target version.
The container remains isolated and can be stopped after inspection.

Reminders and manufacturer management remain a fictional in-memory prototype.
No real notifications, real manufacturer records or production operational claims
are made. Existing tracked credential history still requires owner review as
already documented before this repair. No deployment is authorized by this report.

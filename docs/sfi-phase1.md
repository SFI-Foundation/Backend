# SFI Phase 1 delivery

## Scope and architecture

See [the initial audit](sfi-phase1-audit.md), [public link evidence](sfi-phase1-link-validation.json),
[import results](sfi-phase1-import-results.md), and [verification](sfi-phase1-verification.md).

The existing Flask/SQLAlchemy API and Jekyll/vanilla-JS/Sass frontend remain in use.
`catalog.py` aggregates existing rows by normalized **full** specification number.
Suffixes and slash qualifiers remain significant (20.1/1 and 20.1/2 stay separate): 25.5 and 25.5E are different identities. Historical
revision labels and product aliases remain in the response; they are not promoted
to current PDF links. Categories are a union across associated legacy rows and
reviewed import metadata. No legacy rows, users, gear, chunks or foreign keys are
deleted by the new importer. Newly created admin records cannot duplicate an
existing full number. Existing legacy duplicates are retained for reference
integrity; list/search/stats consistently operate on canonical identities.

An additive `sfi_catalog_entries` table stores one JSON payload per full number.
It contains descriptions, aliases, categories, keywords, product-specific
recertification rules, source hashes/locations, document hashes, match status,
verified public-link evidence and review warnings. This avoids changing existing
columns or assigning revision dates to the legacy `effective_date` field.
`SfiSpecChunk.spec` repairs the missing inverse relationship. The existing chatbot
search adapter continues returning ORM records. Search uses fixed ORM reads and
an in-memory ranker suitable for this small catalog, with no user-supplied SQL.

## Local import

Use the backend's existing Python environment (`pip install -r requirements.txt`
when preparing a new environment). No external AI/OCR services are used. DOCX
processing uses standard-library ZIP/XML and PDF processing uses existing
pdfplumber. Keep sources and detailed reports outside both repositories.

From Backend, set the actual source directory. In this workspace it is:

```bash
export SFI_PRIVATE_DATA_DIR=/home/ruhaanb622/sfi-foundation/sfi-private-data
python scripts/import_sfi_catalog.py --source-dir "$SFI_PRIVATE_DATA_DIR" \
  --dry-run --report /tmp/sfi-import-report.json
```

Omitting `--apply` always means dry-run. `--source-dir` overrides the environment.
The default is `../sfi-private-data` from the current directory; use an absolute
path when invoking from another directory. `--catalog` optionally supplies a
reviewed legacy JSON catalog for category/alias enrichment. No URL is guessed
from these legacy filenames.

```bash
# Optional public downloads only; no private source text is transmitted.
python scripts/import_sfi_catalog.py --source-dir "$SFI_PRIVATE_DATA_DIR" \
  --validate-links --report /tmp/sfi-import-with-links.json

# Strict review gate: nonzero for unresolved source/document/category warnings.
python scripts/import_sfi_catalog.py --source-dir "$SFI_PRIVATE_DATA_DIR" \
  --strict --report /tmp/sfi-strict-report.json
```

The actual supplied data does not pass strict review because documents/categories
remain unresolved. Non-strict imports retain review flags and unavailable links.
Parser errors or an empty catalog block all writes. Database writes commit once;
failures roll back and are reported. Stable normalized full numbers and sorted
JSON make repeats no-ops. Unknown extension fields, existing categories, aliases,
keywords and manually reviewed product names survive subsequent imports. Source
conflicts retain both values and cannot establish a current public PDF.

The importer accepts structured four-column list tables in PDF/DOCX and nested
PDFs in ZIP. It does not execute macros or extract archive members to disk. Limits:
512 members/files, 256 MiB total expanded data, 16 MiB per document, compression
ratio 200, 100 pages per PDF. Absolute/traversal/Windows paths, symlinks, duplicate
archive names, encrypted members and unsafe XML declarations are rejected.
Additional DOCX/list PDFs and standalone specification PDFs can be placed under
the source directory. Other file types are ignored. Scans need a separately
approved local OCR workflow; none are uploaded automatically.

## Migration and isolated database

Do **not** use `scripts/db_init.py`: it drops all application tables. Do not use
legacy `generate_data` against an existing database. The retained `initSfiSpecs`
function now inserts only missing full numbers and never deletes/replaces rows.
For local SQLite, normal Flask startup creates missing tables and seeds an empty
catalog from the sibling Frontend (or SFI-Frontend) JSON, or explicit
`SFI_SPECS_PATH`. Restart the backend
after updating the code. Existing catalog rows and metadata are preserved.
Startup does not import documents or verify PDF links.

For production and non-SQLite databases, run the explicit migration before
starting the updated application.

Prepare an entirely new disposable catalog sandbox:

```bash
python scripts/phase1_local.py --database sqlite:////tmp/sfi-phase1-local.db --prepare
python scripts/migrate_sfi_catalog.py --database sqlite:////tmp/sfi-phase1-local.db
python scripts/import_sfi_catalog.py --source-dir "$SFI_PRIVATE_DATA_DIR" \
  --apply --database sqlite:////tmp/sfi-phase1-local.db \
  --validate-links --report /tmp/sfi-applied-report.json
```

`--prepare` refuses existing files. For an existing development SQLite database,
run only the migration and import with its explicit URI. The migration takes a
SQLite backup, creates only the additional table, and is repeatable. Legacy IDs
and rows stay intact. An existing `sfi_specs` table is required for apply. The
migration uses SQLAlchemy DDL. The repairs were tested against an isolated
MySQL 8.4 instance: additive/repeated migrations, full imports, repeated imports,
Unicode, rollback, legacy foreign keys, canonical archives and concurrent creates.
Stop writers and take a separately verified MySQL backup before any eventual
MySQL rollout: MySQL DDL implicitly commits. No production database was accessed.

`SFI_DATABASE_URI` is an optional full-app database override for isolated local
work. The importer/migration still require `--database` and never infer a
production URI from application configuration. Avoid secrets in shell history.

## Search API

Existing public routes, unchanged paths:

* `GET /api/sfi/specs` — browse, optionally `category=<exact label>`.
* `GET /api/sfi/specs/search?q=16.1` — deterministic metadata search.
* `GET /api/sfi/categories` — sorted canonical category labels.
* `GET /api/sfi/stats` — canonical counts and per-category membership counts.
* `GET /api/sfi/specs/<legacy-id>` — canonical representation of that legacy row.

Search trims and collapses whitespace and is case-insensitive. Rank order: exact
full number, number prefix, product/alias phrase, description/keywords, category.
Every query term must match. Ties use full number then stable legacy ID.
`sfi_search_terms.json` contains only explicitly verified terminology and source
links (for example harness/seat belt terms in restraint documents). There is no
new AI search dependency. The existing optional classifier remains separate.

Parameters: `q` up to 200 characters; category up to 100; `page=1..100000`;
`limit=1..200` (default 200). Empty search returns JSON 400; browse uses `/specs`.
Invalid pagination/length also returns 400. Missing migration or database
unavailability returns JSON 503. Out-of-range pages return an empty array.
SQL punctuation is treated as text, never SQL or wildcard syntax.

Default responses remain arrays, with legacy fields (`id`, `spec_number`,
`product_name`, `category`, `subcategory`, `spec_pdf`, manufacturer/products paths,
`effective_date`). Add `format=page` for the frontend envelope:

```json
{"items": [], "total": 0, "page": 1, "limit": 20}
```

Additive fields include `canonical_id`, `legacy_ids`, `legacy_revisions`, `aliases`,
`categories`, `description`, `revision_date`, `recertification_rules`, `keywords`,
`import_status`, `document_status`, `view_spec_url`,
`local_document_available`, and `warnings`. Old PDF paths remain for compatibility;
**only `view_spec_url` with `document_status=verified_current` is actionable**.
Default arrays carry `X-Total-Count`; cross-origin clients should use the envelope.
Category membership totals may exceed the unique overall count. Category filters
now match whole labels, not substrings. Admin writes keep existing authorization;
401/403 remain enforced, duplicate creates return 409. Actual normalized identity/revision/PDF changes
invalidate link evidence until reviewed; unchanged saves and product-only edits preserve approval. Editing a category preserves previous
associations; removal of a category requires a reviewed metadata change.

## Documents and future public access

The validator discovers links on official SFI category pages, checks every
redirect against the official HTTPS host allowlist, limits response sizes, then
verifies PDF bytes, content number, filename consistency, effective date and
latest edited/revised date against the reconciled list. Reviewed-only dates are
not treated as revisions. A newer public PDF that disagrees with the supplied
list is flagged for review rather than silently replacing that list.

Local evidence has a separate `local_document_status` (`local_current_unpublished`,
`outdated`, or `missing`). Public document states are `not_checked`,
`verified_current`, `rejected`, `temporarily_unavailable`, and `needs_review`.
Every explicit negative check revokes approval. Historical evidence is retained
privately. Imports cannot restore approval based only on equal revision strings. Unmatched, missing, ambiguous and conflict cases cannot
produce a view action. The UI never publishes local paths. Original PDFs remain
in the private source folder/archive with hashes and member paths in the local
report. No files were uploaded. Standalone revalidation is available with:

```bash
python scripts/validate_sfi_links.py --import-report /tmp/sfi-import-report.json \
  --report /tmp/sfi-public-link-report.json \
  --database sqlite:////tmp/sfi-phase1-local.db
```

For eventual deployment, prefer validated official links. If SFI approves serving
its own documents, use an authenticated backend download or private object storage
with authorized, short-lived signed URLs. Confirm redistribution rights, audience,
revision ownership and replacement policy before publishing. A public GitHub repo
or Jekyll assets directory is not private document storage.

## Launch and manual verification

From Backend:

```bash
python scripts/phase1_local.py --database sqlite:////tmp/sfi-phase1-local.db --port 8605
```

This opt-in localhost server reuses the real catalog blueprint and database code;
it has no real accounts. For browser administration, add `--demo-accounts` both
when preparing a NEW sandbox and when starting it. This creates only two fictional
accounts and requires a preparation marker. Open `http://localhost:8605/local-demo/`
and choose a synthetic role. This opt-in sandbox also registers the real group
and gear routes for authorized fictional QA flows. Use `localhost` consistently
for cookie hosts. The classifier deliberately reports Offline in this sandbox. Existing classifier/profile routes belong to the full
application and are unavailable in this focused sandbox. To test those features,
use the normal `main.py` with an explicitly isolated `SFI_DATABASE_URI`, after
migration; do not point it at an existing production database.

From Frontend:

```bash
npm ci
bundle install
bundle exec jekyll serve --host 127.0.0.1 --port 4000 --baseurl "" \
  --destination /tmp/sfi-phase1-preview
```

Open `http://localhost:4000/sfi-specs/` and
`http://localhost:4000/sfi-manufacturer-demo/`. Existing API configuration selects
`http://localhost:8605` locally. The demo uses memory only and resets on refresh.
It has fictional manufacturer names and DEMO registration/specification IDs;
no real manufacturer certification is inferred from catalog data. No jobs,
email, SMS, account access or persistence are implemented by the prototype.

Manual checklist:

1. Dry-run both source lists; inspect conflicts, unmatched records and file hashes.
   Apply only to the sandbox; repeat and confirm zero inserts/updates.
2. Search `3.2A`, `16.1`, `25.5`, uppercase names, repeated whitespace, `harness`,
   and a description. Exact full number must rank first when present.
3. Select All and overlapping categories; confirm each full number appears once
   and category badges/counts remain consistent. 25.5E stays distinct from 25.5.
4. Check revision and rating-specific recertification details. Open verified PDFs;
   ensure missing/outdated documents have no fabricated link.
5. Use Tab, Enter, clear, Previous/Next and category buttons. Test narrow screens,
   no-match queries, offline/error retry and loading announcements.
6. Open the labeled prototype. Search/filter fictional registrations, edit an
   expiration, change the preview instant/timezone, disable six-month/all notices,
   and inspect upcoming/overdue messages. Refresh to confirm reset.
7. Check leap-year/month-end and local-midnight transitions; expiration day is
   inclusive and overdue starts on the following local calendar day.
8. In an isolated full-app account fixture, confirm anonymous/non-admin catalog
   writes fail and duplicate creates return 409. Never use production accounts.

## Rollout, rollback and limitations

No push, merge, deployment, production configuration change, real manufacturer
access or outgoing notification occurred. Review both feature branches together.
Before a PR: resolve/document remaining source exceptions, review tracked secrets
with credential owners, verify target database backup/restore, test MySQL in a
throwaway environment, and agree on any future document publication policy.

An eventual approved rollout should stop catalog writers, back up the database,
apply the additive migration, dry-run/review imports, apply in one transaction,
verify canonical counts and sample public links, then release the compatible UI.
Run strict mode as a review gate, not an instruction to invent missing values.
Revalidate public links near release: verification is point-in-time.

Rollback application commits with ordinary revert commits or restore the prior
release after team approval; never rewrite shared history. Leave the additive
table and imported rows intact when rolling back code. For a data rollback,
restore the verified backup only while writers are stopped and after accounting
for newer user writes. Never drop all tables or delete users to undo a catalog
change. No automatic production rollback or destructive down migration is supplied.

Known limits: small-catalog in-memory search, target deployment database still requires rollout checks, no scanned
OCR, no automatic source-conflict resolution, no public hosting of private PDFs,
no real manufacturer-management backend and no notification delivery. Legacy
SQLAlchemy/deprecation warnings and unrelated Jekyll route/post warnings remain.
Existing tracked database/model files, Frontend `.env`, mirrored PDFs, a game ZIP
and an approximately 84 MB HTML file were reported and left unchanged. Secret
values are intentionally absent from these documents and new commits.

## Repair acceptance

See [repair and browser evidence](sfi-phase1-repairs.md) for final commands and
results. Canonical deletion now means archive, not physical row deletion:
`DELETE /api/sfi/specs/<id>` requires `{"confirm_canonical_id":"16.1"}`.
It hides every row in that identity while retaining historical/related records.
Admins inspect `GET /api/sfi/specs/archived` and restore with
`POST /api/sfi/specs/<id>/restore` and the same confirmation. Restoration requires
fresh PDF review; it cannot revive a historical approval. Imports preserve archive
flags. Canonical renames move the group together and retain an archived tombstone.

Creation reserves the unique metadata primary key in the same transaction as the
legacy insert. Conflicting concurrent requests receive 409 with a rollback; no
destructive uniqueness migration touches legacy duplicates. Input objects, string
types, lengths and full-number grammar are checked before binding values to SQL.
Catalog responses use `Cache-Control: no-store` so archive/restore and PDF revocation
are visible immediately. The standalone validator's optional explicit `--database`
persists only document states and evidence, with snapshot checks to avoid granting
stale approval after concurrent edits. Its nonzero exit may accompany a successful
revocation; it reports failed document validation, not a rolled-back revocation.

## Empty catalog after normal startup (2026-11-12)

The `/sfi-specs/` initial All request must return the Phase 1 envelope
`{items, total, page, limit}`. A successful response with `items: []` and
`total: 0` means the connected database has no published catalog; it is different
from an API failure or a filtered search with no matches. The frontend never
substitutes a bundled JSON catalog for the backend.

In the `SFI-Backend` / `SFI-Frontend` workspace, normal `python main.py` startup
previously searched only sibling `Frontend/_data/sfi_specs.json`. With no
`SFI_SPECS_PATH`, it logged `Local SFI catalog seed skipped` and left the local
SQLite catalog empty. Source discovery now checks `Frontend`, then
`SFI-Frontend`, independently of the current working directory. An explicit
`SFI_SPECS_PATH` remains authoritative, including missing or invalid sources;
an invalid preferred source does not silently fall back to another catalog.
The existing nonproduction SQLite bootstrap runs only when `sfi_specs` has no
rows. It leaves existing rows, canonical archives, document approvals and related
records intact. It does not import private documents or approve PDF links.

Local browser evidence before the fix: `window.SFI_API_BASE` was
`http://localhost:8605`; the process was the sibling Backend's `main.py`, using
`instance/volumes/user_management.db`, with zero rows in both `sfi_specs` and
`sfi_catalog_entries`. The stats/categories/paginated-list requests returned
200 and valid empty responses. CORS allowed `http://localhost:4500`.
Restarting normal `main.py` against an explicitly disposable SQLite database
with the repaired source discovery produced:

| Request | Before | After |
| --- | --- | --- |
| `/api/sfi/stats` | 200; 0 specs, 0 categories, 0 subcategories | 200; 103 canonical specs, 6 categories, 8 subcategories |
| `/api/sfi/categories` | 200; `[]` | 200; array of 6 categories |
| `/api/sfi/specs?format=page&page=1&limit=20&category=all` | 200; 0 items, total 0 | 200; 20 items, total 103 |
| `/api/sfi/health` | 404; HTML | 404; HTML |

`/api/sfi/health` is registered by `scripts/phase1_local.py` only. Its 404 under
normal `main.py` is expected and does not establish the backend revision. Use
the stats/categories/page contract and the deployed checkout/image revision to
check compatibility. The public JSON bootstrap is intentionally less rich than
a reviewed Phase 1 private import: these 103 identities all remain `not_checked`
with no public PDF actions. Do not infer document approval from catalog presence.

For this workspace, stop the existing local backend in its terminal, then restart
it on this feature branch. This command explicitly selects the readable source
and retains normal database configuration:

```bash
cd /home/ruhaanb622/sfi-foundation/SFI-Backend
SFI_SPECS_PATH=/home/ruhaanb622/sfi-foundation/SFI-Frontend/_data/sfi_specs.json \
  venv/bin/python main.py
```

Wait for the frontend's normal Jekyll regeneration, then refresh
`http://localhost:4500/sfi-specs/`. If the local database already contains rows,
startup intentionally does not top it up; review the explicit additive import
below rather than using `generate_data`. Changing a source path does not import
or approve documents in an existing catalog.

### Hosted checks and operator-only migration/import

The published Pages artifact at `https://sfi-foundation.github.io/Frontend/`
currently builds an empty `sfi_api_base`, selecting
`https://greppers-be.opencodingsociety.com`. Read-only checks on 2026-11-12 found
that backend's stats returned 140 legacy rows / 7 categories / 9 subcategories,
but `format=page&category=all` returned an empty **array**, not the Phase 1
envelope. Responses did not contain `Access-Control-Allow-Origin` for
`https://sfi-foundation.github.io`; Chromium confirmed that the requests were
blocked by CORS. The hosted problem therefore needs a compatible backend
rollout and CORS/proxy verification, rather than a blind data reseed.
No deployed host/database access or deployment revision was available through
the connected tools; Backend GitHub deployments and Actions runs were empty.
The exact deployed database, table counts, metadata migration and import state
remain unverified. Do not infer those from legacy public stats.

Before any production write, the operator must identify the serving process or
container and revision (`git rev-parse HEAD`, or the image's recorded source
revision), compare it with the reviewed Backend revision containing PR #38 and
this fix, and inspect the effective `SFI_DATABASE_URI` or MySQL target with
credentials redacted. Open SQLite with `mode=ro` if applicable. For MySQL use a
read-only session to check existence and row counts of `sfi_specs` and
`sfi_catalog_entries`; inspect archive/document status distribution without
rewriting it. Check the actual proxy serving the Greppers hostname forwards
OPTIONS and lets Flask own credentialed CORS. The current Flask allowlist already
includes the Pages origin; adding duplicate proxy CORS headers is unnecessary.

Read-only HTTP checks (run after rollout too):

```bash
curl -i -H 'Origin: https://sfi-foundation.github.io' \
  https://greppers-be.opencodingsociety.com/api/sfi/stats
curl -i -H 'Origin: https://sfi-foundation.github.io' \
  https://greppers-be.opencodingsociety.com/api/sfi/categories
curl -i -H 'Origin: https://sfi-foundation.github.io' \
  'https://greppers-be.opencodingsociety.com/api/sfi/specs?format=page&page=1&limit=20&category=all'
curl -i -X OPTIONS -H 'Origin: https://sfi-foundation.github.io' \
  -H 'Access-Control-Request-Method: GET' \
  https://greppers-be.opencodingsociety.com/api/sfi/specs
```

Expect exactly one allow-origin header matching the Pages origin, credentialed
CORS, a successful preflight, and a paginated object containing real rows. If the
operator confirms a different backend URL, set Frontend `_config.yml`
`sfi_api_base` to its scheme/host (without `/api`) and rebuild the published
artifact; verify `assets/js/sfi/api-base.js` and the browser Network URLs.
Do not pick an unverified replacement host.

The importer dry-run below reads sources and writes only a private local report;
it does not connect to or change the target database. This review's dry-run is
under `/tmp/sfi-empty-catalog-fix/import-dry-run.json`: 220 observations, 108
canonical identities, 29 unmatched identities, 2 unmatched documents, and no
conflicting source fields. That run did not validate external links or apply
anything; its non-strict unblocked status is not import approval. Review missing sources,
conflicts, warnings and document evidence before approving an apply. Keep reports
outside Git. `--validate-links` performs read-only requests to official SFI URLs;
omitting it does not verify or approve any current public document.

```bash
# From Backend, using the deployment's Python environment:
python scripts/import_sfi_catalog.py --dry-run \
  --source-dir "$SFI_PRIVATE_DATA_DIR" --catalog sfi_specs.json \
  --validate-links --report /tmp/sfi-catalog-dry-run.json
```

Only if inspection confirms migration/import is needed: stop writers, take and
verify a target database backup, coordinate a maintenance window, and review the
report. The operator supplies `SFI_TARGET_DATABASE_URI` through the deployment's
secret configuration; never echo it or commit it. These are the existing
explicit, additive commands, prepared for the operator and **not executed against
production** during this fix:

```bash
python scripts/migrate_sfi_catalog.py --database "$SFI_TARGET_DATABASE_URI"
python scripts/import_sfi_catalog.py --apply --database "$SFI_TARGET_DATABASE_URI" \
  --source-dir "$SFI_PRIVATE_DATA_DIR" --catalog sfi_specs.json \
  --validate-links --report /tmp/sfi-catalog-applied.json
```

Preserve legacy IDs, archives and existing reviewed approvals. If the database is
already migrated/imported, do not re-import merely to fix CORS or an old backend
image. Follow the earlier migration/rollback guidance, including MySQL DDL
limitations. Deployment and all production writes remain operator actions.

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

For a successful startup with an empty catalog, see
[the local empty-catalog investigation and recovery](sfi-empty-catalog-recovery.md).
The application must use the same database that was migrated and imported;
merging the code does not copy a previously prepared `/tmp` catalog.

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
Normal application startup does not import documents or create the new metadata
table. Run its explicit migration first.

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

Legacy catalog discovery supports sibling checkouts named `Frontend` or
`SFI-Frontend`, in that order. An explicit `SFI_SPECS_PATH` remains authoritative;
an invalid override fails rather than silently switching sources. The public
frontend uses `https://sfi.opencodingsociety.com` at the domain root, and that
exact HTTPS origin is included in Flask's credentialed CORS allowlist.

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

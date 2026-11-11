# Phase 1 audit

## Safety and baseline (2026-11-10)

Work is in isolated `phase1/Backend` and `phase1/Frontend` worktrees on
`feature/sfi-phase1-spec-search`. Bases: Backend
`146179056ea57910accc79d098fa8434211b019c`; Frontend
`3273784f303993d3a535d62b41debc69786cff12`. Both origins were fetched.
The frontend origin is a personal fork; the official team HEAD was independently
checked and is the same commit. Neither original checkout nor local main moved.

The original backend has unrelated uncommitted feedback/profile changes in
README.md, api/user.py, main.py, testing/test_sfi_profile.py, two binary runtime
files, and four new feedback files. They remain in that checkout untouched.
The original frontend is clean. The requested ~/sfi-project does not exist;
the supplied repositories and private sources are in ~/sfi-foundation.

## Existing architecture and defects

Flask/Flask-RESTful, SQLAlchemy, Flask-Migrate, SQLite locally and configured
MySQL in production. No Alembic migration directory exists; the gear migration
uses an explicit additive CLI. Jekyll, vanilla JavaScript and scoped Sass serve
the frontend. Reuse these frameworks and existing admin authorization.

* The backend JSON and frontend catalog each contain 140 expanded records for
  103 full spec numbers. The tracked user database has the same counts. Repeated
  categories cause duplicate cards. Product names are not safe identities.
* `initSfiSpecs` deletes all catalog rows, risking identifiers and PDF chunks.
  `scripts/db_init.py` drops ALL application tables; do not run it.
* `SfiSpec.chunks` names a missing inverse relationship. An unreachable block
  after `search_sfi_spec_chunks` contains that inverse. This breaks mapping.
* Metadata search exists but lacks canonical results, descriptions, exact-match
  priority, bounded pagination and keyword metadata. Public UI instead downloads
  the entire catalog and applies a separate fuzzy ranker.
* Frontend constructs public URLs from filenames, including dated hardcoded
  showcase PDFs; neither HTTP success nor current revision was established.
* CRUD endpoints already use `admin_required`; preserve it. Search is public.
* `main.py` creates tables/groups at import. Catalog ingestion must remain an
  explicit CLI, independent of main and its broad initialization.

## Source inspection

All expected files exist outside Git: SpecList3.pdf (7 pages, structured tables),
SpecList.docx (Word tables), Specs.zip (81 members, ~18.5 MB expanded, PDFs under
Specs/). Lists are marked updated June 16, 2026. Full numbers include revision
suffixes; 3.2A has separate product rating/recertification rules. 6.1W is explicitly
a section within 6.1. Individual PDFs distinguish effective dates, edits,
reviews and manufacturer retests. These must not become one generic expiry.

## Git hygiene and baseline checks

Databases and a model binary are already tracked in Backend. Frontend currently
tracks a `.env` containing API-key and password variables (values not reproduced),
as well as existing mirrored public PDFs and a game asset ZIP. Its history also
contains old `.env` commits. Credential owners must review/rotate exposed values. Reported, not removed or rewritten. Existing
default secret/password fallbacks are unsuitable for deployment. No private
documents will be added. Ignore new databases, archives, caches and reports.

Before changes: `unittest discover -s tests -v`: 10 passed. Catalog/config tests:
14 executed, 2 errors from the broken chunk relationship. Frontend baseline and
final verification are recorded in the delivery notes.

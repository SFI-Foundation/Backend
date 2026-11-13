# Empty specification catalog: diagnosis and deployment guidance

## Root cause

The application opened its empty default SQLite database while the imported
Phase 1 catalog remained in a separately prepared database. Both catalog tables
existed in the selected database but contained zero records. Merging application
code did not provision that database, and restarting selected the same empty file.
There was no evidence of startup deleting specification records.

`__init__.py` loads backend configuration and chooses `SFI_DATABASE_URI` when set,
otherwise configured MySQL credentials, otherwise `sqlite:///volumes/user_management.db`.
Flask-SQLAlchemy resolves that relative SQLite URI under the Flask **instance**
directory. The default development file is therefore
`instance/volumes/user_management.db`, relative to the backend checkout.
`SFI_SPECS_PATH` selects legacy seed input; it does not select a database.

Normal startup creates legacy tables but leaves catalog metadata migration and
specification import to the explicit Phase 1 workflow. The public API previously
returned HTTP 200 with empty arrays and zero statistics for this state. The
frontend correctly displayed those responses. Neither frontend response parsing
nor public visibility filtering caused the regression.

## Data flow and diagnostics

1. The explicit legacy seed loads the configured specification JSON and inserts
   missing normalized full numbers without deleting existing records.
2. `scripts/migrate_sfi_catalog.py` adds the metadata table. The canonical
   `scripts/import_sfi_catalog.py` workflow reconciles source lists and documents,
   defaults to dry-run, and requires an explicit database for writes.
3. `catalog.canonical_specs()` groups legacy records by full identity, overlays
   metadata, unions categories, and excludes archived identities from public reads.
4. Browse, search, categories, and statistics use that canonical set. Browse and
   search return arrays by default or `{items, total, page, limit}` with
   `format=page`. The frontend requests the envelope and renders its items/counts.

The repaired catalog code detects a physically empty specification table before
archive filtering. Public catalog handlers return HTTP 503 with:

```json
{
  "error": "Catalog not initialized; verify the selected database and follow the Phase 1 setup or recovery workflow",
  "code": "catalog_not_initialized"
}
```

Missing metadata tables and unavailable database connections retain their existing
HTTP 503 diagnostics. Legitimate no-match searches and catalogs whose records are
all archived still return HTTP 200 with empty results. The change does not run
seeds, migrations, imports, or document verification automatically.

Public specification visibility is separate from PDF approval. An unverified or
rejected PDF does not hide its specification. Only `verified_current` evidence
and an allowed official PDF URL produce an actionable `view_spec_url`.
Archive filtering, authentication, approval, and revocation rules remain intact.

Anonymous requests to `/api/sfi/me` and `/api/id` correctly return HTTP 401 because
there is no session or JWT. These identity probes control account/admin UI and do
not gate public catalog reads.

## Verified local recovery

Recovery was completed separately from this code change. The established canonical
importer was first run in dry-run mode against the original sources. Its identities,
source hashes, revisions, categories, document matches, and recertification rules
matched the saved final Phase 1 database. The selected database already had the
required schema, so no migration was needed for this local recovery.

Before data changes, the active database and verified source were backed up and
recovery was rehearsed on a separate copy. With local writers stopped, only exact
catalog rows were inserted into the empty selected catalog in one transaction.
Catalog rows were compared with the saved source, noncatalog table contents were
checked unchanged, and database integrity and foreign-key checks passed. Existing
database files were retained. Recovery scripts, data, backups, and detailed local
evidence remain outside this repository.

| Measure | Before recovery | After recovery and restart |
| --- | ---: | ---: |
| Legacy specification rows | 0 | 148 |
| Imported metadata identities | 0 | 108 |
| Public canonical specifications | 0 | 111 |
| Categories | 0 | 8 |
| Subcategories | 0 | 8 |

The original Phase 1 reconciliation reported 106 imported identities and 77 local
matches. Later parser repairs restored `20.1/1` and `20.1/2`, yielding 108 imported
identities and 79 identity/document matches. Three retained legacy-only identities
account for the 111 public results. Shared-document matches do not establish PDF
approval.

All saved PDF states were preserved: 63 verified-current, 16 rejected, and 29
needs-review imported states, plus 3 unchecked legacy-only records. Exactly 63
public specifications had actionable PDF URLs. No PDF was revalidated or promoted
by recovery; the saved approval timestamps remain historical evidence.

## Verification

Run from the backend checkout:

```bash
PYTHONPATH=.:tests venv/bin/python -m unittest discover -s tests -p 'test_*catalog*.py'
PYTHONPATH=.:tests venv/bin/python -m unittest discover -s tests -p 'test_phase1_repairs.py'
PYTHONPATH=.:tests venv/bin/python -m unittest discover -s tests -p 'test_public_security.py'
PYTHONPATH=.:tests venv/bin/python -m unittest discover -s testing -p 'test_sfi_config.py'
git diff --check
```

All **56 backend tests** passed (28 catalog, 13 Phase 1 repair, 7 public security,
8 configuration). The four initialization regressions cover empty and populated
databases, array/envelope compatibility, search and statistics, public archive
filtering, PDF gating, and reopening a file database with revocation preserved.
Existing repair tests cover approval-preserving saves, document-edit invalidation,
negative revalidation, repeat imports, archive/restore, and unauthorized writes.

Frontend Phase 1 tests passed across three test files. Signed-out Chromium checks
against the real local API verified desktop/mobile rendering, counts, pagination,
category filtering, specification numbers, product names, case-insensitive search,
no-match results, PDF restrictions, and absence of page JavaScript errors.

The normal application was stopped and started again without a database override.
Complete public catalog responses and statistics were identical after restart:
111 specifications, 8 categories, and 8 subcategories. Anonymous identity responses
remained HTTP 401.

## Deployment considerations

This PR supplies diagnostics and regression coverage. **Catalog provisioning is a
separate operation** and is not performed by merging or starting this code.

Use the [established Phase 1 workflow](sfi-phase1.md) to provision the same database
selected by the application. For a new isolated sandbox, the documented sequence
is preparation, additive migration, import dry-run/review, then explicit apply.
Preparation refuses existing files. An existing populated database requires a
reviewed additive migration/import or recovery plan that preserves its data and
PDF decisions. Do not replace it with a seed or a local QA database.

Before any authorized data-changing rollout, stop relevant writers, take and
verify a database backup, validate the planned changes, and verify the public API
afterward. Do not use destructive `scripts/db_init.py` or broad `generate_data`
for catalog recovery. MySQL migration requires its own backup and rollout review.

No production database, credentials, environment files, imported catalog payloads,
or recovery artifacts are included in this change. Deployment still requires
separate catalog provisioning and review of unresolved PDF/category evidence.

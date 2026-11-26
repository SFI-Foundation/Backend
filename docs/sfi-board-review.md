# Board-review catalog and revised PDF process

Paired local branch: `demo/board-review-20261125`, based on current fetched Backend
main `75d0306`. [Frontend meeting guide](https://github.com/SFI-Foundation/Frontend/blob/demo/board-review-20261125/docs/sfi-board-review.md)
contains exact startup commands, URLs and the walkthrough. Existing Backend checkout
changes (including feedback work) were preserved in their original location.

The only catalog behavior change is a documented product-term alias for Spec 3.3:
`racing gloves`. The supplied lists explicitly include Gloves under Spec 3.3;
the phrase maps that product language into the existing deterministic search.
Every query word must match, which previously made `racing gloves` fail even
though `gloves` matched imported metadata. No classifier or parallel catalog was
added. Exact-number ranking, category membership and canonical deduplication are
unchanged. Category remains optional.

## Current implemented process for a revised specification PDF

This is the repository's existing technical publication gate. Jennifer's approval
of SFI's operational ownership and business policy is still needed; this document
does not claim that approval has already occurred.

1. Obtain the authoritative revised PDF and updated specification lists from the
   responsible SFI owner. Preserve originals privately, with revision provenance.
   **Jennifer:** confirm the owner, approval authority and authoritative dates.
2. Update the private source set (`SpecList.docx`, `SpecList3.pdf`, `Specs.zip`)
   consistently. Run `scripts/import_sfi_catalog.py --dry-run` with an explicit
   source directory and private report path. Review conflicts, unmatched identities,
   hashes and effective/edited/revised dates. Strict mode is a review gate, not
   permission to infer missing information. **Jennifer:** resolve conflicting
   revisions, rating details or recertification values before accepting them.
3. Publish through the existing official SFI publication channel, using an
   authorized document owner. A local private PDF alone does not authorize a link.
   **Jennifer:** confirm replacement/publication and historical-retention policy.
   Hosting copies in this application remains unimplemented pending permission and
   access decisions. Do not place private PDFs in Jekyll assets or a public repo.
4. Apply reviewed metadata through the existing importer to an explicitly selected,
   prepared/migrated database. Alternatively an authorized admin can edit the
   existing canonical record's revision/effective/PDF fields. There is no new
   upload screen. Actual number/revision/effective-date/PDF-path changes revoke
   document approval (`needs_review`); normalized no-op saves and product-only
   edits preserve it. Canonical edits cover the related legacy rows.
5. Revalidate official links against the updated reviewed metadata using the
   existing standalone validator. It discovers official pages, restricts HTTPS
   redirects/hosts and response size, checks PDF bytes, identity, filename and
   revision dates, then persists the result only if the database snapshot still
   matches. Example, using the freshly generated importer report:

   ```bash
   python scripts/validate_sfi_links.py \
     --import-report /tmp/revised-spec-import.json \
     --report /tmp/revised-spec-public-validation.json \
     --database sqlite:////tmp/revised-spec-review.db
   ```

   Only `verified_current` plus a validated official `view_spec_url` produces the
   public PDF action. A newer public PDF that disagrees with the list needs review;
   matching a date string alone cannot restore historical approval. Failed checks,
   definitive missing files and mismatches revoke the action. A nonzero validator
   exit can mean the revocation was successfully saved, not rolled back.
6. Verify through public `/sfi-specs/`: correct metadata, one canonical result,
   approved PDF opening or visible unavailability, and optional category filters.
   Archive/restore retains history; restore requires fresh approval. Catalog
   responses use `Cache-Control: no-store`. Revalidate near any eventual release
   because approval evidence is point-in-time. This task makes no production changes.

Original detailed references: [catalog implementation](sfi-phase1.md) and
[repair/approval regression behavior](sfi-phase1-repairs.md).

## Local fixture and verification

`scripts/prepare_board_review.py` reuses `phase1_local.prepare`, the additive
migration, `build_import`, `validate_links`, and `apply_import`. It refuses existing
SQLite files and non-SQLite databases. It keeps reports private and checks public
approval for Specs 1.1 and 3.3 only. The other documents remain unavailable for the
meeting's negative-state example. No manufacturer or reminder backend is added;
those records stay in the existing development-gated browser prototype.

Prepared live fixture: `sfi-private-data/board-review/preview.db` under the workspace root,
backed up from and preserving `/tmp/sfi-board-review.db`. Relaunch after WSL/reboot
from the root with `./start-sfi-board-review.sh start`; use
`./start-sfi-board-review.sh restart` for config/dependency/database-URI changes.
The launcher enables `--reload` (stat, debugger disabled), watches Python and
`sfi_search_terms.json`, and never initializes or overwrites an existing fixture.
Backend state/logs are in `reports/board-preview-live/`. A second independent preparation
at `/tmp/sfi-board-rebuild-check.db` verified the repeatable helper against supplied
sources and official PDFs. Both meeting PDFs were verified with their supplied
hashes and revision evidence. Private reports/logs are under `/tmp/sfi-board-*`.
The initial catalog contains 111 unique specifications; 108 reconcile with the
supplied lists. Existing source exceptions remain documented by the importer.

The focused server now registers the existing profile/settings blueprints. Their
real auth guards return 401 for guests, allowing the current public header to
render its normal guest state. The catalog-only fixture contains no real accounts;
`--demo-accounts` is not used for the board review.

Checks:

```bash
PYTHON_DOTENV_DISABLED=1 SFI_DATABASE_URI=sqlite:// \
  /home/ruhaanb622/sfi-foundation/SFI-Backend/venv/bin/python \
  -m unittest discover -s tests -v
PYTHON_DOTENV_DISABLED=1 SFI_DATABASE_URI=sqlite:// \
  /home/ruhaanb622/sfi-foundation/SFI-Backend/venv/bin/python \
  -m unittest testing.test_sfi_config testing.test_sfi_pdf_ingest -v
```

The final discovery run completed 86 tests: 83 passed and three MySQL checks skipped.
The suite covers product terms without category, canonical deduplication, approved/
unsafe/unavailable URLs, negative revalidation, revocation on edits, no-op saves,
archive/restore and retained evidence. Three existing disposable-MySQL tests require
`SFI_QA_MYSQL_URI` and were skipped; no live database was used. Additional config/PDF
ingest checks passed (15 tests). Known SQLAlchemy relationship/deprecation warnings
remain unrelated to these changes.

Normal-browser evidence is recorded in
`/tmp/sfi-board-browser-evidence/results.json`: homepage navigation, both search
examples, actual official PDF requests/new tabs/200 bytes, unavailable document
without action, all 111 unique results, multi-test dashboard, selected-record
reminder dates, mobile fit, reset, and demo-control exclusion over HTTP.

Jennifer's manufacturer/test/renewal/reminder decisions are listed together in the
frontend guide. Manufacturer dates are manually supplied fictional values; racer
recertification periods do not drive them. There is no delivery, scheduling or
appointment implementation.

## Live preview handoff

Use `./start-sfi-board-review.sh start` from the workspace root and open
<http://localhost:4600/>. `restart` is the exact full refresh command after config,
dependency, plugin, environment or database-URI changes; `status` shows actual
commands and working directories. The server uses the durable prepared fixture
at `sfi-private-data/board-review/preview.db`, and stat reload is opt-in only.
The original 8605 backend and 4500 preview are preserved. Ordinary Python and
product-term JSON edits reload automatically; the debugger remains disabled.
A reversible alias edit was verified through the real public search, restored,
and verified absent. Windows localhost API and rendered Edge dashboard checks
passed. See the frontend guide and `reports/board-preview-live/` for evidence.

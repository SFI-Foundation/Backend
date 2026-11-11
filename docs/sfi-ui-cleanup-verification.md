# Phase 1 UI cleanup follow-up — 2026-11-11

Both repositories use `feature/sfi-phase1-ui-cleanup`, preserving the existing Phase 1 and earlier cleanup commits. No push, merge or deployment occurred.

Full current report, exact commands, complete changed-file manifests, browser evidence and remaining issues: [Frontend acceptance report](../../Frontend/docs/sfi-ui-cleanup-verification.md).

Backend follow-up expands manufacturer-route checks across default and production-like configurations, GET/POST and attempted query-parameter opt-in. All remain 404 without sample records. The PDF-ingestion test now registers the existing User/Section models before fixture table creation so it runs independently.

Implementation follow-up commits: Frontend `ee9164082`; Backend `0c2ab67`. The final documentation commit in each repository is the branch HEAD reported by `git log -1`.

Executed: 58 backend regressions passed against SQLite plus a dedicated disposable MySQL schema (zero skips); 7 configuration, 7 PDF-ingestion and 13 isolated full-app authentication/profile cases passed. Rendered-client authentication and gear integrations passed. Catalog/import/PDF-verification row checksums remain unchanged in the source and disposable SQLite databases. No private artifacts are committed.

Review http://localhost:4000/sfi-specs/ and the default-disabled http://localhost:4000/sfi-manufacturer-demo/ (404). The explicitly enabled development prototype is isolated at http://localhost:4100/sfi-manufacturer-demo/. Backend health is http://localhost:8605/api/sfi/health, using `/tmp/sfi-ui-cleanup-20261111.db`.

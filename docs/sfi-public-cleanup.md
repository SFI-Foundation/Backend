# SFI Phase 1 public cleanup — local review

## Git protection

Cleanup worktrees:

- Backend: `/home/ruhaanb622/sfi-foundation/phase1/public-cleanup/Backend`
- Frontend: `/home/ruhaanb622/sfi-foundation/phase1/public-cleanup/Frontend`

Both use `feature/sfi-phase1-public-cleanup`.
Backend base: `b134c76fa75cdac857975d306cd7fc75780c85b3`.
Frontend base: `77915a71106e82a215ac3da54fab129290d221bc`.
The accepted Phase 1 worktrees remain on `feature/sfi-phase1-spec-search`.
The original backend's unrelated uncommitted changes, original frontend checkout and main branches were preserved. No push, reset, force-push, merge, deployment, private-source upload or notification occurred.

## Public changes

Removed the interactive car/zone showcase, classifier input/actions, model statistics and public manufacturer-prototype link. Search, all category memberships, canonical deduplication, metadata, pagination, verified-PDF links and unavailable/review states are retained. Statistics and mobile spacing use the existing design tokens. Old research UI is retained as excluded `_internal/specification-research.md`; reusable manufacturer page and JS are development-only. Server classifier research requires an explicit local flag and is prohibited in production.

Security details and owner actions: [security review](sfi-public-security.md).
Jennifer's shareable report: [17 PDF discrepancies](sfi-pdf-discrepancies-for-jennifer.md).
The printable PDF is in ignored `../Frontend/qa-evidence/sfi-pdf-discrepancies-for-jennifer.pdf`; do not publish the QA directory. No report was sent to Jennifer.

## Launch the reviewed website

Use two terminals. Commands below point to the cleanup worktrees, not the accepted or original worktrees. Dependencies are already available in this workspace. On a new machine, create a virtual environment/install Backend requirements, run `npm install` in Frontend, and install its Ruby bundle. Never copy credentials from the old frontend `.env`.

Terminal 1:

```bash
cd /home/ruhaanb622/sfi-foundation/phase1/public-cleanup/Backend
PYTHON_DOTENV_DISABLED=1 /home/ruhaanb622/sfi-foundation/SFI-Backend/venv/bin/python scripts/phase1_local.py \
  --database sqlite:////tmp/sfi-public-cleanup-local.db --port 8605 --demo-accounts
```

Terminal 2:

```bash
cd /home/ruhaanb622/sfi-foundation/phase1/public-cleanup/Frontend
BUNDLE_PATH=/tmp/sfi-phase1-gems make public-review-serve
```

Open **http://localhost:4000/sfi-specs/**. Use `localhost` consistently for frontend and API cookies. The HTTP bind remains loopback only. Test `16.1`, `20.1/1`, `20.1/2`, a product name, category chips and pagination. `16.1` has an existing verified PDF action; disputed/missing documents have no current-PDF action. Visit **http://localhost:4000/sfi-manufacturer-demo/** to confirm 404. The optional local-only account selector is **http://localhost:8605/local-demo/**; choose synthetic member/admin to inspect authorization. These are fictional QA users, not manufacturer records. Ctrl+C stops each owned server. If a port is occupied, identify its process and stop only the matching review server; do not use the legacy broad `make stop` target.

The existing SQLite fixture was freshly created for this review and populated with the previously accepted local validation evidence. It has 111 canonical results and preserves all 108 imported document states (63 verified, 16 rejected, 29 needing review). No disputed PDF was newly approved. Three additional legacy-only identities retain their existing review state. This fixture is local and disposable, never production.

To prepare a different NEW local database, use `phase1_local.py --database <new SQLite URI> --prepare --demo-accounts`, then `migrate_sfi_catalog.py --database <same URI>`. Preparation refuses existing files. Follow `sfi-phase1.md` for explicit private-source import and public-link validation; keep detailed provenance outside Git. A fresh import without verification will correctly show unavailable PDF actions. The full app reads Backend `.env`; start from `.env.example`, keep all real values local, and supply persistent random secrets for stable sessions. The isolated review command disables dotenv and generates local signing material without production secrets. Restarting it invalidates its synthetic sessions.

Production startup requirements: `IS_PRODUCTION=true`, `SECRET_KEY` with at least 32 cryptographically random characters, strong `ADMIN_PASSWORD` and `DEFAULT_PASSWORD` of at least 16 characters, and complete authenticated MySQL configuration (`DB_ENDPOINT`, `DB_USERNAME`, `DB_PASSWORD` or `SFI_DATABASE_URI`). Supplied placeholders/weak secrets, partial database configuration, SQLite production fallback, invalid booleans and production research flags fail before opening the DB. Optional other seeded-user passwords are independently random if omitted. Do not run legacy seed/migration scripts against production during review.

## Internal prototype inspection

The default build emits neither the manufacturer route nor its dataset. For an explicit local development preview only:

```bash
JEKYLL_ENV=development BUNDLE_PATH=/tmp/sfi-phase1-gems bundle exec jekyll serve \
  --config _config.yml,_config.development.yml --host 127.0.0.1 --port 4100 --baseurl "" \
  --destination /tmp/sfi-internal-demo-preview
```

Open `/sfi-manufacturer-demo/` on that port. Do not combine the development overlay with a production build: it fails. No manufacturer API or notification sender exists. The retained classifier API separately requires `IS_PRODUCTION=false SFI_INTERNAL_RESEARCH=true`; there is no classifier UI in the public search page.

## QA results

See the final acceptance evidence appended below. Screenshots, generated PDF, detailed audit candidates and browser JSON are ignored under `Frontend/qa-evidence/`. They are not served by Jekyll.

## Executed verification

| Check | Result |
|---|---|
| Backend `unittest discover -s tests -v`, SQLite and separate disposable MySQL schema | 58 passed; zero skips |
| Backend configuration/PDF-ingestion suites | 14 passed |
| Isolated full-app authentication/profile suite | 13 passed |
| Frontend profile, gear, search, manufacturer prototype and cleanup cases (`node --test --test-isolation=none`, with `SFI_BUILT_SITE`) | 38 passed; zero skips |
| Rendered client → real Flask authentication integration | 7 passed |
| Gear moderation integration | 1 passed |
| Production Jekyll build through focused Make target | Passed; inherited duplicate-route/post-link warnings remain |
| Complete artifact credential/prototype scan | 3 passed; all generated files scanned |
| Sass and API/baseurl configuration validation | Passed |
| Research/demo strict boolean and production-off gate checks | Passed |
| Explicit development prototype build and Chromium preview | Passed; fictional labels, five synthetic records, working filters, noindex, no notification POSTs |
| Same directory development build after switching flag off | Prototype page and JS dataset removed |
| Ruff critical checks, changed Python format/compile, browser-script syntax and Git whitespace | Passed |

The first browser run exposed a leftover removed-control listener; it was fixed and now has a full-page initialization regression test. Visual inspection identified a third mobile statistic wrapping to an extra row and a scoped header rule that did not apply; both were corrected. Tests were rerun after the relevant changes. An initial production output scan found inherited embedded provider keys; those were removed and the final complete output scan passed. Initial socket/theme-fetch restrictions were resolved using explicit execution approvals. These earlier failures are not counted as passes.

The real localhost browser run uses `scripts/test-sfi-public-browser.cjs`, Chromium and the actual Flask/Jekyll servers (no API mocks). It checks 1440×1000 and 390×844, 16.1 and both 20.1 qualifiers, product search, every category, all 111 identities across six pages, previous-page behavior, official PDF opening and 200 PDF bytes, unavailable/rejected documents, every internal navigation destination, disabled manufacturer/research routes and assets, environment/QA access, CORS allow/deny/preflight, member/admin permissions, actual password login and logout. The full document-status/URL snapshot is identical before and after: 63 verified_current, 16 rejected, 29 needs_review and 3 legacy not_checked. Page exceptions, unexpected console errors and failed requests are zero in the final run. Expected anonymous 401 and deliberate blocked-route 404 responses are recorded separately from unexpected errors.

### Screenshot evidence

Ignored directory: `/home/ruhaanb622/sfi-foundation/phase1/public-cleanup/Frontend/qa-evidence/`.
For both `desktop-` and `mobile-`: `specification-page.png`, `search-16.1.png`, `search-20.1-1.png`, `search-20.1-2.png`, `all-categories.png`, `pdf-unavailable.png`, `public-navigation.png`, `manufacturer-demo-blocked.png`. Additional files: `mobile-search-controls.png`, `development-only-manufacturer-demo.png`, `browser-results.json`, the two-page shareable PDF and rendered PDF page previews. Actual PNGs and the report pages were opened and visually reviewed; screenshots are not merely generated. No credentials, private source pages, production data or real manufacturer records appear in them.

### Reproduce final browser checks

With the two main review servers running, from Frontend:

```bash
LD_LIBRARY_PATH=/tmp/sfi-phase1-browser-libs/root/usr/lib/x86_64-linux-gnu \
PLAYWRIGHT_MODULE=/tmp/sfi-phase1-browser/node_modules/playwright \
CHROME_PATH=/home/ruhaanb622/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome \
SFI_QA_PYTHON=/home/ruhaanb622/sfi-foundation/SFI-Backend/venv/bin/python \
node scripts/test-sfi-public-browser.cjs
```

This deliberately changes only the disposable synthetic member's password in `/tmp/sfi-public-cleanup-local.db`, in memory, to exercise the normal password login. Never point the harness at production. The synthetic role selector remains available for manual review. The test prints the tracked shareable HTML report from sibling Backend/docs into the ignored evidence directory. A separate optional `SFI_QA_DEMO_OFF_URL` can point to the development preview rebuilt with the flag off to verify stale output is unreachable over HTTP.

### Remaining production release blockers

Credential owners must revoke/rotate potentially active exposures and plan session/account remediation; SFI must confirm the 17 disputed public PDFs and eight unresolved category assignments. Revalidate official links near release. Production secrets/database/HTTPS/CORS/cookie settings and the inherited backend's unrelated legacy functionality need a release review. The inherited educational publication scope still produces duplicate-route/deprecation warnings. No disputed version has been approved here. Passing local catalog/auth acceptance does not establish production readiness.

## Files changed

### Backend

- `.env.example`
- `.gitignore`
- `__init__.py`
- `api/sfi_classifier.py`
- `api/sfi_spec.py`
- `api/user.py`
- `docs/sfi-pdf-discrepancies-for-jennifer.html`
- `docs/sfi-pdf-discrepancies-for-jennifer.md`
- `docs/sfi-public-cleanup.md`
- `docs/sfi-public-security.md`
- `instance/volumes/sfi_specs.db`
- `instance/volumes/sfi_specs.db.bak`
- `instance/volumes/user_management.db`
- `instance/volumes/user_management_bak.db`
- `main.py`
- `scripts/old/rds_init.py`
- `scripts/old/update_data.py`
- `scripts/phase1_local.py`
- `security_config.py`
- `testing/test_sfi_profile.py`
- `tests/test_public_security.py`

### Frontend

- `.env`
- `.env.example`
- `.gitignore`
- `Makefile`
- `_config.development.yml`
- `_config.yml`
- `_includes/slim_sidebar.html`
- `_internal/manufacturer-demo.js`
- `_internal/manufacturer-demo.md`
- `_internal/specification-research.md`
- `_layouts/base_chatadpt.html`
- `_layouts/base_chatog.html`
- `_layouts/certchatbot.html`
- `_layouts/chatbot.html`
- `_layouts/lessonbase.html`
- `_layouts/lessonbasecapture.html`
- `_layouts/sfi.html`
- `_plugins/internal_demos.rb`
- `_plugins/public_output_guard.rb`
- `_posts/CSP/flask/2023-10-22-flask-debug-walk.md`
- `_posts/CSP/flask/2023-10-22-flocker_api.md`
- `_posts/Foundation/B-tools_and_equipment/2025-08-06-flask-api.md`
- `_posts/Foundation/C-github_pages/2023-08-24-github_pages-anatomy.md`
- `_posts/Foundation/C-github_pages/2023-08-25-github_pages-utterances.md`
- `_posts/Foundation/C-github_pages/2023-08-26-github-pages-jekyll.md`
- `_posts/Foundation/C-github_pages/2025-08-18-nbfilemanagement.md`
- `_sass/sfi/base/_page.scss`
- `assets/js/sfi/manufacturer-demo.js`
- `docs/sfi-public-cleanup.md`
- `hacks/cs-portfolio-quest/analytics/submodule_1.md`
- `hacks/cs-portfolio-quest/resume/submodule_5.md`
- `navigation/sfi-manufacturer-demo.md`
- `navigation/sfi-specs.md`
- `package.json`
- `scripts/test-sfi-demo-gates.rb`
- `scripts/test-sfi-manufacturer-demo.mjs`
- `scripts/test-sfi-public-browser.cjs`
- `scripts/test-sfi-public-cleanup.mjs`
- `scripts/test-sfi-spec-search.mjs`

# Backend #8 — development evidence (2026-10-23)

Owner @ruhaanb622; proposed priority High. Board originally Backlog (parking lot),
then Progress (In Progress); Integration (PR) only after the results below.
No deployment, presentation, or stakeholder acceptance is claimed.

Backend branch `feature/8-sfi-config` starts at fetched origin/main
`31ad1151c2140aa77d2a45d7c6561920ef360317`; Frontend companion branch
`feature/backend-8-sfi-config` starts at
`7f636f28fc0f9bb047e221d1a787c8bcd853d4b1`.
Frontend PR #16 was verified merged at `2026-10-23T00:07:48Z`; Backend PR #16
returned 404. Open Backend #24 and Frontend #17 were inspected and kept separate.
Neither repository/parent search nor GitHub repository root contained AGENTS.md.

## Exact commands and final results

Disposable sibling clones: `/tmp/sfi-config/Backend` and `/tmp/sfi-config/Frontend`.
Python executable: `/home/ruhaanb622/sfi-foundation/SFI-Backend/venv/bin/python`
(existing Python 3.12.3 environment; fresh dependency installation not claimed).
Clones were made with `git clone --no-hardlinks` from local sources, then their
origins were set to the organization URLs, fetched, and branched from origin/main.
No compatibility symlink was created.

```bash
PYTHON_DOTENV_DISABLED=1 "$PYTHON" testing/test_sfi_config.py -v
# Ran 7 tests in 2.331s; OK; exit 0.
PYTHON_DOTENV_DISABLED=1 "$PYTHON" testing/test_sfi_profile.py
# Ran 13 tests in 19.618s; OK; exit 0 (isolated child snapshots).
```

The focused tests cover default, absolute/relative custom and blank paths;
repository/scripts/unrelated working directories; missing, malformed and invalid
schema files; importer validation before any delete; shared classifier fallback;
stale cache rejection; actionable 503; allowed and disallowed GET/OPTIONS origins.
The profile suite retains existing authentication, session and role checks.
It now supplies an explicit JSON fixture because its isolated snapshot has no
sibling Frontend. Nine existing warning/deprecation lines remain in that suite.

Only inside the disposable Backend clone, the copied SQLite fixture was replaced
with a new empty `instance/volumes/user_management.db`. The actual initializer ran:

```bash
env -i PATH=/usr/bin:/bin PYTHON_DOTENV_DISABLED=1 FORCE_YES=true \
  MPLCONFIGDIR=/tmp/sfi-config/mpl "$PYTHON" scripts/db_init.py
# Exit 0. Imported 140 spec rows; trained on 2150 samples (54.0% reported training accuracy).
env -i PATH=/usr/bin:/bin PYTHON_DOTENV_DISABLED=1 \
  MPLCONFIGDIR=/tmp/sfi-config/mpl FLASK_PORT=18423 "$PYTHON" main.py
curl -fsS http://localhost:18423/api/sfi/specs
curl -fsS http://localhost:18423/api/sfi/classifier/status
```

Both GETs returned 200; specs JSON contains 140 rows. Classifier status:
`trained=true`, `training_samples=2150`, `spec_classes=103`,
`category_classes=7`, `accuracy=0.5395` (training metric, not held-out accuracy).
A real OPTIONS with Origin `https://sfi-foundation.github.io`, requested POST
and `Authorization, Content-Type, X-Origin` returned **204**, exact allow-origin,
credentials **true**, and those allowed headers. GET with Origin
`https://evil.example` returned **403**, no allow-origin header.
An additional isolated full-app check confirmed invalid import leaves 140 rows,
JSON fallback loads 136 product entries, altered data invalidates the saved
classifier, login and `/api/sfi/me` each return **200** with credentialed CORS.
No existing/shared database was reset or migrated. Generated clone DB/model files
are excluded from the commits by explicit staging.

Frontend used the existing ignored Gemfile.lock and installed dependencies:

```bash
bundle check
# The Gemfile's dependencies are satisfied.
bundle exec jekyll build --disable-disk-cache --destination /tmp/sfi-config/site
# Final build exit 0; done in 30.585 seconds; 83 warning/deprecation lines.
node scripts/test-sfi-api-config.mjs /tmp/sfi-config/site
# PASS: local/loopback/Pages defaults, custom URL, auth credentials,
# quiz requests, and generated SFI script references.
LD_LIBRARY_PATH=/tmp/sfi-config/libs/extracted/usr/lib/x86_64-linux-gnu \
PLAYWRIGHT_MODULE=/tmp/sfi-config/browser/node_modules/playwright \
node scripts/test-sfi-setup-browser.mjs /tmp/sfi-config/site /Frontend /tmp/sfi-config/theme.png
# PASS: 13 pages; no missingLocalRequests or pageErrors; CSS/logo 200;
# navigation rgb(26,95,168), header rgb(255,255,255), body font Inter.
LD_LIBRARY_PATH=/tmp/sfi-config/libs/extracted/usr/lib/x86_64-linux-gnu \
PLAYWRIGHT_MODULE=/tmp/sfi-config/browser/node_modules/playwright \
node scripts/test-sfi-config-browser.mjs /tmp/sfi-config/site http://localhost:18423
# PASS: actual browser CORS + preflight from real localhost:4600 server;
# 140 rendered rows; trained status; custom API base; unchanged blue nav; zero page errors.
git diff --check
# Exit 0 in both feature clones.
```

No CSS/theme assets changed. The static smoke excludes external services; the
separate live test exercises the actual disposable backend. The custom backend
URL is injected only in the test server's script response, exercising the same
shared config value without changing the deployed default. Browser libraries and
Playwright were installed/extracted only under `/tmp`.

## Earlier attempts and limits

- Initial CLI network and listening sockets were blocked in the sandbox; authorized
  external CLI/server runs succeeded. The GitHub connector could not resolve
  Backend PR #16 (404); CLI confirmed it is Frontend PR #16 that merged.
- First db_init attempt stopped at its prompt (EOF); rerun used FORCE_YES only in
  the disposable clone. Importing main creates tables before that prompt.
- First profile run: 13 tests, one error because isolated snapshots lacked a sibling
  Frontend; explicit fixture-path configuration fixed it (final 13/13 pass).
- Bundler without the local ignored lockfile resolved newer missing gems; using the
  existing installed lockfile passed. No dependency upgrade is included.
- Chromium initially lacked libnspr4/libnss3/libasound; Debian packages were
  extracted into `/tmp`. First live browser test used intercepted navigation and
  hit Chromium loopback access protection; real local HTTP serving passed.
- Jekyll retains existing Sass/post_url and duplicate-output warnings. nginx is
  inspected here, but target-host syntax check/reload and deployed behavior remain
  pending; both templates forward CORS/OPTIONS to Flask with no competing headers.
- Production URL replacement is unconfirmed. Current service default is retained;
  `sfi_api_base` enables a later confirmed URL. Existing production cookies still
  target `.opencodingsociety.com`; a different host requires cookie verification.
- Deployment, real Pages-to-backend auth/CORS, presentation, and stakeholder
  acceptance remain pending. Do not merge, mark Done, or auto-close #8.

The original Backend status remains only `M instance/volumes/user_management.db`;
original Frontend remains clean. Those checkouts and their running preview were
not edited by this work. Key Commits and both PR links are retained in issue #8.

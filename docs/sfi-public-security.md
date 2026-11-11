# Public cleanup security review

This branch removes confirmed credential exposures from current source and adds configuration/build gates. It does not rotate credentials, rewrite history, certify the whole inherited application, or authorize release.

## Confirmed fixes

- Frontend `.env` is removed from Git tracking; its local file is retained. `.env.example` contains comments only. Environment variants and private-key formats are ignored; Jekyll explicitly excludes environment files, internal prototypes, QA evidence and engineering documentation.
- Removed embedded provider keys from six inherited frontend layouts, four GitHub Pages lesson posts, two portfolio lesson pages, the VoiceRSS sidebar and the weather API lesson. Replaced published example account passwords with placeholders. Existing backend `GEMINI_API_KEY` and other provider configuration remain server-side. Retained unrelated educational AI examples no longer contain usable embedded keys; wiring those examples to an authorized server integration is separate work.
- Removed hardcoded `rds_password` in Backend `scripts/old/rds_init.py` and `scripts/old/update_data.py`. Both now require `DB_ENDPOINT`, `DB_USERNAME` and `DB_PASSWORD`; neither script was executed.
- Four tracked backend SQLite/database backup files are removed from the index and retained locally. Database contents and password hashes are no longer added to new feature commits. The classifier research model is unchanged.
- `security_config.py` validates strict true/false flags, secret strength, required production secrets, complete DB settings, and production MySQL configuration before database initialization. Missing local values use cryptographic per-process random values. Supplied placeholders and trivially weak values fail with variable names only. Production requires environment-provided `SECRET_KEY`, `ADMIN_PASSWORD` and `DEFAULT_PASSWORD`; no known password or signing-secret fallback remains. Optional seed-account passwords are independently random if omitted.
- Flask session cookies use HttpOnly; production uses Secure / SameSite=None and local uses SameSite=Lax. Existing authentication JWT cookie names, HTTPS domain policy, CORS allowlist and credential handling are preserved. Authentication reads the validated production flag. Full-app direct startup disables debugging in production. Removed raw request-body logging in the legacy user-update handler.
- Classifier endpoints and ML detect mode are gated behind `SFI_INTERNAL_RESEARCH=false` by default. Production rejects enabling that flag and the API independently blocks it in production. Research code is retained.
- Manufacturer data existed only in static prototype JavaScript; no manufacturer dataset API existed. Both page and dataset now live in `_internal`, outside default output. Explicit boolean `sfi_manufacturer_demo: true` works only with `JEKYLL_ENV=development`; production opt-in fails. Default/off builds emit neither page nor dataset. No real manufacturers, expiration jobs or notification services were created.
- The Jekyll output guard fails on common AWS/Google/GitHub/private-key patterns and secret-file names. Artifact tests also compare known exposed values privately in memory and reject fictional manufacturer data. Errors contain paths, never credential values.

## Owner-action checklist — values intentionally omitted

**Assume potentially active exposures until the relevant owner confirms revocation. Removing current files does not remove history.** No validity probes or production-account changes were made.

| Owner | Variables / credential type | Locations requiring review and owner action |
|---|---|---|
| Gamify / shared development account owner | `GAMIFY_API_KEY`, `ADMIN_PASSWORD`, `DEFAULT_PASSWORD`, `MIRAGE_PASSWORD` | Frontend `.env` history. Revoke/rotate keys and reset any reused account passwords. Review use/access logs. |
| Google Cloud / Gemini project owner | `GEMINI_API_KEY`, `VITE_GEMINI_API_KEY`, `API_KEY`, `apiKey`, `gemini-api-key`, provider keys in URLs | Frontend historical `.env`, `_config.yml`, `_layouts/{base_chatadpt,base_chatog,chatbot,certchatbot,lessonbase,lessonbasecapture}.html`, `_posts/Foundation/C-github_pages/`, and `hacks/cs-portfolio-quest/{analytics,resume}/`. Further historical locations are listed below. Revoke exposed keys and review quotas, billing, restrictions and access logs. Store replacements only on the server. |
| VoiceRSS / weather API owners | `API_KEY` | Frontend `_includes/slim_sidebar.html` and `_posts/Foundation/B-tools_and_equipment/2025-08-06-flask-api.md` history. Verify ownership and revoke/rotate potentially active keys. |
| Database / Kasm infrastructure owner | `rds_password`, `DB_PASSWORD`, `PASSWORD` | Backend `scripts/old/{rds_init,update_data}.py`, historical `__init__.py`, `scripts/db_restore-sqlite2prod.py`; Frontend historical `_notebooks/KASM/**/2024-08-10-rds-documentation.ipynb`. Rotate/revoke any still-active database credentials; inspect access logs and shared-password reuse. Do not execute legacy migration scripts as part of cleanup. |
| Backend authentication / account owner | signing-secret fallback, JWTs, account passwords and database password hashes | Backend historical `cookies.txt`, `LOGIN_CREDENTIALS.md`, `README.md`, `scripts/verify_*.py`, `main.py`, `api/user.py`, `model/{user,users,players}.py`, and tracked database history. Review whether formerly public/default passwords were used, reset affected accounts, invalidate exposed sessions, and supply a new strong production signing key through managed configuration. Rotation will invalidate sessions and needs an owner-controlled rollout. |
| Legacy stock API owner | `api_key` | Backend historical `api/stock.py`. Confirm whether the key remains active and revoke/rotate if so. |

Additional frontend historical provider-key locations: `_includes/nav/gchat.html`, `_layouts/{interactives}.html`, `_posts/Foundation/C-github_pages/2025-08-23-jekyll_themes.md`, `hacks/wordquill.md`, `hacks/cs-portfolio-quest/resume/submodule_6.md`, `_notebooks/CSSE/JavaScriptLessons/Mathematic_Expressions/`, `_notebooks/Foundation/F-projects/2025-09-02-whack_a_mole.ipynb`. Historical JWT-shaped values also occur in `assets/js/gamify/adventureGame.js`, `casino/dices.md` and JWT lesson posts/notebooks; account owners should confirm these were synthetic/expired and invalidate any active tokens.

Public WordPress `data-secret` embed identifiers, game UI properties named `secretBanner`, synthetic unit-test values, intentionally fictional cybersecurity exercises and third-party package test fixtures are heuristic candidates, not evidence of active SFI credentials. Do not rotate unrelated accounts solely because these words occur.

## Audit scope and limits

Read-only reachable-history scan: Backend **697 commits / 1,075 selected text blobs**; Frontend **19,078 commits / 28,890 selected text blobs**. Scanned all reachable local refs and current tracked files using provider patterns and credential-assignment heuristics; redacted candidate locations and blob IDs remain only in ignored `Frontend/qa-evidence/{backend,frontend}-secret-audit.json`. Original values were inspected only in memory and never emitted in reports or terminal summaries.

This is a bounded heuristic audit, not a proof that history is secret-free. Selected text blobs up to 4 MiB were scanned; encoded secrets, large/binary artifacts, unreachable objects, remote-only refs and external accounts are outside that history scan. Database history may retain personal data/hashes and needs owner-controlled remediation. No history was rewritten or remote refs fetched/changed. All known exposed values tested against the complete generated static artifact are absent; common provider-token patterns are absent. New output is protected by a build guard, but owners still need a mature secret scanner in CI and review of historical exposure.

## Remaining release risks

- Owner revocation/rotation above is unresolved; active status has not been tested.
- Seventeen public PDF discrepancies and eight category assignments still require SFI confirmation. Preserve unavailable states and revalidate links close to release.
- The inherited backend has broad legacy functionality outside this change. This work is not a comprehensive production authorization, CSRF, arbitrary-code-execution, AI proxy, file-upload or notification-service audit. Existing unrelated features and deployment settings need a separate release review; passing catalog/auth acceptance does not certify them.
- Jekyll still reports inherited duplicate output-route and deprecated post-link warnings outside the SFI specification page. Review/clean the inherited publication scope before a production release.
- Require `IS_PRODUCTION=true`, a persistent environment-provided signing key, strong bootstrap credentials, reviewed MySQL settings, HTTPS/domain/cookie/CORS validation and normal server/deployment controls in the eventual production environment. Do not use the loopback sandbox or development server for production.

Implementation follows Flask's [configuration](https://flask.palletsprojects.com/en/stable/config/) and [cookie security guidance](https://flask.palletsprojects.com/en/stable/web-security/). Local acceptance and production readiness are separate decisions.

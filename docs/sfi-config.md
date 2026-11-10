# Backend #8 — configuration capstone

Owner: @ruhaanb622. Proposed priority: High. Branch: feature/8-sfi-config.
The list of spec objects manages importer/classifier input; validation sequences
path selection, decoding, and field checks, iterating over entries and selecting
clear failure messages. Tests compare default/custom paths, working directories,
invalid data, allowed and disallowed origins and preflights. These supporting
notes do not claim eligibility for an individual Create submission.

```mermaid
flowchart LR
    ENV["Backend .env / SFI_SPECS_PATH"] --> PATH["Resolve relative to Backend root"]
    JSON["Default sibling Frontend/_data/sfi_specs.json"] --> LOAD["Shared loader: validate JSON and entries"]
    PATH --> LOAD
    LOAD --> IMPORT["Importer: validate before replacing rows"]
    IMPORT --> DB[("SQLite")]
    DB --> CLASS["Classifier: prefer current DB rows"]
    LOAD -->|"JSON fallback"| CLASS
    CFG["Frontend sfi_api_base or existing service default"] --> JS["Shared api-base.js: SFI pages and auth"]
    JS --> LOCAL["Local preview: localhost:4500"]
    JS --> PAGES["Origin: https://sfi-foundation.github.io"]
    LOCAL --> APP["Flask exact origin allowlist + credentials + OPTIONS"]
    PAGES --> NGINX["nginx forwards OPTIONS; no duplicate CORS"] --> APP
    APP --> DB
    APP --> CLASS
    APP --> DENY["Unapproved Origin: 403; no allow-origin header"]
```

The source is validated before destructive import. Admin retraining continues
using DB edits; a fingerprint invalidates a saved classifier trained on other
input. No symlink is required. CORS includes credentials and preserves existing
auth handlers. The current frontend service remains the default because no
replacement URL was confirmed.

Development evidence is retained in issue #8. Deployment (including nginx syntax
check/reload on the target host), production authentication/CORS, presentation,
and stakeholder acceptance remain pending. Do not mark Done or auto-close.

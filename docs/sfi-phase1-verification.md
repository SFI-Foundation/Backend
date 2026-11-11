# Phase 1 verification after independent-review repairs

The original delivery's incorrect 108-row/106-identity/109-result claims are
superseded by [corrected reconciliation](sfi-phase1-import-results.md) and the
[complete repair report](sfi-phase1-repairs.md). This repair began with the clean
Phase 1 worktrees; the original dirty backend worktree was preserved.

Final executed results:

| Check | Result |
| --- | --- |
| Full backend suite, including disposable MySQL 8.4 | 51 passed, zero skipped |
| Config and PDF ingestion suites | 14 passed |
| Isolated profile/authentication harness | 13 passed |
| Frontend profile, gear, search and reminder cases | 34 passed |
| Profile/auth/role UI integration | 7 passed |
| Gear review UI integration | 1 passed |
| Full Jekyll build, scoped Sass, API config checks | Passed |
| Real localhost Chromium acceptance | 16 groups passed; desktop 1440×1000, mobile 390×844 |
| Screenshots captured and visually reviewed | 19, kept outside tracked source |
| Reconciled source observations and identities | 220 observations; 108 source identities; 111 public canonical identities |
| Actual SQLite/MySQL repeated import | 0 inserts, 0 updates, 108 unchanged |
| Public PDF audit | 80 URLs checked, 63 verified, 17 requiring review |

The running application was tested over HTTP at localhost:4000 and localhost:8605.
Unit/DOM tests and the two bridge integration suites complement those browser
checks; the bridge suites report their restricted-environment WSGI pipe transport
and are not presented as browser acceptance. All application databases used by QA
are disposable; no production credentials or database were used.

The browser-discovered mobile input height and cached archive-response defects
were repaired and retested. Explicit labels, keyboard focus, screen reader names,
invalid-value feedback, no outgoing notifications, archive/restore persistence,
negative revalidation, live PDF opening and concurrent creation were exercised.
Expected intentional 4xx console messages, navigation/preflight aborts and the
local QA login page's missing favicon are recorded in the detailed report.

# Optional motorsports onboarding

The current-user profile API stores self-reported motorsports preferences separately
from authentication roles, permission groups, and the retained community-interest
fields. Manufacturer, sanctioning-body, inspector, and staff selections grant no
privileges or organization ownership. Administrator bootstrap, credentials, login,
and role assignment are unchanged.

## API

`GET /api/sfi/profile` retains its existing fields and adds `preferences`. Users
without a preference record receive empty defaults without creating a record.
All profile responses remain private and use `Cache-Control: no-store`.

`PATCH /api/sfi/profile/preferences` and its `PUT` compatibility alias accept JSON
with any subset of the following fields:

| Field | Values / limit | Unanswered value |
| --- | --- | --- |
| `involvement` | Unique enum array | `[]` |
| `visit_reasons` | Unique enum array | `[]` |
| `disciplines` | Unique enum array | `[]` |
| `resources` | Unique enum array | `[]` |
| `update_interests` | Unique enum array; never email consent | `[]` |
| `primary_goal` | One enum value | `null` |
| `organization_name` | Text, 200 characters | `""` |
| `organization_website` | HTTP(S) URL, 500 characters | `""` |
| `job_title` | Text, 120 characters | `""` |
| `additional_notes` | Plain text, 500 characters | `""` |

The machine identifiers are defined in `model/sfi_onboarding.py`. Unknown keys,
unknown values, duplicate selections, wrong types, excessive lengths, malformed
websites, and contradictory exclusive selections return HTTP 400 with field errors.
Websites cannot contain credentials or executable schemes and are never fetched.
Identity is taken exclusively from the existing authenticated session or verified
token. An editable user ID, role, group, or permission field is rejected.

Omitted fields preserve saved answers. Explicit `null` clears a field to its
unanswered representation. `{}` is valid; saving all-empty answers is optional.
Successful writes return the refreshed profile. Failed transactions roll back.
Existing `interests` and `/api/sfi/profile/interests` remain compatible and separate.

```json
{
  "involvement": ["manufacturer", "technical_inspector"],
  "primary_goal": "technical_resources"
}
```

Text must be rendered with `textContent` or a form control's `value`, never as HTML.
Preferences are excluded from public user representations and authentication tokens.
Organization details are unverified claims and do not link to official SFI records.
Any future organization-claim feature needs separate administrator verification.

## Schema preparation and rollback

The additive `sfi_onboarding_preferences` table has a `user_id` primary/foreign key
and one JSON `answers` column. It does not alter `users` or `sfi_profiles`, remap
legacy classifications, or discard legacy interests. The primary key prevents
duplicate records. Existing startup table creation also recognizes the new model.

Before serving the updated API, use the repository's explicit migration convention:

```sh
venv/bin/python scripts/migrate_sfi_onboarding.py --database <explicit-reviewed-uri>
```

The script does not import application configuration or infer database credentials.
Stop writers and take the environment's normal backup first. MySQL DDL is not
transactional. Repeated upgrade is safe.

```sh
venv/bin/python scripts/migrate_sfi_onboarding.py --database <explicit-reviewed-uri> --downgrade
```

Downgrade removes only an empty preferences table and refuses to discard saved
answers. A populated table may remain when rolling back application code; the old
code ignores it. Export/retention decisions require separate review before deletion.
No live migration is part of the development tests or PR publication.

## Verification and limits

```sh
venv/bin/python testing/test_sfi_profile.py
PYTHON_DOTENV_DISABLED=1 venv/bin/python -m unittest discover -s tests -v
```

The profile runner copies source into a disposable directory and exercises real
authentication, owner isolation, validation, partial edits, legacy compatibility,
rollback, migration repeat/reverse behavior, denied self-reported privilege claims,
and preserved administrator access. Broader suites cover authentication recovery,
session/JWT authorization, catalog document approval, and gear permissions.

SQLite migration behavior is tested locally. Existing MySQL integration checks
require a separately configured disposable `SFI_QA_MYSQL_URI`; they must never use
production. Concurrent edits are not versioned; there is no multi-tab conflict UI.
No email subscriptions, organization verification, or manufacturer directory are
introduced by this feature. Release the schema/backend before the dependent frontend.

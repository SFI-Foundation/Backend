# Actual source import and document review

All three expected sources were present. Detailed private provenance reports are
in /tmp/sfi-phase1-final-import-report.json and /tmp/sfi-phase1-cli-repeat-report.json,
outside Git. No original PDF, DOCX, ZIP, database or PDF cache is added by this work.

| Measure | Count |
| --- | ---: |
| PDF list observations | 108 |
| DOCX list observations | 108 |
| Parsed observations combined | 216 |
| Canonical full specification numbers | 106 |
| Redundant/variant observations above canonical count | 110 |
| Conflicting source fields | 0 |
| Archive PDFs inspected | 80 |
| Listed identities matched to local PDFs | 77 |
| Listed identities without their own matching local PDF | 29 |
| Unmatched archive PDFs | 3 |
| First apply metadata inserts | 106 |
| Final repeated apply inserts / updates / unchanged | 0 / 0 / 106 |
| Canonical API results including preserved legacy-only identities | 109 |
| Public URLs checked | 80 |
| Public URLs verified against current supplied metadata | 63 |
| Public URL revision/number review exceptions | 17 |

The 110 extra observations include confirmations between the two lists and
separate product-rating rules (108 observations per source, 106 identities).
They are not 110 corrupt records. Legacy category duplication is separate:
140 expanded rows originally represented 103 full specification numbers.
The importer never deletes those rows. 3.2A and 3.4 rating-specific periods remain
separate rules within one identity, not one invented expiration period.

## Missing local matches

10.1G, 10.2A, 10.3B, 10.4B, 10.5A, 10.6, 11.1, 2.1C, 2.2D, 2.3V, 2.4D, 2.5E, 2.6C, 2.7E, 21.1, 22.1, 25.1K, 25.2E, 25.3D, 25.4D, 25.5E, 25.6A, 40.1, 47.1A, 47.2A, 47.3A, 6.1W, 8.1, 9.1

6.1W is explicitly a section within 6.1, not a standalone PDF in this archive.
That source note is retained; no separate URL is fabricated. Missing matches may
reflect specifications not distributed as individual PDFs; review with SFI rather
than assuming every absent document should be public.

## Unmatched archive documents

* Specs/Spec_20.1.pdf — content number identified; absent from supplied lists.
* Specs/Spec_36.1.pdf — content number identified; absent from supplied lists.
* Specs/Spec_36.2.pdf — content number identified; absent from supplied lists.

The technical bulletin at Specs/TechBulletin_3.2.pdf is matched by its explicit
SFI Technical Bulletin 3.2 header. Wrong-number matches are rejected.
All archive/source originals remain untouched in the private folder.

## Category review

No category was invented for these new full numbers: 11.1, 21.1, 22.1, 3.2, 8.1, 9.1.
They display under the explicit Needs category review label until reviewed.
Existing category associations, product names, PDFs and effective dates remain
available in legacy records and import evidence. Source-list omissions never
erase existing identities. These retained legacy-only records are review items,
not current-document endorsements.

## Public links

The public-only evidence file is [sfi-phase1-link-validation.json](sfi-phase1-link-validation.json).
Checked at 2026-11-11T02:44:08.518158+00:00; all discovery requests used official SFI pages.
The report contains public URLs/hashes/status only, with no private PDF contents.

The 17 exceptions are:

1.2, 1.3, 1.5, 18.1, 20.1, 28.2, 28.4, 29.1, 30.1, 32.1, 34.1, 36.1, 36.2, 39.1, 39.2, 4.2, 44.1

An exception can mean that the public document is newer than the supplied list,
older, absent from the lists, or its revision evidence cannot be reconciled. It
must not be represented as current automatically. Unverified actions are absent
from the UI. The other source identities also lack verified public URLs; their
local files stay private. Revalidate near release; links can change after audit.

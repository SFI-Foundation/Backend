# Actual source import and document review

All three expected sources were present. Detailed private provenance reports are
in /tmp/sfi-repair-verified-import-report.json and /tmp/sfi-repair-repeat-import-report.json,
outside Git. No original PDF, DOCX, ZIP, database or PDF cache is added by this work.

| Measure | Count |
| --- | ---: |
| PDF list observations | 110 |
| DOCX list observations | 110 |
| Parsed observations combined | 220 |
| Canonical full specification numbers | 108 |
| Redundant/variant observations above canonical count | 112 |
| Conflicting source fields | 0 |
| Archive PDFs inspected | 80 |
| Listed identities matched to local PDFs | 79 |
| Listed identities without their own matching local PDF | 29 |
| Unmatched archive PDFs | 2 |
| First apply metadata inserts | 108 |
| Final repeated apply inserts / updates / unchanged | 0 / 0 / 108 |
| Canonical API results including preserved legacy-only identities | 111 |
| Public URLs checked | 80 |
| Public URLs verified against current supplied metadata | 63 |
| Public URL revision/number review exceptions | 17 |

The 112 extra observations include confirmations between the two lists and
separate product-rating rules (110 observations per source, 108 identities).
They include confirmations and rating variants; they are not corrupt records. Legacy category duplication is separate:
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

* Specs/Spec_36.1.pdf — content number identified; absent from supplied lists.
* Specs/Spec_36.2.pdf — content number identified; absent from supplied lists.

20.1/1 and 20.1/2 remain distinct age/rating identities and explicitly share
the 20.1 PDF. Its revision discrepancy remains unresolved; neither identity
is approved for a current-document action. The old statement that 20.1 was
unmatched was incorrect. The original review counted 108 rows per list because
the parser silently dropped these two slash-qualified rows; this repair corrects
that to 110 rows per list.

The technical bulletin at Specs/TechBulletin_3.2.pdf is matched by its explicit
SFI Technical Bulletin 3.2 header. Wrong-number matches are rejected.
All archive/source originals remain untouched in the private folder.

## Category review

No category was invented for these new full numbers: 11.1, 20.1/1, 20.1/2, 21.1, 22.1, 3.2, 8.1, 9.1.
They display under the explicit Needs category review label until reviewed.
Existing category associations, product names, PDFs and effective dates remain
available in legacy records and import evidence. Source-list omissions never
erase existing identities. These retained legacy-only records are review items,
not current-document endorsements.

## Public links

The public-only evidence file is [sfi-phase1-link-validation.json](sfi-phase1-link-validation.json).
Checked at 2026-11-11T04:44:38.521059+00:00; all discovery requests used official SFI pages.
The report contains public URLs/hashes/status only, with no private PDF contents.

The 17 exceptions are:

1.2, 1.3, 1.5, 18.1, 20.1, 28.2, 28.4, 29.1, 30.1, 32.1, 34.1, 36.1, 36.2, 39.1, 39.2, 4.2, 44.1

An exception can mean that the public document is newer than the supplied list,
older, absent from the lists, or its revision evidence cannot be reconciled. It
must not be represented as current automatically. Unverified actions are absent
from the UI. The other source identities also lack verified public URLs; their
local files stay private. Revalidate near release; links can change after audit.

## Database verification after repairs

Disposable SQLite and MySQL 8.4 both retain the 140 original public legacy rows,
add eight previously absent identities, and expose 111 canonical results. A fresh
MySQL import inserted 108 metadata entries; the repeat inserted/updated zero and
left 108 unchanged. Synthetic archive test records remain separate and hidden.

The fresh live audit has 63 verified identities, 16 rejected identities (including
both 20.1 qualifiers), and 29 source identities requiring review without a public
candidate. These identity counts differ from the 80 URLs because 20.1 is shared
and two public PDFs are absent from the supplied lists. No source exception was
automatically declared current.

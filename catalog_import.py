"""Local-only source parsing, reconciliation and transactional catalog upserts."""

import hashlib
import io
import json
import re
import stat
import unicodedata
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

import pdfplumber

from catalog import (
    NUMBER,
    document_number,
    normalize_number,
    retain_document_history,
    valid_number,
)

MAX_MEMBERS = 512
MAX_FILE = 16 * 1024 * 1024
MAX_TOTAL = 256 * 1024 * 1024
MAX_PAGES = 100
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}


def clean(value):
    return ' '.join(str(value or '').split())


def comparable(value):
    value = unicodedata.normalize('NFKC', clean(value)).casefold()
    return re.sub(r'[^a-z0-9]', '', value)


def dates(value):
    pattern = r'\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s*(\d{1,2}),?\s*(\d{4})'
    result = []
    for month, day, year in re.findall(pattern, value, re.IGNORECASE):
        try:
            m = datetime.strptime(month[:3].title(), '%b').month
            result.append(datetime(int(year), m, int(day)).date().isoformat())
        except ValueError:
            continue
    return result


def safe_members(archive):
    members = archive.infolist()
    if len(members) > MAX_MEMBERS or sum(m.file_size for m in members) > MAX_TOTAL:
        raise ValueError('Archive exceeds member or expanded-size limit')
    seen = set()
    for m in members:
        name = m.filename
        path = PurePosixPath(name)
        mode = m.external_attr >> 16
        if (
            path.is_absolute()
            or '..' in path.parts
            or '\\' in name
            or ':' in name
            or stat.S_ISLNK(mode)
            or name in seen
            or m.flag_bits & 1
        ):
            raise ValueError('Unsafe, encrypted, or duplicate archive member')
        seen.add(name)
        if m.file_size > MAX_FILE or m.file_size / max(1, m.compress_size) > 200:
            raise ValueError('Archive member exceeds resource limit')
    return members


def table_record(cells, source, location):
    first = clean(cells[0]) if cells else ''
    looks_like_spec = bool(re.match(r'^(?:SFI\s|[0-9])', first, re.IGNORECASE))
    first = re.sub(r'^SFI\s*(?:SPEC(?:IFICATION)?\s*)?', '', first, flags=re.IGNORECASE)
    if len(cells) != 4:
        if looks_like_spec:
            raise ValueError(
                f'{source} {location}: unsupported specification row (expected four columns)'
            )
        return None
    match = re.match(
        r'^('
        + NUMBER.replace('/', r'\s*/\s*')
        + r'|[0-9]{1,3}\.[0-9]{1,3}\s+[A-Za-z])(?=\s|$|\()',
        first,
        re.IGNORECASE,
    )
    if not match:
        if looks_like_spec:
            raise ValueError(
                f'{source} {location}: malformed or unsupported specification identifier'
            )
        return None
    number = normalize_number(match.group(1))
    # DOCX sometimes splits a revision letter from its number.
    spaced = re.match(r'^(\d+\.\d+)\s+([A-Za-z])(?=\s|$)', first)
    if spaced:
        number = normalize_number(''.join(spaced.groups()))
    if (
        not valid_number(number)
        or not clean(cells[1])
        or first[match.end() :].lstrip().startswith('/')
    ):
        raise ValueError(f'{source} {location}: invalid specification row')
    return {
        'spec_number': number,
        'product_name': clean(cells[1]),
        'revision_date': clean(cells[2]),
        'recertification': clean(cells[3]),
        'identifier_detail': clean(first[match.end() :]),
        'source': source,
        'location': location,
    }


def parse_docx(data, source):
    if len(data) > MAX_FILE:
        raise ValueError('DOCX exceeds size limit')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        safe_members(archive)
        xml = archive.read('word/document.xml')
    if b'<!DOCTYPE' in xml or b'<!ENTITY' in xml:
        raise ValueError('Unsafe XML declaration')
    root = ElementTree.fromstring(xml)
    records = []
    digest = hashlib.sha256(data).hexdigest()
    for index, row in enumerate(root.findall('.//w:tr', NS), 1):
        cells = [
            ' '.join(
                ''.join(
                    (node.text or '')
                    if node.tag == '{' + NS['w'] + '}t'
                    else ' '
                    if node.tag in {'{' + NS['w'] + '}br', '{' + NS['w'] + '}tab'}
                    else ''
                    for node in p.iter()
                )
                for p in c.findall('.//w:p', NS)
            )
            for c in row.findall('w:tc', NS)
        ]
        record = table_record(cells, source, f'row {index}')
        if record:
            record['source_sha256'] = digest
            records.append(record)
    return records


def parse_list_pdf(data, source):
    if len(data) > MAX_FILE or not data.startswith(b'%PDF-'):
        raise ValueError('Invalid or oversized PDF')
    records = []
    digest = hashlib.sha256(data).hexdigest()
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        if len(pdf.pages) > MAX_PAGES:
            raise ValueError('PDF exceeds page limit')
        for index, page in enumerate(pdf.pages, 1):
            for table_index, table in enumerate(page.extract_tables(), 1):
                for row_index, row in enumerate(table, 1):
                    record = table_record(
                        row,
                        source,
                        f'page {index}, table {table_index}, row {row_index}',
                    )
                    if record:
                        record['source_sha256'] = digest
                        records.append(record)
            page.close()
    return records


def inspect_pdf(data, source):
    if len(data) > MAX_FILE or not data.startswith(b'%PDF-'):
        raise ValueError('Invalid or oversized PDF')
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        if len(pdf.pages) > MAX_PAGES:
            raise ValueError('PDF exceeds page limit')
        first = pdf.pages[0].extract_text() or ''
        last = pdf.pages[-1].extract_text() or ''
    header = re.search(
        r'SFI\s+(?:SPECIFICATION|TECHNICAL\s+BULLETIN)\s+(' + NUMBER + r')\b',
        first,
        re.IGNORECASE,
    )
    number = normalize_number(header.group(1)) if header else None
    effective = re.search(r'EFFECTIVE\s*:\s*([^\n]+)', first, re.IGNORECASE)
    effective_dates = dates(effective.group(1)) if effective else []
    revision_dates = list(effective_dates)
    for line in last.splitlines():
        if re.match(r'\s*(Edited|Revised)\s*:', line, re.IGNORECASE):
            revision_dates.extend(dates(line))
    filename = re.search(
        r'(?:Spec[_ -]|TechBulletin[_ -])(' + NUMBER + r')(?=[_. -]|$)',
        Path(source).name,
        re.IGNORECASE,
    )
    filename_number = normalize_number(filename.group(1)) if filename else None
    return {
        'source': source,
        'sha256': hashlib.sha256(data).hexdigest(),
        'spec_number': number,
        'filename_number': filename_number,
        'effective_date': effective_dates[0] if effective_dates else None,
        'latest_change': max(revision_dates) if revision_dates else None,
        'status': 'identified'
        if number and (not filename_number or filename_number == number)
        else 'number_mismatch',
    }


def current_document(document, record):
    expected = dates(record.get('revision_date', ''))
    return (
        document.get('status') == 'identified'
        and document.get('spec_number') == document_number(record['spec_number'])
        and expected
        and document.get('effective_date') == expected[0]
        and document.get('latest_change') == max(expected)
    )


def reconcile(records):
    groups = defaultdict(list)
    for record in records:
        groups[record['spec_number']].append(record)
    result, conflicts = [], []
    for number, rows in sorted(groups.items()):
        variants = defaultdict(list)
        for row in rows:
            variants[comparable(row['product_name'])].append(row)
        rules, provenance, warnings = [], [], []
        for variants_rows in variants.values():
            for field in ('revision_date', 'recertification'):
                values = {
                    tuple(dates(r[field]))
                    if field == 'revision_date' and dates(r[field])
                    else comparable(r[field])
                    for r in variants_rows
                }
                if len(values) > 1:
                    conflicts.append(
                        {
                            'spec_number': number,
                            'field': field,
                            'values': sorted({r[field] for r in variants_rows}),
                        }
                    )
                    warnings.append(f'Conflicting {field}; review source values')
            rules.append(
                {
                    'product': variants_rows[0]['product_name'],
                    'period': variants_rows[0]['recertification']
                    if len({comparable(r['recertification']) for r in variants_rows})
                    == 1
                    else 'Conflicting source values — review required',
                    'source_values': sorted(
                        {r['recertification'] for r in variants_rows}
                    ),
                }
            )
        # Different descriptions may be legitimate rating variants; keep all.
        revisions = {tuple(dates(r['revision_date'])) for r in rows}
        if len(revisions) > 1:
            conflicts.append(
                {
                    'spec_number': number,
                    'field': 'revision_date',
                    'values': sorted({r['revision_date'] for r in rows}),
                }
            )
            warnings.append('Conflicting revision dates; current PDF unavailable')
        names_by_source = defaultdict(set)
        for r in rows:
            names_by_source[r['source']].add(comparable(r['product_name']))
        if len({tuple(sorted(v)) for v in names_by_source.values()}) > 1:
            conflicts.append(
                {
                    'spec_number': number,
                    'field': 'product_name',
                    'values': sorted({r['product_name'] for r in rows}),
                }
            )
            warnings.append('Product variants disagree between supplied lists')
        source_sets = {r['source'] for r in rows}
        if len(source_sets) < 2:
            warnings.append('Metadata appears in only one supplied list')
        provenance = [
            {
                'source': r['source'],
                'source_sha256': r.get('source_sha256'),
                'location': r['location'],
                'product_name': r['product_name'],
                'revision_date': r['revision_date'],
                'recertification': r['recertification'],
                'identifier_detail': r.get('identifier_detail', ''),
            }
            for r in rows
        ]
        result.append(
            {
                'spec_number': number,
                'product_name': rows[0]['product_name'],
                'description': '; '.join(
                    dict.fromkeys(
                        clean(r['product_name'] + ' ' + r.get('identifier_detail', ''))
                        for r in rows
                    )
                ),
                'aliases': sorted({r['product_name'] for r in rows}),
                'revision_date': rows[0]['revision_date']
                if len(revisions) == 1
                else '',
                'recertification_rules': rules,
                'provenance': provenance,
                'warnings': warnings,
                'import_status': 'conflict'
                if any(c['spec_number'] == number for c in conflicts)
                else 'parsed',
            }
        )
    return result, conflicts


def build_import(source_dir, legacy_data=None):
    root = Path(source_dir).resolve()
    if not root.is_dir():
        raise ValueError('Source directory does not exist')
    records, documents, warnings, errors = [], [], [], []
    files = []
    # Stop traversal early rather than materializing an unbounded directory tree.
    for path in root.rglob('*'):
        files.append(path)
        if len(files) > MAX_MEMBERS:
            raise ValueError('Source directory exceeds member limit')
    files.sort()
    if (
        len(files) > MAX_MEMBERS
        or sum(f.stat().st_size for f in files if f.is_file()) > MAX_TOTAL
    ):
        raise ValueError('Source directory exceeds resource limits')
    expanded_total = 0
    for path in files:
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('Symlinks are not supported in private source directories')
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        suffix = path.suffix.lower()
        # Archive is bounded separately by expanded size.
        if suffix not in ('.zip', '.pdf', '.docx'):
            continue
        try:
            if suffix == '.zip':
                with zipfile.ZipFile(path) as archive:
                    members = safe_members(archive)
                    expanded_total += sum(m.file_size for m in members)
                    if expanded_total > MAX_TOTAL:
                        raise ValueError('Combined archives exceed expanded-size limit')
                    for member in members:
                        if (
                            member.filename.lower().endswith('.pdf')
                            and not member.is_dir()
                        ):
                            documents.append(
                                inspect_pdf(
                                    archive.read(member),
                                    relative + '::' + member.filename,
                                )
                            )
            else:
                if path.stat().st_size > MAX_FILE:
                    raise ValueError('Source file exceeds resource limit')
                data = path.read_bytes()
                if suffix == '.docx':
                    records.extend(parse_docx(data, relative))
                else:
                    parsed = parse_list_pdf(data, relative)
                    if parsed:
                        records.extend(parsed)
                    else:
                        documents.append(inspect_pdf(data, relative))
        except Exception as exc:  # noqa: BLE001 -- report failures without approving documents
            errors.append({'source': relative, 'error': str(exc)})
    expected = {'SpecList3.pdf', 'SpecList.docx', 'Specs.zip'}
    missing = sorted(expected - {p.name for p in files if p.is_file()})
    warnings.extend('Missing expected source: ' + p for p in missing)
    entries, conflicts = reconcile(records)
    legacy = defaultdict(list)
    for item in legacy_data or []:
        for number in item.get('spec_numbers', []):
            legacy[normalize_number(number)].append(item)
    matched = set()
    for entry in entries:
        number = entry['spec_number']
        old = legacy[number]
        entry['categories'] = sorted({i['category'] for i in old if i.get('category')})
        entry['aliases'] = sorted(
            set(entry['aliases']) | {i['product_name'] for i in old}
        )
        entry['keywords'] = sorted(
            {k for i in old for k in i.get('keywords', []) if isinstance(k, str)}
        )
        candidates = [
            d
            for d in documents
            if d['spec_number'] == document_number(number)
            and d['status'] == 'identified'
        ]
        entry['local_documents'] = candidates
        matched.update(d['source'] for d in candidates)
        current = [d for d in candidates if current_document(d, entry)]
        entry['local_document_status'] = (
            'local_current_unpublished'
            if current
            else 'outdated'
            if candidates
            else 'missing'
        )
        entry['document'] = {
            'status': 'needs_review' if candidates and not current else 'not_checked'
        }
        if not candidates:
            entry['warnings'].append('No matching local PDF; no public URL inferred')
        elif not current:
            entry['warnings'].append('Local PDF revision differs from current list')
        if entry['import_status'] == 'conflict':
            entry['document'] = {'status': 'needs_review'}
        if not entry['categories']:
            entry['warnings'].append(
                'No verified catalog category; category review required'
            )
        if len({d['sha256'] for d in candidates}) > 1:
            entry['warnings'].append('Multiple local PDF versions retained')
    counts = {
        'parsed': len(records),
        'canonical': len(entries),
        'matched': sum(bool(e['local_documents']) for e in entries),
        'unmatched': sum(not e['local_documents'] for e in entries),
        'duplicate': len(records) - len(entries),
        'conflicting': len({c['spec_number'] for c in conflicts}),
        'documents': len(documents),
        'unmatched_documents': sum(d['source'] not in matched for d in documents),
    }
    return {
        'counts': counts,
        'entries': entries,
        'conflicts': conflicts,
        'warnings': warnings,
        'errors': errors,
        'unmatched_documents': [d for d in documents if d['source'] not in matched],
        'missing_sources': missing,
    }


def apply_import(session, report):
    """One commit, rollback on failure; deterministic JSON avoids no-op UPDATEs."""
    from model.sfi_spec import SfiCatalogEntry, SfiSpec

    if report['errors'] or not report['entries']:
        raise ValueError('Import has parser errors or no records; no changes applied')
    counts = {'inserted': 0, 'updated': 0, 'unchanged': 0}
    try:
        existing_rows = defaultdict(list)
        for row in session.query(SfiSpec).order_by(SfiSpec.id).all():
            existing_rows[normalize_number(row.spec_number)].append(row)
        for incoming in report['entries']:
            entry = dict(incoming)
            number = entry['spec_number']
            rows = existing_rows[number]
            if not rows:
                session.add(
                    SfiSpec(
                        spec_number=number,
                        product_name=entry['product_name'],
                        category=(entry['categories'] or ['Needs category review'])[0],
                    )
                )
            old = session.get(SfiCatalogEntry, number)
            if old:
                previous = json.loads(old.payload)
                verified = previous.get('document', {})
                if (
                    verified.get('status')
                    in (
                        'verified_current',
                        'rejected',
                        'temporarily_unavailable',
                        'needs_review',
                    )
                    and incoming['import_status'] != 'conflict'
                    and (
                        incoming.get('document', {}).get('status') == 'not_checked'
                        or (
                            incoming.get('document') == {'status': 'needs_review'}
                            and incoming.get('local_document_status') == 'outdated'
                        )
                    )
                    and not incoming.get('document', {}).get('checked_at')
                    and dates(previous.get('revision_date', ''))
                    and dates(previous.get('revision_date', ''))
                    == dates(incoming.get('revision_date', ''))
                ):
                    entry['document'] = verified

                # Preserve unknown extensions and existing aliases/categories/keywords.
                entry = {**previous, **entry}
                for field in ('categories', 'aliases', 'keywords'):
                    entry[field] = sorted(
                        set(previous.get(field, [])) | set(entry.get(field, []))
                    )
                for field in previous.get('manual_edits', []):
                    if field in (
                        'product_name',
                        'description',
                        'revision_date',
                        'recertification_rules',
                    ):
                        entry[field] = previous.get(field, entry.get(field))
                if incoming['import_status'] == 'conflict':
                    # Keep reviewed values until source conflict is resolved, invalidate link.
                    for field in (
                        'product_name',
                        'description',
                        'revision_date',
                        'recertification_rules',
                    ):
                        entry[field] = previous.get(field, incoming[field])
            if (
                old
                and entry['document'].get('status') == 'verified_current'
                and (
                    entry['revision_date'] != incoming['revision_date']
                    or set(previous.get('manual_edits', []))
                    & {'spec_number', 'spec_pdf', 'effective_date'}
                )
            ):
                entry['document'] = {
                    'status': 'needs_review',
                    'reason': 'manual_document_fields_require_review',
                }
            history = retain_document_history(
                previous if old else {}, entry['document']
            )
            for evidence in incoming.get('document_history', []):
                if evidence not in history:
                    history.append(evidence)
            entry['document_history'] = history
            payload = json.dumps(entry, sort_keys=True, ensure_ascii=False)
            if old is None:
                session.add(SfiCatalogEntry(spec_number=number, payload=payload))
                counts['inserted'] += 1
            elif old.payload != payload:
                old.payload = payload
                counts['updated'] += 1
            else:
                counts['unchanged'] += 1
        session.commit()
    except Exception:
        session.rollback()
        raise
    return counts

"""Validated canonical management. Never delete legacy rows or related evidence."""

import json
from datetime import UTC, datetime

from __init__ import db
from catalog import normalize_number, normalized, retain_document_history, valid_number
from model.sfi_spec import SfiCatalogEntry, SfiSpec

LIMITS = {
    'product_name': 255,
    'category': 100,
    'subcategory': 100,
    'spec_number': 20,
    'effective_date': 50,
    'revision_date': 100,
    'spec_pdf': 255,
    'manufacturer_pdf': 255,
    'products_pdf': 255,
}
REQUIRED = {'product_name', 'category', 'spec_number'}


def validate_input(value, creating=False):
    if not isinstance(value, dict) or not value:
        return None, 'A nonempty JSON object is required'
    if set(value) - LIMITS.keys():
        return None, 'Unsupported fields'
    if creating and REQUIRED - value.keys():
        return None, 'Product name, category, and specification number are required'
    data = {}
    for key, raw in value.items():
        if not isinstance(raw, str):
            return None, f'{key} must be a string'
        if len(raw) > LIMITS[key]:
            return None, f'{key} exceeds {LIMITS[key]} characters'
        text = ' '.join(raw.split())
        if any(ord(c) < 32 for c in raw if c not in '\t\r\n'):
            return None, f'{key} contains unsupported control characters'
        if key in REQUIRED and not text:
            return None, f'{key} cannot be blank'
        if key == 'spec_number':
            text = normalize_number(text)
            if not valid_number(text):
                return (
                    None,
                    'Invalid specification number (examples: 16.1, 3.2A, 20.1/1)',
                )
        data[key] = text
    return data, None


def related(number):
    return [
        s
        for s in SfiSpec.query.order_by(SfiSpec.id).all()
        if normalize_number(s.spec_number) == number
    ]


def overlay_for(number):
    # PK reservation serializes new identities; row locks serialize existing
    # canonical edits on MySQL. No uniqueness constraint touches legacy rows.
    return db.session.execute(
        db.select(SfiCatalogEntry)
        .where(SfiCatalogEntry.spec_number == number)
        .with_for_update()
    ).scalar_one_or_none()


def write_payload(overlay, payload):
    overlay.payload = json.dumps(payload, sort_keys=True, ensure_ascii=False)


def create_spec(data):
    number = data['spec_number']
    if related(number) or db.session.get(SfiCatalogEntry, number):
        return {
            'error': 'Specification already exists; edit or restore its canonical entry'
        }, 409
    payload = {'document': {'status': 'not_checked'}}
    if 'revision_date' in data:
        payload.update(
            revision_date=data['revision_date'], manual_edits=['revision_date']
        )
    overlay = SfiCatalogEntry(spec_number=number, payload=json.dumps(payload))
    db.session.add(overlay)
    # Flush the unique canonical key before inserting the legacy row. A racing
    # creator loses here and the route rolls back the entire transaction.
    db.session.flush()
    spec = SfiSpec(**{k: v for k, v in data.items() if k != 'revision_date'})
    db.session.add(spec)
    db.session.commit()
    return spec.to_dict(), 201


def update_spec(id, data):
    spec = db.session.get(SfiSpec, id)
    if not spec:
        return {'error': 'Spec not found'}, 404
    number = normalize_number(spec.spec_number)
    overlay = overlay_for(number)
    payload = json.loads(overlay.payload) if overlay else {}
    if payload.get('archived'):
        return {'error': 'Restore this canonical entry before editing'}, 409
    if overlay is None:
        overlay = SfiCatalogEntry(spec_number=number, payload='{}')
        db.session.add(overlay)
        db.session.flush()
    rows = related(number)
    original_categories = {r.category for r in rows if r.category}
    target = data.get('spec_number', number)
    if target != number:
        if related(target) or db.session.get(SfiCatalogEntry, target):
            return {'error': 'Target specification already exists'}, 409
        # Keep an archived tombstone for the old identity. An import must not
        # silently resurrect an administrator's renamed canonical entry.
        replacement = SfiCatalogEntry(spec_number=target, payload='{}')
        db.session.add(replacement)
        db.session.flush()
        write_payload(overlay, {**payload, 'archived': True, 'renamed_to': target})
        overlay = replacement
        for row in rows:
            row.spec_number = target

    changed = set()
    for field, value in data.items():
        old = (
            payload.get('revision_date', '')
            if field == 'revision_date'
            else payload.get('product_name', spec.product_name)
            if field == 'product_name'
            else getattr(spec, field)
        )
        # Numbers and display metadata are case/whitespace normalized. PDF paths
        # remain case sensitive; path case can identify a different document.
        equal = (
            normalize_number(old) == value
            if field == 'spec_number'
            else str(old or '').strip() == value
            if field.endswith('_pdf')
            else normalized(old) == normalized(value)
        )
        if not equal:
            changed.add(field)
    if target != number:
        changed.add('spec_number')
    if changed & {'spec_number', 'revision_date', 'effective_date', 'spec_pdf'}:
        document = {
            'status': 'needs_review',
            'reason': 'administrative_document_change',
        }
        payload['document_history'] = retain_document_history(payload, document)
        payload['document'] = document
    for field in changed - {'spec_number', 'revision_date'}:
        for row in rows:
            setattr(row, field, data[field])
    if 'revision_date' in changed:
        payload['revision_date'] = data['revision_date']
    if 'product_name' in changed:
        payload['product_name'] = data['product_name']
        payload['aliases'] = sorted(
            set(payload.get('aliases', [])) | {data['product_name']}
        )
    if 'category' in changed:
        payload['categories'] = sorted(
            set(payload.get('categories', []))
            | original_categories
            | {data['category']}
        )
    if changed:
        payload['manual_edits'] = sorted(set(payload.get('manual_edits', [])) | changed)
    write_payload(overlay, payload)
    db.session.commit()
    return spec.to_dict(), 200


def archive_spec(id, data, archived):
    spec = db.session.get(SfiSpec, id)
    if not spec:
        return {'error': 'Spec not found'}, 404
    number = normalize_number(spec.spec_number)
    if not isinstance(data, dict) or data.get('confirm_canonical_id') != number:
        return {
            'error': 'Confirm the exact canonical identity; all associated legacy rows are retained',
            'canonical_id': number,
            'legacy_row_count': len(related(number)),
        }, 409
    overlay = overlay_for(number)
    payload = json.loads(overlay.payload) if overlay else {}
    if not overlay:
        overlay = SfiCatalogEntry(spec_number=number, payload='{}')
        db.session.add(overlay)
    if bool(payload.get('archived')) != archived:
        payload.update(
            archived=archived, archive_changed_at=datetime.now(UTC).isoformat()
        )
        # Restoring visibility is not fresh PDF verification.
        document = {'status': 'needs_review', 'reason': 'canonical_archive_changed'}
        payload['document_history'] = retain_document_history(payload, document)
        payload['document'] = document
    write_payload(overlay, payload)
    db.session.commit()
    return {
        'message': 'Canonical specification archived'
        if archived
        else 'Canonical specification restored',
        'canonical_id': number,
        'archived': archived,
        'legacy_rows_retained': len(related(number)),
    }, 200

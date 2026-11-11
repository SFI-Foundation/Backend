"""
SFI Spec Model — stores parsed SFI Foundation specification data.

Each row represents one spec entry (e.g., SFI Spec 1.1 for
"Replacement Flywheels and Clutch Assemblies" under Auto Racing).

Data is loaded from _data/sfi_specs.json which is produced by
scripts/extract_sfi_specs.py in the greppers frontend repo.
"""

import json
import os
import re
from sqlalchemy import or_
from sqlalchemy.orm import synonym
from sfi_config import load_specs
from __init__ import app, db


_SEARCH_STOP_WORDS = {
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'does', 'for', 'from',
    'how', 'i', 'in', 'is', 'it', 'of', 'on', 'or', 'the', 'to', 'what',
    'which', 'with',
}


def _search_terms(query):
    terms = re.findall(r'[a-z0-9]+(?:\.[a-z0-9]+)*', query.lower())
    return list(dict.fromkeys(
        term for term in terms if term not in _SEARCH_STOP_WORDS
    ))[:20]


def _field_match_score(terms, *fields):
    normalized_fields = [str(field or '').lower() for field in fields]
    score = 0
    for term in terms:
        if term in normalized_fields[0]:
            score += 8
        if term in normalized_fields[1]:
            score += 4
        if term in normalized_fields[2]:
            score += 2
        if term in normalized_fields[3]:
            score += 1
    return score


def _text_match_score(terms, text):
    text_terms = re.findall(r'[a-z0-9]+(?:\.[a-z0-9]+)*', (text or '').lower())
    frequencies = {}
    for term in text_terms:
        frequencies[term] = frequencies.get(term, 0) + 1
    return sum(min(frequencies.get(term, 0), 3) for term in terms)


class SfiSpec(db.Model):
    """SQLAlchemy model for the sfi_specs table."""
    __tablename__ = 'sfi_specs'

    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    subcategory = db.Column(db.String(100), default='')
    spec_number = db.Column(db.String(20), nullable=False)
    spec_pdf = db.Column(db.String(255), default='')
    manufacturer_pdf = db.Column(db.String(255), default='')
    products_pdf = db.Column(db.String(255), default='')
    effective_date = db.Column(db.String(50), default='')

    chunks = db.relationship(
        'SfiSpecChunk',
        back_populates='spec',
        cascade='all, delete-orphan',
    )

    def legacy_dict(self):
        """Convert this spec to a JSON-serializable dictionary."""
        return {
            "id": self.id,
            "product_name": self.product_name,
            "category": self.category,
            "subcategory": self.subcategory,
            "spec_number": self.spec_number,
            "spec_pdf": self.spec_pdf,
            "manufacturer_pdf": self.manufacturer_pdf,
            "products_pdf": self.products_pdf,
            "effective_date": self.effective_date,
        }

    def to_dict(self):
        from catalog import canonical_specs
        return next(item for item in canonical_specs(include_archived=True) if self.id in item['legacy_ids'])


class SfiCatalogEntry(db.Model):
    """Additive metadata overlay; legacy rows and foreign keys remain intact."""
    __tablename__ = 'sfi_catalog_entries'
    spec_number = db.Column(db.String(20), primary_key=True)
    payload = db.Column(db.Text, nullable=False)


class SfiSpecChunk(db.Model):
    """A page-scoped text chunk extracted from an SFI spec PDF."""
    __tablename__ = 'sfi_spec_chunks'

    id = db.Column(db.Integer, primary_key=True)
    spec_id = db.Column(db.Integer, db.ForeignKey('sfi_specs.id'), nullable=False, index=True)
    page = db.Column(db.Integer, nullable=False)
    chunk_index = db.Column(db.Integer, nullable=False)
    text = db.Column(db.Text, nullable=False)
    content = synonym('text')
    spec = db.relationship('SfiSpec', back_populates='chunks')


def search_sfi_specs(query, limit=None):
    """Compatibility adapter for existing chatbot callers expecting ORM rows."""
    from catalog import find_specs
    results = find_specs(query)
    if limit is not None:
        results = results[:limit]
    return [db.session.get(SfiSpec, item['id']) for item in results]


def search_sfi_spec_chunks(query, spec_ids, limit=5):
    """Return the most relevant stored PDF chunks for a question."""
    terms = _search_terms(query)
    if not terms:
        return []

    filters = [
        SfiSpecChunk.content.ilike(f'%{term}%')
        for term in terms
    ]
    if spec_ids:
        filters.append(SfiSpecChunk.spec_id.in_(spec_ids))

    candidates = (
        db.session.query(SfiSpecChunk, SfiSpec)
        .join(SfiSpec, SfiSpec.id == SfiSpecChunk.spec_id)
        .filter(or_(*filters))
        .all()
    )
    spec_id_set = set(spec_ids)
    ranked = sorted(
        candidates,
        key=lambda row: (
            -(
                _text_match_score(terms, row[0].content)
                + (1 if row[0].spec_id in spec_id_set else 0)
            ),
            row[1].spec_number,
            row[0].page,
            row[0].chunk_index,
        ),
    )
    return [chunk for chunk, _spec in ranked[:limit]]


def initSfiSpecs():
    """Explicit legacy seed: insert missing full numbers without deleting rows.

    Rich metadata imports use scripts/import_sfi_catalog.py instead.
    """
    data = load_specs()  # validate before opening a write transaction
    from catalog import normalize_number
    try:
        existing = {normalize_number(s.spec_number) for s in SfiSpec.query.all()}
        for entry in data:
            for i, number in enumerate(entry.get('spec_numbers', [])):
                key = normalize_number(number)
                if key in existing:
                    continue
                def at(field):
                    values = entry.get(field, [])
                    return values[i] if i < len(values) else ''
                db.session.add(SfiSpec(
                    product_name=entry['product_name'], category=entry['category'],
                    subcategory=entry.get('subcategory', ''), spec_number=key,
                    spec_pdf=at('spec_pdfs'), manufacturer_pdf=at('manufacturer_pdfs'),
                    products_pdf=at('products_pdfs'), effective_date=entry.get('effective_date', ''),
                ))
                existing.add(key)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

"""Canonical public catalog and deterministic search. No import side effects."""

import json
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

NUMBER = r'[0-9]{1,3}\.[0-9]{1,3}[A-Z]?(?:/[1-9][0-9]{0,2})?'
# These age/rating identities explicitly share the base specification document.
SHARED_DOCUMENTS = {'20.1/1': '20.1', '20.1/2': '20.1'}


def valid_number(value):
    return isinstance(value, str) and re.fullmatch(NUMBER, value) is not None


def document_number(number):
    return SHARED_DOCUMENTS.get(number, number)


def retain_document_history(previous, incoming):
    """Retain evidence privately, without making historical links actionable."""
    history = list(previous.get('document_history', []))
    old = previous.get('document')
    if old and old != incoming and old not in history:
        history.append(old)
    return history


def normalize_number(value):
    value = re.sub(
        r'^SFI\s*(?:SPEC(?:IFICATION)?\s*)?', '', str(value).strip(), flags=re.I
    )
    return re.sub(r'\s+', '', value).upper()


def normalized(value):
    return ' '.join(str(value or '').casefold().split())


def official_url(value):
    try:
        p = urlparse(value or '')
        return (
            p.scheme == 'https'
            and p.hostname in {'sfifoundation.com', 'www.sfifoundation.com'}
            and not p.username
            and not p.password
            and p.port in (None, 443)
            and p.path.startswith('/wp-content/')
            and p.path.lower().endswith('.pdf')
        )
    except ValueError:
        return False


@lru_cache(maxsize=1)
def verified_terms():
    return json.loads(Path(__file__).with_name('sfi_search_terms.json').read_text())


def canonical_specs(include_archived=False):
    from model.sfi_spec import SfiSpec, SfiCatalogEntry

    overlays = {
        x.spec_number: json.loads(x.payload) for x in SfiCatalogEntry.query.all()
    }
    groups = {}
    for row in SfiSpec.query.order_by(SfiSpec.id).all():
        key = normalize_number(row.spec_number)
        groups.setdefault(key, []).append(row)
    result = []
    for key, rows in groups.items():
        item = rows[0].legacy_dict()
        metadata = overlays.get(key, {})
        if metadata.get('archived') and not include_archived:
            continue
        item['archived'] = bool(metadata.get('archived'))
        item.update(spec_number=key, canonical_id=key, legacy_ids=[r.id for r in rows])
        item['categories'] = sorted(
            set(metadata.get('categories', []))
            | {r.category for r in rows if r.category}
        )
        item['aliases'] = sorted(
            {r.product_name for r in rows} | set(metadata.get('aliases', []))
        )
        item['legacy_revisions'] = sorted(
            {r.effective_date for r in rows if r.effective_date}
        )
        for field in (
            'product_name',
            'description',
            'revision_date',
            'recertification_rules',
            'keywords',
            'import_status',
        ):
            item[field] = metadata.get(
                field,
                item.get(
                    field, [] if field in ('keywords', 'recertification_rules') else ''
                ),
            )
        item['keywords'] = sorted(
            set(item['keywords']) | set(verified_terms().get(key, {}).get('terms', []))
        )
        doc = metadata.get('document') or {}
        verified = doc.get('status') == 'verified_current' and official_url(
            doc.get('url')
        )
        item['view_spec_url'] = doc['url'] if verified else None
        item['document_status'] = doc.get('status', 'not_checked')
        item['local_document_available'] = bool(metadata.get('local_documents'))
        item['warnings'] = metadata.get('warnings', [])
        result.append(item)
    return sorted(result, key=lambda x: (x['spec_number'], x['id']))


def find_specs(query='', category='', items=None):
    """Catalog is small; fixed ORM reads, no interpolated SQL.

    Rank exact number, number prefix, product/alias phrase, description/keyword,
    then category. Require every whitespace-delimited query term to match.
    """
    q = normalized(query)
    number = normalize_number(q)
    terms = q.split()
    ranked = []
    for item in canonical_specs() if items is None else items:
        if (
            category
            and normalized(category) != 'all'
            and normalized(category) not in map(normalized, item['categories'])
        ):
            continue
        names = normalized(' '.join([item['product_name'], *item['aliases']]))
        detail = normalized(
            ' '.join([item.get('description', ''), *item.get('keywords', [])])
        )
        cats = normalized(' '.join(item['categories']))
        haystack = ' '.join(
            [
                normalized(item['spec_number']),
                names,
                detail,
                cats,
                normalized(item.get('subcategory')),
            ]
        )
        exact = bool(q) and number == item['spec_number']
        if q and not exact and not all(term in haystack for term in terms):
            continue
        score = 10000 if exact else 0
        if q:
            score += 1000 * normalized(item['spec_number']).startswith(q)
            score += 500 * (q in names) + 100 * (q in detail) + 10 * (q in cats)
            score += sum(
                20 * (t in names) + 5 * (t in detail) + (t in cats) for t in terms
            )
        ranked.append((score, item))
    return [
        item
        for _, item in sorted(
            ranked, key=lambda pair: (-pair[0], pair[1]['spec_number'], pair[1]['id'])
        )
    ]

"""Searchable text extracted from the public SFI Foundation website."""

import re
from sqlalchemy import or_
from __init__ import db


_STOP_WORDS = {
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'but', 'by', 'does', 'do',
    'for', 'from', 'how', 'i', 'in', 'is', 'it', 'of', 'on', 'or', 'the',
    'to', 'what', 'which', 'who', 'with',
}


def _terms(query):
    return list(dict.fromkeys(
        word for word in re.findall(r'[a-z0-9]+(?:\.[a-z0-9]+)*', query.lower())
        if word not in _STOP_WORDS
    ))[:20]


class SfiSitePage(db.Model):
    """A searchable text snapshot of one official SFI Foundation page."""
    __tablename__ = 'sfi_site_pages'

    id = db.Column(db.Integer, primary_key=True)
    path = db.Column(db.String(255), nullable=False, unique=True, index=True)
    url = db.Column(db.String(500), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)


def search_sfi_site_pages(query, limit=3):
    """Return site pages ranked by title, path, and body keyword relevance."""
    terms = _terms(query)
    if not terms:
        return []

    matches = SfiSitePage.query.filter(or_(*(
        SfiSitePage.title.ilike(f'%{term}%') |
        SfiSitePage.path.ilike(f'%{term}%') |
        SfiSitePage.content.ilike(f'%{term}%')
        for term in terms
    ))).all()

    def score(page):
        title = (page.title or '').lower()
        path = (page.path or '').lower()
        words = re.findall(r'[a-z0-9]+(?:\.[a-z0-9]+)*', (page.content or '').lower())
        frequencies = {}
        for word in words:
            frequencies[word] = frequencies.get(word, 0) + 1
        return sum(
            (5 if term in title else 0)
            + (2 if term in path else 0)
            + min(frequencies.get(term, 0), 3)
            for term in terms
        )

    ranked = sorted(matches, key=lambda page: (-score(page), page.path))
    return ranked[:limit]

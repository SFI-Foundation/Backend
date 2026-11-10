#!/usr/bin/env python3
"""Fetch and index selected public SFI Foundation pages for chatbot retrieval.

Run from the repository root with:
    python scripts/index_sfi_site.py
"""

import os
import re
import sys
import time
from html.parser import HTMLParser
from urllib.parse import urlparse

import requests

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from __init__ import app, db
from model.sfi_site_page import SfiSitePage


BASE_URL = 'https://sfifoundation.com'
SITE_PATHS = (
    '/',
    '/about-sfi-foundation/',
    '/specs-program/',
    '/specifications-participating-manufacturers/',
    '/incident-response-training/',
    '/tech-inspector-certification/',
    '/contact/',
)
REQUEST_TIMEOUT = 20
MAX_PAGE_TEXT = 20000


class _PageTextParser(HTMLParser):
    _SKIP_TAGS = {'aside', 'footer', 'form', 'header', 'nav', 'script', 'style', 'svg'}
    _VOID_TAGS = {
        'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link',
        'meta', 'param', 'source', 'track', 'wbr',
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_parts = []
        self.text_parts = []
        self._in_title = False
        self._skip_stack = []

    def handle_starttag(self, tag, _attrs):
        tag = tag.lower()
        if tag == 'title':
            self._in_title = True
        if self._skip_stack:
            if tag not in self._VOID_TAGS:
                self._skip_stack.append(tag)
        elif tag in self._SKIP_TAGS:
            self._skip_stack.append(tag)

        if not self._skip_stack and tag in {
            'br', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'p',
            'section',
        }:
            self.text_parts.append(' ')

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == 'title':
            self._in_title = False
        if self._skip_stack:
            if tag in self._skip_stack:
                index = len(self._skip_stack) - 1 - self._skip_stack[::-1].index(tag)
                del self._skip_stack[index:]
            return
        if tag in {
            'br', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'p',
            'section',
        }:
            self.text_parts.append(' ')

    def handle_data(self, data):
        if self._in_title:
            self.title_parts.append(data)
        elif not self._skip_stack:
            self.text_parts.append(data)


def extract_page(html, path):
    parser = _PageTextParser()
    parser.feed(html)
    title = ' '.join(' '.join(parser.title_parts).split())
    content = re.sub(r'\s+', ' ', ' '.join(parser.text_parts)).strip()
    if not content:
        raise ValueError('page contained no visible text')
    if not title:
        title = path.strip('/').replace('-', ' ').title() or 'SFI Foundation'
    return title[:255], content[:MAX_PAGE_TEXT]


def index_site_pages():
    successes = 0
    failures = 0
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'SFI-Backend site indexer (contact: info@sfifoundation.com)'
    })

    with app.app_context():
        db.create_all()
        for path in SITE_PATHS:
            url = BASE_URL + path
            try:
                response = session.get(url, timeout=REQUEST_TIMEOUT)
                response.raise_for_status()
                title, content = extract_page(response.text, path)
                canonical_path = urlparse(response.url).path or '/'
                page = SfiSitePage.query.filter_by(path=canonical_path).first()
                if page is None:
                    page = SfiSitePage(path=canonical_path, url=response.url)
                    db.session.add(page)
                page.url = response.url
                page.title = title
                page.content = content
                db.session.commit()
                successes += 1
                print(f'Indexed {response.url} ({len(content)} characters)')
            except (requests.RequestException, ValueError) as exc:
                db.session.rollback()
                failures += 1
                app.logger.warning('Could not index SFI page %s: %s', url, exc)
            time.sleep(0.5)

    print(f'SFI site indexing complete: {successes} succeeded, {failures} failed.')
    return successes, failures


if __name__ == '__main__':
    index_site_pages()

"""Validate links discovered on official SFI pages; never upload local sources."""

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests
from catalog import official_url
from catalog_import import MAX_FILE, inspect_pdf, current_document

ROOT = 'https://sfifoundation.com/specifications-participating-manufacturers/'
HOSTS = {'sfifoundation.com', 'www.sfifoundation.com'}


class Anchors(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.labels = {}
        self.current = None
        self.label = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.current = next((v for k, v in attrs if k == 'href'), None)
            self.label = []
            if self.current:
                self.links.append(self.current)

    def handle_data(self, data):
        if self.current:
            self.label.append(data)

    def handle_endtag(self, tag):
        if tag == 'a' and self.current:
            self.labels[self.current] = ' '.join(''.join(self.label).split()).casefold()
            self.current = None


def fetch(url, max_size=MAX_FILE):
    """Bound redirects and bytes; validate every redirect before following."""
    for _ in range(5):
        p = urlparse(url)
        if (
            p.scheme != 'https'
            or p.hostname not in HOSTS
            or p.username
            or p.password
            or p.port not in (None, 443)
        ):
            raise ValueError('Non-official URL rejected')
        with requests.get(
            url,
            timeout=(5, 20),
            stream=True,
            allow_redirects=False,
            headers={'User-Agent': 'SFI-Phase1-link-audit/1.0'},
        ) as response:
            if response.is_redirect:
                url = urljoin(url, response.headers['Location'])
                continue
            response.raise_for_status()
            data = bytearray()
            for block in response.iter_content(65536):
                data.extend(block)
                if len(data) > max_size:
                    raise ValueError('Response exceeds size limit')
            return url, bytes(data)
    raise ValueError('Too many redirects')


def discover():
    url, data = fetch(ROOT, 4 * 1024 * 1024)
    parser = Anchors()
    parser.feed(data.decode('utf-8', errors='replace'))
    pages = {url}
    for href in parser.links:
        target = urljoin(url, href)
        p = urlparse(target)
        if (
            p.hostname in HOSTS
            and p.scheme == 'https'
            and any(
                word in parser.labels.get(href, '')
                for word in (
                    'auto racing',
                    'drag racing',
                    'boat racing',
                    'fuel related',
                    'tractor',
                    'protective gear',
                )
            )
            and not p.path.lower().endswith('.pdf')
        ):
            pages.add(target.split('#')[0])
    pdfs, failures = {}, []
    for page in sorted(pages)[:12]:
        try:
            final, content = fetch(page, 4 * 1024 * 1024)
            parser = Anchors()
            parser.feed(content.decode('utf-8', errors='replace'))
            for href in parser.links:
                target = urljoin(final, href)
                if official_url(target) and re.search(
                    r'/specs/', urlparse(target).path, re.I
                ):
                    pdfs[target] = page
        except Exception as exc:
            failures.append({'page': page, 'error': type(exc).__name__})
    return pdfs, failures


def validate_links(entries):
    try:
        links, failures = discover()
    except Exception as exc:
        return {
            'checked': 0,
            'verified_current': 0,
            'results': [],
            'discovery_failures': [{'page': ROOT, 'error': type(exc).__name__}],
        }
    by_number = {e['spec_number']: e for e in entries}

    def check(pair):
        url, page = pair
        result = {'url': url, 'discovered_on': page}
        try:
            final, data = fetch(url)
            doc = inspect_pdf(data, urlparse(final).path)
            number = doc['spec_number']
            result.update(
                spec_number=number,
                sha256=doc['sha256'],
                effective_date=doc['effective_date'],
                latest_change=doc['latest_change'],
            )
            entry = by_number.get(number)
            if (
                entry
                and entry['import_status'] != 'conflict'
                and current_document(doc, entry)
            ):
                result.update(status='verified_current', url=final)
            else:
                result['status'] = 'revision_or_number_mismatch'
        except Exception as exc:
            result.update(status='unavailable', error=type(exc).__name__)
        return result

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(check, sorted(links.items())))
    for number, entry in by_number.items():
        matches = [
            r
            for r in results
            if r.get('spec_number') == number and r['status'] == 'verified_current'
        ]
        if matches:
            # Prefer the bare official hostname, then deterministic lexical order.
            selected = sorted(
                matches,
                key=lambda r: (
                    urlparse(r['url']).hostname != 'sfifoundation.com',
                    r['url'],
                ),
            )[0]
            entry['document'] = selected
    return {
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'discovery_failures': failures,
        'checked': len(results),
        'verified_current': sum(r['status'] == 'verified_current' for r in results),
        'results': results,
    }

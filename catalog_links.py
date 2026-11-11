"""Validate links discovered on official SFI pages; never upload local sources."""

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests
from catalog import official_url, document_number, retain_document_history
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
    """Every explicit check replaces approval, including failed rediscovery.

    Discovery/transport failures are temporary. Wrong bytes, identity, revision,
    or a definitive 404/410 reject the candidate. Unreadable evidence needs review.
    An old verified URL is checked even when it disappears from the index.
    """
    checked_at = datetime.now(timezone.utc).isoformat()
    try:
        links, failures = discover()
    except Exception as exc:
        links, failures = {}, [{'page': ROOT, 'error': type(exc).__name__}]
    for entry in entries:
        old_url = entry.get('document', {}).get('url')
        if official_url(old_url):
            links.setdefault(old_url, 'previous verification')

    def check(pair):
        url, page = pair
        result = {
            'url': url,
            'requested_url': url,
            'discovered_on': page,
            'checked_at': checked_at,
        }
        # Filename associates a failed download or wrong-content result with its
        # intended identity. It never establishes successful verification.
        match = re.search(
            r'/Spec_([0-9]+\.[0-9]+[A-Z]?)(?=[_.-]|$)', urlparse(url).path, re.I
        )
        result['target_number'] = match.group(1).upper() if match else None
        try:
            final, data = fetch(url)
            doc = inspect_pdf(data, urlparse(final).path)
            result.update(
                spec_number=doc['spec_number'],
                sha256=doc['sha256'],
                effective_date=doc['effective_date'],
                latest_change=doc['latest_change'],
                document_identity_status=doc['status'],
                url=final,
            )
            result['status'] = 'inspected'
        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else None
            result.update(
                status='rejected' if code in (404, 410) else 'temporarily_unavailable',
                error=type(exc).__name__,
                http_status=code,
            )
        except requests.RequestException as exc:
            result.update(status='temporarily_unavailable', error=type(exc).__name__)
        except ValueError as exc:
            result.update(status='rejected', error=type(exc).__name__)
        except Exception as exc:
            result.update(status='needs_review', error=type(exc).__name__)
        return result

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(check, sorted(links.items())))
    outcomes = []
    for entry in entries:
        number = document_number(entry['spec_number'])
        previous_url = entry.get('document', {}).get('url')
        candidates = [
            r
            for r in results
            if r.get('target_number') == number
            or (not r.get('target_number') and r.get('spec_number') == number)
            or r['url'] == previous_url
            or r.get('requested_url') == previous_url
        ]
        assessed = []
        for result in candidates:
            doc = dict(result)
            if doc['status'] == 'inspected':
                evidence = {**doc, 'status': doc['document_identity_status']}
                doc['status'] = (
                    'verified_current'
                    if entry.get('import_status') != 'conflict'
                    and current_document(evidence, entry)
                    else 'rejected'
                )
            assessed.append(doc)
        # A known rejected candidate cannot revive via matching date strings in
        # apply_import. Only a fresh successful content check grants approval.
        priority = {
            'verified_current': 0,
            'rejected': 1,
            'needs_review': 2,
            'temporarily_unavailable': 3,
        }
        assessed.sort(
            key=lambda r: (
                priority[r['status']],
                urlparse(r['url']).hostname != 'sfifoundation.com',
                r['url'],
            )
        )
        selected = (
            assessed[0]
            if assessed
            else {
                'status': 'temporarily_unavailable' if failures else 'needs_review',
                'checked_at': checked_at,
                'reason': 'discovery_failed' if failures else 'no_official_candidate',
            }
        )
        entry['document_history'] = retain_document_history(entry, selected)
        entry['document'] = selected
        outcomes.append({'canonical_id': entry['spec_number'], **selected})
    # Classify every inspected public URL, including those absent from the lists.
    for result in results:
        related = [r for r in outcomes if r.get('url') == result['url']]
        result['status'] = (
            'verified_current'
            if any(r['status'] == 'verified_current' for r in related)
            else 'rejected'
            if result['status'] == 'inspected'
            else result['status']
        )
    return {
        'checked_at': checked_at,
        'discovery_failures': failures,
        'checked': len(results),
        'verified_current': sum(r['status'] == 'verified_current' for r in results),
        'results': results,
        'entries': outcomes,
    }

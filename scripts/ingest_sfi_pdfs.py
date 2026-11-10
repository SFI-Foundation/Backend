#!/usr/bin/env python3
"""Download, extract, and chunk the official SFI spec PDFs.

Run from the repository root with ``python scripts/ingest_sfi_pdfs.py``.
Set ``SFI_PDF_BASE_URL`` to override the base used for relative PDF paths.
"""

import hashlib
import json
import logging
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pdfplumber
import requests

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from __init__ import app, db  # noqa: E402
from model.sfi_spec import SfiSpec, SfiSpecChunk  # noqa: E402


LOGGER = logging.getLogger('sfi_pdf_ingest')
SOURCE_JSON = REPOSITORY_ROOT / 'sfi_specs.json'
DEFAULT_BASE_URL = 'https://sfifoundation.com/wp-content/pdfs/'
CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
DOWNLOAD_DELAY_SECONDS = 0.25


def collect_pdf_paths(spec_data):
    """Return the unique non-empty PDF paths declared in the source JSON."""
    return list(dict.fromkeys(
        pdf_path.strip()
        for entry in spec_data
        for pdf_path in entry.get('spec_pdfs', [])
        if isinstance(pdf_path, str) and pdf_path.strip()
    ))


def resolve_pdf_url(pdf_path, base_url):
    """Resolve a JSON PDF path against the configurable official PDF base."""
    url = urljoin(base_url.rstrip('/') + '/', pdf_path)
    if urlparse(url).scheme not in ('http', 'https'):
        raise ValueError(f'Unsupported PDF URL scheme: {url}')
    return url


def chunk_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Split normalized page text into bounded, overlapping chunks."""
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError('Chunk overlap must be non-negative and smaller than chunk size')

    text = re.sub(r'\s+', ' ', text).strip()
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            boundary = text.rfind(' ', start + chunk_size // 2, end)
            if boundary > start:
                end = boundary

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(text):
            break
        start = max(start + 1, end - overlap)

    return chunks


def cache_path_for(cache_dir, url):
    """Choose a stable, collision-resistant cache filename for a URL."""
    filename = Path(urlparse(url).path).name or 'spec.pdf'
    digest = hashlib.sha256(url.encode('utf-8')).hexdigest()[:16]
    return cache_dir / f'{digest}-{filename}'


def is_pdf(path):
    try:
        with path.open('rb') as pdf_file:
            return pdf_file.read(5) == b'%PDF-'
    except OSError:
        return False


def download_pdf(session, url, cache_dir):
    """Return a valid cached PDF or download it atomically into the cache."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    destination = cache_path_for(cache_dir, url)
    if is_pdf(destination):
        LOGGER.info('Using cached PDF: %s', destination.name)
        return destination

    temporary_path = None
    try:
        with session.get(url, stream=True, timeout=(5, 30)) as response:
            response.raise_for_status()
            with tempfile.NamedTemporaryFile(
                mode='wb', dir=cache_dir, suffix='.download', delete=False
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                for block in response.iter_content(chunk_size=64 * 1024):
                    if block:
                        temporary_file.write(block)

        if not is_pdf(temporary_path):
            raise ValueError(f'Response did not contain a PDF: {url}')
        os.replace(temporary_path, destination)
        temporary_path = None
        return destination
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def extract_page_chunks(pdf_path):
    """Extract text page-by-page, returning (page number, chunk text) pairs."""
    extracted = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ''
            extracted.extend(
                (page_number, chunk)
                for chunk in chunk_text(page_text)
            )

    if not extracted:
        raise ValueError('PDF contains no extractable text')
    return extracted


def replace_spec_chunks(specs, page_chunks):
    """Replace a spec's chunks after its PDF has been fully extracted."""
    for spec in specs:
        db.session.query(SfiSpecChunk).filter_by(spec_id=spec.id).delete(
            synchronize_session=False
        )
        for chunk_index, (page_number, text) in enumerate(page_chunks):
            db.session.add(SfiSpecChunk(
                spec_id=spec.id,
                page=page_number,
                chunk_index=chunk_index,
                text=text,
            ))
    db.session.commit()


def ingest():
    """Process each unique PDF and return summary counts."""
    try:
        with SOURCE_JSON.open(encoding='utf-8') as source_file:
            spec_data = json.load(source_file)
    except (OSError, json.JSONDecodeError) as error:
        LOGGER.error('Cannot read %s: %s', SOURCE_JSON, error)
        return 0, 1, 0

    pdf_paths = collect_pdf_paths(spec_data)
    base_url = os.environ.get('SFI_PDF_BASE_URL', DEFAULT_BASE_URL)
    cache_dir = Path(app.instance_path) / 'sfi_pdf_cache'
    succeeded = 0
    failed = 0
    specs_updated = 0

    with requests.Session() as session:
        session.headers.update({'User-Agent': 'SFI-spec-PDF-ingester/1.0'})
        for index, pdf_path in enumerate(pdf_paths):
            try:
                specs = SfiSpec.query.filter_by(spec_pdf=pdf_path).all()
                if not specs:
                    raise ValueError(f'No SFI specs in the database reference {pdf_path}')

                url = resolve_pdf_url(pdf_path, base_url)
                cached_pdf = download_pdf(session, url, cache_dir)
                page_chunks = extract_page_chunks(cached_pdf)
                replace_spec_chunks(specs, page_chunks)
                succeeded += 1
                specs_updated += len(specs)
                LOGGER.info(
                    'Ingested %s: %d chunks across %d spec records',
                    pdf_path, len(page_chunks), len(specs)
                )
            except Exception:
                db.session.rollback()
                failed += 1
                LOGGER.exception('Skipping PDF %s', pdf_path)
            if index + 1 < len(pdf_paths):
                time.sleep(DOWNLOAD_DELAY_SECONDS)

    return succeeded, failed, specs_updated


def main():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    with app.app_context():
        db.create_all()
        succeeded, failed, specs_updated = ingest()

    print(
        f'SFI PDF ingestion complete: {succeeded} succeeded, {failed} failed '
        f'({specs_updated} spec records updated).'
    )
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())

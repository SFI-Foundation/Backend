import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from flask import Flask

from scripts import ingest_sfi_pdfs
from __init__ import db
from model.sfi_spec import SfiSpec, SfiSpecChunk


class SfiPdfIngestionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.test_app = Flask('sfi_pdf_ingest_test')
        cls.test_app.config.update(
            SQLALCHEMY_DATABASE_URI=f"sqlite:///{Path(cls.temp_dir.name) / 'test.db'}",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        db.init_app(cls.test_app)
        with cls.test_app.app_context():
            db.create_all()

    @classmethod
    def tearDownClass(cls):
        with cls.test_app.app_context():
            db.session.remove()
            db.drop_all()
        cls.temp_dir.cleanup()

    def test_collect_pdf_paths_deduplicates_source_paths(self):
        paths = ingest_sfi_pdfs.collect_pdf_paths([
            {'spec_pdfs': ['specs/Spec_1.1.pdf', '']},
            {'spec_pdfs': ['specs/Spec_1.1.pdf', 'https://example.test/spec.pdf']},
        ])

        self.assertEqual(
            paths,
            ['specs/Spec_1.1.pdf', 'https://example.test/spec.pdf'],
        )

    def test_resolve_pdf_url_uses_official_base_for_relative_paths(self):
        self.assertEqual(
            ingest_sfi_pdfs.resolve_pdf_url(
                'specs/Spec_1.1.pdf',
                'https://sfifoundation.com/wp-content/pdfs/',
            ),
            'https://sfifoundation.com/wp-content/pdfs/specs/Spec_1.1.pdf',
        )

    def test_chunk_text_respects_size_and_overlaps(self):
        text = ' '.join(f'word{i}' for i in range(300))
        chunks = ingest_sfi_pdfs.chunk_text(text, chunk_size=200, overlap=30)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 200 for chunk in chunks))
        self.assertTrue(any(set(left.split()) & set(right.split()) for left, right in zip(chunks, chunks[1:])))

    def test_download_pdf_reuses_cached_content(self):
        session = MagicMock()
        response = MagicMock()
        response.__enter__.return_value = response
        response.iter_content.return_value = [b'%PDF-1.4 test']
        session.get.return_value = response
        cache_dir = Path(self.temp_dir.name) / 'pdf-cache'

        first = ingest_sfi_pdfs.download_pdf(
            session, 'https://example.test/spec.pdf', cache_dir
        )
        second = ingest_sfi_pdfs.download_pdf(
            session, 'https://example.test/spec.pdf', cache_dir
        )

        self.assertEqual(first, second)
        self.assertEqual(session.get.call_count, 1)
        self.assertEqual(first.read_bytes(), b'%PDF-1.4 test')

    def test_extract_page_chunks_keeps_one_based_page_numbers(self):
        first_page = MagicMock()
        first_page.extract_text.return_value = 'Requirement on page one.'
        second_page = MagicMock()
        second_page.extract_text.return_value = None
        third_page = MagicMock()
        third_page.extract_text.return_value = 'Requirement on page three.'
        pdf = MagicMock(pages=[first_page, second_page, third_page])
        pdf.__enter__.return_value = pdf

        with patch.object(ingest_sfi_pdfs.pdfplumber, 'open', return_value=pdf):
            chunks = ingest_sfi_pdfs.extract_page_chunks(Path('unused.pdf'))

        self.assertEqual(chunks, [
            (1, 'Requirement on page one.'),
            (3, 'Requirement on page three.'),
        ])

    def test_replacing_chunks_is_idempotent_and_queryable_by_spec(self):
        with self.test_app.app_context():
            spec = SfiSpec(
                product_name='Test spec',
                category='Testing',
                spec_number='99.1',
                spec_pdf='specs/Test.pdf',
            )
            db.session.add(spec)
            db.session.commit()

            ingest_sfi_pdfs.replace_spec_chunks(
                [spec], [(1, 'First chunk'), (2, 'Second chunk')]
            )
            ingest_sfi_pdfs.replace_spec_chunks(
                [spec], [(1, 'Updated chunk')]
            )

            chunks = SfiSpecChunk.query.filter_by(spec_id=spec.id).all()
            self.assertEqual(len(chunks), 1)
            self.assertEqual(chunks[0].page, 1)
            self.assertEqual(chunks[0].chunk_index, 0)
            self.assertEqual(chunks[0].text, 'Updated chunk')

            db.session.delete(spec)
            db.session.commit()

    def test_ingest_continues_after_a_pdf_parse_failure(self):
        source_json = Path(self.temp_dir.name) / 'specs.json'
        source_json.write_text(json.dumps([
            {'spec_pdfs': ['specs/Good.pdf', 'specs/Scanned.pdf']},
        ]), encoding='utf-8')

        with self.test_app.app_context():
            good_spec = SfiSpec(
                product_name='Good spec',
                category='Testing',
                spec_number='99.2',
                spec_pdf='specs/Good.pdf',
            )
            scanned_spec = SfiSpec(
                product_name='Scanned spec',
                category='Testing',
                spec_number='99.3',
                spec_pdf='specs/Scanned.pdf',
            )
            db.session.add_all([good_spec, scanned_spec])
            db.session.commit()
            db.session.add(SfiSpecChunk(
                spec_id=scanned_spec.id,
                page=1,
                chunk_index=0,
                text='Existing text stays available',
            ))
            db.session.commit()

            session = MagicMock()
            session.__enter__.return_value = session
            session.headers = {}
            with (
                patch.object(ingest_sfi_pdfs, 'SOURCE_JSON', source_json),
                patch.object(
                    ingest_sfi_pdfs,
                    'download_pdf',
                    side_effect=[Path('good.pdf'), Path('scanned.pdf')],
                ),
                patch.object(
                    ingest_sfi_pdfs,
                    'extract_page_chunks',
                    side_effect=[[(1, 'New extracted text')], ValueError('no text')],
                ),
                patch.object(ingest_sfi_pdfs.requests, 'Session', return_value=session),
                patch.object(ingest_sfi_pdfs.time, 'sleep'),
            ):
                result = ingest_sfi_pdfs.ingest()

            self.assertEqual(result, (1, 1, 1))
            self.assertEqual(
                [chunk.text for chunk in SfiSpecChunk.query.filter_by(
                    spec_id=good_spec.id
                ).all()],
                ['New extracted text'],
            )
            self.assertEqual(
                [chunk.text for chunk in SfiSpecChunk.query.filter_by(
                    spec_id=scanned_spec.id
                ).all()],
                ['Existing text stays available'],
            )
            db.session.delete(good_spec)
            db.session.delete(scanned_spec)
            db.session.commit()

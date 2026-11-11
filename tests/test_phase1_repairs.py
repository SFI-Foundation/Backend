"""Regression tests for the independent acceptance findings; synthetic data only."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import jwt
import requests
import test_phase1_catalog as fixture
from sqlalchemy import create_engine

from __init__ import db
from catalog import normalize_number, valid_number
from catalog_import import apply_import, build_import, parse_docx, table_record
from catalog_links import validate_links
from model.sfi_spec import SfiCatalogEntry, SfiSpec, SfiSpecChunk

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://sfifoundation.com/wp-content/pdfs/specs/Spec_16.1.pdf'


def docx_bytes(rows):
    from xml.sax.saxutils import escape

    xml = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:tbl>'
    for row in rows:
        xml += (
            '<w:tr>'
            + ''.join(
                '<w:tc><w:p><w:r><w:t>' + escape(cell) + '</w:t></w:r></w:p></w:tc>'
                for cell in row
            )
            + '</w:tr>'
        )
    xml += '</w:tbl></w:body></w:document>'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('word/document.xml', xml)
    return buffer.getvalue()


class IdentifierRepairTests(unittest.TestCase):
    def test_full_qualified_identifiers_preserve_age_rating_detail_and_shared_pdf(self):
        rows = [
            [number, 'Synthetic Cage', 'March 1, 2026', period]
            for number, period in [
                ('20.1/1 (Age 5-7)', '2 Years'),
                ('20.1/2 (Age 8-12)', '5 Years'),
            ]
        ]
        parsed = parse_docx(docx_bytes(rows), 'Synthetic.docx')
        self.assertEqual([r['spec_number'] for r in parsed], ['20.1/1', '20.1/2'])
        self.assertIn('Age 5-7', parsed[0]['identifier_detail'])
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'Synthetic.docx').write_bytes(docx_bytes(rows))
            Path(directory, 'Spec_20.1.pdf').write_bytes(
                fixture.pdf_bytes(['SFI SPECIFICATION 20.1 EFFECTIVE: MARCH 1, 2026'])
            )
            report = build_import(directory)
            self.assertEqual(report['counts']['canonical'], 2)
            self.assertEqual(report['counts']['matched'], 2)
            self.assertEqual(report['counts']['unmatched_documents'], 0)
            first, second = report['entries']
            self.assertNotEqual(
                first['recertification_rules'], second['recertification_rules']
            )
            self.assertEqual(first['local_documents'], second['local_documents'])
            self.assertNotEqual(first['document']['status'], 'verified_current')
        self.assertEqual(normalize_number(' SFI Spec 20.1 / 2 '), '20.1/2')
        self.assertTrue(valid_number('20.1/2'))
        self.assertEqual(
            table_record(['SFI 20.1 / 2', 'Synthetic', '', ''], 'x', 'row 1')[
                'spec_number'
            ],
            '20.1/2',
        )

    def test_pdf_qualified_rows_are_not_silently_skipped(self):
        # Exercise the actual PDF table parser boundary using a synthetic table.
        from unittest.mock import MagicMock

        pdf = MagicMock()
        pdf.__enter__.return_value = pdf
        page = MagicMock()
        pdf.pages = [page]
        page.extract_tables.return_value = [
            [
                ['20.1/1', 'Synthetic young rating', 'March 1, 2026', '2 Years'],
                ['20.1/2', 'Synthetic older rating', 'March 1, 2026', '5 Years'],
            ]
        ]
        with patch('catalog_import.pdfplumber.open', return_value=pdf):
            records = fixture.parse_list_pdf(b'%PDF-synthetic', 'Synthetic.pdf')
        self.assertEqual([r['spec_number'] for r in records], ['20.1/1', '20.1/2'])
        self.assertIn('table 1, row 2', records[1]['location'])

    def test_malformed_specification_rows_fail_with_source_reference(self):
        for row in [
            ['20.1/0', 'x', '', ''],
            ['20.1/ABC', 'x', '', ''],
            ['16.1?', 'x', '', ''],
            ['20.1/1', 'x'],
            ['SFI ???', 'x', '', ''],
        ]:
            with (
                self.subTest(row=row),
                self.assertRaisesRegex(ValueError, 'Synthetic.docx row 7'),
            ):
                table_record(row, 'Synthetic.docx', 'row 7')
        self.assertIsNone(
            table_record(['Spec', 'Product', 'Revision', 'Period'], 'x', 'row 1')
        )
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'Synthetic.docx').write_bytes(
                docx_bytes([['20.1/ABC', 'x', '', '']])
            )
            report = build_import(directory)
            self.assertTrue(report['errors'])
            self.assertIn('row 1', report['errors'][0]['error'])

    def test_combined_archives_enforce_total_expanded_size(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ('a.zip', 'b.zip'):
                with zipfile.ZipFile(
                    Path(directory, name), 'w', compression=zipfile.ZIP_DEFLATED
                ) as archive:
                    archive.writestr('file.txt', b'a' * 700)
            with patch('catalog_import.MAX_TOTAL', 1000):
                report = build_import(directory)
            self.assertTrue(
                any('Combined archives' in e['error'] for e in report['errors'])
            )


class AdminRepairTests(unittest.TestCase):
    setUp = fixture.CatalogTests.setUp
    tearDown = fixture.CatalogTests.tearDown
    seed = fixture.CatalogTests.seed

    def login_admin(self):
        from model.user import User

        user = User(name='Synthetic QA Admin', uid='repair-admin', role='Admin')
        db.session.add(user)
        db.session.commit()
        self.client.set_cookie(
            'token',
            jwt.encode(
                {'_uid': user.uid}, self.app.config['SECRET_KEY'], algorithm='HS256'
            ),
        )

    def verified(self):
        self.seed()
        report = fixture.report_fixture()
        report['entries'][0]['document'] = {
            'status': 'verified_current',
            'url': URL,
            'checked_at': 'synthetic-prior',
        }
        apply_import(db.session, report)
        return report

    def test_normalized_noop_and_product_only_saves_keep_approval(self):
        self.verified()
        self.login_admin()
        before = db.session.get(SfiCatalogEntry, '16.1').payload
        data = {
            k: v
            for k, v in self.client.get('/api/sfi/specs/1').json.items()
            if k
            in ('spec_number', 'product_name', 'category', 'effective_date', 'spec_pdf')
        }
        data['spec_number'] = 'SFI 16.1'
        data['product_name'] = '  Demo   Restraints '
        for _ in range(2):
            response = self.client.put('/api/sfi/specs/1', json=data)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['view_spec_url'], URL)
        self.assertEqual(db.session.get(SfiCatalogEntry, '16.1').payload, before)
        response = self.client.put(
            '/api/sfi/specs/1', json={'product_name': 'Synthetic renamed product'}
        )
        self.assertEqual(response.json['view_spec_url'], URL)
        self.assertEqual(response.json['product_name'], 'Synthetic renamed product')

    def test_actual_document_changes_and_identity_rename_invalidate(self):
        self.verified()
        self.login_admin()
        for field, value in [
            ('revision_date', 'April 1, 2026'),
            ('effective_date', 'New revision'),
            ('spec_pdf', 'new.pdf'),
            ('spec_number', '16.9/1'),
        ]:
            with self.subTest(field=field):
                response = self.client.put('/api/sfi/specs/1', json={field: value})
                self.assertEqual(response.status_code, 200)
                self.assertIsNone(response.json['view_spec_url'])
                self.assertEqual(response.json['document_status'], 'needs_review')
                repeated = self.client.put('/api/sfi/specs/1', json={field: value})
                self.assertEqual(repeated.json['document_status'], 'needs_review')
        self.assertEqual(
            len([r for r in SfiSpec.query.all() if r.spec_number == '16.9/1']), 2
        )
        self.assertEqual(
            json.loads(db.session.get(SfiCatalogEntry, '16.1').payload)['renamed_to'],
            '16.9/1',
        )

    def test_single_and_multiple_row_archive_requires_confirmation_and_preserves_relations(
        self,
    ):
        self.verified()
        self.login_admin()
        db.session.add(
            SfiSpecChunk(spec_id=1, page=1, chunk_index=0, text='Synthetic history')
        )
        db.session.commit()
        count = SfiSpec.query.count()
        for id, number, rows in [(1, '16.1', 2), (3, '3.2A', 1)]:
            self.assertEqual(
                self.client.delete(f'/api/sfi/specs/{id}').status_code, 409
            )
            response = self.client.delete(
                f'/api/sfi/specs/{id}', json={'confirm_canonical_id': number}
            )
            self.assertEqual(response.json['legacy_rows_retained'], rows)
            self.assertNotIn(
                number,
                [s['canonical_id'] for s in self.client.get('/api/sfi/specs').json],
            )
            self.assertEqual(self.client.get(f'/api/sfi/specs/{id}').status_code, 410)
            self.assertEqual(
                self.client.get(f'/api/sfi/specs/{id}').headers['Cache-Control'],
                'no-store',
            )
            self.assertIn(
                number,
                [
                    s['canonical_id']
                    for s in self.client.get('/api/sfi/specs/archived').json
                ],
            )
        apply_import(db.session, fixture.report_fixture())
        self.assertEqual(self.client.get('/api/sfi/specs/2').status_code, 410)
        self.assertEqual(SfiSpec.query.count(), count)
        self.assertEqual(SfiSpecChunk.query.count(), 1)
        response = self.client.post(
            '/api/sfi/specs/2/restore', json={'confirm_canonical_id': '16.1'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.client.get('/api/sfi/specs/1').json['view_spec_url'])

    def test_invalid_admin_payloads_are_4xx_before_database_binding(self):
        self.seed()
        self.login_admin()
        valid = {'spec_number': '98.1', 'product_name': 'Synthetic', 'category': 'QA'}
        invalid = [[], ['x'], None, 'x', 42, {}, {'spec_number': '98.1'}]
        for key in valid:
            for bad in [None, [], {}, 4, True, ' ', 'x' * 300]:
                invalid.append({**valid, key: bad})
        for bad in [
            'SFI',
            'SFI SPEC',
            '/',
            '16',
            '16.1/0',
            '16.1/ABC',
            'nope',
            '16.1<script>',
        ]:
            invalid.append({**valid, 'spec_number': bad})
        invalid += [
            {**valid, 'unknown': 'x'},
            {**valid, 'spec_pdf': []},
            {**valid, 'revision_date': False},
        ]
        for payload in invalid:
            for method, path in [
                ('post', '/api/sfi/specs'),
                ('put', '/api/sfi/specs/1'),
            ]:
                if method == 'put' and payload == {'spec_number': '98.1'}:
                    continue  # Partial updates are supported; creates require all fields.
                with self.subTest(payload=payload, method=method):
                    response = getattr(self.client, method)(
                        path, data=json.dumps(payload), content_type='application/json'
                    )
                    self.assertEqual(response.status_code, 400, response.json)
        self.assertEqual(
            self.client.post(
                '/api/sfi/specs', json={**valid, 'spec_number': 'SFI 16.1'}
            ).status_code,
            409,
        )
        self.assertEqual(SfiSpec.query.count(), 6)

    def test_negative_revalidation_transitions_and_repeat_imports_public_api(self):
        report = self.verified()

        def check(data=None, failure=None, links=True):
            with (
                patch(
                    'catalog_links.discover',
                    return_value=({URL: 'official'} if links else {}, []),
                ),
                patch(
                    'catalog_links.fetch', side_effect=failure, return_value=(URL, data)
                ),
            ):
                validate_links(report['entries'])
            apply_import(db.session, report)
            return self.client.get('/api/sfi/specs/1').json

        wrong = fixture.pdf_bytes(['SFI SPECIFICATION 16.1 EFFECTIVE: MARCH 2, 2026'])
        self.assertEqual(check(wrong)['document_status'], 'rejected')
        self.assertIsNone(self.client.get('/api/sfi/specs/1').json['view_spec_url'])
        unchecked = fixture.report_fixture()
        unchecked['entries'][0]['document'] = {'status': 'not_checked'}
        apply_import(db.session, unchecked)
        apply_import(db.session, unchecked)
        self.assertEqual(
            self.client.get('/api/sfi/specs/1').json['document_status'], 'rejected'
        )
        self.assertEqual(
            check(failure=requests.Timeout())['document_status'],
            'temporarily_unavailable',
        )
        good = fixture.pdf_bytes(['SFI SPECIFICATION 16.1 EFFECTIVE: MARCH 1, 2026'])
        self.assertEqual(check(good)['view_spec_url'], URL)
        self.assertEqual(
            check(
                fixture.pdf_bytes(['SFI SPECIFICATION 99.1 EFFECTIVE: MARCH 1, 2026'])
            )['document_status'],
            'rejected',
        )
        self.assertGreater(
            len(
                json.loads(db.session.get(SfiCatalogEntry, '16.1').payload)[
                    'document_history'
                ]
            ),
            1,
        )

    def test_discovery_failure_invalidates_old_approval_and_404_is_rejected(self):
        report = self.verified()
        with (
            patch('catalog_links.discover', side_effect=requests.Timeout()),
            patch('catalog_links.fetch', side_effect=requests.Timeout()),
        ):
            result = validate_links(report['entries'])
        self.assertTrue(result['discovery_failures'])
        self.assertEqual(
            report['entries'][0]['document']['status'], 'temporarily_unavailable'
        )
        response = requests.Response()
        response.status_code = 404
        with (
            patch('catalog_links.discover', return_value=({URL: 'official'}, [])),
            patch(
                'catalog_links.fetch', side_effect=requests.HTTPError(response=response)
            ),
        ):
            validate_links(report['entries'])
        self.assertEqual(report['entries'][0]['document']['status'], 'rejected')

    def test_explicit_rejection_without_timestamp_cannot_reuse_old_approval(self):
        report = self.verified()
        report['entries'][0]['document'] = {'status': 'rejected'}
        apply_import(db.session, report)
        apply_import(db.session, report)
        item = self.client.get('/api/sfi/specs/1').json
        self.assertEqual(item['document_status'], 'rejected')
        self.assertIsNone(item['view_spec_url'])


class CliRepairTests(unittest.TestCase):
    def run_cli(self, script, args, wrapper=None):
        command = [sys.executable, str(ROOT / 'scripts' / script), *args]
        if wrapper:
            command = [sys.executable, '-c', wrapper, *args]
        return subprocess.run(
            command,
            cwd=ROOT,
            env={**os.environ, 'PYTHON_DOTENV_DISABLED': '1'},
            capture_output=True,
            check=False,
            text=True,
            timeout=40,
        )

    def test_import_cli_actual_success_blocked_and_apply_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory, 'sources')
            source.mkdir()
            doc = source / 'Synthetic.docx'
            doc.write_bytes(
                docx_bytes([['20.1/1', 'Synthetic Cage', 'March 1, 2026', '2 Years']])
            )
            args = [
                '--source-dir',
                str(source),
                '--report',
                str(Path(directory, 'report.json')),
            ]
            self.assertEqual(self.run_cli('import_sfi_catalog.py', args).returncode, 0)
            self.assertNotEqual(
                self.run_cli('import_sfi_catalog.py', [*args, '--strict']).returncode, 0
            )
            database = 'sqlite:///' + str(Path(directory, 'qa.db'))
            engine = create_engine(database)
            SfiSpec.__table__.create(engine)
            SfiCatalogEntry.__table__.create(engine)
            for _ in range(2):
                result = self.run_cli(
                    'import_sfi_catalog.py', [*args, '--apply', '--database', database]
                )
                self.assertEqual(result.returncode, 0, result.stderr)
            engine.dispose()
            doc.write_bytes(docx_bytes([['20.1/NO', 'Synthetic Cage', '', '']]))
            self.assertNotEqual(
                self.run_cli('import_sfi_catalog.py', args).returncode, 0
            )

    def test_validator_cli_actual_success_failure_and_mismatch_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory, 'input.json')
            report.write_text(json.dumps(fixture.report_fixture()))
            args = [
                '--import-report',
                str(report),
                '--report',
                str(Path(directory, 'output.json')),
            ]
            database = 'sqlite:///' + str(Path(directory, 'validation.db'))
            engine = create_engine(database)
            SfiSpec.__table__.create(engine)
            SfiCatalogEntry.__table__.create(engine)
            from sqlalchemy.orm import Session

            with Session(engine) as session:
                apply_import(session, fixture.report_fixture())
            args += ['--database', database]
            for mode, expected in [('success', 0), ('timeout', 1), ('mismatch', 1)]:
                # Mock only external I/O; execute the real __main__ and sys.exit.
                wrapper = f"""import sys, runpy
from unittest.mock import patch
sys.path[:0] = [{str(ROOT)!r}, {str(ROOT / 'tests')!r}]
from test_phase1_catalog import pdf_bytes
import requests
url = {URL!r}
data = pdf_bytes(['SFI SPECIFICATION 16.1 EFFECTIVE: MARCH {2 if mode == 'mismatch' else 1}, 2026'])
with patch('catalog_links.discover', return_value=({{url: 'official'}}, [])), patch('catalog_links.fetch', return_value=(url, data), side_effect={'requests.Timeout()' if mode == 'timeout' else 'None'}):
    sys.argv[0] = {str(ROOT / 'scripts/validate_sfi_links.py')!r}
    runpy.run_path(sys.argv[0], run_name='__main__')
"""
                result = self.run_cli('validate_sfi_links.py', args, wrapper)
                self.assertEqual(result.returncode, expected, result.stderr)
                with Session(engine) as session:
                    state = json.loads(session.get(SfiCatalogEntry, '16.1').payload)[
                        'document'
                    ]['status']
                    self.assertEqual(
                        state,
                        {
                            'success': 'verified_current',
                            'timeout': 'temporarily_unavailable',
                            'mismatch': 'rejected',
                        }[mode],
                    )
            engine.dispose()


if __name__ == '__main__':
    unittest.main()

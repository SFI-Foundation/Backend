"""Synthetic Phase 1 tests; private documents are not test fixtures."""

import io
import json
import jwt
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from flask import Flask
from flask_login import LoginManager
from sqlalchemy import create_engine, event, text
from __init__ import db
from model.persona import Persona, UserPersona
from model.user import User
from model.group import SfiGroup
from model.sfi_spec import SfiSpec, SfiSpecChunk, SfiCatalogEntry, initSfiSpecs
from api.sfi_spec import sfi_spec_api
from catalog import canonical_specs, find_specs
from catalog_import import (
    parse_docx,
    parse_list_pdf,
    inspect_pdf,
    safe_members,
    reconcile,
    build_import,
    apply_import,
    current_document,
)
from scripts.migrate_sfi_catalog import upgrade
from catalog_links import fetch as fetch_official


def pdf_bytes(lines, table=False):
    # Small valid generated PDF, only synthetic text. No additional PDF framework.
    operations = []
    if table:
        for x in (20, 100, 330, 480, 590):
            operations.append(f'{x} 600 m {x} 700 l S')
        for y in (600, 650, 700):
            operations.append(f'20 {y} m 590 {y} l S')
        for y, cells in [
            (675, ['Spec', 'Product', 'Current Revision Date', 'Period']),
            (625, ['16.1', 'Demo Restraints', 'March 1, 2026', '2 Years']),
        ]:
            for x, cell in zip((25, 105, 335, 485), cells):
                operations.append(f'BT /F1 9 Tf {x} {y} Td ({cell}) Tj ET')
    else:
        for i, line in enumerate(lines):
            line = line.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
            operations.append(f'BT /F1 10 Tf 30 {750 - i * 20} Td ({line}) Tj ET')
    stream = '\n'.join(operations).encode()
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Length '
        + str(len(stream)).encode()
        + b' >>\nstream\n'
        + stream
        + b'\nendstream',
    ]
    output = b'%PDF-1.4\n'
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output += f'{index} 0 obj\n'.encode() + obj + b'\nendobj\n'
    xref = len(output)
    output += b'xref\n0 6\n0000000000 65535 f \n' + b''.join(
        f'{n:010} 00000 n \n'.encode() for n in offsets[1:]
    )
    return (
        output + f'trailer << /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode()
    )


def source_row(
    number='16.1',
    source='a.pdf',
    period='2 Years',
    revision='March 1, 2026',
    product='Demo Restraints',
):
    return dict(
        spec_number=number,
        product_name=product,
        revision_date=revision,
        recertification=period,
        source=source,
        location='page 1',
    )


def report_fixture(number='16.1'):
    entries, conflicts = reconcile(
        [source_row(number), source_row(number, source='b.docx')]
    )
    entries[0].update(
        categories=['Auto Racing', 'Drag Racing'],
        keywords=['synthetic-harness'],
        local_documents=[],
        document={'status': 'missing'},
    )
    return {'entries': entries, 'conflicts': conflicts, 'errors': []}


class ParserTests(unittest.TestCase):
    def test_pdf_table_metadata_and_revision_are_separate(self):
        rows = parse_list_pdf(pdf_bytes([], table=True), 'Synthetic.pdf')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['spec_number'], '16.1')
        self.assertEqual(rows[0]['revision_date'], 'March 1, 2026')
        self.assertEqual(rows[0]['recertification'], '2 Years')

    def test_docx_preserves_runs_and_spaced_revision_suffix(self):
        xml = """<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:tbl><w:tr>"""
        for value in ['3.2 A', 'Demo Suit', 'March 1, 2026', '5 Years']:
            xml += f'<w:tc><w:p><w:r><w:t>{value[:4]}</w:t></w:r><w:r><w:t>{value[4:]}</w:t></w:r></w:p></w:tc>'
        xml += '</w:tr></w:tbl></w:body></w:document>'
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as archive:
            archive.writestr('word/document.xml', xml)
        row = parse_docx(data.getvalue(), 'Synthetic.docx')[0]
        self.assertEqual(row['spec_number'], '3.2A')
        self.assertEqual(row['revision_date'], 'March 1, 2026')

    def test_duplicate_and_variant_rules_preserved(self):
        rows = [source_row(), source_row(source='b.docx')]
        entries, conflicts = reconcile(rows)
        self.assertEqual(len(entries), 1)
        self.assertFalse(conflicts)
        rows += [
            source_row(product='Demo Restraints High Rating', period='5 Years'),
            source_row(
                source='b.docx', product='Demo Restraints High Rating', period='5 Years'
            ),
        ]
        entries, conflicts = reconcile(rows)
        self.assertEqual(len(entries[0]['recertification_rules']), 2)
        self.assertFalse(conflicts)

    def test_conflicting_sources_are_explicit(self):
        entries, conflicts = reconcile(
            [source_row(), source_row(source='b.docx', period='5 Years')]
        )
        self.assertEqual(entries[0]['import_status'], 'conflict')
        self.assertTrue(conflicts)
        self.assertEqual(
            entries[0]['recertification_rules'][0]['source_values'],
            ['2 Years', '5 Years'],
        )

    def test_wrong_pdf_filename_or_old_revision_is_unavailable(self):
        data = pdf_bytes(
            ['SFI SPECIFICATION 16.1 EFFECTIVE: MARCH 1, 2026', 'Edited: March 2, 2026']
        )
        wrong = inspect_pdf(data, 'Spec_16.2.pdf')
        self.assertEqual(wrong['status'], 'number_mismatch')
        good = inspect_pdf(data, 'Spec_16.1.pdf')
        self.assertFalse(current_document(good, source_row()))
        self.assertTrue(
            current_document(
                good, source_row(revision='March 1, 2026 Edited Mar. 2, 2026')
            )
        )

    def test_explicit_technical_bulletin_header_is_supported(self):
        doc = inspect_pdf(
            pdf_bytes(['SFI TECHNICAL BULLETIN 3.2 EFFECTIVE: FEBRUARY 26, 2014']),
            'TechBulletin_3.2.pdf',
        )
        self.assertEqual(doc['spec_number'], '3.2')
        self.assertEqual(doc['status'], 'identified')

    def test_safe_nested_archive_and_traversal_symlink_bomb_rejection(self):
        for name in ['../../outside.pdf', '/absolute.pdf', 'C:/bad.pdf', 'a\\bad.pdf']:
            data = io.BytesIO()
            with zipfile.ZipFile(data, 'w') as archive:
                archive.writestr(name, 'x')
            with zipfile.ZipFile(data) as archive, self.assertRaises(ValueError):
                safe_members(archive)
        for kind in ['symlink', 'bomb', 'duplicate']:
            data = io.BytesIO()
            with zipfile.ZipFile(
                data, 'w', compression=zipfile.ZIP_DEFLATED
            ) as archive:
                member = zipfile.ZipInfo('nested/spec.pdf')
                if kind == 'symlink':
                    member.external_attr = 0o120777 << 16
                archive.writestr(member, b'x')
                if kind == 'bomb':
                    archive.writestr('bomb', b'0' * 100000)
                if kind == 'duplicate':
                    archive.writestr('nested/spec.pdf', 'x')
            with zipfile.ZipFile(data) as archive, self.assertRaises(ValueError):
                safe_members(archive)
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as archive:
            archive.writestr('nested/spec.pdf', 'x')
        with zipfile.ZipFile(data) as archive:
            self.assertEqual(len(safe_members(archive)), 1)

    def test_missing_sources_and_wrong_pdf_audited(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'Only.pdf').write_bytes(
                pdf_bytes(['SFI SPECIFICATION 16.1 EFFECTIVE: MARCH 1, 2026'])
            )
            report = build_import(directory)
            self.assertEqual(report['counts']['unmatched_documents'], 1)
            self.assertIn('Specs.zip', report['missing_sources'])

    def test_public_fetch_rejects_nonofficial_and_redirect_ssrf(self):
        for url in [
            'http://sfifoundation.com/a.pdf',
            'https://example.com/a.pdf',
            'https://sfifoundation.com.evil.test/a.pdf',
        ]:
            with self.assertRaises(ValueError):
                fetch_official(url)
        from unittest.mock import MagicMock

        response = MagicMock()
        response.__enter__.return_value = response
        response.is_redirect = True
        response.headers = {'Location': 'https://evil.test/a.pdf'}
        with patch('catalog_links.requests.get', return_value=response) as get:
            with self.assertRaises(ValueError):
                fetch_official('https://sfifoundation.com/a.pdf')
            self.assertEqual(get.call_count, 1)


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            SQLALCHEMY_DATABASE_URI='sqlite://',
            SECRET_KEY='synthetic-test-key',
            JWT_TOKEN_NAME='token',
        )
        db.init_app(self.app)
        login = LoginManager(self.app)
        login.user_loader(lambda uid: db.session.get(User, int(uid)))
        self.app.register_blueprint(sfi_spec_api)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def seed(self):
        db.session.add_all(
            [
                SfiSpec(
                    spec_number='16.1',
                    product_name='Driver Restraints',
                    category='Auto Racing',
                    effective_date='Old revision',
                ),
                SfiSpec(
                    spec_number='16.1',
                    product_name='Driver Harness',
                    category='Drag Racing',
                    effective_date='Another revision',
                ),
                SfiSpec(
                    spec_number='3.2a',
                    product_name='Driver Suits',
                    category='Protective Gear',
                ),
                SfiSpec(
                    spec_number='25.5',
                    product_name='Demo Chassis',
                    category='Drag Racing',
                ),
                SfiSpec(
                    spec_number='25.5E',
                    product_name='Demo Chassis',
                    category='Drag Racing',
                ),
                SfiSpec(
                    spec_number='99.1',
                    product_name='Unrelated',
                    category='Driver Restraints',
                ),
            ]
        )
        db.session.commit()

    def test_all_dedup_categories_revisions_and_distinct_suffixes(self):
        self.seed()
        items = self.client.get('/api/sfi/specs').json
        self.assertEqual(len(items), 5)
        item = next(i for i in items if i['spec_number'] == '16.1')
        self.assertEqual(item['categories'], ['Auto Racing', 'Drag Racing'])
        self.assertEqual(len(item['legacy_revisions']), 2)
        self.assertEqual(self.client.get('/api/sfi/stats').json['total_specs'], 5)
        self.assertEqual(
            len(self.client.get('/api/sfi/specs?category=Drag%20Racing').json), 3
        )
        self.assertIn('spec_pdf', item)  # existing array and legacy keys retained
        self.assertIsNone(item['view_spec_url'])

    def test_number_case_whitespace_and_ranking(self):
        self.seed()
        for q, number in [
            ('  3.2A  ', '3.2A'),
            ('16.1', '16.1'),
            ('25.5', '25.5'),
            ('sfi 3.2a', '3.2A'),
        ]:
            self.assertEqual(
                self.client.get('/api/sfi/specs/search', query_string={'q': q}).json[0][
                    'spec_number'
                ],
                number,
            )
        found = self.client.get(
            '/api/sfi/specs/search?q=DRIVER%20%20%20RESTRAINTS'
        ).json
        self.assertEqual(found[0]['spec_number'], '16.1')
        self.assertEqual(found[-1]['spec_number'], '99.1')

    def test_keyword_description_and_alias_search(self):
        self.seed()
        apply_import(db.session, report_fixture())
        for q in ['synthetic-harness', 'Demo Restraints', 'Driver Harness']:
            self.assertEqual(find_specs(q)[0]['spec_number'], '16.1')

    def test_pagination_errors_and_injection_literal(self):
        self.seed()
        for params in [
            {'q': ''},
            {'q': 'x' * 201},
            {'q': 'a', 'page': 0},
            {'q': 'a', 'limit': 201},
            {'q': 'a', 'page': 'NaN'},
        ]:
            self.assertEqual(
                self.client.get(
                    '/api/sfi/specs/search', query_string=params
                ).status_code,
                400,
            )
        page = self.client.get('/api/sfi/specs?format=page&page=2&limit=2').json
        self.assertEqual((len(page['items']), page['total']), (2, 5))
        self.assertEqual(
            self.client.get('/api/sfi/specs?format=page&page=100&limit=2').json[
                'items'
            ],
            [],
        )
        for q in ["' OR 1=1 --", '%', '_']:
            self.assertEqual(
                self.client.get('/api/sfi/specs/search', query_string={'q': q}).json, []
            )
        self.assertEqual(SfiSpec.query.count(), 6)

    def test_repeat_upsert_preserves_users_and_legacy_rows(self):
        self.seed()
        user = User(name='Synthetic Owner', uid='synthetic-owner')
        db.session.add(user)
        db.session.commit()
        report = report_fixture()
        self.assertEqual(apply_import(db.session, report)['inserted'], 1)
        with patch.object(
            db.engine.dialect, 'do_execute', wraps=db.engine.dialect.do_execute
        ) as execute:
            self.assertEqual(apply_import(db.session, report)['unchanged'], 1)
            self.assertFalse(
                any(
                    str(c.args[1])
                    .lstrip()
                    .upper()
                    .startswith(('UPDATE', 'INSERT', 'DELETE'))
                    for c in execute.call_args_list
                )
            )
        self.assertEqual(SfiSpec.query.count(), 6)
        self.assertEqual(User.query.one().uid, 'synthetic-owner')

    def test_failed_import_rolls_back_new_spec_and_overlay(self):
        def fail(*args):
            raise RuntimeError('synthetic database failure')

        event.listen(SfiCatalogEntry, 'before_insert', fail)
        try:
            with self.assertRaises(RuntimeError):
                apply_import(db.session, report_fixture())
        finally:
            event.remove(SfiCatalogEntry, 'before_insert', fail)
        self.assertEqual(SfiSpec.query.count(), 0)
        self.assertEqual(SfiCatalogEntry.query.count(), 0)

    def test_legacy_seed_never_deletes_or_rewrites(self):
        self.seed()
        count = SfiSpec.query.count()
        with patch(
            'model.sfi_spec.load_specs',
            return_value=[
                {
                    'product_name': 'Changed',
                    'category': 'Other',
                    'spec_numbers': ['16.1'],
                }
            ],
        ):
            initSfiSpecs()
            initSfiSpecs()
        self.assertEqual(SfiSpec.query.count(), count)
        self.assertEqual(db.session.get(SfiSpec, 1).product_name, 'Driver Restraints')

    def test_admin_writes_still_require_auth(self):
        self.seed()
        for method, path in [
            ('post', '/api/sfi/specs'),
            ('put', '/api/sfi/specs/1'),
            ('delete', '/api/sfi/specs/1'),
        ]:
            self.assertEqual(
                getattr(self.client, method)(path, json={}).status_code, 401
            )

    def test_verified_synonyms(self):
        self.seed()
        self.assertEqual(find_specs('seat belt')[0]['spec_number'], '16.1')

    def test_regular_user_cannot_write_and_admin_cannot_create_duplicates(self):
        self.seed()
        user = User(name='Synthetic Member', uid='member')
        db.session.add(user)
        db.session.commit()
        token = jwt.encode(
            {'_uid': user.uid}, self.app.config['SECRET_KEY'], algorithm='HS256'
        )
        self.client.set_cookie('token', token)
        self.assertEqual(
            self.client.post(
                '/api/sfi/specs',
                json={'product_name': 'x', 'category': 'x', 'spec_number': '16.1'},
            ).status_code,
            403,
        )
        user.role = 'Admin'
        db.session.commit()
        response = self.client.post(
            '/api/sfi/specs',
            json={'product_name': 'x', 'category': 'x', 'spec_number': ' 16.1 '},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(SfiSpec.query.count(), 6)

    def test_admin_edit_preserves_canonical_metadata_and_invalidates_link(self):
        self.seed()
        report = report_fixture()
        report['entries'][0]['document'] = {
            'status': 'verified_current',
            'url': 'https://sfifoundation.com/wp-content/pdfs/specs/Spec_16.1.pdf',
        }
        apply_import(db.session, report)
        user = User(name='Synthetic Admin', uid='demo-admin', role='Admin')
        db.session.add(user)
        db.session.commit()
        self.client.set_cookie(
            'token',
            jwt.encode(
                {'_uid': user.uid}, self.app.config['SECRET_KEY'], algorithm='HS256'
            ),
        )
        response = self.client.put(
            '/api/sfi/specs/1',
            json={
                'spec_number': '16.1',
                'product_name': 'Manually reviewed name',
                'spec_pdf': 'changed.pdf',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json['view_spec_url'])
        self.assertEqual(response.json['product_name'], 'Manually reviewed name')
        apply_import(db.session, report)
        self.assertEqual(
            find_specs('16.1')[0]['product_name'], 'Manually reviewed name'
        )

    def test_conflict_does_not_replace_reviewed_metadata(self):
        self.seed()
        report = report_fixture()
        apply_import(db.session, report)
        report['entries'][0].update(
            import_status='conflict', revision_date='January 1, 1900'
        )
        apply_import(db.session, report)
        item = find_specs('16.1')[0]
        self.assertEqual(item['revision_date'], 'March 1, 2026')
        self.assertEqual(item['import_status'], 'conflict')

    def test_current_pdf_only_when_official_verified(self):
        self.seed()
        report = report_fixture()
        report['entries'][0]['document'] = {
            'status': 'verified_current',
            'url': 'https://sfifoundation.com/wp-content/pdfs/specs/Spec_16.1.pdf',
        }
        apply_import(db.session, report)
        self.assertTrue(find_specs('16.1')[0]['view_spec_url'])
        report['entries'][0]['document']['url'] = 'https://evil.test/a.pdf'
        apply_import(db.session, report)
        self.assertIsNone(find_specs('16.1')[0]['view_spec_url'])


class MigrationTests(unittest.TestCase):
    def test_additive_repeatable_preserves_every_legacy_table(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = create_engine('sqlite:///' + str(Path(directory, 'test.db')))
            with engine.begin() as connection:
                connection.execute(
                    text('CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)')
                )
                connection.execute(text("INSERT INTO users VALUES (7, 'Synthetic')"))
                connection.execute(
                    text(
                        'CREATE TABLE sfi_specs (id INTEGER PRIMARY KEY, spec_number TEXT)'
                    )
                )
                connection.execute(text("INSERT INTO sfi_specs VALUES (42, '16.1')"))
            upgrade(engine)
            upgrade(engine)
            with engine.connect() as connection:
                self.assertEqual(
                    connection.execute(text('SELECT * FROM users')).all(),
                    [(7, 'Synthetic')],
                )
                self.assertEqual(
                    connection.execute(text('SELECT * FROM sfi_specs')).all(),
                    [(42, '16.1')],
                )
                self.assertEqual(
                    connection.execute(
                        text('SELECT count(*) FROM sfi_catalog_entries')
                    ).scalar(),
                    0,
                )
            engine.dispose()


if __name__ == '__main__':
    unittest.main()

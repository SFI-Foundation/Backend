"""Opt-in tests against a dedicated disposable MySQL schema, never app config."""

import json
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

import test_phase1_catalog as fixture
from flask import Flask
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from __init__ import db
from catalog_admin import archive_spec, create_spec
from catalog_import import apply_import
from model.sfi_spec import SfiCatalogEntry, SfiSpec, SfiSpecChunk
from scripts.migrate_sfi_catalog import upgrade

URI = os.environ.get('SFI_QA_MYSQL_URI', '')


@unittest.skipUnless(URI, 'Set SFI_QA_MYSQL_URI to an isolated disposable MySQL schema')
class DisposableMySQLTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(URI, connect_args={'connect_timeout': 5})
        url = self.engine.url
        if url.host not in ('localhost', '127.0.0.1') or not url.database.startswith(
            'sfi_phase1_qa'
        ):
            raise ValueError('Only an explicitly named localhost QA schema is allowed')
        self.app = Flask('mysql-phase1-qa')
        self.app.config['SQLALCHEMY_DATABASE_URI'] = URI
        db.init_app(self.app)
        with self.engine.begin() as connection:
            SfiSpecChunk.__table__.drop(connection, checkfirst=True)
            SfiSpec.__table__.drop(connection, checkfirst=True)
            SfiCatalogEntry.__table__.drop(connection, checkfirst=True)
            SfiSpec.__table__.create(connection)
            SfiSpecChunk.__table__.create(connection)
        upgrade(self.engine)
        self.context = self.app.app_context()
        self.context.push()

    def tearDown(self):
        db.session.remove()
        self.context.pop()
        self.engine.dispose()

    def test_additive_migration_import_repeat_unicode_and_rollback(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    'CREATE TABLE IF NOT EXISTS qa_sentinel (id INTEGER PRIMARY KEY, label VARCHAR(100))'
                )
            )
            connection.execute(text('DELETE FROM qa_sentinel'))
            connection.execute(
                text("INSERT INTO qa_sentinel VALUES (1, 'Synthetic preserved')")
            )
        upgrade(self.engine)
        upgrade(self.engine)
        report = fixture.report_fixture('20.1/1')
        report['entries'][0]['product_name'] = 'Synthetic café 安全 🏁'
        with Session(self.engine) as session:
            self.assertEqual(apply_import(session, report)['inserted'], 1)
            self.assertEqual(apply_import(session, report)['unchanged'], 1)
            row = session.query(SfiSpec).one()
            self.assertEqual(row.product_name, 'Synthetic café 安全 🏁')
            self.assertEqual(row.spec_number, '20.1/1')
            self.assertEqual(
                session.execute(text('SELECT label FROM qa_sentinel')).scalar(),
                'Synthetic preserved',
            )

            def fail(*args):
                raise RuntimeError('Synthetic rollback')

            event.listen(SfiCatalogEntry, 'before_insert', fail)
            try:
                with self.assertRaises(RuntimeError):
                    apply_import(session, fixture.report_fixture('20.1/2'))
            finally:
                event.remove(SfiCatalogEntry, 'before_insert', fail)
            self.assertEqual(session.query(SfiSpec).count(), 1)
            self.assertEqual(session.query(SfiCatalogEntry).count(), 1)

    def test_canonical_archive_preserves_legacy_duplicates_and_foreign_keys(self):
        db.session.add_all(
            [
                SfiSpec(spec_number='16.1', product_name='Synthetic A', category='QA'),
                SfiSpec(spec_number='16.1', product_name='Synthetic B', category='QA'),
            ]
        )
        db.session.commit()
        first = SfiSpec.query.first()
        db.session.add(
            SfiSpecChunk(
                spec_id=first.id, page=1, chunk_index=0, text='Synthetic history'
            )
        )
        db.session.commit()
        result, status = archive_spec(first.id, {'confirm_canonical_id': '16.1'}, True)
        self.assertEqual(status, 200)
        self.assertEqual(result['legacy_rows_retained'], 2)
        self.assertEqual(SfiSpecChunk.query.count(), 1)
        self.assertTrue(
            json.loads(db.session.get(SfiCatalogEntry, '16.1').payload)['archived']
        )

    def test_concurrent_creators_reserve_one_database_identity(self):
        barrier = Barrier(2)
        import catalog_admin

        original = catalog_admin.related

        def synchronized(number):
            rows = original(number)
            barrier.wait(timeout=10)
            return rows

        def worker():
            with self.app.app_context():
                try:
                    return create_spec(
                        {
                            'spec_number': '98.1/1',
                            'product_name': 'Synthetic race',
                            'category': 'QA',
                        }
                    )[1]
                except IntegrityError:
                    db.session.rollback()
                    return 409
                finally:
                    db.session.remove()

        with (
            patch('catalog_admin.related', side_effect=synchronized),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            statuses = list(pool.map(lambda _: worker(), range(2)))
        self.assertEqual(sorted(statuses), [201, 409])
        self.assertEqual(SfiSpec.query.count(), 1)
        self.assertEqual(SfiCatalogEntry.query.count(), 1)


if __name__ == '__main__':
    unittest.main()

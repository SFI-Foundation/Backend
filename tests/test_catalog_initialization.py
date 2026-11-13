"""Empty selected database must not look like a healthy public catalog."""

import json
import tempfile
import unittest
from pathlib import Path

from flask import Flask

from __init__ import db
from api.sfi_spec import sfi_spec_api
from model.sfi_spec import SfiCatalogEntry, SfiSpec
from tests import test_phase1_catalog as fixture


class CatalogInitializationTests(unittest.TestCase):
    setUp = fixture.CatalogTests.setUp
    tearDown = fixture.CatalogTests.tearDown
    seed = fixture.CatalogTests.seed

    def test_empty_selected_database_is_unavailable_not_zero_catalog(self):
        for path in (
            '/api/sfi/specs',
            '/api/sfi/specs?format=page',
            '/api/sfi/specs/search?q=16.1',
            '/api/sfi/categories',
            '/api/sfi/stats',
        ):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 503, path)
            self.assertEqual(response.json['code'], 'catalog_not_initialized')
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(SfiSpec.query.count(), 0)
        self.assertEqual(SfiCatalogEntry.query.count(), 0)

    def test_populated_database_preserves_array_envelope_stats_and_search(self):
        self.seed()
        response = self.client.get('/api/sfi/specs')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json), 5)
        self.assertEqual(response.headers['X-Total-Count'], '5')
        page = self.client.get('/api/sfi/specs?format=page&limit=2').json
        self.assertEqual(len(page['items']), 2)
        self.assertEqual(page['total'], 5)
        stats = self.client.get('/api/sfi/stats').json
        self.assertEqual(stats['total_specs'], 5)
        self.assertEqual(stats['total_categories'], 4)
        self.assertEqual(stats['total_subcategories'], 0)
        self.assertEqual(stats['by_category']['Drag Racing'], 3)
        for query in ('16.1', 'driver restraints'):
            found = self.client.get('/api/sfi/specs/search', query_string={'q': query})
            self.assertEqual(found.status_code, 200)
            self.assertEqual(found.json[0]['spec_number'], '16.1')
        no_match = self.client.get('/api/sfi/specs/search?q=no-such-product')
        self.assertEqual(no_match.status_code, 200)
        self.assertEqual(no_match.json, [])

    def test_unverified_records_visible_archives_hidden_approval_unchanged(self):
        self.seed()
        states = {'16.1': 'verified_current', '3.2A': 'needs_review',
                  '25.5': 'rejected', '25.5E': 'temporarily_unavailable',
                  '99.1': 'not_checked'}
        for number, status in states.items():
            db.session.add(SfiCatalogEntry(spec_number=number, payload=json.dumps({
                'archived': number == '25.5',
                'document': {'status': status,
                             'url': 'https://sfifoundation.com/wp-content/demo.pdf'},
            })))
        db.session.commit()
        original = {x.spec_number: x.payload for x in SfiCatalogEntry.query.all()}
        response = self.client.get('/api/sfi/specs')
        self.assertEqual(response.status_code, 200)
        items = {x['spec_number']: x for x in response.json}
        self.assertEqual(set(items), set(states) - {'25.5'})
        self.assertTrue(items['16.1']['view_spec_url'])
        for number in set(items) - {'16.1'}:
            self.assertIsNone(items[number]['view_spec_url'])
        self.assertEqual(self.client.get('/api/sfi/stats').json['total_specs'], 4)
        self.assertEqual(original, {x.spec_number: x.payload for x in SfiCatalogEntry.query.all()})
        for entry in SfiCatalogEntry.query.all():
            payload = json.loads(entry.payload)
            payload['archived'] = True
            entry.payload = json.dumps(payload)
        db.session.commit()
        # An intentionally archived catalog is initialized and legitimately empty.
        self.assertEqual(self.client.get('/api/sfi/specs').status_code, 200)
        self.assertEqual(self.client.get('/api/sfi/specs').json, [])
        self.assertEqual(self.client.get('/api/sfi/categories').json, [])
        self.assertEqual(self.client.get('/api/sfi/stats').json['total_specs'], 0)

    def test_reopening_file_database_preserves_catalog_and_revocation(self):
        with tempfile.TemporaryDirectory() as directory:
            uri = 'sqlite:///' + str(Path(directory, 'catalog.db'))
            def app():
                result = Flask('catalog-restart-test')
                result.config['SQLALCHEMY_DATABASE_URI'] = uri
                db.init_app(result)
                result.register_blueprint(sfi_spec_api)
                return result
            first = app()
            with first.app_context():
                db.create_all()
                db.session.add(SfiSpec(spec_number='16.1', product_name='Restraints',
                                       category='Auto Racing', subcategory='Harnesses'))
                payload = json.dumps({'document': {'status': 'rejected'}})
                db.session.add(SfiCatalogEntry(spec_number='16.1', payload=payload))
                db.session.commit()
                before = first.test_client().get('/api/sfi/specs').json
                db.session.remove()
                db.engine.dispose()
            second = app()
            with second.app_context():
                response = second.test_client().get('/api/sfi/specs')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json, before)
                self.assertIsNone(response.json[0]['view_spec_url'])
                self.assertEqual(SfiCatalogEntry.query.one().payload, payload)
                self.assertEqual(second.test_client().get('/api/sfi/stats').json['total_subcategories'], 1)
                db.session.remove()
                db.engine.dispose()


if __name__ == '__main__':
    unittest.main()

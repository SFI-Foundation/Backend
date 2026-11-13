"""Run in a disposable clone with PYTHON_DOTENV_DISABLED=1."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sfi_config import SpecDataError, load_specs, specs_path

class SpecConfigTests(unittest.TestCase):
    def test_default_names_and_cwd(self):
        previous = Path.cwd()
        try:
            for name in ('Frontend', 'SFI-Frontend'):
                with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                    backend = Path(folder) / 'SFI-Backend'
                    (backend / 'scripts').mkdir(parents=True)
                    source = Path(folder) / name / '_data/sfi_specs.json'
                    source.parent.mkdir(parents=True)
                    source.write_text('[{"product_name":"Harness","category":"Safety","spec_numbers":["16.1"]}]')
                    with patch('sfi_config.BACKEND_ROOT', backend), patch.dict(os.environ, {'SFI_SPECS_PATH': ''}):
                        for cwd in (backend, backend / 'scripts', Path('/tmp')):
                            os.chdir(cwd)
                            self.assertEqual(specs_path(), source)
                            self.assertEqual(len(load_specs()), 1)
        finally:
            os.chdir(previous)

    def test_default_precedence_and_explicit_override_never_fall_back(self):
        with tempfile.TemporaryDirectory() as folder:
            backend = Path(folder) / 'Backend'
            for name in ('Frontend', 'SFI-Frontend'):
                source = Path(folder) / name / '_data/sfi_specs.json'
                source.parent.mkdir(parents=True)
                source.write_text('invalid source')
            primary = Path(folder) / 'Frontend/_data/sfi_specs.json'
            with patch('sfi_config.BACKEND_ROOT', backend), patch.dict(os.environ, {'SFI_SPECS_PATH': ''}):
                self.assertEqual(specs_path(), primary)
                with self.assertRaises(SpecDataError):
                    load_specs()
                for value in ('missing.json', str(Path(folder) / 'missing.json')):
                    with patch.dict(os.environ, {'SFI_SPECS_PATH': value}):
                        self.assertEqual(specs_path(), (backend / value).resolve())
                        with self.assertRaises(SpecDataError):
                            load_specs()

    def test_custom_relative_and_absolute(self):
        with tempfile.TemporaryDirectory() as folder:
            backend = Path(folder) / 'Backend'
            source = Path(folder) / 'custom.json'
            source.write_text('[{"product_name":"Harness","category":"Safety","spec_numbers":["16.1"]}]')
            for value in (str(source), '../custom.json'):
                with patch('sfi_config.BACKEND_ROOT', backend), patch.dict(os.environ, {'SFI_SPECS_PATH': value}):
                    self.assertEqual(specs_path(), source)
                    self.assertEqual(len(load_specs()), 1)

    def test_missing_and_invalid(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / 'specs.json'
            with patch.dict(os.environ, {'SFI_SPECS_PATH': str(file)}):
                with self.assertRaisesRegex(SpecDataError, 'Set SFI_SPECS_PATH'):
                    load_specs()
                for content in ('bad json', '{}', '[]', '[null]', '[{}]', '[{"product_name":"x","category":"y","spec_numbers":[1]}]'):
                    file.write_text(content)
                    with self.subTest(content=content), self.assertRaisesRegex(SpecDataError, str(file)):
                        load_specs()

class ClassifierErrorTests(unittest.TestCase):
    def test_actionable_unavailable_source(self):
        from api.sfi_classifier import SfiClassifierAPI
        with patch('model.sfi_classifier.SfiClassifier.get_instance', side_effect=SpecDataError('SFI spec data at /missing: Set SFI_SPECS_PATH')):
            body, status = SfiClassifierAPI._Status().get()
        self.assertEqual(status, 503)
        self.assertIn('SFI_SPECS_PATH', body['error'])

class ConsumerTests(unittest.TestCase):
    def test_invalid_source_does_not_begin_database_delete(self):
        from model.sfi_spec import initSfiSpecs
        with patch('model.sfi_spec.load_specs', side_effect=SpecDataError('invalid fixture')), patch('model.sfi_spec.db.session') as session:
            with self.assertRaises(SpecDataError):
                initSfiSpecs()
            session.query.assert_not_called()

    def test_classifier_fallback_and_cache_fingerprint(self):
        from model.sfi_classifier import SfiClassifier
        import joblib
        data = [{'product_name':'helmet', 'category':'safety', 'spec_numbers':['1.1']}]
        classifier = SfiClassifier()
        with patch.object(classifier, '_load_db_specs', return_value=[]), patch('model.sfi_classifier.load_specs', return_value=data) as loader:
            classifier._load_data()
            loader.assert_called_once_with()
        self.assertEqual(classifier.spec_lookup['1.1']['product_name'], 'helmet')
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / 'model.joblib'
            joblib.dump({'data_digest': classifier._data_digest()}, file)
            classifier.specs_data[0]['product_name'] = 'changed source'
            with self.assertRaisesRegex(ValueError, 'source changed'):
                classifier._load_saved(file)

class CorsTests(unittest.TestCase):
    def test_origins_and_preflight(self):
        from __init__ import app, ALLOWED_ORIGINS
        self.assertIn('https://sfi.opencodingsociety.com', ALLOWED_ORIGINS)
        client = app.test_client()
        for origin in (*ALLOWED_ORIGINS, 'https://evil.example', 'https://sfi.opencodingsociety.com.evil.example', 'http://localhost:4500.evil.example', 'https://sfi-foundation.github.io/Frontend', 'null', 'https://open-coding-society.github.io'):
            for method in ('GET', 'OPTIONS'):
                response = client.open('/api/sfi/specs', method=method, headers={
                    'Origin': origin, 'Access-Control-Request-Method': 'POST',
                    'Access-Control-Request-Headers': 'Content-Type, Authorization, X-Origin'})
                with self.subTest(origin=origin, method=method):
                    if origin in ALLOWED_ORIGINS:
                        self.assertEqual(response.headers['Access-Control-Allow-Origin'], origin)
                        self.assertEqual(response.headers['Access-Control-Allow-Credentials'], 'true')
                        self.assertIn('Origin', response.headers['Vary'])
                        if method == 'OPTIONS':
                            self.assertEqual(response.status_code, 204)
                            self.assertIn('Authorization', response.headers['Access-Control-Allow-Headers'])
                    else:
                        self.assertEqual(response.status_code, 403)
                        self.assertNotIn('Access-Control-Allow-Origin', response.headers)
        self.assertNotEqual(client.get('/').status_code, 403)

if __name__ == '__main__':
    unittest.main()

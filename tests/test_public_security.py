"""Production config and public research boundaries; synthetic values only."""

import os
import secrets
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from flask import Flask
from security_config import settings, ConfigurationError

ROOT = Path(__file__).resolve().parents[1]


def production():
    return dict(
        IS_PRODUCTION='true',
        SECRET_KEY=secrets.token_urlsafe(48),
        ADMIN_PASSWORD=secrets.token_urlsafe(24),
        DEFAULT_PASSWORD=secrets.token_urlsafe(24),
        DB_ENDPOINT='mysql.invalid',
        DB_USERNAME='synthetic',
        DB_PASSWORD=secrets.token_urlsafe(24),
    )


class PublicSecurityTests(unittest.TestCase):
    def test_safe_local_defaults_and_production_cookie_policy(self):
        a, b = settings({}), settings({})
        self.assertFalse(a['SFI_INTERNAL_RESEARCH'])
        self.assertFalse(a['IS_PRODUCTION'])
        self.assertNotEqual(a['SECRET_KEY'], b['SECRET_KEY'])
        self.assertGreaterEqual(len(a['SECRET_KEY']), 32)
        self.assertNotEqual(a['DEFAULT_PASSWORD'], a['ADMIN_PASSWORD'])
        self.assertFalse(a['SESSION_COOKIE_SECURE'])
        prod = settings(production())
        self.assertTrue(prod['SESSION_COOKIE_SECURE'])
        self.assertTrue(prod['SESSION_COOKIE_HTTPONLY'])
        self.assertEqual(prod['SESSION_COOKIE_SAMESITE'], 'None')

    def test_required_production_secrets_fail_with_names_only(self):
        for key in ('SECRET_KEY', 'DEFAULT_PASSWORD', 'ADMIN_PASSWORD'):
            env = production()
            env.pop(key)
            with self.subTest(key=key), self.assertRaisesRegex(ConfigurationError, key):
                settings(env)
        for key in ('SECRET_KEY', 'ADMIN_PASSWORD', 'DEFAULT_PASSWORD'):
            env = production()
            marker = 'replace-with-test-placeholder'
            env[key] = marker
            with self.assertRaises(ConfigurationError) as error:
                settings(env)
            self.assertNotIn(marker, str(error.exception))
        env = production()
        env['SECRET_KEY'] = 'x' * 64
        with self.assertRaises(ConfigurationError):
            settings(env)

    def test_invalid_flags_partial_database_and_sqlite_production_fail(self):
        for env in (
            {'IS_PRODUCTION': 'yes'},
            {'SFI_INTERNAL_RESEARCH': '1'},
            {'DB_ENDPOINT': 'mysql.invalid'},
            {'SFI_DATABASE_URI': 'malformed'},
        ):
            with self.subTest(keys=list(env)), self.assertRaises(ConfigurationError):
                settings(env)
        for updates in (
            {'SFI_INTERNAL_RESEARCH': 'true'},
            {'SFI_DATABASE_URI': 'sqlite:////tmp/qa.db'},
            {'DB_ENDPOINT': '', 'DB_USERNAME': '', 'DB_PASSWORD': ''},
        ):
            env = {**production(), **updates}
            with self.assertRaises(ConfigurationError):
                settings(env)

    def test_actual_startup_fails_before_database_connection(self):
        env = {
            k: v
            for k, v in os.environ.items()
            if not any(
                x in k
                for x in ('SECRET', 'PASSWORD', 'DB_', 'SFI_DATABASE', 'IS_PRODUCTION')
            )
        }
        env.update(PYTHON_DOTENV_DISABLED='1', IS_PRODUCTION='true')
        result = subprocess.run(
            [sys.executable, '-c', 'import __init__'],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('SECRET_KEY is required', result.stderr)
        self.assertNotIn('OperationalError', result.stderr)

    def test_classifier_api_disabled_in_default_and_production_even_when_forced(self):
        from api.sfi_classifier import sfi_classifier_api

        for config in ({}, {'IS_PRODUCTION': True, 'SFI_INTERNAL_RESEARCH': True}):
            app = Flask('research-boundary')
            app.config.update(config)
            app.register_blueprint(sfi_classifier_api)
            client = app.test_client()
            for route, method in [
                ('/api/sfi/classify', 'post'),
                ('/api/sfi/classifier/status', 'get'),
                ('/api/sfi/classifier/retrain', 'post'),
            ]:
                self.assertEqual(getattr(client, method)(route).status_code, 404)

    def test_explicit_local_research_flag_preserves_prototype(self):
        from api.sfi_classifier import sfi_classifier_api

        app = Flask('enabled-research')
        app.config.update(SFI_INTERNAL_RESEARCH=True, IS_PRODUCTION=False)
        app.register_blueprint(sfi_classifier_api)
        with patch('model.sfi_classifier.SfiClassifier.get_instance') as model:
            model.return_value.get_status.return_value = {'trained': False}
            self.assertEqual(
                app.test_client().get('/api/sfi/classifier/status').json,
                {'trained': False},
            )

    def test_manufacturer_endpoints_never_expose_sample_records(self):
        from scripts.phase1_local import create_app

        app = create_app('sqlite://')
        client = app.test_client()
        for route in (
            '/api/sfi/manufacturers',
            '/api/sfi/manufacturer-demo',
            '/sfi-manufacturer-demo/',
        ):
            response = client.get(route)
            self.assertEqual(response.status_code, 404)
            self.assertNotIn(b'DEMO-001', response.data)


if __name__ == '__main__':
    unittest.main()

"""Configuration tests use source copies and generated .env files, never local secrets."""
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from security_config import settings, ConfigurationError


class SettingsConfigurationTests(unittest.TestCase):
    def test_env_loading_from_another_directory_and_environment_precedence(self):
        with tempfile.TemporaryDirectory(prefix='sfi-settings-config-') as directory:
            source = Path(directory)
            for name in ('__init__.py', 'security_config.py'):
                shutil.copyfile(ROOT / name, source / name)
            (source / '.env').write_text(
                'SECRET_KEY=' + secrets.token_urlsafe(48) + '\n'
                'DB_ENDPOINT=127.0.0.1\nDB_PORT=13376\nDB_NAME=sfi_preferences_qa\n'
                'DB_USERNAME=synthetic\nDB_PASSWORD=' + secrets.token_urlsafe(36) + '\n'
                'FLASK_PORT=8605\n')
            code = """import json
from __init__ import app
from sqlalchemy.engine import make_url
url = make_url(app.config['SQLALCHEMY_DATABASE_URI'])
print(json.dumps({'driver': url.drivername, 'host': url.host, 'port': url.port,
                  'database': url.database, 'username': url.username,
                  'password_present': bool(url.password), 'port_override': app.config['FLASK_PORT']}))
"""
            env = {'PATH': os.defpath, 'PYTHONPATH': directory, 'FLASK_PORT': '8606'}
            result = subprocess.run([sys.executable, '-c', code], cwd='/tmp', env=env, capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout), {
                'driver': 'mysql+pymysql', 'host': '127.0.0.1', 'port': 13376,
                'database': 'sfi_preferences_qa', 'username': 'synthetic',
                'password_present': True, 'port_override': 8606})

    def test_invalid_database_configuration_fails_without_exposing_values(self):
        for port in ('0', '65536', 'not-a-port'):
            with self.assertRaisesRegex(ConfigurationError, 'DB_PORT'):
                settings({'DB_PORT': port})
        with self.assertRaisesRegex(ConfigurationError, 'DB_NAME'):
            settings({'DB_NAME': ' '})
        with self.assertRaisesRegex(ConfigurationError, 'configured together'):
            settings({'DB_ENDPOINT': 'synthetic.invalid'})
        with self.assertRaisesRegex(ConfigurationError, 'Production requires MySQL'):
            settings({'IS_PRODUCTION': 'true', 'SECRET_KEY': secrets.token_urlsafe(48),
                      'DEFAULT_PASSWORD': secrets.token_urlsafe(24), 'ADMIN_PASSWORD': secrets.token_urlsafe(24)})


if __name__ == '__main__':
    unittest.main(verbosity=2)

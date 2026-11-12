"""Normal main.py bootstrap, with only disposable SQLite and synthetic sources."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
STARTUP = """
import json, sys
from pathlib import Path
import sfi_config
sfi_config.BACKEND_ROOT = Path(sys.argv[1])
import main
from __init__ import app
client = app.test_client()
print('CATALOG_RESULT=' + json.dumps({
    'stats': client.get('/api/sfi/stats').get_json(),
    'page': client.get('/api/sfi/specs?format=page&page=1&limit=20&category=all').get_json(),
}))
"""


class NormalStartupTests(unittest.TestCase):
    def startup(self, backend, database, override=''):
        env = {key: value for key, value in os.environ.items()
               if not any(word in key for word in ('SECRET', 'PASSWORD', 'DB_', 'SFI_DATABASE', 'IS_PRODUCTION'))}
        env.update(PYTHON_DOTENV_DISABLED='1', IS_PRODUCTION='false',
                   SFI_SPECS_PATH=override, SFI_DATABASE_URI=f'sqlite:///{database}')
        result = subprocess.run([sys.executable, '-c', STARTUP, str(backend)],
                                cwd=ROOT, env=env, text=True, capture_output=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = next(line.removeprefix('CATALOG_RESULT=') for line in result.stdout.splitlines()
                    if line.startswith('CATALOG_RESULT='))
        return json.loads(data), result.stderr

    def test_alias_bootstraps_empty_catalog_and_restart_preserves_rows_archives_and_approvals(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            backend = root / 'SFI-Backend'
            backend.mkdir()
            source = root / 'SFI-Frontend/_data/sfi_specs.json'
            source.parent.mkdir(parents=True)
            source.write_text(json.dumps([{'product_name': 'Synthetic Harness', 'category': 'Safety',
                                          'spec_numbers': ['16.1', '20.1/1']}]))
            database = root / 'catalog.db'
            result, log = self.startup(backend, database)
            self.assertNotIn('Local SFI catalog seed skipped', log)
            self.assertEqual(result['stats']['total_specs'], 2)
            self.assertEqual(result['page']['total'], 2)
            self.assertEqual(len(result['page']['items']), 2)
            with sqlite3.connect(database) as connection:
                # Persist canonical metadata exactly as production operations do;
                # startup must not rewrite or resurrect these records.
                connection.execute("INSERT INTO sfi_catalog_entries (spec_number, payload) VALUES (?, ?)",
                                   ('16.1', json.dumps({'archived': True, 'document': {
                                       'status': 'verified_current',
                                       'url': 'https://sfifoundation.com/wp-content/pdfs/Spec_16.1.pdf'}})))
                before_rows = connection.execute('SELECT * FROM sfi_specs ORDER BY id').fetchall()
                before_meta = connection.execute('SELECT * FROM sfi_catalog_entries ORDER BY spec_number').fetchall()
            source.write_text('invalid: existing catalogs must not attempt to reseed')
            restarted, log = self.startup(backend, database)
            self.assertNotIn('Local SFI catalog seed skipped', log)
            self.assertEqual(restarted['page']['total'], 1)
            self.assertEqual(restarted['page']['items'][0]['spec_number'], '20.1/1')
            with sqlite3.connect(database) as connection:
                self.assertEqual(connection.execute('SELECT * FROM sfi_specs ORDER BY id').fetchall(), before_rows)
                self.assertEqual(connection.execute('SELECT * FROM sfi_catalog_entries ORDER BY spec_number').fetchall(), before_meta)

    def test_missing_explicit_source_logs_warning_and_leaves_empty_catalog(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            result, log = self.startup(root / 'Backend', root / 'empty.db', str(root / 'missing.json'))
            self.assertIn('Local SFI catalog seed skipped', log)
            self.assertIn('SFI_SPECS_PATH', log)
            self.assertEqual(result['page']['total'], 0)
            self.assertEqual(result['stats']['total_specs'], 0)


if __name__ == '__main__':
    unittest.main()

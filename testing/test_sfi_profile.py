"""Run with venv/bin/python testing/test_sfi_profile.py.

Copies source into a disposable directory and re-executes with a clean environment.
Never imports the real application's config or opens its database in the parent.
"""
import os
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def isolated_run():
    source = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='sfi-profile-tests-') as directory:
        target = Path(directory)
        files = subprocess.check_output(
            ['git', 'ls-files', '-co', '--exclude-standard', '-z'], cwd=source
        ).decode().split('\0')
        for name in set(files):
            path = Path(name)
            if not name or path.parts[0] in ('instance', 'venv', '.git'):
                continue
            if path.suffix != '.py' and path.parts[0] not in ('datasets', 'templates'):
                continue
            if path.name.startswith('.env') or path.suffix in ('.db', '.sqlite', '.sqlite3'):
                continue
            if (source / path).is_file():
                destination = target / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / path, destination)
        # Explicit fixture source: isolated snapshots have no sibling Frontend.
        shutil.copyfile(source / 'sfi_specs.json', target / 'sfi_specs.json')
        shutil.copyfile(source / 'sfi_search_terms.json', target / 'sfi_search_terms.json')
        (target / 'instance/volumes').mkdir(parents=True)
        environment = {
            'PATH': os.defpath, 'PYTHON_DOTENV_DISABLED': '1',
            'MPLCONFIGDIR': str(target / 'matplotlib'),
            'SFI_PROFILE_TEST_ROOT': str(target),
            'SFI_SPECS_PATH': str(target / 'sfi_specs.json'),
        }
        if '--demo' in sys.argv:
            port = int(os.environ.get('SFI_DEMO_PORT') or '8865')
            assert 1024 <= port <= 65535
            environment['SFI_DEMO_PORT'] = str(port)
        # Opt-in engine verification accepts only an explicitly disposable localhost schema.
        qa_uri = os.environ.get('SFI_QA_MYSQL_URI')
        if qa_uri:
            from sqlalchemy.engine import make_url
            url = make_url(qa_uri)
            assert url.get_backend_name() == 'mysql' and url.host == '127.0.0.1'
            assert url.database.startswith('sfi_preferences_qa') and url.port == 13376
            environment['SFI_DATABASE_URI'] = qa_uri
            environment['SFI_QA_MYSQL_URI'] = qa_uri
        return subprocess.run(
            [sys.executable, str(target / 'testing/test_sfi_profile.py'), '--isolated']
            + (['--bridge'] if '--bridge' in sys.argv else [])
            + (['--demo'] if '--demo' in sys.argv else []),
            cwd=target, env=environment,
        ).returncode


if __name__ == '__main__' and '--isolated' not in sys.argv:
    raise SystemExit(isolated_run())

if __name__ != '__main__' and 'SFI_PROFILE_TEST_ROOT' not in os.environ:
    import unittest
    raise unittest.SkipTest('Run testing/test_sfi_profile.py directly for isolated tests.')

# Guard against accidentally invoking child-mode tests in the real checkout.
root = Path(os.environ['SFI_PROFILE_TEST_ROOT']).resolve()
assert root == Path.cwd().resolve() == Path(__file__).resolve().parents[1]
assert root.parent == Path(tempfile.gettempdir()) and root.name.startswith('sfi-profile-tests-')
sys.path.insert(0, str(root))

import contextlib
import io
import secrets
import socket
import unittest
from unittest.mock import patch


def deny_network(*args, **kwargs):
    raise RuntimeError('External networking disabled in isolated profile tests')


original_connect = socket.socket.connect

def isolated_connect(sock, address):
    if os.environ.get('SFI_QA_MYSQL_URI') and address == ('127.0.0.1', 13376):
        return original_connect(sock, address)
    return deny_network()

socket.socket.connect = isolated_connect
# create_connection uses socket.connect, retaining the narrow localhost allowlist.

import main
from __init__ import app, db
from model.user import User
from model.sfi_profile import SfiProfile, empty_interests
from model.sfi_onboarding import SfiOnboarding, empty_preferences, MULTI_CHOICES, TEXT_LIMITS
from model.group import SfiGroup, initSfiGroups, user_has_permission
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError

app.config.update(TESTING=True, SECRET_KEY=secrets.token_hex(32))


class ProfileTests(unittest.TestCase):
    def test_account_settings_cross_device_database_and_isolation(self):
        from model.sfi_settings import SfiSettings
        self.login()
        first = self.client.get('/api/sfi/settings')
        self.assertEqual(first.json, {'version': 1, 'revision': 0, 'preferences': {}})
        self.assertEqual(first.headers['Cache-Control'], 'no-store')
        payload = {'theme': 'dark', 'accent': 'purple', 'language': 'es', 'textSize': 'large', 'resultsPerPage': 10}
        saved = self.client.patch('/api/sfi/settings', json={'version': 1, 'revision': 0, 'preferences': payload})
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(db.session.get(SfiSettings, self.user.id).preferences, payload)
        second = app.test_client()
        self.login(second)
        self.assertEqual(second.get('/api/sfi/settings').json, saved.json)
        edited = second.patch('/api/sfi/settings', json={'version': 1, 'revision': 1, 'preferences': {'accent': 'teal'}})
        self.assertEqual(edited.json['revision'], 2)
        # Independent connection after engine disposal; database file survives.
        db.session.remove()
        db.engine.dispose()
        self.assertEqual(self.client.get('/api/sfi/settings').json['preferences'], {**payload, 'accent': 'teal'})
        # A fresh backend process reopens the same explicitly disposable DB.
        code = """import json
import main
from __init__ import app, db
from sqlalchemy import text
with app.app_context():
    row = db.session.execute(text('SELECT preferences FROM sfi_account_settings WHERE user_id=:id'), {'id': int(__import__('os').environ['SFI_RESTART_USER_ID'])}).scalar_one()
    print(json.dumps({'stored': json.loads(row) if isinstance(row, str) else row}))
"""
        environment = dict(os.environ, SFI_DATABASE_URI=db.engine.url.render_as_string(hide_password=False),
                           SFI_RESTART_USER_ID=str(self.user.id))
        restarted = subprocess.run([sys.executable, '-c', code], cwd=root, env=environment, capture_output=True, text=True, check=True)
        stored = json.loads(restarted.stdout.strip().splitlines()[-1])['stored']
        self.assertEqual(stored, {**payload, 'accent': 'teal'})

        stale = self.client.patch('/api/sfi/settings', json={'version': 1, 'revision': 1, 'preferences': {'theme': 'light'}})
        self.assertEqual(stale.status_code, 409)
        other = User(name='Separate Account', uid='separate_' + secrets.token_hex(6), password=self.password)
        db.session.add(other)
        db.session.commit()
        isolated = app.test_client()
        self.login(isolated, other.uid)
        self.assertEqual(isolated.get('/api/sfi/settings').json['preferences'], {})
        self.assertEqual(self.client.delete('/api/authenticate').status_code, 200)
        self.assertEqual(self.client.get('/api/sfi/settings').status_code, 401)
        self.assertEqual(second.get('/api/sfi/settings').json['revision'], 2)

    def test_account_settings_migration_preserves_accounts_and_refuses_data_loss(self):
        from scripts.migrate_sfi_settings import migrate
        from model.sfi_settings import SfiSettings
        self.login()
        self.client.patch('/api/sfi/settings', json={'version': 1, 'revision': 0, 'preferences': {'language': 'es'}})
        user_id, original_hash, original_role = self.user.id, self.user._password, self.user.role
        db.session.remove()
        migrate(db.engine)
        migrate(db.engine)
        with self.assertRaisesRegex(ValueError, 'Refusing to discard'):
            migrate(db.engine, downgrade=True)
        self.assertEqual(db.session.get(User, user_id)._password, original_hash)
        self.assertEqual(db.session.get(User, user_id).role, original_role)
        self.assertEqual(db.session.get(SfiSettings, user_id).preferences['language'], 'es')

    def test_account_settings_security_validation_and_rollback(self):
        from model.sfi_settings import SfiSettings
        self.assertEqual(self.client.get('/api/sfi/settings').status_code, 401)
        self.assertEqual(self.client.patch('/api/sfi/settings', json={}).status_code, 401)
        self.login()
        for values in ({'role': 'Admin'}, {'user_id': 999}, {'__proto__': {}}, {'theme': 'arbitrary'},
                       {'textSize': 999}, {'resultsPerPage': True}, {'highContrast': 'true'}, [], None):
            response = self.client.patch('/api/sfi/settings', json={'version': 1, 'revision': 0, 'preferences': values})
            self.assertEqual(response.status_code, 400)
        for body in ({}, [], {'version': True, 'revision': 0, 'preferences': {}},
                     {'version': 1, 'revision': False, 'preferences': {}},
                     {'version': 1, 'revision': 0, 'preferences': {}, 'user_id': self.user.id}):
            self.assertEqual(self.client.patch('/api/sfi/settings', json=body).status_code, 400)
        self.assertEqual(self.client.patch('/api/sfi/settings', data='{', content_type='application/json').status_code, 400)
        self.assertEqual(self.client.patch('/api/sfi/settings', data='{}').status_code, 415)
        self.assertEqual(self.client.patch('/api/sfi/settings', data=' ' * 16385, content_type='application/json').status_code, 413)
        with patch.object(db.session, 'commit', side_effect=SQLAlchemyError('synthetic failure')):
            self.assertEqual(self.client.patch('/api/sfi/settings', json={'version': 1, 'revision': 0, 'preferences': {'theme': 'dark'}}).status_code, 503)
        self.assertIsNone(db.session.get(SfiSettings, self.user.id))
        self.assertEqual(db.session.get(User, self.user.id).role, 'User')
        forbidden = self.client.patch('/api/sfi/settings', headers={'Origin': 'https://untrusted.example'}, json={'version': 1, 'revision': 0, 'preferences': {}})
        self.assertEqual(forbidden.status_code, 403)
        self.assertNotIn('Access-Control-Allow-Origin', forbidden.headers)


    def preferences(self, body):
        return self.client.patch('/api/sfi/profile/preferences', json=body)

    def test_motorsports_full_partial_reload_edit_clear_and_legacy(self):
        self.login()
        self.assertEqual(self.get().json['preferences'], empty_preferences())
        self.assertIsNone(db.session.get(SfiOnboarding, self.user.id))
        self.assertEqual(self.preferences({}).status_code, 200)  # All optional.
        self.save(self.answers)
        full = {key: [value for value in values if value not in ('prefer_not_to_answer', 'not_applicable')]
                for key, values in MULTI_CHOICES.items()}
        full.update(organization_name='Synthetic Racing', organization_website='https://example.org/racing',
                    job_title='Engineer', primary_goal='research_equipment',
                    additional_notes='<script>alert("untrusted text")</script>')
        self.assertEqual(self.preferences(full).json['preferences'], full)
        db.session.remove()
        self.assertEqual(self.get().json['preferences'], full)
        edited = self.preferences({'involvement': ['driver'], 'primary_goal': None,
                                   'organization_website': None}).json['preferences']
        self.assertEqual(edited, {**full, 'involvement': ['driver'], 'primary_goal': None,
                                 'organization_website': ''})
        self.assertEqual(self.get().json['interests'], self.answers)
        self.assertEqual(self.preferences(empty_preferences()).json['preferences'], empty_preferences())
        self.assertEqual(SfiOnboarding.query.filter_by(user_id=self.user.id).count(), 1)
        self.assertEqual(self.get().json['interests'], self.answers)
        self.save(empty_interests())
        self.assertEqual(self.get().json['preferences'], empty_preferences())

    def test_preference_validation_limits_and_atomicity(self):
        self.login()
        valid = {'involvement': ['driver'], 'additional_notes': 'Saved'}
        self.preferences(valid)
        invalid = [None, [], {'unknown': []}, {'primary_goal': []}, {'primary_goal': 'Admin'},
                   {'organization_name': 42}, {'additional_notes': False},
                   {'additional_notes': 'bad\x00text'},
                   {'involvement': ['prefer_not_to_answer', 'driver']},
                   {'disciplines': ['not_applicable', 'road_racing']}]
        for key in MULTI_CHOICES:
            invalid.extend([{key: ['unknown']}, {key: 'driver'}, {key: [['driver']]},
                            {key: [MULTI_CHOICES[key][0]] * 2}])
        for key, limit in TEXT_LIMITS.items():
            invalid.append({key: 'x' * (limit + 1)})
        for url in ('example.org', 'javascript:alert(1)', 'https://u:p@example.org',
                    'https://example.org:99999', 'https://', 'https://exa mple.org',
                    'https://example.org\\@evil.org', 'https://example.org\n/path',
                    'https://invalid-.example', 'https://-invalid.example'):
            invalid.append({'organization_website': url})
        for body in invalid:
            with self.subTest(body=body):
                response = self.client.patch('/api/sfi/profile/preferences', data=json.dumps(body), content_type='application/json')
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.get().json['preferences']['additional_notes'], 'Saved')
        self.assertEqual(self.client.patch('/api/sfi/profile/preferences', data='{}').status_code, 415)
        self.assertEqual(self.client.patch('/api/sfi/profile/preferences', data='{', content_type='application/json').status_code, 400)
        for key in ('organization_name', 'job_title', 'additional_notes'):
            self.assertEqual(self.preferences({key: 'x' * TEXT_LIMITS[key]}).status_code, 200)
        self.assertEqual(self.preferences({'organization_website': 'https://example.org/' + 'x' * 480}).status_code, 200)
        self.assertEqual(self.preferences({key: None for key in empty_preferences()}).json['preferences'], empty_preferences())

    def test_preference_claims_cannot_escalate_or_target_other_users(self):
        self.assertEqual(self.preferences({}).status_code, 401)
        self.login()
        other = User(name='Other racer', uid='other_' + secrets.token_hex(6), password=self.password)
        db.session.add(other)
        db.session.commit()
        original_hash = self.user._password
        for claim in ('sfi_staff', 'manufacturer', 'sanctioning_body', 'technical_inspector'):
            self.assertEqual(self.preferences({'involvement': [claim], 'organization_name': 'Claimed SFI'}).status_code, 200)
            for route in ('/api/sfi/profile/roles', '/api/sfi/users', '/api/sfi/groups', '/api/sfi/gear/all'):
                self.assertEqual(self.client.get(route).status_code, 403)
            self.assertEqual(self.client.patch(f'/api/sfi/profile/roles/{other.id}', json={'role': 'Admin'}).status_code, 403)
            self.assertFalse(self.get().json['can_manage_roles'])
            self.assertEqual(self.user.role, 'User')
            self.assertFalse(user_has_permission(self.user, 'can_manage_users'))
            self.assertEqual(self.user._password, original_hash)
        for key, value in (('user_id', other.id), ('uid', other.uid), ('role', 'Admin'),
                           ('groups', ['administrators']), ('can_manage_roles', True), ('permissions', {})):
            self.assertEqual(self.preferences({key: value}).status_code, 400)
        self.assertIsNone(db.session.get(SfiOnboarding, other.id))
        self.assertEqual(self.client.patch(f'/api/sfi/profile/preferences/{other.id}', json={}).status_code, 404)
        self.assertEqual(self.preferences({'involvement': ['administrator']}).status_code, 400)
        for path in ('/api/sfi/profile', '/api/sfi/profile/preferences'):
            self.assertEqual(app.test_client().get(path).status_code, 401 if path.endswith('profile') else 405)
        # The public/account list representation never includes private preferences.
        self.assertTrue(all('preferences' not in item and 'organization_name' not in item
                            for item in self.client.get('/api/user').json))
        self.assertEqual(self.client.patch('/api/sfi/profile/preferences', json={},
                         headers={'Origin': 'https://untrusted.example'}).status_code, 403)

    def test_admin_login_and_privileges_survive_preferences(self):
        admin = User(name='Preferences admin', uid='admin_' + secrets.token_hex(6),
                     password=self.password, role='Admin')
        db.session.add(admin)
        db.session.commit()
        initSfiGroups()
        self.login(uid=admin.uid)
        original_hash = admin._password
        self.assertEqual(self.preferences({'involvement': ['enthusiast']}).status_code, 200)
        self.assertEqual(self.get().json['role'], 'Admin')
        self.assertTrue(self.get().json['can_manage_roles'])
        self.assertEqual(self.client.get('/api/sfi/profile/roles').status_code, 200)
        self.assertEqual(self.client.get('/api/sfi/users').status_code, 200)
        self.assertEqual(admin._password, original_hash)

    def test_preferences_rollback(self):
        self.login()
        self.preferences({'additional_notes': 'Saved'})
        with patch.object(db.session, 'commit', side_effect=SQLAlchemyError('synthetic failure')):
            self.assertEqual(self.preferences({'additional_notes': 'Unsaved'}).status_code, 500)
        self.assertEqual(self.get().json['preferences']['additional_notes'], 'Saved')

    def test_preferences_migration_repeat_reverse_and_legacy_preservation(self):
        from scripts.migrate_sfi_onboarding import migrate
        from sqlalchemy import create_engine, text
        with tempfile.TemporaryDirectory() as directory:
            engine = create_engine('sqlite:///' + str(Path(directory) / 'migration.db'))
            with engine.begin() as connection:
                connection.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY)'))
                connection.execute(text('INSERT INTO users VALUES (1)'))
                connection.execute(text('CREATE TABLE sfi_profiles (user_id INTEGER PRIMARY KEY, skills TEXT)'))
                connection.execute(text("INSERT INTO sfi_profiles VALUES (1, 'Legacy skills')"))
            migrate(engine)
            migrate(engine)
            with engine.begin() as connection:
                self.assertEqual(connection.scalar(text('SELECT skills FROM sfi_profiles')), 'Legacy skills')
                connection.execute(text("INSERT INTO sfi_onboarding_preferences VALUES (1, '{}')"))
            with self.assertRaises(ValueError):
                migrate(engine, downgrade=True)
            with engine.begin() as connection:
                connection.execute(text('DELETE FROM sfi_onboarding_preferences'))
            migrate(engine, downgrade=True)
            migrate(engine, downgrade=True)
            migrate(engine)
            engine.dispose()

    def setUp(self):
        self.context = app.app_context()
        self.context.push()
        self.password = secrets.token_urlsafe(24)
        self.uid = 'review_' + secrets.token_hex(6)
        self.user = User(name='SFI Review User', uid=self.uid, password=self.password)
        db.session.add(self.user)
        db.session.commit()
        self.client = app.test_client()
        self.answers = {
            'causes': ['Motorsports safety', 'Community support'],
            'participation': ['Volunteer', 'Share expertise'],
            'skills': 'Event coordination', 'volunteering': True, 'availability': 'Monthly',
        }

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def login(self, client=None, uid=None):
        with contextlib.redirect_stdout(io.StringIO()):
            response = (client or self.client).post('/api/authenticate', json={
                'uid': uid or self.uid, 'password': self.password,
            })
        self.assertEqual(response.status_code, 200)

    def get(self):
        return self.client.get('/api/sfi/profile')

    def save(self, body):
        return self.client.put('/api/sfi/profile/interests', json=body)

    def test_authentication_and_logout(self):
        self.assertNotEqual(self.user._password, self.password)
        self.assertTrue(self.user.is_password(self.password))
        self.assertFalse(self.user.is_password('incorrect'))
        self.assertEqual(self.get().status_code, 401)
        self.assertEqual(self.save(self.answers).status_code, 401)
        self.assertEqual(self.client.post('/api/authenticate', json={
            'uid': self.uid, 'password': 'incorrect',
        }).status_code, 401)
        self.login()
        self.assertEqual(self.client.get('/api/id').json['uid'], self.uid)
        self.assertEqual(self.get().json['uid'], self.uid)
        self.assertEqual(self.client.delete('/api/authenticate').status_code, 200)
        self.assertEqual(self.get().status_code, 401)

    def test_optional_quiz_round_trip_and_clear(self):
        self.login()
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['interests'], empty_interests())
        self.assertIsNone(db.session.get(SfiProfile, self.user.id))
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(self.save(self.answers).status_code, 200)
        db.session.remove()
        self.assertEqual(self.get().json['interests'], self.answers)
        self.answers.update(skills='Mentoring', volunteering=False, availability='')
        self.assertEqual(self.save(self.answers).json['interests'], self.answers)
        self.assertEqual(self.save(empty_interests()).status_code, 200)
        self.assertEqual(self.get().json['interests'], empty_interests())

    def test_user_isolation_and_identity_rejection(self):
        other = User(name='Other member', uid='other_' + secrets.token_hex(6), password=self.password)
        db.session.add(other)
        db.session.commit()
        self.login()
        self.assertEqual(self.save(self.answers).status_code, 200)
        for field, value in [('user_id', other.id), ('uid', other.uid), ('role', 'Admin'),
                             ('permissions', {'can_manage_users': True}), ('groups', ['administrators'])]:
            self.assertEqual(self.save({**self.answers, field: value}).status_code, 400)
        other_client = app.test_client()
        self.login(other_client, other.uid)
        self.assertEqual(other_client.get('/api/sfi/profile').json['interests'], empty_interests())
        self.assertEqual(self.user.role, 'User')

    def test_invalid_answers_leave_saved_answers_intact(self):
        self.login()
        self.save(self.answers)
        invalid = [[], None, {}, {**self.answers, 'causes': 'Environment'},
                   {**self.answers, 'causes': [['nested']]},
                   {**self.answers, 'causes': ['Environment', 'Environment']},
                   {**self.answers, 'participation': ['Admin']},
                   {**self.answers, 'skills': 'x' * 501}, {**self.answers, 'skills': 5},
                   {**self.answers, 'volunteering': 1}, {**self.answers, 'volunteering': 'yes'},
                   {**self.answers, 'availability': 'Every minute'}]
        for body in invalid:
            with self.subTest(body_type=type(body).__name__):
                # JSON null must be sent explicitly (Flask's json=None omits the body).
                response = self.client.put('/api/sfi/profile/interests', data=json.dumps(body), content_type='application/json')
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.put('/api/sfi/profile/interests', data='{}').status_code, 415)
        self.assertEqual(self.client.put('/api/sfi/profile/interests', data='{', content_type='application/json').status_code, 400)
        self.assertEqual(self.get().json['interests'], self.answers)

    def test_database_error_rolls_back(self):
        self.login()
        self.save(self.answers)
        with patch.object(db.session, 'commit', side_effect=SQLAlchemyError('test failure')):
            self.assertEqual(self.save({**self.answers, 'skills': 'Not saved'}).status_code, 500)
        self.assertEqual(self.get().json['interests'], self.answers)

    def test_existing_account_survives_additive_schema_creation(self):
        columns = [column['name'] for column in inspect(db.engine).get_columns('users')]
        original_hash = self.user._password
        user_id = self.user.id
        db.session.remove()  # Release MySQL metadata locks before additive DDL.
        # Recreate ONLY the new table in this disposable database, simulating an old schema.
        SfiProfile.__table__.drop(db.engine)
        db.create_all()
        self.assertEqual(columns, [column['name'] for column in inspect(db.engine).get_columns('users')])
        self.assertEqual(db.session.get(User, user_id)._password, original_hash)
        self.login()
        self.assertEqual(self.get().json['interests'], empty_interests())
        self.assertEqual(self.save(self.answers).status_code, 200)

    def test_signup_and_self_edit_do_not_grant_privileges(self):
        uid = 'signup_' + secrets.token_hex(6)
        with contextlib.redirect_stdout(io.StringIO()):
            response = self.client.post('/api/user', json={
                'uid': uid, 'name': 'New member', 'password': self.password,
                'role': 'Admin', 'groups': ['administrators'],
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.query.filter_by(_uid=uid).one().role, 'User')
        for reserved in {'admin', 'ADMIN', 'admin ', app.config['ADMIN_UID']}:
            self.assertEqual(self.client.post('/api/user', json={
                'uid': reserved, 'name': 'Reserved', 'password': self.password,
            }).status_code, 400)
        self.login()
        with contextlib.redirect_stdout(io.StringIO()):
            response = self.client.put('/api/user', json={'role': 'Admin', 'name': 'Updated member'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['role'], 'User')
        self.assertEqual(response.json['name'], 'Updated member')
        self.assertEqual(self.client.put('/api/user', json={'uid': 'admin'}).status_code, 400)
        self.assertEqual(self.client.put('/api/user', json={'uid': 'ADMIN '} ).status_code, 400)
        self.assertEqual(self.client.put('/api/user', json={'uid': app.config['ADMIN_UID']}).status_code, 400)

    def test_flask_login_session_compatibility(self):
        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.user.id)
            session['_fresh'] = True
        self.assertEqual(self.get().status_code, 200)
        self.assertEqual(self.save(self.answers).status_code, 200)
        self.assertEqual(self.client.delete('/api/authenticate').status_code, 200)
        self.assertEqual(self.get().status_code, 401)

    def test_profile_name_edit(self):
        self.login()
        original_hash = self.user._password
        user_id = self.user.id
        db.session.remove()  # Release MySQL metadata locks before additive DDL.
        response = self.client.put('/api/sfi/profile', json={'name': '  SFI Volunteer  '})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['name'], 'SFI Volunteer')
        self.assertEqual(response.json['role_label'], 'Member')
        self.assertFalse(response.json['can_manage_roles'])
        db.session.remove()
        self.assertEqual(self.get().json['name'], 'SFI Volunteer')
        self.assertEqual(User.query.filter_by(_uid=self.uid).one()._password, original_hash)
        for body in ({'name': ''}, {'name': 'x'}, {'name': 'x' * 256}, {'name': []},
                     {'name': 'Valid', 'role': 'Admin'}, {'uid': 'admin'}):
            self.assertEqual(self.client.put('/api/sfi/profile', json=body).status_code, 400)
        self.assertEqual(self.get().json['name'], 'SFI Volunteer')

    def test_admin_only_roles_and_permission_synchronization(self):
        self.login()
        endpoint = f'/api/sfi/profile/roles/{self.user.id}'
        self.assertEqual(self.client.get('/api/sfi/profile/roles').status_code, 403)
        self.assertEqual(self.client.patch(endpoint, json={'role': 'Admin'}).status_code, 403)
        admin = User(name='Review Administrator', uid='review_admin_' + secrets.token_hex(6),
                     password=self.password, role='Admin')
        db.session.add(admin)
        db.session.commit()
        admin_client = app.test_client()
        self.login(admin_client, admin.uid)
        self.assertEqual(admin_client.get('/api/sfi/profile/roles').status_code, 200)
        self.assertEqual(admin_client.patch(f'/api/sfi/profile/roles/{admin.id}', json={'role': 'Member'}).status_code, 409)
        for role in ('Admin', 'Volunteer', 'Donor', 'Member', 'User', 'Teacher'):
            response = admin_client.patch(endpoint, json={'role': role})
            self.assertEqual(response.status_code, 200)
            db.session.refresh(self.user)
            self.assertEqual(self.user.role, role)
            self.assertEqual(user_has_permission(self.user, 'can_manage_users'), role == 'Admin')
            self.assertEqual(self.get().json['can_manage_roles'], role == 'Admin')
        self.assertEqual(admin_client.patch(endpoint, json={'role': 'Owner'}).status_code, 400)
        self.assertEqual(admin_client.patch(endpoint, json={'role': 'Admin', 'user_id': admin.id}).status_code, 400)
        self.assertEqual(admin_client.patch('/api/sfi/profile/roles/99999999', json={'role': 'Member'}).status_code, 404)

    def test_upstream_bearer_auth_and_password_hash_redaction(self):
        import jwt
        token = jwt.encode({'_uid': self.uid}, app.config['SECRET_KEY'], algorithm='HS256')
        self.assertEqual(self.client.get('/api/sfi/profile', headers={'Authorization': 'Bearer ' + token}).status_code, 200)
        self.assertEqual(self.client.get('/api/sfi/profile', headers={'Authorization': 'Bearer invalid'}).status_code, 401)
        self.login()
        self.assertNotIn('password', self.client.get('/api/id').json)
        self.assertTrue(all('password' not in record for record in self.client.get('/api/user').json))
        self.assertNotIn('password', self.client.put('/api/user', json={'name': 'Safe response'}).json)
        self.assertIn('password', self.user.read())  # Internal admin backups remain compatible.

    def test_existing_sfi_gear_moderation_and_public_endpoints(self):
        self.login()
        for path in ('/api/sfi/specs', '/api/sfi/categories', '/api/sfi/stats'):
            with self.subTest(path=path):
                # Since the catalog-initialization fix, a fresh empty database
                # must report unavailability, never a healthy empty catalog.
                response = self.client.get(path)
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json['code'], 'catalog_not_initialized')
        self.assertEqual(self.client.get('/api/sfi/classifier/status').status_code, 404)
        response = self.client.post('/api/sfi/gear', json={'name': 'Isolated helmet', 'spec': '31.1', 'category': 'Helmet'})
        self.assertEqual(response.status_code, 200)
        gear_id = response.json['id']
        self.assertEqual(response.json['status'], 'pending')
        self.assertEqual(self.client.get('/api/sfi/gear/all').status_code, 403)
        self.assertEqual(self.client.patch(f'/api/sfi/gear/{gear_id}/status', json={'status': 'approved'}).status_code, 403)
        self.assertEqual(self.save(self.answers).status_code, 200)
        self.assertEqual(self.client.get('/api/sfi/gear').json[0]['id'], gear_id)
        admin = User(name='Gear Reviewer', uid='gear_admin_' + secrets.token_hex(6), password=self.password, role='Admin')
        db.session.add(admin)
        SfiGroup.by_name('administrators').members.append(admin)
        db.session.commit()
        admin_client = app.test_client()
        self.login(admin_client, admin.uid)
        self.assertEqual(admin_client.patch(f'/api/sfi/gear/{gear_id}/status', json={'status': 'approved'}).status_code, 200)
        self.assertEqual(self.client.get('/api/sfi/gear').json[0]['status'], 'approved')

    def test_startup_groups_never_grant_admin_based_on_username(self):
        untrusted = User(name='Untrusted identity', uid='admin', password=self.password, role='User')
        trusted = User(name='Trusted administrator', uid='trusted_' + secrets.token_hex(6), password=self.password, role='Admin')
        legacy = User(name='Existing group administrator', uid='legacy_' + secrets.token_hex(6), password=self.password, role='User')
        db.session.add_all([untrusted, trusted, legacy])
        SfiGroup.by_name('administrators').members.append(legacy)
        db.session.commit()
        initSfiGroups()
        self.assertFalse(user_has_permission(untrusted, 'can_manage_users'))
        self.assertTrue(user_has_permission(trusted, 'can_manage_users'))
        self.assertTrue(user_has_permission(legacy, 'can_manage_users'))


def wsgi_bridge():
    """Start real HTTP over a Unix socket, plus private test-control IPC."""
    import threading
    from werkzeug.serving import make_server
    password = secrets.token_urlsafe(24)
    uid = 'bridge_' + secrets.token_hex(6)
    admin_uid = 'bridge_admin_' + secrets.token_hex(6)
    with app.app_context():
        db.session.add(User(name='Integration Member', uid=uid, password=password))
        db.session.add(User(name='Integration Admin', uid=admin_uid, password=password, role='Admin'))
        db.session.commit()
        # Bridge users are created after main's initial group seeding. Apply the
        # normal role-to-group initialization for these synthetic accounts too.
        initSfiGroups()
    client = app.test_client()
    socket_path = str(root / 'flask.sock')
    server = None
    try:
        server = make_server('unix://' + socket_path, 0, app)
        os.chmod(socket_path, 0o600)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
    except (OSError, SystemExit):
        # Restricted CI may prohibit binding even AF_UNIX. Use real WSGI requests
        # via the private pipe, and report that this is not a live HTTP-server test.
        socket_path = None
    print(json.dumps({'fixture': {'uid': uid, 'admin_uid': admin_uid,
                                 'password': password, 'socket': socket_path}}), flush=True)
    try:
        for line in sys.stdin:
            request_data = json.loads(line)
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    if request_data.get('proof_uid'):
                        from model.sfi_settings import SfiSettings
                        with app.app_context():
                            account = User.query.filter_by(_uid=request_data['proof_uid']).one()
                            settings = db.session.get(SfiSettings, account.id)
                            result = {'ok': True, 'status': 200, 'data': {
                                'name': account.name, 'role': account.role,
                                'revision': settings.revision if settings else 0,
                                'preferences': settings.preferences if settings else {}}}
                    elif request_data.get('reconnect'):
                        with app.app_context():
                            db.session.remove()
                            db.engine.dispose()
                        result = {'ok': True, 'status': 200, 'data': {}}
                    else:
                        response = client.open(
                            request_data['path'], method=request_data.get('method', 'GET'),
                            data=request_data.get('body'), headers=request_data.get('headers', {}),
                        )
                        result = {'ok': 200 <= response.status_code < 300,
                                  'status': response.status_code,
                                  'data': response.get_json(silent=True),
                                  'headers': dict(response.headers)}
                print(json.dumps({'id': request_data['id'], **result}), flush=True)
            except Exception:
                print(json.dumps({'id': request_data['id'], 'failure': 'WSGI integration request failed'}), flush=True)
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    if '--demo' in sys.argv:
        from scripts.migrate_sfi_catalog import upgrade
        from catalog_admin import create_spec
        with app.app_context():
            upgrade(db.engine)
            for index in range(23):
                create_spec({'spec_number': '99.' + str(index + 1),
                             'product_name': 'Synthetic demonstration equipment ' + str(index + 1),
                             'category': 'Demonstration'})
        # All data is in this runner's disposable copy. Create synthetic accounts
        # through the ordinary UI; no built-in passwords or privileged accounts.
        port = int(os.environ.get('SFI_DEMO_PORT') or '8865')
        print(f'Disposable demo API: http://localhost:{port}. Register synthetic accounts through the frontend. Data is removed when stopped.', flush=True)
        app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False)
    elif '--bridge' in sys.argv:
        wsgi_bridge()
    else:
        unittest.main(argv=[sys.argv[0]], verbosity=2)

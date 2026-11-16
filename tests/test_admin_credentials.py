"""Authentication/recovery regressions using only disposable SQLite and dummy secrets."""

import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import jwt
from flask import Flask
from flask_login import LoginManager

from __init__ import db
from api.group import group_api
from api.sfi_profile import sfi_profile_api
from api.user import user_api
from model.group import SfiGroup, initSfiGroups
from model.persona import Persona, UserPersona  # noqa: F401 -- ORM targets
from model.user import User
from scripts.admin_credentials import RecoveryError, main, reconcile
from security_config import ConfigurationError

PASSWORD = 'Synthetic!Recovery-4826-Only'
OLD_PASSWORD = 'Synthetic!Previous-9753-Only'
UID = 'synthetic-administrator'


class ConfigurationLoadingTests(unittest.TestCase):
    def test_backend_dotenv_is_independent_of_cwd_and_shell_has_precedence(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            backend = Path(directory, 'backend')
            backend.mkdir()
            for name in ('__init__.py', 'security_config.py'):
                shutil.copyfile(root / name, backend / name)
            (backend / '.env').write_text(
                f'ADMIN_UID={UID}\nADMIN_PASSWORD={PASSWORD}\n'
                'SECRET_KEY=synthetic-only-session-signing-key-39482\n'
                'SFI_DATABASE_URI=sqlite:///intended.db\n'
            )
            excluded = {'ADMIN_UID', 'ADMIN_PASSWORD', 'SECRET_KEY', 'SFI_DATABASE_URI',
                        'IS_PRODUCTION', 'DEFAULT_PASSWORD', 'USER_PASSWORD',
                        'TEACHER_PASSWORD', 'MY_PASSWORD', 'DB_ENDPOINT',
                        'DB_USERNAME', 'DB_PASSWORD', 'PYTHON_DOTENV_DISABLED'}
            env = {k: v for k, v in os.environ.items() if k not in excluded}
            env['PYTHONPATH'] = str(backend)
            code = (
                'import __init__ as core; from pathlib import Path; core.app.app_context().push(); '
                f'assert core.app.config["ADMIN_UID"] == {UID!r}; '
                f'assert core.app.config["ADMIN_PASSWORD"] == {PASSWORD!r}; '
                'assert Path(core.db.engine.url.database) == '
                f'Path({str(backend / "instance" / "intended.db")!r})'
            )
            result = subprocess.run([sys.executable, '-c', code], cwd=directory,
                                    env=env, capture_output=True)
            self.assertEqual(result.returncode, 0, 'Backend-relative dotenv loading failed')
            env['ADMIN_UID'] = 'synthetic-shell-override'
            result = subprocess.run([sys.executable, '-c',
                'import __init__ as core; assert core.app.config["ADMIN_UID"] == "synthetic-shell-override"'],
                cwd=directory, env=env, capture_output=True)
            self.assertEqual(result.returncode, 0, 'Shell precedence changed unexpectedly')


class AdminCredentialsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name, 'auth.db')
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True, SQLALCHEMY_DATABASE_URI='sqlite:///' + str(self.path),
            SECRET_KEY='synthetic-only-session-signing-key-39482',
            JWT_TOKEN_NAME='test-auth', ADMIN_UID=UID, ADMIN_USER='Synthetic Admin',
            ADMIN_PASSWORD=PASSWORD, IS_PRODUCTION=False,
        )
        db.init_app(self.app)
        login = LoginManager(self.app)
        login.user_loader(lambda uid: db.session.get(User, int(uid)))
        for blueprint in (user_api, group_api, sfi_profile_api):
            self.app.register_blueprint(blueprint)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        initSfiGroups()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.engine.dispose()
        self.context.pop()
        self.directory.cleanup()

    def recover(self, **kwargs):
        return reconcile(str(self.path), UID, PASSWORD, **kwargs)

    def admin(self, password=PASSWORD):
        user = User(name='Synthetic Admin', uid=UID, password=password, role='Admin')
        db.session.add(user)
        SfiGroup.by_name('administrators').members.append(user)
        db.session.commit()
        return user

    def login(self, password=PASSWORD, uid=UID):
        return self.client.post('/api/authenticate', json={'uid': uid, 'password': password})

    def test_missing_account_requires_explicit_bootstrap(self):
        self.assertEqual(self.login().status_code, 401)
        with self.assertRaises(RecoveryError):
            self.recover()
        result = self.recover(bootstrap=True)
        self.assertEqual(result['action'], 'bootstrap')
        self.assertFalse(result['applied'])
        self.assertEqual(User.query.count(), 0)

    def test_bootstrap_login_authorization_and_logout(self):
        self.recover(bootstrap=True, apply=True)
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['user']['role'], 'Admin')
        self.assertIn('HttpOnly', response.headers['Set-Cookie'])
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        token = self.client.get_cookie('test-auth').value
        decoded = jwt.decode(token, self.app.config['SECRET_KEY'], algorithms=['HS256'])
        self.assertEqual(decoded['_uid'], UID)
        self.assertLessEqual(decoded['exp'], (datetime.now(timezone.utc) + timedelta(hours=12)).timestamp())
        self.assertEqual(self.client.get('/api/id').status_code, 200)
        self.assertNotIn('password', self.client.get('/api/id').json)
        self.assertTrue(self.client.get('/api/sfi/me').json['isAdmin'])
        self.assertEqual(self.client.get('/api/sfi/groups').status_code, 200)
        self.assertEqual(self.client.get('/api/sfi/users').status_code, 200)
        self.assertEqual(self.client.delete('/api/authenticate').status_code, 200)
        self.assertIsNone(self.client.get_cookie('test-auth'))
        self.assertEqual(self.client.get('/api/id').status_code, 401)
        self.assertEqual(self.client.get('/api/sfi/users').status_code, 401)

    def test_invalid_password_unknown_uid_and_malformed_inputs(self):
        self.admin()
        for payload in ({'uid': UID, 'password': OLD_PASSWORD},
                        {'uid': 'unknown-user', 'password': PASSWORD}):
            self.assertEqual(self.client.post('/api/authenticate', json=payload).status_code, 401)
            self.assertIsNone(self.client.get_cookie('test-auth'))
        for payload in ([], 'bad', {'uid': [], 'password': PASSWORD},
                        {'uid': UID, 'password': ['bad']}):
            self.assertIn(self.client.post('/api/authenticate', json=payload).status_code, (400, 401))

    def test_stale_password_repair_preserves_users_roles_and_groups(self):
        admin = self.admin(OLD_PASSWORD)
        other = User(name='Synthetic Member', uid='member', password=OLD_PASSWORD)
        extra = SfiGroup(name='extra', can_view_all_gear=True)
        extra.members.append(admin)
        db.session.add_all([other, extra])
        db.session.commit()
        old_hash, other_hash, admin_id = admin._password, other._password, admin.id
        groups = [g.id for g in admin.sfi_groups.all()]
        self.assertEqual(self.login().status_code, 401)
        result = self.recover(user_id=admin_id)
        self.assertFalse(result['password_matches'])
        self.assertEqual(admin._password, old_hash)
        self.recover(user_id=admin_id, apply=True)
        self.assertEqual(User.query.count(), 2)
        self.assertEqual(admin.id, admin_id)
        self.assertEqual(admin.role, 'Admin')
        self.assertEqual([g.id for g in admin.sfi_groups.all()], groups)
        self.assertEqual(other._password, other_hash)
        self.assertEqual(self.login(OLD_PASSWORD).status_code, 401)
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.client.get('/api/sfi/users').status_code, 200)
        repaired = admin._password
        self.recover(user_id=admin_id, apply=True)
        self.assertEqual(admin._password, repaired)

    def test_wrong_database_identity_and_production_are_rejected(self):
        admin = self.admin(OLD_PASSWORD)
        wrong = Path(self.directory.name, 'wrong.db')
        wrong.touch()
        for path in (wrong, Path(self.directory.name, 'missing.db'), Path('auth.db')):
            with self.assertRaises(RecoveryError):
                reconcile(str(path), UID, PASSWORD, user_id=admin.id, apply=True)
        for uid, user_id in ((UID, admin.id + 1), ('wrong-identity', admin.id), (UID, None)):
            with self.assertRaises(RecoveryError):
                reconcile(str(self.path), uid, PASSWORD, user_id=user_id, apply=True)
        self.app.config['IS_PRODUCTION'] = True
        with self.assertRaises(RecoveryError):
            self.recover(user_id=admin.id, apply=True)
        self.assertTrue(admin.is_password(OLD_PASSWORD))

    def test_non_admin_identity_never_elevated(self):
        member = User(name='Synthetic Member', uid=UID, password=OLD_PASSWORD)
        db.session.add(member)
        db.session.commit()
        for options in ({'bootstrap': True}, {'user_id': member.id}):
            with self.assertRaises(RecoveryError):
                self.recover(apply=True, **options)
        self.assertEqual(member.role, 'User')
        self.assertTrue(member.is_password(OLD_PASSWORD))

    def test_bootstrap_refuses_other_admins_or_colliding_identities(self):
        for uid, role in (('other-admin', 'Admin'), (UID.upper(), 'User'),
                          (UID + ' ', 'User')):
            user = User(name='Synthetic Conflict', uid=uid, password=OLD_PASSWORD, role=role)
            db.session.add(user)
            db.session.commit()
            with self.assertRaises(RecoveryError):
                self.recover(bootstrap=True, apply=True)
            db.session.delete(user)
            db.session.commit()
        admin = self.admin()
        collision = User(name='Synthetic Collision', uid=UID.upper(), password=OLD_PASSWORD)
        db.session.add(collision)
        db.session.commit()
        with self.assertRaises(RecoveryError):
            self.recover(user_id=admin.id, apply=True)

    def test_group_only_admin_repair_preserves_role_and_permissions(self):
        admin = self.admin(OLD_PASSWORD)
        admin.role = 'User'
        db.session.commit()
        self.recover(user_id=admin.id, apply=True)
        self.assertEqual(admin.role, 'User')
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.client.get('/api/sfi/users').status_code, 200)

    def test_weak_missing_or_hash_password_rejected(self):
        for password in ('', 'short', 'x' * 32, 'replace-with-a-long-password',
                         'pbkdf2:sha256:1000000$synthetic$value'):
            with self.assertRaises((ConfigurationError, RecoveryError)):
                reconcile(str(self.path), UID, password, bootstrap=True, apply=True)
        self.assertEqual(User.query.count(), 0)

    def test_cli_requires_confirmation_and_never_displays_credentials(self):
        args = ['--database-path', str(self.path), '--uid', UID, '--bootstrap']
        output = io.StringIO()
        with (patch('__init__.app', self.app),
              patch.dict(os.environ, ADMIN_UID=UID, ADMIN_PASSWORD=PASSWORD),
              contextlib.redirect_stdout(output), contextlib.redirect_stderr(output)):
            self.assertEqual(main(args), 0)
            self.assertEqual(User.query.count(), 0)
            for answer in ('no', EOFError()):
                with patch('builtins.input', side_effect=[answer]):
                    self.assertEqual(main(args + ['--apply']), 1)
                self.assertEqual(User.query.count(), 0)
            with patch('builtins.input', return_value='APPLY'):
                self.assertEqual(main(args + ['--apply']), 0)
        user = User.query.one()
        for sensitive in (PASSWORD, user._password, self.app.config['SECRET_KEY']):
            self.assertNotIn(sensitive, output.getvalue())

    def test_ordinary_users_denied(self):
        member = User(name='Synthetic Member', uid='member', password=PASSWORD)
        db.session.add(member)
        db.session.commit()
        self.assertEqual(self.login(uid='member').status_code, 200)
        for route in ('/api/sfi/users', '/api/sfi/groups', '/api/sfi/profile/roles'):
            self.assertEqual(self.client.get(route).status_code, 403)

    def test_flask_login_session_supported(self):
        admin = self.admin()
        with self.client.session_transaction() as session:
            session['_user_id'] = str(admin.id)
            session['_fresh'] = True
        self.assertEqual(self.client.get('/api/sfi/users').status_code, 200)

    def test_invalid_and_expired_jwt_rejected(self):
        self.admin()
        for token in ('invalid-token', jwt.encode(
                {'_uid': UID, 'exp': datetime.now(timezone.utc) - timedelta(seconds=1)},
                self.app.config['SECRET_KEY'], algorithm='HS256')):
            self.client.set_cookie('test-auth', token)
            self.assertEqual(self.client.get('/api/sfi/users').status_code, 401)

    def test_all_public_signup_paths_reject_reserved_admin_identities(self):
        for uid in ('admin', ' ADMIN ', UID, UID.upper(), UID + ' '):
            payload = {'name': 'Synthetic', 'uid': uid, 'password': PASSWORD, 'role': 'Admin'}
            for route, body in (('/api/user', payload), ('/api/user/guest', payload),
                                ('/api/users', [payload])):
                response = self.client.post(route, json=body)
                self.assertIn(response.status_code, (200, 400))
                if route == '/api/users':
                    self.assertTrue(response.json['errors'])
                else:
                    self.assertEqual(response.status_code, 400)
        self.assertEqual(User.query.count(), 0)
        for route in ('/api/user', '/api/user/guest'):
            uid = 'ordinary-' + route.rsplit('/', 1)[1]
            with patch('model.user.KasmUser'):
                response = self.client.post(route, json={
                    'name': 'Synthetic Member', 'uid': uid, 'password': PASSWORD,
                    'role': 'Admin', 'groups': ['administrators'],
                })
            self.assertEqual(response.status_code, 200)
            user = User.query.filter_by(_uid=uid).one()
            self.assertEqual(user.role, 'User')
            self.assertEqual(user.sfi_groups.count(), 0)


if __name__ == '__main__':
    unittest.main()

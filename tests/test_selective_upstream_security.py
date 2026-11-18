"""Upstream guard regressions, with synthetic accounts, memory DBs and stubbed execution."""
import secrets
import subprocess
import unittest
from unittest.mock import patch

import jwt
from flask import Flask, g
from flask_login import LoginManager

import main
from __init__ import db
from api.analytics import analytics_api
from api.javascript_exec_api import javascript_exec_api
from api.python_exec_api import python_exec_api
from model.user import User


class UpstreamGuardTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY=secrets.token_urlsafe(48),
                               JWT_TOKEN_NAME='test_jwt', SQLALCHEMY_DATABASE_URI='sqlite://')
        db.init_app(self.app)
        login = LoginManager(self.app)
        login.user_loader(lambda user_id: db.session.get(User, int(user_id)))
        for blueprint in (analytics_api, python_exec_api, javascript_exec_api):
            self.app.register_blueprint(blueprint)
        self.app.add_url_rule('/update_user/<string:uid>', view_func=main.update_user, methods=['PUT'])
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.users = {}
        for uid, role in [('synthetic-admin', 'Admin'), ('synthetic-user', 'User'),
                          ('synthetic-other', 'User')]:
            user = User(name=uid, uid=uid, role=role, password=secrets.token_urlsafe(24))
            db.session.add(user)
            db.session.flush()
            self.users[uid] = user.id
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def client(self, uid=None, mode='bearer'):
        # Each client must resolve its own identity even inside our outer DB context.
        g.pop('_login_user', None)
        client = self.app.test_client()
        if uid:
            if mode == 'session':
                with client.session_transaction() as session:
                    session['_user_id'] = str(self.users[uid])
                    session['_fresh'] = True
            else:
                token = jwt.encode({'_uid': uid}, self.app.config['SECRET_KEY'], algorithm='HS256')
                if mode == 'cookie':
                    client.set_cookie('test_jwt', token)
                else:
                    client.environ_base['HTTP_AUTHORIZATION'] = 'Bearer ' + token
        return client

    def test_anonymous_update_returns_401_without_writes(self):
        response = self.client().put('/update_user/synthetic-other', json={'name': 'Changed'})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json, {'error': 'Authentication required'})
        self.assertEqual(db.session.get(User, self.users['synthetic-other']).name, 'synthetic-other')

    def test_non_admin_update_remains_forbidden(self):
        response = self.client('synthetic-user', 'session').put(
            '/update_user/synthetic-other', json={'name': 'Changed'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(db.session.get(User, self.users['synthetic-other']).name, 'synthetic-other')

    def test_admin_update_and_missing_user_remain_supported(self):
        client = self.client('synthetic-admin', 'session')
        self.assertEqual(client.put('/update_user/synthetic-other', json={'name': 'Changed'}).status_code, 200)
        self.assertEqual(db.session.get(User, self.users['synthetic-other']).name, 'Changed')
        self.assertEqual(client.put('/update_user/missing', json={'name': 'Changed'}).status_code, 404)

    def test_anonymous_and_invalid_tokens_cannot_reach_analytics(self):
        with patch('api.analytics.GitHubUser') as github:
            for headers in ({}, {'Authorization': 'Bearer invalid'}):
                response = self.client().get('/api/analytics/github/user/received_issue_comments', headers=headers)
                self.assertEqual(response.status_code, 401)
            github.assert_not_called()

    def test_analytics_uses_the_authenticated_account_for_all_auth_methods(self):
        for uid in ('synthetic-user', 'synthetic-other'):
            for mode in ('session', 'bearer', 'cookie'):
                with self.subTest(uid=uid, mode=mode), patch('api.analytics.GitHubUser') as github:
                    github.return_value.get_total_received_issue_comments.return_value = ({'count': 7}, 200)
                    response = self.client(uid, mode).get('/api/analytics/github/user/received_issue_comments')
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json, {'count': 7})
                    self.assertEqual(github.return_value.get_total_received_issue_comments.call_args.args[0], uid)

    def test_unauthenticated_runners_never_create_files_or_execute_code(self):
        for language in ('python', 'javascript'):
            module = 'api.' + language + '_exec_api'
            with patch(module + '.subprocess.run') as run, patch(module + '.tempfile.NamedTemporaryFile') as temp:
                for headers in ({}, {'Authorization': 'Bearer invalid'}):
                    response = self.client().post('/run/' + language, json={'code': 'synthetic'}, headers=headers)
                    self.assertEqual(response.status_code, 401)
                run.assert_not_called()
                temp.assert_not_called()

    def test_authenticated_runners_preserve_output_and_blank_input_contract(self):
        for language in ('python', 'javascript'):
            for mode in ('session', 'bearer', 'cookie'):
                with self.subTest(language=language, mode=mode), patch(
                    'api.' + language + '_exec_api.subprocess.run',
                    return_value=subprocess.CompletedProcess([], 0, 'synthetic output', '')
                ) as run:
                    client = self.client('synthetic-user', mode)
                    self.assertEqual(client.post('/run/' + language, json={'code': 'synthetic'}).json,
                                     {'output': 'synthetic output'})
                    self.assertEqual(run.call_count, 1)
                    self.assertEqual(client.post('/run/' + language, json={'code': '  '}).status_code, 400)
                    self.assertEqual(run.call_count, 1)

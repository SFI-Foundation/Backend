"""Backend #4: real auth, group checks, models and routes on disposable SQLite."""
from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import patch

import jwt
from flask import Flask, g
from flask_login import LoginManager
from sqlalchemy.exc import SQLAlchemyError

from __init__ import db
from api.user_gear import user_gear_api
from model.group import SfiGroup
from model.persona import Persona, UserPersona  # Register User relationship targets.
from model.user import User
from model.user_gear import UserGear


class GearReviewAPITests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True, SQLALCHEMY_DATABASE_URI='sqlite://',
            SECRET_KEY='isolated-gear-review-api-test-secret', JWT_TOKEN_NAME='token',
        )
        db.init_app(self.app)
        login = LoginManager(self.app)
        login.user_loader(lambda uid: db.session.get(User, int(uid)))
        self.app.register_blueprint(user_gear_api)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.member = User(name='Racer', uid='racer')
        self.other = User(name='Other racer', uid='other')
        self.admin = User(name='Reviewer', uid='admin-role', role='Admin')
        self.group_admin = User(name='Group admin', uid='group-admin')
        self.delegate = User(name='Delegate', uid='delegate')
        administrators = SfiGroup(name='administrators')
        administrators.members.append(self.group_admin)
        delegates = SfiGroup(name='delegates', can_approve_gear=True, can_view_all_gear=True)
        delegates.members.append(self.delegate)
        db.session.add_all([self.member, self.other, self.admin, administrators, delegates])
        db.session.commit()
        self.member_id, self.other_id, self.admin_id = self.member.id, self.other.id, self.admin.id
        self.pending_old = self.gear(self.member_id, 'Old pending helmet', 10)
        self.pending_new = self.gear(self.other_id, 'New pending suit', 3)
        self.approved = self.gear(self.other_id, 'Approved harness', 2, 'approved')
        self.rejected = self.gear(self.member_id, 'Rejected suit', 1, 'rejected')
        self.client = self.app.test_client()
        self.authenticate('admin-role')

    def gear(self, user_id, name, age, status='pending'):
        gear = UserGear.create(user_id, {'name': name})
        gear.created_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=age)
        if status != 'pending':
            gear.set_status(status, self.admin_id, 'Original review')
        db.session.commit()
        return gear.id

    def authenticate(self, uid, expired=False):
        expiry = datetime.now(timezone.utc) + timedelta(minutes=-1 if expired else 5)
        token = jwt.encode({'_uid': uid, 'exp': expiry}, self.app.config['SECRET_KEY'], algorithm='HS256')
        self.client.set_cookie('token', token)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def review(self, gear_id, body):
        return self.client.put(f'/api/sfi/gear/{gear_id}/review',
                               data=json.dumps(body), content_type='application/json')

    def snapshot(self, gear_id):
        return db.session.get(UserGear, gear_id).to_dict()

    def test_pending_oldest_first_with_owner_metadata(self):
        response = self.client.get('/api/sfi/gear/pending')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item['id'] for item in response.json], [self.pending_old, self.pending_new])
        self.assertEqual(response.json[0]['owner'], {'id': self.member_id, 'uid': 'racer', 'name': 'Racer'})
        self.assertNotIn('password', response.json[0]['owner'])

    def test_all_filters_combine_and_empty_matches_are_lists(self):
        for query, expected in (
            ('', [self.rejected, self.approved, self.pending_new, self.pending_old]),
            ('?status=pending', [self.pending_new, self.pending_old]),
            (f'?user={self.member_id}', [self.rejected, self.pending_old]),
            (f'?status=rejected&user={self.member_id}', [self.rejected]),
            (f'?status=approved&user={self.member_id}', []),
            ('?user=999999', []),
        ):
            with self.subTest(query=query):
                response = self.client.get('/api/sfi/gear/all' + query)
                self.assertEqual(response.status_code, 200)
                self.assertEqual([item['id'] for item in response.json], expected)
                for item in response.json:
                    self.assertIn('uid', item['owner'])

    def test_invalid_filters_return_400(self):
        for query in ('?status=', '?status=unknown', '?status=pending&status=approved',
                      '?user=', '?user=0', '?user=-1', '?user=1.5', '?user=racer',
                      '?user=9223372036854775808', '?user=' + '9' * 100,
                      '?user=1&user=2', '?user=%EF%BC%91'):
            with self.subTest(query=query):
                self.assertEqual(self.client.get('/api/sfi/gear/all' + query).status_code, 400)

    def test_admin_approve_reject_persist_and_update_pending_queue(self):
        original = self.snapshot(self.pending_old)
        response = self.review(self.pending_old, {
            'status': 'approved', 'notes': '  Label verified  ',
            'reviewer_id': self.other_id, 'updated_at': '1900-01-01',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['reviewer_id'], self.admin_id)
        self.assertEqual(response.json['reviewer_notes'], 'Label verified')
        self.assertEqual(response.json['reviewNote'], 'Label verified')
        self.assertEqual(response.json['created_at'], original['created_at'])
        self.assertGreaterEqual(response.json['updated_at'], original['updated_at'])
        self.assertIsNotNone(response.json['reviewedAt'])
        response = self.review(self.pending_new, {'status': 'rejected', 'notes': ' Certification expired '})
        self.assertEqual(response.status_code, 200)
        db.session.remove()
        self.assertEqual(self.snapshot(self.pending_old)['status'], 'approved')
        self.assertEqual(self.snapshot(self.pending_new)['reviewer_notes'], 'Certification expired')
        self.assertEqual(self.client.get('/api/sfi/gear/pending').json, [])
        rejected = self.client.get('/api/sfi/gear/all?status=rejected').json
        self.assertIn(self.pending_new, [item['id'] for item in rejected])
        self.authenticate('other')
        own = self.client.get('/api/sfi/gear').json
        self.assertEqual(next(item for item in own if item['id'] == self.pending_new)['reviewer_notes'], 'Certification expired')

    def test_invalid_bodies_leave_audit_fields_unchanged(self):
        original = self.snapshot(self.pending_old)
        for body in (None, [], 1, 'approved', {}, {'status': 1}, {'status': []},
                     {'status': 'pending'}, {'status': 'invalid'}, {'status': 'rejected'},
                     {'status': 'rejected', 'notes': ' \n\t '},
                     {'status': 'rejected', 'notes': None},
                     {'status': 'approved', 'notes': []},
                     {'status': 'approved', 'notes': {'text': 'bad'}}):
            with self.subTest(body=body):
                self.assertEqual(self.review(self.pending_old, body).status_code, 400)
                self.assertEqual(self.snapshot(self.pending_old), original)
        for data, content_type in (('{', 'application/json'), ('status=approved', 'text/plain'), ('', 'application/json')):
            self.assertEqual(self.client.put(f'/api/sfi/gear/{self.pending_old}/review', data=data, content_type=content_type).status_code, 400)
        self.assertEqual(self.snapshot(self.pending_old), original)

    def test_missing_gear_returns_404(self):
        self.assertEqual(self.review(999999, {'status': 'approved'}).status_code, 404)

    def test_unauthenticated_and_expired_requests_return_401(self):
        self.client.delete_cookie('token')
        for expired in (False, True):
            if expired:
                self.authenticate('admin-role', expired=True)
            for path in ('/api/sfi/gear/pending', '/api/sfi/gear/all'):
                self.assertEqual(self.client.get(path).status_code, 401)
            self.assertEqual(self.review(self.pending_old, {'status': 'approved'}).status_code, 401)

    def test_nonadmins_cannot_read_or_review_other_users_gear(self):
        original = self.snapshot(self.pending_old)
        for uid in ('racer', 'other', 'delegate'):
            self.authenticate(uid)
            for path in ('/api/sfi/gear/pending', '/api/sfi/gear/all', '/api/sfi/gear/all?status=invalid'):
                self.assertEqual(self.client.get(path).status_code, 403)
            self.assertEqual(self.review(self.pending_old, {'status': 'approved'}).status_code, 403)
            self.assertEqual(self.review(999999, {'status': 'approved'}).status_code, 403)
        self.assertEqual(self.snapshot(self.pending_old), original)

    def test_administrators_group_and_flask_login_session_are_supported(self):
        self.authenticate('group-admin')
        self.assertEqual(self.client.get('/api/sfi/gear/pending').status_code, 200)
        self.assertEqual(self.review(self.pending_old, {'status': 'approved'}).status_code, 200)
        self.client.delete_cookie('token')
        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.admin_id)
            session['_fresh'] = True
        # This fixture keeps an outer app context; clear Flask-Login's cached
        # anonymous user to emulate the new app context of a real HTTP request.
        g.pop('_login_user', None)
        self.assertEqual(self.client.get('/api/sfi/gear/all').status_code, 200)
        self.assertEqual(self.review(self.pending_new, {'status': 'rejected', 'notes': 'Check label'}).status_code, 200)

    def test_legacy_patch_validates_notes_and_keeps_delegated_permissions(self):
        self.authenticate('delegate')
        path = f'/api/sfi/gear/{self.pending_old}/status'
        self.assertEqual(self.client.patch(path, json={'status': 'rejected'}).status_code, 400)
        self.assertEqual(self.snapshot(self.pending_old)['status'], 'pending')
        response = self.client.patch(path, json={'status': 'rejected', 'note': 'Needs recertification'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['reviewer_notes'], 'Needs recertification')
        self.assertEqual(self.client.patch(path, json={'status': 'pending'}).status_code, 200)
        self.assertEqual(self.snapshot(self.pending_old)['status'], 'pending')

    def test_database_failure_rolls_back_review(self):
        original = self.snapshot(self.pending_old)
        with patch.object(db.session, 'commit', side_effect=SQLAlchemyError('simulated failure')):
            with self.assertLogs(self.app.logger, level='ERROR'):
                response = self.review(self.pending_old, {'status': 'rejected', 'notes': 'Not saved'})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.snapshot(self.pending_old), original)


if __name__ == '__main__':
    unittest.main()

"""Run: python -m unittest discover -s tests -v (isolated in-memory databases)."""
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
import jwt
from flask import Flask
from flask_login import LoginManager
from __init__ import db
from model.user import User
from model.persona import Persona, UserPersona
from model.user_gear import UserGear
from model.group import SfiGroup
from api.user_gear import user_gear_api
from scripts.migrate_user_gear import upgrade


class GearTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI='sqlite://',
                               SECRET_KEY='test-only-secret-key-for-gear-tests', JWT_TOKEN_NAME='token')
        db.init_app(self.app)
        login = LoginManager(self.app)
        login.user_loader(lambda uid: db.session.get(User, int(uid)))
        self.app.register_blueprint(user_gear_api)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.user = User(name='Test Racer', uid='racer')
        self.other = User(name='Other Racer', uid='other')
        db.session.add_all([self.user, self.other])
        db.session.commit()
        self.client = self.app.test_client()
        token = jwt.encode({'_uid': 'racer'}, self.app.config['SECRET_KEY'], algorithm='HS256')
        self.client.set_cookie('token', token)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_create_list_delete_and_owner_isolation(self):
        foreign = UserGear.create(self.other.id, {'name': 'Other helmet'})
        response = self.client.post('/api/sfi/gear', json={'name': 'Helmet', 'source': 'detector', 'status': 'approved', 'reviewer_notes': 'spoof'})
        self.assertEqual(response.status_code, 200)
        item = response.json
        self.assertEqual(item['status'], 'pending')
        self.assertEqual(item['source'], 'detector')
        self.assertEqual(item['reviewer_notes'], '')
        self.assertIsNone(item['reviewer_id'])
        for key in ('created_at', 'updated_at', 'createdAt', 'updatedAt'):
            datetime.fromisoformat(item[key])
        self.assertEqual([x['id'] for x in self.client.get('/api/sfi/gear').json], [item['id']])
        self.assertEqual(self.client.delete(f'/api/sfi/gear/{foreign.id}').status_code, 403)
        self.assertEqual(self.client.delete(f"/api/sfi/gear/{item['id']}").status_code, 200)
        self.assertEqual(self.client.get('/api/sfi/gear').json, [])
        self.client.delete_cookie('token')
        self.assertEqual(self.client.get('/api/sfi/gear').status_code, 401)

    def test_review_alias_and_update_timestamp(self):
        gear = UserGear.create(self.user.id, {'name': 'Suit'})
        self.assertEqual(gear.source, 'manual')
        old = datetime.utcnow() - timedelta(days=1)
        gear.updated_at = old
        db.session.commit()
        note = 'Needs recertification. ' * 40
        gear.set_status('rejected', self.other.id, note)
        self.assertGreater(gear.updated_at, old)
        self.assertEqual(gear.read()['reviewer_notes'], note)
        self.assertEqual(gear.to_dict()['reviewNote'], note)
        self.assertEqual(gear.review_note, note)
        self.assertEqual(gear.reviewer_id, self.other.id)
        with self.assertRaises(ValueError):
            gear.set_status('invalid', self.other.id)

    def test_fresh_schema_and_persisted_review(self):
        from sqlalchemy import inspect
        columns = {column['name'] for column in inspect(db.engine).get_columns('user_gear')}
        self.assertTrue({'status', 'source', 'reviewer_id', 'reviewer_notes',
                         'created_at', 'updated_at'}.issubset(columns))
        gear = UserGear.create(self.user.id, {'name': 'Harness', 'source': 'classifier'})
        gear_id, reviewer_id = gear.id, self.other.id
        gear.set_status('rejected', reviewer_id, 'Please recertify')
        db.session.remove()
        saved = db.session.get(UserGear, gear_id)
        self.assertEqual(saved.status, 'rejected')
        self.assertEqual(saved.source, 'classifier')
        self.assertEqual(saved.reviewer_id, reviewer_id)
        self.assertEqual(saved.reviewer_notes, 'Please recertify')
        self.assertEqual(saved.read()['reviewNote'], saved.reviewer_notes)
        self.assertIsNotNone(saved.updated_at)

    def test_existing_permission_based_auto_approval(self):
        group = SfiGroup(name='reviewers', can_approve_gear=True)
        group.members.append(self.user)
        db.session.add(group)
        db.session.commit()
        response = self.client.post('/api/sfi/gear', json={'name': 'Staff helmet'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['status'], 'approved')
        self.assertEqual(response.json['reviewer_id'], self.user.id)
        self.assertIsNotNone(response.json['reviewedAt'])

    def test_existing_review_api_keeps_note_aliases_and_permissions(self):
        gear = UserGear.create(self.user.id, {'name': 'Suit'})
        path = f'/api/sfi/gear/{gear.id}/status'
        self.assertEqual(self.client.patch(path, json={'status': 'approved'}).status_code, 403)
        group = SfiGroup(name='reviewers', can_approve_gear=True)
        group.members.append(self.user)
        db.session.add(group)
        db.session.commit()
        response = self.client.patch(path, json={'status': 'rejected', 'note': 'Expired label'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['reviewer_notes'], 'Expired label')
        self.assertEqual(response.json['reviewNote'], 'Expired label')
        self.assertEqual(response.json['updated_at'], response.json['updatedAt'])

    def test_normal_orm_updates_refresh_timestamp(self):
        gear = UserGear.create(self.user.id, {'name': 'Helmet'})
        created = gear.created_at
        old = datetime.utcnow() - timedelta(days=1)
        gear.updated_at = old
        db.session.commit()
        gear.name = 'Updated helmet'
        db.session.commit()
        self.assertGreater(gear.updated_at, old)
        self.assertEqual(gear.created_at, created)


class MigrationTests(unittest.TestCase):
    def test_legacy_schemas_preserve_data_and_repeat_safely(self):
        for reviewed in (False, True):
            with self.subTest(reviewed=reviewed), sqlite3.connect(':memory:') as connection:
                connection.execute('CREATE TABLE users (id INTEGER PRIMARY KEY)')
                connection.execute('INSERT INTO users VALUES (1)')
                connection.execute('CREATE TABLE user_gear (id INTEGER PRIMARY KEY, user_id INTEGER, name TEXT)')
                connection.execute("INSERT INTO user_gear VALUES (7, 1, 'Helmet')")
                if reviewed:
                    connection.execute('ALTER TABLE user_gear ADD COLUMN review_note TEXT')
                    connection.execute('ALTER TABLE user_gear ADD COLUMN status TEXT')
                    connection.execute("UPDATE user_gear SET review_note='Old note', status='rejected'")
                connection.commit()
                upgrade(connection)
                connection.row_factory = sqlite3.Row
                first = dict(connection.execute('SELECT * FROM user_gear').fetchone())
                self.assertEqual(first['name'], 'Helmet')
                self.assertEqual(first['status'], 'rejected' if reviewed else 'pending')
                self.assertEqual(first['reviewer_notes'], 'Old note' if reviewed else '')
                self.assertTrue(first['updated_at'])
                upgrade(connection)
                self.assertEqual(first, dict(connection.execute('SELECT * FROM user_gear').fetchone()))
                self.assertEqual(connection.execute('PRAGMA foreign_key_list(user_gear)').fetchone()['table'], 'users')

    def test_preserves_existing_review_metadata_and_timestamps(self):
        with sqlite3.connect(':memory:') as connection:
            connection.executescript('''
                CREATE TABLE users (id INTEGER PRIMARY KEY);
                INSERT INTO users VALUES (1);
                CREATE TABLE user_gear (
                    id INTEGER PRIMARY KEY, user_id INTEGER, name TEXT, source TEXT,
                    status TEXT, reviewer_id INTEGER, review_note TEXT,
                    created_at DATETIME, reviewed_at DATETIME
                );
                INSERT INTO user_gear VALUES (
                    7, 1, 'Helmet', 'ai-detection', 'approved', 1, 'Original note',
                    '2026-01-01 00:00:00', '2026-01-02 00:00:00'
                );
            ''')
            upgrade(connection)
            connection.row_factory = sqlite3.Row
            row = dict(connection.execute('SELECT * FROM user_gear').fetchone())
            self.assertEqual(row['source'], 'ai-detection')
            self.assertEqual(row['status'], 'approved')
            self.assertEqual(row['reviewer_id'], 1)
            self.assertEqual(row['reviewer_notes'], 'Original note')
            self.assertEqual(row['created_at'], '2026-01-01 00:00:00')
            self.assertEqual(row['updated_at'], row['reviewed_at'])
            connection.execute("UPDATE user_gear SET reviewer_notes = 'New note'")
            connection.commit()
            upgrade(connection)
            self.assertEqual(connection.execute('SELECT reviewer_notes FROM user_gear').fetchone()[0], 'New note')

    def test_cli_creates_recoverable_backup_and_rejects_missing_database(self):
        script = Path(__file__).resolve().parents[1] / 'scripts/migrate_user_gear.py'
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'gear.db'
            missing = subprocess.run([sys.executable, str(script), str(database)], capture_output=True, text=True)
            self.assertNotEqual(missing.returncode, 0)
            self.assertFalse(database.exists())
            with sqlite3.connect(database) as connection:
                connection.execute('CREATE TABLE user_gear (id INTEGER PRIMARY KEY, name TEXT)')
                connection.execute("INSERT INTO user_gear VALUES (7, 'Helmet')")
            subprocess.run([sys.executable, str(script), str(database)], check=True, capture_output=True)
            backups = list(Path(directory).glob('gear.db.*.bak'))
            self.assertEqual(len(backups), 1)
            with sqlite3.connect(backups[0]) as connection:
                self.assertEqual(connection.execute('SELECT * FROM user_gear').fetchall(), [(7, 'Helmet')])
                self.assertEqual(len(connection.execute('PRAGMA table_info(user_gear)').fetchall()), 2)
            with sqlite3.connect(database) as connection:
                self.assertEqual(connection.execute('SELECT status FROM user_gear').fetchone()[0], 'pending')

    def test_failed_upgrade_rolls_back_schema_and_data(self):
        with sqlite3.connect(':memory:') as connection:
            connection.executescript('''
                CREATE TABLE user_gear (id INTEGER PRIMARY KEY, name TEXT);
                INSERT INTO user_gear VALUES (7, 'Helmet');
                CREATE TRIGGER block_updates BEFORE UPDATE ON user_gear
                BEGIN SELECT RAISE(ABORT, 'simulated migration failure'); END;
            ''')
            with self.assertRaises(sqlite3.IntegrityError):
                upgrade(connection)
            self.assertEqual([row[1] for row in connection.execute('PRAGMA table_info(user_gear)')], ['id', 'name'])
            self.assertEqual(connection.execute('SELECT * FROM user_gear').fetchall(), [(7, 'Helmet')])


if __name__ == '__main__':
    unittest.main()

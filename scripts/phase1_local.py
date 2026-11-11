#!/usr/bin/env python3
"""Opt-in localhost catalog sandbox. No existing users, jobs or main.py startup."""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask, request, jsonify, g, redirect, make_response
from flask_login import LoginManager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from __init__ import db, validate_cors_origin, add_cors_headers
from api.sfi_spec import sfi_spec_api
from model.persona import Persona, UserPersona  # noqa: F401 -- register ORM relationship targets
from model.sfi_spec import SfiSpec, SfiSpecChunk
from model.user import User
from model.user_gear import UserGear  # register the optional synthetic gear table
from model.group import initSfiGroups
from api.authorize import auth_required
import jwt


def create_app(database, demo_accounts=False):
    app = Flask('sfi-phase1-local')
    app.config.update(
        SQLALCHEMY_DATABASE_URI=database,
        SECRET_KEY=os.urandom(32),
        JWT_TOKEN_NAME='phase1-local-token',
    )
    db.init_app(app)
    login = LoginManager(app)
    login.user_loader(
        lambda uid: db.session.get(User, int(uid)) if demo_accounts else None
    )

    @app.before_request
    def local_origin():
        if request.path == '/local-demo/' and request.headers.get(
            'Origin'
        ) == request.host_url.rstrip('/'):
            return None
        return validate_cors_origin()

    app.after_request(add_cors_headers)
    app.register_blueprint(sfi_spec_api)

    @app.get('/api/sfi/health')
    def health():
        with app.app_context():
            db.session.execute(text('SELECT 1'))
        return {'status': 'ok', 'mode': 'isolated-local-catalog'}

    @app.get('/api/id')
    @auth_required()
    def me():
        return jsonify(
            id=g.current_user.id,
            uid=g.current_user.uid,
            name=g.current_user.name,
            role=g.current_user.role,
            isAdmin=g.current_user.role == 'Admin',
        )

    if demo_accounts:
        # Enabling test accounts requires a marker created by --prepare. Never
        # seed or authenticate against an arbitrary existing application DB.
        with app.app_context():
            if db.engine.url.get_backend_name() != 'sqlite':
                raise ValueError(
                    'Demo accounts require a prepared local SQLite sandbox'
                )
            db.session.execute(
                text('SELECT id FROM phase1_local_sandbox WHERE id=1')
            ).one()
            if not User.query.filter_by(_uid='phase1-synthetic-admin').first():
                raise ValueError('Prepare a new sandbox with --demo-accounts first')

        from api.group import group_api
        from api.user_gear import user_gear_api

        app.register_blueprint(group_api)
        app.register_blueprint(user_gear_api)
        # Normal password authentication on synthetic users, confined to this
        # prepared disposable database. No production account is seeded.
        from flask_restful import Api
        from api.user import UserAPI

        Api(app).add_resource(UserAPI._Security, '/api/authenticate')

        @app.route('/local-demo/', methods=['GET', 'POST'])
        def demo_login():
            if request.method == 'GET':
                return (
                    '<h1>Isolated local QA accounts</h1><p>Fictional users. Local testing only.</p>'
                    '<form method="post"><button name="role" value="Admin">Use synthetic admin</button> '
                    '<button name="role" value="User">Use synthetic member</button></form>'
                )
            role = request.form.get('role')
            if role not in ('Admin', 'User'):
                return {'error': 'Choose a synthetic test role'}, 400
            user = User.query.filter_by(
                _uid='phase1-synthetic-' + ('admin' if role == 'Admin' else 'member')
            ).one()
            response = make_response(redirect('http://localhost:4000/sfi-specs/'))
            response.set_cookie(
                app.config['JWT_TOKEN_NAME'],
                jwt.encode(
                    {'_uid': user.uid}, app.config['SECRET_KEY'], algorithm='HS256'
                ),
                httponly=True,
                samesite='Lax',
            )
            return response

    else:
        app.add_url_rule('/api/sfi/me', view_func=me)
    return app


def prepare(database, demo_accounts=False):
    engine = create_engine(database)
    if (
        engine.url.get_backend_name() != 'sqlite'
        or not engine.url.database
        or Path(engine.url.database).exists()
    ):
        raise ValueError(
            'Preparation requires a NEW SQLite file; existing databases are never initialized'
        )
    with engine.begin() as connection:
        SfiSpec.__table__.create(connection)
        SfiSpecChunk.__table__.create(connection)
        if demo_accounts:
            db.metadata.create_all(connection)
            connection.execute(
                text('CREATE TABLE phase1_local_sandbox (id INTEGER PRIMARY KEY)')
            )
            connection.execute(text('INSERT INTO phase1_local_sandbox VALUES (1)'))
    source = Path(__file__).resolve().parents[1] / 'sfi_specs.json'
    with Session(engine) as session:
        if demo_accounts:
            session.add_all(
                [
                    User(
                        name='Fictional QA Administrator',
                        uid='phase1-synthetic-admin',
                        role='Admin',
                    ),
                    User(
                        name='Fictional QA Member',
                        uid='phase1-synthetic-member',
                        role='User',
                    ),
                ]
            )
        for entry in json.loads(source.read_text()):
            for index, number in enumerate(entry['spec_numbers']):

                def at(field):
                    values = entry.get(field, [])
                    return values[index] if index < len(values) else ''

                session.add(
                    SfiSpec(
                        spec_number=number,
                        product_name=entry['product_name'],
                        category=entry['category'],
                        subcategory=entry.get('subcategory', ''),
                        effective_date=entry.get('effective_date', ''),
                        spec_pdf=at('spec_pdfs'),
                        manufacturer_pdf=at('manufacturer_pdfs'),
                        products_pdf=at('products_pdfs'),
                    )
                )
        session.commit()
    engine.dispose()
    if demo_accounts:
        with create_app(database).app_context():
            initSfiGroups()
    print('New catalog sandbox prepared; run migrate_sfi_catalog.py next.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    parser.add_argument(
        '--prepare',
        action='store_true',
        help='Create only a new catalog sandbox and seed public legacy catalog',
    )
    parser.add_argument('--port', type=int, default=8605)
    parser.add_argument(
        '--demo-accounts',
        action='store_true',
        help='Opt-in synthetic accounts in a NEW prepared SQLite sandbox only',
    )
    args = parser.parse_args()
    if args.prepare:
        prepare(args.database, args.demo_accounts)
    else:
        create_app(args.database, args.demo_accounts).run(
            host='127.0.0.1', port=args.port, debug=False
        )


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Opt-in localhost catalog sandbox. No existing users, jobs or main.py startup."""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask
from flask_login import LoginManager
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from __init__ import db, validate_cors_origin, add_cors_headers
from api.sfi_spec import sfi_spec_api
from model.persona import Persona, UserPersona
from model.sfi_spec import SfiSpec, SfiSpecChunk


def create_app(database):
    app = Flask('sfi-phase1-local')
    app.config.update(
        SQLALCHEMY_DATABASE_URI=database,
        SECRET_KEY=os.urandom(32),
        JWT_TOKEN_NAME='phase1-local-token',
    )
    db.init_app(app)
    login = LoginManager(app)
    login.user_loader(lambda uid: None)  # no real users/accounts in this sandbox
    app.before_request(validate_cors_origin)
    app.after_request(add_cors_headers)
    app.register_blueprint(sfi_spec_api)
    return app


def prepare(database):
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
    source = Path(__file__).resolve().parents[1] / 'sfi_specs.json'
    with Session(engine) as session:
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
    args = parser.parse_args()
    if args.prepare:
        prepare(args.database)
    else:
        create_app(args.database).run(host='127.0.0.1', port=args.port, debug=False)


if __name__ == '__main__':
    main()

"""Explicit additive preferences migration; never opens the configured app DB.

Stop writers and take a normal backup before deployment. MySQL DDL is not
transactional. Downgrade refuses to delete saved preferences; export and clear
them through a separately reviewed process before removing the table.
"""
import argparse
from sqlalchemy import (Column, ForeignKey, Integer, JSON, MetaData, Table,
                        create_engine, inspect, select, func)


def migrate(engine, downgrade=False):
    metadata = MetaData()
    Table('users', metadata, Column('id', Integer, primary_key=True))
    table = Table('sfi_account_settings', metadata,
                  Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
                  Column('revision', Integer, nullable=False, default=1),
                  Column('preferences', JSON, nullable=False))
    with engine.begin() as connection:
        if not inspect(connection).has_table('users'):
            raise ValueError('An existing users table is required.')
        if downgrade:
            if inspect(connection).has_table(table.name):
                if connection.scalar(select(func.count()).select_from(table)):
                    raise ValueError('Refusing to discard saved preferences.')
                table.drop(connection)
        else:
            table.create(connection, checkfirst=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', help='Explicit disposable SQLite URI; prefer --from-env for secrets')
    parser.add_argument('--from-env', action='store_true', help='Use Backend .env/config without importing main or seeding data')
    parser.add_argument('--downgrade', action='store_true')
    args = parser.parse_args()
    if bool(args.database) == bool(args.from_env):
        parser.error('Choose exactly one of --database or --from-env')
    if args.from_env:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from __init__ import app, db
        with app.app_context():
            engine = db.engine
    else:
        engine = create_engine(args.database)
    migrate(engine, args.downgrade)
    print('Preferences schema migration complete; existing account and legacy profile data unchanged.')

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
    table = Table('sfi_onboarding_preferences', metadata,
                  Column('user_id', Integer, ForeignKey('users.id'), primary_key=True),
                  Column('answers', JSON, nullable=False))
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
    parser.add_argument('--database', required=True, help='Explicit SQLAlchemy URI')
    parser.add_argument('--downgrade', action='store_true')
    args = parser.parse_args()
    engine = create_engine(args.database)
    migrate(engine, args.downgrade)
    print('Preferences schema migration complete; existing account and legacy profile data unchanged.')

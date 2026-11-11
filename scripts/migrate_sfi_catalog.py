#!/usr/bin/env python3
"""Add the Phase 1 metadata table without changing legacy rows or tables.

Explicit CLI, matching the repository's additive migration convention. SQLite
is verified; SQLAlchemy DDL also supports the configured MySQL engine. Back up
MySQL externally and stop writers first (MySQL DDL is not transactional).
"""

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine
from model.sfi_spec import SfiCatalogEntry


def upgrade(engine):
    with engine.begin() as connection:
        SfiCatalogEntry.__table__.create(connection, checkfirst=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--database',
        required=True,
        help='Explicit SQLAlchemy URI; never inferred from production config',
    )
    args = parser.parse_args()
    engine = create_engine(args.database)
    if engine.url.get_backend_name() == 'sqlite':
        path = Path(engine.url.database or '')
        if not path.is_file():
            parser.error(
                'Existing SQLite database required; create an isolated empty SQLite file first for a fresh sandbox.'
            )
        backup = path.with_name(
            path.name
            + '.'
            + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
            + '.bak'
        )
        with sqlite3.connect(path) as source, sqlite3.connect(backup) as target:
            source.backup(target)
        print('Backup:', backup)
    upgrade(engine)
    print('Phase 1 metadata schema ready; legacy data unchanged.')


if __name__ == '__main__':
    main()

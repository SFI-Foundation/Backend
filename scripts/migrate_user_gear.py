#!/usr/bin/env python3
"""Non-destructive, repeatable SQLite upgrade; run with the server stopped."""
import argparse
from datetime import datetime
from pathlib import Path
import sqlite3

COLUMNS = {
    'source': "VARCHAR(40) DEFAULT 'manual'",
    'status': "VARCHAR(20) NOT NULL DEFAULT 'pending'",
    'reviewer_id': 'INTEGER REFERENCES users(id)',
    'reviewed_at': 'DATETIME',
    'reviewer_notes': "TEXT DEFAULT ''",
    'created_at': 'DATETIME',
    'updated_at': 'DATETIME',
}


def upgrade(connection):
    columns = {row[1] for row in connection.execute('PRAGMA table_info(user_gear)')}
    if not columns:
        raise ValueError('No user_gear table. Initialize a fresh database with db_init.py.')
    # Explicit transaction makes all schema and data changes atomic.
    connection.execute('BEGIN IMMEDIATE')
    try:
        for name, definition in COLUMNS.items():
            if name not in columns:
                connection.execute(f'ALTER TABLE user_gear ADD COLUMN {name} {definition}')
        if 'reviewer_notes' not in columns and 'review_note' in columns:
            connection.execute("UPDATE user_gear SET reviewer_notes = COALESCE(review_note, '')")
        now = datetime.utcnow().isoformat(sep=' ')
        connection.execute('UPDATE user_gear SET created_at = ? WHERE created_at IS NULL', (now,))
        connection.execute('UPDATE user_gear SET updated_at = COALESCE(reviewed_at, created_at) WHERE updated_at IS NULL')
        connection.execute("UPDATE user_gear SET status = 'pending' WHERE status IS NULL")
        connection.execute("UPDATE user_gear SET source = 'manual' WHERE source IS NULL")
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path)
    args = parser.parse_args()
    if not args.database.is_file():
        parser.error('Database must already exist; no empty database will be created.')
    backup = args.database.with_name(args.database.name + '.' + datetime.utcnow().strftime('%Y%m%dT%H%M%S%f') + '.bak')
    with sqlite3.connect(args.database) as connection:
        with sqlite3.connect(backup) as destination:
            connection.backup(destination)
        upgrade(connection)
    print(f'Upgrade complete. Backup: {backup}')


if __name__ == '__main__':
    main()

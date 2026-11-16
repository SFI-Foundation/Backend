#!/usr/bin/env python3
"""Explicit, non-destructive recovery for the configured local administrator."""

import argparse
import os
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class RecoveryError(ValueError):
    """Safe operator-facing error; never include database values or secrets."""


def identity_key(uid):
    # Fail closed on case, whitespace, compatibility and accent collisions.
    return ''.join(
        c for c in unicodedata.normalize('NFKD', uid.strip().casefold())
        if not unicodedata.combining(c)
    )


def reconcile(database_path, expected_uid, password, *, bootstrap=False,
              user_id=None, apply=False):
    """Validate first; apply only in an explicit, locked local transaction.

    Dry runs roll back. Existing users receive only a password change; their
    role, memberships and all other data are preserved. No startup/network
    initialization is imported or invoked.
    """
    from flask import current_app
    from sqlalchemy import text
    from __init__ import db
    from model.group import SfiGroup
    from model.persona import Persona, UserPersona  # noqa: F401 -- ORM targets
    from model.user import User
    from security_config import secret

    if current_app.config.get('IS_PRODUCTION'):
        raise RecoveryError('Recovery is restricted to local development databases.')
    if (not expected_uid or expected_uid != expected_uid.strip()
            or len(expected_uid) > 255
            or expected_uid != current_app.config.get('ADMIN_UID')):
        raise RecoveryError('Explicit UID must exactly match configured ADMIN_UID.')
    # Unlike development startup, recovery must never generate a random fallback.
    validated = secret({'ADMIN_PASSWORD': password or ''}, 'ADMIN_PASSWORD',
                       production=True, minimum=16)
    if validated != password or password.startswith('pbkdf2:sha256:'):
        raise RecoveryError('ADMIN_PASSWORD must be a strong plaintext credential without surrounding whitespace.')
    url = db.engine.url
    supplied = Path(database_path)
    if (url.get_backend_name() != 'sqlite' or not url.database or url.query
            or not supplied.is_absolute() or not supplied.is_file()
            or not Path(url.database).is_file()
            or supplied.resolve() != Path(url.database).resolve()):
        raise RecoveryError('Database must be an existing absolute SQLite path matching application configuration.')

    try:
        if apply:
            db.session.execute(text('BEGIN IMMEDIATE'))
        users = User.query.all()
        matches = [u for u in users if identity_key(u.uid) == identity_key(expected_uid)]
        if len(matches) > 1 or (matches and matches[0].uid != expected_uid):
            raise RecoveryError('Conflicting administrator identities; manual review required.')
        user = matches[0] if matches else None
        admin_group = SfiGroup.by_name('administrators')
        authorized_ids = {u.id for u in users if u.role == 'Admin'}
        if admin_group:
            authorized_ids.update(u.id for u in admin_group.members.all())

        if bootstrap:
            if user or authorized_ids or user_id is not None:
                raise RecoveryError('Bootstrap requires a missing identity and no existing administrators. Recover an authorized account instead.')
            permissions = ('can_approve_gear', 'can_view_all_gear',
                           'can_manage_groups', 'can_manage_users')
            if admin_group and not all(getattr(admin_group, p) for p in permissions):
                raise RecoveryError('Existing administrators group permissions require manual review.')
            action = 'bootstrap'
            matches_password = False
        else:
            if user is None:
                raise RecoveryError('Configured administrator is missing. Review an explicit --bootstrap dry run.')
            if user.id != user_id or user.id not in authorized_ids:
                raise RecoveryError('User ID must identify the existing authorized administrator; no role elevation is allowed.')
            action = 'repair'
            matches_password = user.is_password(password)

        result = {'action': action, 'administrator_exists': user is not None,
                  'password_matches': matches_password, 'user_id': user.id if user else None,
                  'applied': False}
        if not apply:
            return result
        if bootstrap:
            if admin_group is None:
                admin_group = SfiGroup(name='administrators', **dict.fromkeys(permissions, True))
                db.session.add(admin_group)
            user = User(name=current_app.config['ADMIN_USER'], uid=expected_uid,
                        password=password, role='Admin')
            db.session.add(user)
            admin_group.members.append(user)
        elif not matches_password:
            user.set_password(password)
        if not user.is_password(password):
            raise RecoveryError('Credential verification failed; changes rolled back.')
        db.session.commit()
        result.update(applied=True, user_id=user.id, password_matches=True)
        return result
    finally:
        db.session.rollback()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-path', required=True, help='Existing absolute local SQLite path; must match app configuration')
    parser.add_argument('--uid', required=True, help='Exact configured administrator UID')
    parser.add_argument('--user-id', type=int, help='Existing authorized administrator numeric ID (repair only)')
    parser.add_argument('--bootstrap', action='store_true', help='Create the first administrator only when none exists')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='Validate only (default)')
    mode.add_argument('--apply', action='store_true', help='Validate, request confirmation, then apply')
    args = parser.parse_args(argv)
    try:
        # Import only core configuration; main.py has startup database writes.
        from __init__ import app

        if not os.environ.get('ADMIN_UID') or not os.environ.get('ADMIN_PASSWORD'):
            raise RecoveryError('Explicit ADMIN_UID and ADMIN_PASSWORD are required in Backend .env or the process environment.')
        if app.config['ADMIN_PASSWORD'] != os.environ['ADMIN_PASSWORD']:
            raise RecoveryError('ADMIN_PASSWORD must load unchanged from the configured environment.')
        options = dict(bootstrap=args.bootstrap, user_id=args.user_id)
        with app.app_context():
            plan = reconcile(args.database_path, args.uid,
                             os.environ['ADMIN_PASSWORD'], **options)
            print('Database and configured identity validated.')
            print(f"Action: {plan['action']}; administrator exists: {plan['administrator_exists']}; credential matches: {plan['password_matches']}; user ID: {plan['user_id']}")
            if not args.apply:
                print('Dry run complete. No changes made.')
                return 0
            confirmation = input('Type APPLY to modify this local administrator credential: ')
            if confirmation != 'APPLY':
                print('Cancelled. No changes made.')
                return 1
            # Recheck inside the write lock after operator confirmation.
            reconcile(args.database_path, args.uid, os.environ['ADMIN_PASSWORD'],
                      apply=True, **options)
            print('Administrator credential saved and verified. No secrets displayed.')
            return 0
    except (RecoveryError, EOFError) as exc:
        print(str(exc) if isinstance(exc, RecoveryError) else 'Confirmation required. No changes made.', file=sys.stderr)
        return 1
    except Exception:
        # DB exceptions may contain parameter values, including hashes.
        print('Recovery failed. Check configuration and schema locally; no changes committed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())

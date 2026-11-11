"""Validate secrets before database initialization; errors contain names only."""

import os
import secrets

from sqlalchemy.engine import make_url


class ConfigurationError(ValueError):
    pass


def boolean(env, name, default=False):
    value = str(env.get(name, str(default))).strip().lower()
    if value not in ('true', 'false'):
        raise ConfigurationError(f'{name} must be true or false')
    return value == 'true'


def secret(env, name, *, production, minimum=32, required=True):
    value = env.get(name, '').strip()
    if not value:
        if production and required:
            raise ConfigurationError(f'{name} is required in production')
        return secrets.token_urlsafe(48)
    if (
        len(value) < minimum
        or len(set(value)) < 8
        or any(
            word in value.lower()
            for word in (
                'replace-with',
                'changeme',
                'placeholder',
                'password',
                'secret_key',
            )
        )
    ):
        raise ConfigurationError(
            f'{name} must be a strong non-placeholder value (at least {minimum} characters)'
        )
    return value


def settings(env=None):
    env = os.environ if env is None else env
    production = boolean(env, 'IS_PRODUCTION')
    research = boolean(env, 'SFI_INTERNAL_RESEARCH')
    if production and research:
        raise ConfigurationError('SFI_INTERNAL_RESEARCH is forbidden in production')
    result = {'IS_PRODUCTION': production, 'SFI_INTERNAL_RESEARCH': research}
    result['SECRET_KEY'] = secret(env, 'SECRET_KEY', production=production)
    for name in (
        'DEFAULT_PASSWORD',
        'ADMIN_PASSWORD',
        'USER_PASSWORD',
        'TEACHER_PASSWORD',
        'MY_PASSWORD',
    ):
        result[name] = secret(
            env,
            name,
            production=production,
            minimum=16,
            required=name in ('DEFAULT_PASSWORD', 'ADMIN_PASSWORD'),
        )
    db_fields = [
        bool(env.get(name, '').strip())
        for name in ('DB_ENDPOINT', 'DB_USERNAME', 'DB_PASSWORD')
    ]
    if any(db_fields) and not all(db_fields):
        raise ConfigurationError(
            'DB_ENDPOINT, DB_USERNAME and DB_PASSWORD must be configured together'
        )
    uri = env.get('SFI_DATABASE_URI', '').strip()
    if uri:
        try:
            url = make_url(uri)
            if production and (
                url.get_backend_name() != 'mysql'
                or not url.username
                or not url.password
                or not url.host
                or not url.database
            ):
                raise ValueError()
        except Exception:  # noqa: BLE001 -- fail closed across driver/parser errors
            raise ConfigurationError(
                'SFI_DATABASE_URI is invalid; production requires an authenticated MySQL URI'
            ) from None
    if production and not uri and not all(db_fields):
        raise ConfigurationError(
            'Production requires MySQL configuration; SQLite fallback is disabled'
        )
    result.update(
        SESSION_COOKIE_SECURE=production,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='None' if production else 'Lax',
    )
    return result

"""
Shared authorization helpers for SFI API endpoints.

admin_required: 401 if not logged in, 403 if logged in but not an admin.
"""

from functools import wraps
from flask import g
from api.authorize import auth_required
from model.group import user_is_admin


def is_admin(user):
    """Admin = role 'Admin' or membership in the 'administrators' group."""
    return user is not None and (
        getattr(user, 'role', None) == 'Admin' or user_is_admin(user)
    )


def admin_required(func):
    """Decorator for admin-only endpoints (session or JWT auth)."""
    @auth_required()
    @wraps(func)
    def decorated(*args, **kwargs):
        if not is_admin(g.current_user):
            return {"error": "Forbidden", "message": "Admin access required."}, 403
        return func(*args, **kwargs)
    return decorated

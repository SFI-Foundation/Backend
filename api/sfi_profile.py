"""Current-user profile and editable, optional interest quiz."""
from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy.exc import SQLAlchemyError
from urllib.parse import urlsplit
from ipaddress import ip_address
import re

from __init__ import db
from api.authorize import token_required
from model.sfi_profile import SfiProfile, empty_interests
from model.sfi_onboarding import (SfiOnboarding, empty_preferences, MULTI_CHOICES,
                                  GOALS, TEXT_LIMITS)
from model.user import User
from model.group import SfiGroup, user_is_admin


sfi_profile_api = Blueprint('sfi_profile_api', __name__, url_prefix='/api/sfi/profile')

CAUSES = ('Motorsports safety', 'Youth education', 'Community support',
          'Accessibility', 'Environment')
PARTICIPATION = ('Volunteer', 'Donate', 'Attend events', 'Share expertise', 'Stay informed')
AVAILABILITY = ('', 'Occasionally', 'Monthly', 'Weekly')
ROLES = ('Member', 'Volunteer', 'Donor', 'Admin', 'User', 'Teacher')


def can_manage_roles(user):
    return user.role == 'Admin' or user_is_admin(user)


def profile_data():
    user = g.current_user
    profile = db.session.get(SfiProfile, user.id)
    preferences = db.session.get(SfiOnboarding, user.id)
    return {
        'name': user.name,
        'uid': user.uid,
        'role': user.role,
        'role_label': 'Member' if user.role == 'User' else user.role,
        'can_manage_roles': can_manage_roles(user),
        'interests': profile.read() if profile else empty_interests(),
        'preferences': preferences.read() if preferences else empty_preferences(),
    }


@sfi_profile_api.after_request
def private_response(response):
    response.headers['Cache-Control'] = 'no-store'
    return response


@sfi_profile_api.route('', methods=['GET'])
@token_required()
def get_profile():
    return jsonify(profile_data())


@sfi_profile_api.route('', methods=['PUT'])
@token_required()
def edit_profile():
    body = request.get_json(silent=True) if request.is_json else None
    if not isinstance(body, dict) or set(body) != {'name'}:
        return jsonify(message='Provide only your display name.'), 400
    name = body['name']
    if not isinstance(name, str) or not 2 <= len(name.strip()) <= 255:
        return jsonify(message='Name must contain 2 to 255 characters.'), 400
    try:
        g.current_user.name = name.strip()
        db.session.commit()
        return jsonify(profile_data())
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(message='Your profile could not be saved. Please try again.'), 500


@sfi_profile_api.route('/roles', methods=['GET'])
@token_required()
def list_roles():
    if not can_manage_roles(g.current_user):
        return jsonify(message='Administrator access required.'), 403
    return jsonify(roles=list(ROLES), users=[
        {'id': user.id, 'name': user.name, 'uid': user.uid, 'role': user.role}
        for user in User.query.order_by(User._uid).all()
    ], current_user_id=g.current_user.id)


@sfi_profile_api.route('/roles/<int:user_id>', methods=['PATCH'])
@token_required()
def edit_role(user_id):
    if not can_manage_roles(g.current_user):
        return jsonify(message='Administrator access required.'), 403
    body = request.get_json(silent=True) if request.is_json else None
    if (not isinstance(body, dict) or set(body) != {'role'}
            or not isinstance(body['role'], str) or body['role'] not in ROLES):
        return jsonify(message='Choose a valid SFI role.'), 400
    user = db.session.get(User, user_id)
    if user is None:
        return jsonify(message='User not found.'), 404
    if user.id == g.current_user.id:
        return jsonify(message='You cannot change your own role.'), 409
    if user.uid.strip().casefold() in {'admin', current_app.config['ADMIN_UID'].strip().casefold()}:
        return jsonify(message='The reserved administrator account role cannot be changed here.'), 409
    try:
        administrator_group = SfiGroup.by_name('administrators')
        members_group = SfiGroup.by_name('members')
        # Startup normally creates these groups; fail closed if it has not.
        if administrator_group is None or members_group is None:
            return jsonify(message='Permission groups are not initialized.'), 503
        user.role = body['role']
        if body['role'] == 'Admin':
            if user not in administrator_group.members.all():
                administrator_group.members.append(user)
        else:
            if user in administrator_group.members.all():
                administrator_group.members.remove(user)
            if user not in members_group.members.all():
                members_group.members.append(user)
        db.session.commit()
        return jsonify(id=user.id, uid=user.uid, role=user.role)
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(message='Role could not be saved. Please try again.'), 500


@sfi_profile_api.route('/interests', methods=['PUT'])
@token_required()
def save_interests():
    # JSON-only PUT requires a CORS preflight for cross-origin browser writes.
    if not request.is_json:
        return jsonify(message='Send quiz answers as JSON.'), 415
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) != set(empty_interests()):
        return jsonify(message='Provide only causes, participation, skills, volunteering, and availability.'), 400

    for field, choices in (('causes', CAUSES), ('participation', PARTICIPATION)):
        values = body[field]
        if (not isinstance(values, list) or len(values) > len(choices)
                or any(not isinstance(value, str) or value not in choices for value in values)
                or len(set(values)) != len(values)):
            return jsonify(message=f'Choose valid, unique {field} options.'), 400
    if not isinstance(body['skills'], str) or len(body['skills']) > 500:
        return jsonify(message='Skills must be text of at most 500 characters.'), 400
    if body['volunteering'] is not None and type(body['volunteering']) is not bool:
        return jsonify(message='Volunteering must be true, false, or null.'), 400
    if not isinstance(body['availability'], str) or body['availability'] not in AVAILABILITY:
        return jsonify(message='Choose a valid availability option.'), 400

    try:
        profile = db.session.get(SfiProfile, g.current_user.id)
        if profile is None:
            profile = SfiProfile(user_id=g.current_user.id)
            db.session.add(profile)
        for field, value in body.items():
            setattr(profile, field, value.strip() if field == 'skills' else value)
        db.session.commit()
        return jsonify(profile_data())
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error('Unable to save SFI interest quiz answers.')
        return jsonify(message='Your answers could not be saved. Please try again.'), 500


def validate_preferences(body):
    """Validate only supplied keys; null explicitly clears an optional field."""
    if not isinstance(body, dict) or set(body) - set(empty_preferences()):
        return None, {'form': 'Provide only recognized preference fields.'}
    values, errors = {}, {}
    for field, value in body.items():
        if field in MULTI_CHOICES:
            value = [] if value is None else value
            choices = MULTI_CHOICES[field]
            if (not isinstance(value, list) or len(value) > len(choices)
                    or any(not isinstance(item, str) or item not in choices for item in value)
                    or len(set(value)) != len(value)):
                errors[field] = 'Choose valid, unique options.'
            elif len(value) > 1 and (
                    (field == 'involvement' and 'prefer_not_to_answer' in value)
                    or (field == 'disciplines' and 'not_applicable' in value)):
                errors[field] = 'Choose this option alone or select your involvement.'
        elif field == 'primary_goal':
            if value is not None and (not isinstance(value, str) or value not in GOALS):
                errors[field] = 'Choose a valid primary goal or leave it unanswered.'
        else:
            value = '' if value is None else value
            if not isinstance(value, str) or len(value) > TEXT_LIMITS[field]:
                errors[field] = f'Use at most {TEXT_LIMITS[field]} characters.'
            elif any(ord(char) < 32 and char not in ('\n', '\r', '\t') for char in value):
                errors[field] = 'Remove unsupported control characters.'
            else:
                value = value.strip()
                if field == 'organization_website' and value and not valid_website(value):
                    errors[field] = 'Enter a full http:// or https:// website without credentials.'
        values[field] = value
    return values, errors


def valid_website(value):
    # Stored as plain text; never fetched, linked to an official record, or
    # used for verification. Reject executable schemes and embedded credentials.
    try:
        url = urlsplit(value)
        host = url.hostname or ''
        try:
            ip_address(host)
            valid_host = True
        except ValueError:
            encoded = host.encode('idna').decode()
            valid_host = len(encoded) <= 253 and all(
                re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?', label)
                for label in encoded.split('.'))
        return bool(url.scheme in ('http', 'https') and valid_host
                    and url.username is None and url.password is None
                    and not re.search(r'[\s\\]', value) and (url.port is None or url.port > 0))
    except (ValueError, UnicodeError):
        return False


@sfi_profile_api.route('/preferences', methods=['PUT', 'PATCH'])
@token_required()
def save_preferences():
    if not request.is_json:
        return jsonify(message='Send preferences as JSON.'), 415
    values, errors = validate_preferences(request.get_json(silent=True))
    if errors:
        return jsonify(message='Please check the highlighted preferences.', errors=errors), 400
    try:
        # Identity comes exclusively from the authenticated session or verified
        # token. No editable identifiers, roles, groups or permissions accepted.
        profile = db.session.get(SfiOnboarding, g.current_user.id)
        if profile is None:
            profile = SfiOnboarding(user_id=g.current_user.id)
            db.session.add(profile)
        profile.answers = {**(profile.read() if profile.answers else empty_preferences()), **values}
        db.session.commit()
        return jsonify(profile_data())
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error('Unable to save SFI onboarding preferences.')
        return jsonify(message='Your preferences could not be saved. Please try again.'), 500

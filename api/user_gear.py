"""
User Gear API — per-user racing equipment tracking + moderation.

Endpoints:
    GET    /api/sfi/gear                — current user's gear
    POST   /api/sfi/gear                — record a gear item (status=pending unless auto-approved)
    DELETE /api/sfi/gear/<id>           — remove a gear item (owner or admin)
    GET    /api/sfi/gear/all            — all gear, optional status/user filters (admin)
    GET    /api/sfi/gear/pending        — pending gear, oldest first (admin)
    PUT    /api/sfi/gear/<id>/review    — approve/reject with notes (admin)
    PATCH  /api/sfi/gear/<id>/status    — legacy status action (admin or can_approve_gear)
"""

from flask import Blueprint, request, jsonify, g, current_app
from flask_restful import Api, Resource
from sqlalchemy.exc import SQLAlchemyError

from __init__ import db
from api.authorize import token_required
from api.auth_utils import admin_required, is_admin
from model.user import User
from model.user_gear import UserGear, ALLOWED_STATUSES, STATUS_APPROVED, STATUS_REJECTED
from model.group import user_has_permission, user_is_admin

user_gear_api = Blueprint('user_gear_api', __name__, url_prefix='/api/sfi')
api = Api(user_gear_api)


def _dict_with_owner(gear):
    owner = db.session.get(User, gear.user_id)
    return gear.to_dict(owner=owner)


def _save_review(gear_id, allowed_statuses, notes_key):
    """Validate both review routes before updating any persisted review fields."""
    gear = db.session.get(UserGear, gear_id)
    if gear is None:
        return {'error': 'not found'}, 404
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return {'error': 'JSON object required'}, 400
    status = body.get('status')
    if not isinstance(status, str) or status.strip().lower() not in allowed_statuses:
        return {'error': f'status must be one of {allowed_statuses}'}, 400
    status = status.strip().lower()
    notes = body.get(notes_key, '')
    if not isinstance(notes, str):
        return {'error': f'{notes_key} must be text'}, 400
    notes = notes.strip()
    if status == STATUS_REJECTED and not notes:
        return {'error': f'{notes_key} are required when rejecting gear'}, 400
    try:
        # Reviewer identity and audit timestamps always come from the server.
        gear.set_status(status, g.current_user.id, notes)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception('Unable to save gear review')
        return {'error': 'Unable to save gear review'}, 500
    return jsonify(_dict_with_owner(gear))


class UserGearAPI:

    class _GearCollection(Resource):
        @token_required()
        def get(self):
            items = UserGear.get_by_user(g.current_user.id)
            return jsonify([item.to_dict() for item in items])

        @token_required()
        def post(self):
            body = request.get_json(silent=True) or {}
            if not (body.get('name') or '').strip():
                return {'error': 'name is required'}, 400

            auto_approve = user_has_permission(g.current_user, 'can_approve_gear')
            gear = UserGear.create(
                user_id=g.current_user.id,
                data=body,
                auto_approve=auto_approve,
                reviewer_id=g.current_user.id if auto_approve else None,
            )
            return jsonify(gear.to_dict())

    class _GearItem(Resource):
        @token_required()
        def delete(self, gear_id):
            gear = UserGear.query.get(gear_id)
            if not gear:
                return {'error': 'not found'}, 404
            is_owner = gear.user_id == g.current_user.id
            is_admin = user_is_admin(g.current_user)
            if not (is_owner or is_admin):
                return {'error': 'forbidden'}, 403
            gear.delete()
            return jsonify({'message': 'deleted'})

    class _GearAll(Resource):
        @admin_required
        def get(self):
            if any(len(request.args.getlist(key)) > 1 for key in ('status', 'user')):
                return {'error': 'Supply each filter only once'}, 400
            status = request.args.get('status')
            if status is not None:
                status = status.strip().lower()
                if status not in ALLOWED_STATUSES:
                    return {'error': f'status must be one of {ALLOWED_STATUSES}'}, 400
            user_id = request.args.get('user')
            if user_id is not None:
                user_id = user_id.strip()
                if (not user_id.isascii() or not user_id.isdecimal() or
                        len(user_id) > 19 or not 0 < int(user_id) <= 2**63 - 1):
                    return {'error': 'user must be a positive integer owner ID'}, 400
                user_id = int(user_id)
            items = UserGear.get_all(status=status, user_id=user_id)
            return jsonify([_dict_with_owner(i) for i in items])

    class _GearPending(Resource):
        @admin_required
        def get(self):
            items = UserGear.get_pending()
            return jsonify([_dict_with_owner(i) for i in items])

    class _GearReview(Resource):
        @admin_required
        def put(self, gear_id):
            return _save_review(gear_id, (STATUS_APPROVED, STATUS_REJECTED), 'notes')

    class _GearStatus(Resource):
        @token_required()
        def patch(self, gear_id):
            if not (is_admin(g.current_user) or
                    user_has_permission(g.current_user, 'can_approve_gear')):
                return {'error': 'forbidden'}, 403
            return _save_review(gear_id, ALLOWED_STATUSES, 'note')

    api.add_resource(_GearCollection, '/gear')
    api.add_resource(_GearItem, '/gear/<int:gear_id>')
    api.add_resource(_GearAll, '/gear/all')
    api.add_resource(_GearPending, '/gear/pending')
    api.add_resource(_GearReview, '/gear/<int:gear_id>/review')
    api.add_resource(_GearStatus, '/gear/<int:gear_id>/status')

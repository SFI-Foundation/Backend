"""Current account only; strict schema and optimistic concurrency prevent overwrites."""
from flask import Blueprint, g, jsonify, request, current_app
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from __init__ import db
from api.authorize import token_required
from model.sfi_settings import SfiSettings

sfi_settings_api = Blueprint('sfi_settings_api', __name__, url_prefix='/api/sfi/settings')
ENUMS = {
    'theme': ('light', 'dark', 'system'),
    'accent': ('red', 'blue', 'green', 'purple', 'orange', 'teal', 'monochrome'),
    'language': ('en', 'es', 'fr', 'de', 'zh-CN', 'ja'),
    'density': ('comfortable', 'compact'), 'corners': ('standard', 'rounded'),
    'textSize': ('system', 'small', 'default', 'large', 'extra-large'),
    'contentWidth': ('standard', 'reading'), 'resultsPerPage': (10, 20, 50),
    'resultDensity': ('comfortable', 'compact'),
}
BOOLEANS = {
    'lineSpacing', 'letterSpacing', 'underlineLinks', 'highContrast', 'enhancedFocus',
    'reducedMotion', 'noTransitions', 'largeTargets', 'readingFont',
    'reducedDistractions', 'showMetadata', 'rememberFilters', 'highlightMatches',
    'pdfIndicators', 'shortcuts',
}


def valid_preferences(values):
    return isinstance(values, dict) and not (set(values) - (set(ENUMS) | BOOLEANS)) and all(
        (type(value) is type(ENUMS[key][0]) and value in ENUMS[key]) if key in ENUMS
        else type(value) is bool for key, value in values.items())


@sfi_settings_api.after_request
def private_response(response):
    response.headers['Cache-Control'] = 'no-store'
    return response


@sfi_settings_api.route('', methods=['GET', 'PATCH'])
@token_required()
def settings():
    if request.method == 'PATCH':
        # Bound decoded JSON as well as Content-Length (including chunked requests).
        if request.content_length and request.content_length > 16384:
            return jsonify(message='Preference request is too large.'), 413
        if not request.is_json:
            return jsonify(message='Send preferences as JSON.'), 415
        if len(request.get_data()) > 16384:
            return jsonify(message='Preference request is too large.'), 413
        body = request.get_json(silent=True)
        if (not isinstance(body, dict) or set(body) != {'version', 'revision', 'preferences'}
                or type(body['version']) is not int or body['version'] != 1
                or type(body['revision']) is not int or body['revision'] < 0
                or not valid_preferences(body['preferences'])):
            return jsonify(message='Invalid preference values or schema.'), 400
    try:
        row = db.session.get(SfiSettings, g.current_user.id)
        if request.method == 'GET':
            return jsonify(version=1, revision=row.revision if row else 0,
                           preferences=row.preferences if row else {})
        revision = row.revision if row else 0
        if body['revision'] != revision:
            return jsonify(message='Preferences changed on another device. Reload before saving.'), 409
        if row is None:
            db.session.add(SfiSettings(user_id=g.current_user.id, revision=1, preferences=body['preferences']))
        else:
            result = db.session.execute(update(SfiSettings).where(
                SfiSettings.user_id == g.current_user.id, SfiSettings.revision == revision
            ).values(preferences={**row.preferences, **body['preferences']}, revision=revision + 1))
            if result.rowcount != 1:
                db.session.rollback()
                return jsonify(message='Preferences changed on another device. Reload before saving.'), 409
        db.session.commit()
        db.session.expire_all()
        row = db.session.get(SfiSettings, g.current_user.id)
        return jsonify(version=1, revision=row.revision, preferences=row.preferences)
    except IntegrityError:
        db.session.rollback()
        return jsonify(message='Preferences changed on another device. Reload before saving.'), 409
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error('Account preferences database operation failed.')
        return jsonify(message='Preferences could not be saved or loaded. Please retry.'), 503

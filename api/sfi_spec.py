"""
SFI Spec API — full CRUD, search, visual part detection, and stats
for the SFI Foundation web modernization project.

Endpoints:
    GET    /api/sfi/specs              — list all specs (optional ?category= filter)
    POST   /api/sfi/specs              — create a new spec (admin)
    GET    /api/sfi/specs/search       — keyword search (?q=)
    GET    /api/sfi/specs/<int:id>     — get a single spec by ID
    PUT    /api/sfi/specs/<int:id>     — update an existing spec (admin)
    DELETE /api/sfi/specs/<int:id>     — delete a spec (admin)
    GET    /api/sfi/categories         — distinct category list
    POST   /api/sfi/detect             — visual part detector
    GET    /api/sfi/stats              — dashboard summary stats
"""

from functools import wraps

from flask import Blueprint, abort, current_app, jsonify, request
from flask_restful import Api, Resource
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError, OperationalError

from __init__ import db
from api.auth_utils import admin_required
from catalog import canonical_specs, find_specs
from model.sfi_spec import SfiSpec


def catalog_ready(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except IntegrityError:
            db.session.rollback()
            return {
                'error': 'Canonical identity already exists or changed concurrently; reload and retry'
            }, 409
        except OperationalError:
            db.session.rollback()
            return {
                'error': 'Catalog database unavailable; verify the Phase 1 migration and database connection'
            }, 503

    return wrapped


sfi_spec_api = Blueprint('sfi_spec_api', __name__, url_prefix='/api/sfi')
api = Api(sfi_spec_api)


@sfi_spec_api.after_request
def catalog_cache_policy(response):
    # A 410 is cacheable by default. Archive/restore and PDF revalidation must
    # take effect immediately, including revoking previously verified actions.
    response.headers['Cache-Control'] = 'no-store'
    return response


def catalog_response(search=False):
    query = ' '.join(request.args.get('q', '').split())
    category = ' '.join(request.args.get('category', '').split())
    if len(query) > 200 or len(category) > 100:
        return {
            'error': 'Query exceeds 200 characters or category exceeds 100 characters'
        }, 400
    if search and not query:
        return {'error': "Missing 'q' query parameter; use /specs to browse"}, 400
    try:
        page = int(request.args.get('page', '1'))
        limit = int(request.args.get('limit', '200'))
        if page < 1 or page > 100000 or not 1 <= limit <= 200:
            raise ValueError
    except ValueError:
        return {'error': 'page must be 1..100000 and limit must be 1..200'}, 400
    items = find_specs(query, category)
    offset = (page - 1) * limit
    selected = items[offset : offset + limit]
    # Preserve array responses by default. Opt into counts and pagination envelope.
    if request.args.get('format') == 'page':
        return jsonify(items=selected, total=len(items), page=page, limit=limit)
    response = jsonify(selected)
    response.headers['X-Total-Count'] = str(len(items))
    return response


class SfiSpecAPI:
    """API resources for SFI spec CRUD, search, detection, and stats."""

    # ── Search ─────────────────────────────────────────────

    class _Search(Resource):
        """GET /api/sfi/specs/search?q=<keyword>"""

        @catalog_ready
        def get(self):
            return catalog_response(search=True)

    # ── List (GET) + Create (POST) on /specs ───────────────

    class _ListCreate(Resource):
        """GET  /api/sfi/specs?category=<name>  — list specs
        POST /api/sfi/specs                  — create a spec
        """

        @catalog_ready
        def get(self):
            return catalog_response()

        @admin_required
        @catalog_ready
        def post(self):
            from catalog_admin import create_spec, validate_input

            data, error = validate_input(request.get_json(silent=True), creating=True)
            if error:
                return {'error': error}, 400
            return create_spec(data)

    class _DetailUpdateDelete(Resource):
        @catalog_ready
        def get(self, id):
            spec = db.session.get(SfiSpec, id)
            if not spec:
                return {'error': 'Spec not found'}, 404
            item = spec.to_dict()
            if item['archived']:
                return {'error': 'Canonical specification archived'}, 410
            return jsonify(item)

        @admin_required
        @catalog_ready
        def put(self, id):
            from catalog_admin import update_spec, validate_input

            data, error = validate_input(request.get_json(silent=True))
            if error:
                return {'error': error}, 400
            return update_spec(id, data)

        @admin_required
        @catalog_ready
        def delete(self, id):
            from catalog_admin import archive_spec

            return archive_spec(id, request.get_json(silent=True), archived=True)

    class _Archived(Resource):
        @admin_required
        @catalog_ready
        def get(self):
            return jsonify(
                [s for s in canonical_specs(include_archived=True) if s['archived']]
            )

    class _Restore(Resource):
        @admin_required
        @catalog_ready
        def post(self, id):
            from catalog_admin import archive_spec

            return archive_spec(id, request.get_json(silent=True), archived=False)

    # ── Categories ─────────────────────────────────────────

    class _Categories(Resource):
        """GET /api/sfi/categories"""

        @catalog_ready
        def get(self):
            return jsonify(
                sorted({c for s in canonical_specs() for c in s['categories']})
            )

    # ── Visual Part Detector ───────────────────────────────

    class _Detect(Resource):
        """POST /api/sfi/detect

        Accepts {"keywords": "helmet, fire"} or {"keywords": ["helmet","fire"]}.
        The frontend sends keywords extracted from a captured car-part
        image and this returns the most relevant specs ranked by match score.
        """

        def post(self):
            # ML mode: route through SfiClassifier if ?mode=ml
            mode = request.args.get('mode', '').strip().lower()
            if mode == 'ml':
                if current_app.config.get(
                    'IS_PRODUCTION'
                ) or not current_app.config.get('SFI_INTERNAL_RESEARCH', False):
                    abort(404)
                from model.sfi_classifier import SfiClassifier

                data = request.get_json()
                if not data or 'keywords' not in data:
                    return {'error': "Missing 'keywords' in request body"}, 400
                keywords = data['keywords']
                if isinstance(keywords, list):
                    keywords = ', '.join(keywords)
                classifier = SfiClassifier.get_instance()
                return jsonify(classifier.predict(keywords.strip()))

            data = request.get_json()
            if not data or 'keywords' not in data:
                return {'error': "Missing 'keywords' in request body"}, 400

            keywords = data['keywords']
            if isinstance(keywords, str):
                keywords = [k.strip() for k in keywords.split(',') if k.strip()]
            if not keywords:
                return {'error': 'Empty keywords'}, 400

            # Build OR filter across all keyword terms
            filters = []
            for kw in keywords:
                like = f'%{kw}%'
                filters.append(SfiSpec.product_name.ilike(like))
                filters.append(SfiSpec.spec_number.ilike(like))
                filters.append(SfiSpec.category.ilike(like))
                filters.append(SfiSpec.subcategory.ilike(like))

            results = SfiSpec.query.filter(or_(*filters)).all()

            # Score results by how many keywords matched
            scored = []
            for spec in results:
                haystack = f'{spec.product_name} {spec.spec_number} {spec.category} {spec.subcategory}'.lower()
                score = sum(1 for kw in keywords if kw.lower() in haystack)
                scored.append((score, spec))
            scored.sort(key=lambda x: x[0], reverse=True)

            return jsonify(
                {
                    'keywords_used': keywords,
                    'results': [s.to_dict() for _, s in scored],
                    'count': len(scored),
                }
            )

    # ── Stats / Dashboard ─────────────────────────────────

    class _Stats(Resource):
        """GET /api/sfi/stats — summary counts for the admin dashboard."""

        @catalog_ready
        def get(self):
            items = canonical_specs()
            cats = sorted({c for s in items for c in s['categories']})
            return jsonify(
                {
                    'total_specs': len(items),
                    'total_categories': len(cats),
                    'total_subcategories': len(
                        {s['subcategory'] for s in items if s['subcategory']}
                    ),
                    'by_category': {
                        c: sum(c in s['categories'] for s in items) for c in cats
                    },
                }
            )

    # ── Register all routes ────────────────────────────────
    api.add_resource(_Search, '/specs/search')
    api.add_resource(_ListCreate, '/specs')
    api.add_resource(_DetailUpdateDelete, '/specs/<int:id>')
    api.add_resource(_Archived, '/specs/archived')
    api.add_resource(_Restore, '/specs/<int:id>/restore')
    api.add_resource(_Categories, '/categories')
    api.add_resource(_Detect, '/detect')
    api.add_resource(_Stats, '/stats')

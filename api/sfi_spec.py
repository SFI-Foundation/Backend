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

from flask import Blueprint, request, jsonify
from sqlalchemy.exc import OperationalError
from functools import wraps
from flask_restful import Api, Resource
from sqlalchemy import or_
from catalog import canonical_specs, find_specs, normalize_number
from __init__ import db
from model.sfi_spec import SfiSpec
from api.auth_utils import admin_required

def catalog_ready(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except OperationalError:
            db.session.rollback()
            return {'error': 'Catalog database unavailable; verify the Phase 1 migration and database connection'}, 503
    return wrapped


sfi_spec_api = Blueprint('sfi_spec_api', __name__, url_prefix='/api/sfi')
api = Api(sfi_spec_api)


def catalog_response(search=False):
    query = ' '.join(request.args.get('q', '').split())
    category = ' '.join(request.args.get('category', '').split())
    if len(query) > 200 or len(category) > 100:
        return {'error': 'Query exceeds 200 characters or category exceeds 100 characters'}, 400
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
    selected = items[offset:offset + limit]
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
        def post(self):
            data = request.get_json(silent=True)
            if not data:
                return {"error": "Missing JSON body"}, 400

            required = ['product_name', 'category', 'spec_number']
            missing = [f for f in required if not str(data.get(f) or '').strip()]
            if missing:
                return {"error": f"Missing required fields: {', '.join(missing)}"}, 400

            number = normalize_number(data['spec_number'])
            if any(normalize_number(s.spec_number) == number for s in SfiSpec.query.all()):
                return {'error': 'Specification already exists; edit its categories instead'}, 409
            spec = SfiSpec(
                product_name=data['product_name'],
                category=data['category'],
                subcategory=data.get('subcategory', ''),
                spec_number=number,
                spec_pdf=data.get('spec_pdf', ''),
                manufacturer_pdf=data.get('manufacturer_pdf', ''),
                products_pdf=data.get('products_pdf', ''),
                effective_date=data.get('effective_date', ''),
            )
            db.session.add(spec)
            db.session.commit()
            return spec.to_dict(), 201

    # ── Detail (GET) + Update (PUT) + Delete (DELETE) on /specs/<id>

    class _DetailUpdateDelete(Resource):
        """Single-spec operations by ID."""
        def get(self, id):
            spec = SfiSpec.query.get(id)
            if not spec:
                return {"error": "Spec not found"}, 404
            return jsonify(spec.to_dict())

        @admin_required
        def put(self, id):
            spec = SfiSpec.query.get(id)
            if not spec:
                return {"error": "Spec not found"}, 404

            data = request.get_json(silent=True)
            if not data:
                return {"error": "Missing JSON body"}, 400

            blank = [f for f in ('product_name', 'category', 'spec_number')
                     if f in data and not str(data[f] or '').strip()]
            if blank:
                return {"error": f"Required fields cannot be empty: {', '.join(blank)}"}, 400

            if 'spec_number' in data:
                target = normalize_number(data['spec_number'])
                if target != normalize_number(spec.spec_number) and any(s.id != spec.id and normalize_number(s.spec_number) == target for s in SfiSpec.query.all()):
                    return {'error': 'Target specification already exists'}, 409
                data['spec_number'] = target

            from model.sfi_spec import SfiCatalogEntry
            if any(field in data for field in ('spec_number', 'effective_date', 'spec_pdf')):
                overlay = db.session.get(SfiCatalogEntry, normalize_number(spec.spec_number))
                if overlay:
                    import json
                    payload = json.loads(overlay.payload)
                    payload['document'] = {'status': 'needs_review'}
                    overlay.payload = json.dumps(payload, sort_keys=True)

            overlay = db.session.get(SfiCatalogEntry, normalize_number(spec.spec_number))
            if overlay and any(field in data for field in ('product_name', 'category')):
                import json
                payload = json.loads(overlay.payload)
                if 'product_name' in data:
                    payload['product_name'] = data['product_name']
                    payload['aliases'] = sorted(set(payload.get('aliases', [])) | {data['product_name']})
                if 'category' in data:
                    payload['categories'] = sorted(set(payload.get('categories', [])) | {data['category']})
                payload['manual_edits'] = sorted(set(payload.get('manual_edits', [])) | set(data))
                overlay.payload = json.dumps(payload, sort_keys=True)

            for field in ['product_name', 'category', 'subcategory',
                          'spec_number', 'spec_pdf', 'manufacturer_pdf',
                          'products_pdf', 'effective_date']:
                if field in data:
                    setattr(spec, field, data[field])

            db.session.commit()
            return jsonify(spec.to_dict())

        @admin_required
        def delete(self, id):
            spec = SfiSpec.query.get(id)
            if not spec:
                return {"error": "Spec not found"}, 404

            db.session.delete(spec)
            db.session.commit()
            return {"message": "Spec deleted"}, 200

    # ── Categories ─────────────────────────────────────────

    class _Categories(Resource):
        """GET /api/sfi/categories"""
        @catalog_ready
        def get(self):
            return jsonify(sorted({c for s in canonical_specs() for c in s['categories']}))

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
                from model.sfi_classifier import SfiClassifier
                data = request.get_json()
                if not data or 'keywords' not in data:
                    return {"error": "Missing 'keywords' in request body"}, 400
                keywords = data['keywords']
                if isinstance(keywords, list):
                    keywords = ', '.join(keywords)
                classifier = SfiClassifier.get_instance()
                return jsonify(classifier.predict(keywords.strip()))

            data = request.get_json()
            if not data or 'keywords' not in data:
                return {"error": "Missing 'keywords' in request body"}, 400

            keywords = data['keywords']
            if isinstance(keywords, str):
                keywords = [k.strip() for k in keywords.split(',') if k.strip()]
            if not keywords:
                return {"error": "Empty keywords"}, 400

            # Build OR filter across all keyword terms
            filters = []
            for kw in keywords:
                like = f"%{kw}%"
                filters.append(SfiSpec.product_name.ilike(like))
                filters.append(SfiSpec.spec_number.ilike(like))
                filters.append(SfiSpec.category.ilike(like))
                filters.append(SfiSpec.subcategory.ilike(like))

            results = SfiSpec.query.filter(or_(*filters)).all()

            # Score results by how many keywords matched
            scored = []
            for spec in results:
                haystack = f"{spec.product_name} {spec.spec_number} {spec.category} {spec.subcategory}".lower()
                score = sum(1 for kw in keywords if kw.lower() in haystack)
                scored.append((score, spec))
            scored.sort(key=lambda x: x[0], reverse=True)

            return jsonify({
                "keywords_used": keywords,
                "results": [s.to_dict() for _, s in scored],
                "count": len(scored),
            })

    # ── Stats / Dashboard ─────────────────────────────────

    class _Stats(Resource):
        """GET /api/sfi/stats — summary counts for the admin dashboard."""
        @catalog_ready
        def get(self):
            items = canonical_specs()
            cats = sorted({c for s in items for c in s['categories']})
            return jsonify({
                'total_specs': len(items), 'total_categories': len(cats),
                'total_subcategories': len({s['subcategory'] for s in items if s['subcategory']}),
                'by_category': {c: sum(c in s['categories'] for s in items) for c in cats},
            })

    # ── Register all routes ────────────────────────────────
    api.add_resource(_Search, '/specs/search')
    api.add_resource(_ListCreate, '/specs')
    api.add_resource(_DetailUpdateDelete, '/specs/<int:id>')
    api.add_resource(_Categories, '/categories')
    api.add_resource(_Detect, '/detect')
    api.add_resource(_Stats, '/stats')

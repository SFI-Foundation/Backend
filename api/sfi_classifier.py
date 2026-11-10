"""
SFI Classifier API — ML-powered part identification endpoints.

Endpoints:
    POST   /api/sfi/classify           — classify a part description using ML
    GET    /api/sfi/classifier/status   — model status and accuracy info
    POST   /api/sfi/classifier/retrain  — admin only: retrain from the current spec database
"""

from functools import wraps
from sfi_config import SpecDataError
from flask import Blueprint, request, jsonify
from flask_restful import Api, Resource
from model.sfi_classifier import SfiClassifier
from api.auth_utils import admin_required

sfi_classifier_api = Blueprint('sfi_classifier_api', __name__, url_prefix='/api/sfi')
api = Api(sfi_classifier_api)


def spec_data_errors(handler):
    """Expose actionable configuration failures without a generic 500 page."""
    @wraps(handler)
    def wrapped(*args, **kwargs):
        try:
            return handler(*args, **kwargs)
        except SpecDataError as exc:
            return {"error": str(exc)}, 503
    return wrapped


class SfiClassifierAPI:

    class _Classify(Resource):
        """POST /api/sfi/classify

        Accepts {"description": "fire resistant racing helmet"}.
        Returns ML predictions ranked by confidence score.
        """
        @spec_data_errors
        def post(self):
            data = request.get_json()
            if not data or 'description' not in data:
                return {"error": "Missing 'description' in request body"}, 400

            description = data['description'].strip()
            if not description:
                return {"error": "Empty description"}, 400

            top_n = data.get('top_n', 10)
            classifier = SfiClassifier.get_instance()
            result = classifier.predict(description, top_n=top_n)

            return jsonify(result)

    class _Status(Resource):
        """GET /api/sfi/classifier/status"""
        @spec_data_errors
        def get(self):
            classifier = SfiClassifier.get_instance()
            return jsonify(classifier.get_status())

    class _Retrain(Resource):
        """POST /api/sfi/classifier/retrain (admin only)"""
        @admin_required
        @spec_data_errors
        def post(self):
            classifier = SfiClassifier.get_instance()
            if not classifier.retrain():
                return {"error": "Retraining failed: no spec data available"}, 500
            return jsonify(classifier.get_status())

    api.add_resource(_Classify, '/classify')
    api.add_resource(_Status, '/classifier/status')
    api.add_resource(_Retrain, '/classifier/retrain')

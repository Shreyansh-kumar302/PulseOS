from flask import Blueprint, jsonify, request

prediction_bp = Blueprint('prediction', __name__)

@prediction_bp.route('/', methods=['GET'])
def get_predictions():
    return jsonify({
        "status": "success",
        "predictions": [
            {"time": "13:00", "congestion_probability": 0.15},
            {"time": "14:00", "congestion_probability": 0.85},
            {"time": "15:00", "congestion_probability": 0.45}
        ]
    }), 200

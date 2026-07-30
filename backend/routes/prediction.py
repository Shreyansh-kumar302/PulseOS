"""
Prediction Routes
=================
HTTP interface for congestion load forecasting.

All business logic is delegated to PredictionService.
This module is intentionally thin: validate -> call service -> return schema.
"""
from typing import List

from fastapi import APIRouter, Depends

from schemas.prediction import PredictionResult
from services.deps import get_prediction_service
from services.prediction_service import PredictionService

router = APIRouter(prefix="/prediction", tags=["Prediction"])


@router.get(
    "/",
    response_model=List[PredictionResult],
    summary="Get tower load predictions",
    description=(
        "Returns congestion load predictions for all monitored towers. "
        "Currently reads from the fixture store. "
        "Will be backed by a real ML model when PredictionEngine is trained."
    ),
)
def get_predictions(
    service: PredictionService = Depends(get_prediction_service),
) -> List[PredictionResult]:
    """Returns congestion load predictions for monitored towers."""
    return service.get_predictions()

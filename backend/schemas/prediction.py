"""
Prediction Schemas
==================
Canonical models for congestion load forecast results.

PredictionResult is produced by PredictionService (which wraps PredictionEngine)
and consumed by:
  - routes/prediction.py   (HTTP surface)
  - services/dashboard_service.py (KPI aggregation)
  - ai/decision_engine.py  (recommendation trigger, future)
  - Scenario Engine         (future: compare baseline vs scenario predictions)
"""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class CongestionRisk(str, Enum):
    """
    Discrete risk tier derived from predicted load percentage.

    Mapping convention (not enforced by this schema, enforced by PredictionService):
        LOW      -> predicted_load_pct < 50
        MEDIUM   -> 50 <= predicted_load_pct < 75
        HIGH     -> 75 <= predicted_load_pct < 90
        CRITICAL -> predicted_load_pct >= 90
    """
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PredictionResult(BaseModel):
    """
    Congestion load forecast for a single tower at a specific future timestamp.

    Produced by PredictionEngine (currently a mock random sampler).
    Extension point: replace PredictionEngine.predict_load() with a real
    ML model (LSTM, XGBoost, etc.) and populate 'confidence' from model output.
    """
    tower_id: str = Field(..., description="ID of the tower this prediction applies to")
    timestamp: datetime = Field(
        ..., description="UTC datetime of the predicted window"
    )
    predicted_load_pct: float = Field(
        ..., ge=0, le=100,
        description="Predicted utilisation as a percentage of tower capacity"
    )
    congestion_risk: CongestionRisk = Field(
        ..., description="Discrete risk tier derived from predicted load"
    )
    confidence: float = Field(
        ..., ge=0, le=1,
        description="Model confidence score (0 = no confidence, 1 = certain)"
    )

    model_config = {"from_attributes": True}

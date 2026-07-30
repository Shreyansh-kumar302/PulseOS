"""
Prediction Service
==================
Orchestration layer for congestion load forecasting.

Sits between routes/prediction.py (HTTP layer) and the AI engines:
  - ai/prediction_engine.py      (load prediction model)
  - core/feature_engineering.py  (feature extraction)

Extension point: when a real ML model (LSTM, XGBoost, etc.) is trained,
replace the fixture-based get_predictions() with a call to
PredictionEngine.predict_load() fed by real telemetry features.
"""
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from ai.prediction_engine import PredictionEngine
from core.feature_engineering import FeatureEngineer
from schemas.prediction import CongestionRisk, PredictionResult

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")


def _parse_utc(ts_str: str) -> datetime:
    """
    Parses an ISO-8601 timestamp string with optional trailing 'Z' suffix.
    Compatible with Python 3.8+ (fromisoformat does not accept 'Z' before 3.11).
    """
    return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))


def _risk_from_load(load_pct: float) -> CongestionRisk:
    """
    Derives a discrete CongestionRisk tier from a predicted load percentage.

    Mapping:
        [0, 50)   -> LOW
        [50, 75)  -> MEDIUM
        [75, 90)  -> HIGH
        [90, 100] -> CRITICAL
    """
    if load_pct >= 90:
        return CongestionRisk.CRITICAL
    if load_pct >= 75:
        return CongestionRisk.HIGH
    if load_pct >= 50:
        return CongestionRisk.MEDIUM
    return CongestionRisk.LOW


class PredictionService:
    """Orchestrates congestion load predictions for monitored towers."""

    def __init__(self) -> None:
        self._engine = PredictionEngine()
        self._feature_engineer = FeatureEngineer()

    def get_predictions(self) -> List[PredictionResult]:
        """
        Returns current tower load predictions loaded from the JSON fixture.

        The fixture (data/prediction.json) is the authoritative source until
        a real ML model is integrated.

        NOTE: CongestionRisk is re-derived from 'predicted_load_pct' using
        the canonical _risk_from_load() mapping, overriding the raw fixture
        string to ensure consistency even if the fixture is edited manually.

        TODO: replace fixture read with PredictionEngine.predict_load()
              fed by real-time telemetry features.
        """
        fixture_path = os.path.join(_DATA_DIR, "prediction.json")
        with open(fixture_path, encoding="utf-8") as fh:
            raw: Dict[str, Any] = json.load(fh)

        results: List[PredictionResult] = []
        for entry in raw["predictions"]:
            load_pct: float = entry["predicted_load_pct"]
            results.append(
                PredictionResult(
                    tower_id=entry["target_tower"],
                    timestamp=_parse_utc(entry["timestamp"]),
                    predicted_load_pct=load_pct,
                    congestion_risk=_risk_from_load(load_pct),
                    confidence=0.85,  # TODO: populate from real model output
                )
            )
        return results

"""
PulseOS Schemas Package
=======================
Single import surface for all canonical Pydantic models.

Import from here, not from individual schema modules:
    from schemas import Tower, NetworkState, PredictionResult
    from schemas import OptimizationRequest, OptimizationResult

Dependency order (no circular imports):
    common schemas (enums, primitives)
      -> tower.py
      -> user.py
      -> network.py       (imports from tower.py)
      -> scenario.py
      -> prediction.py
      -> optimization.py
      -> recommendation.py
      -> dashboard.py     (imports from recommendation.py)
"""
from schemas.tower import (
    NetworkConnection,
    Tower,
    TowerStatus,
    TowerType,
)
from schemas.user import User
from schemas.network import NetworkState
from schemas.scenario import Scenario, ScenarioEventType, ScenarioRequest
from schemas.prediction import CongestionRisk, PredictionResult
from schemas.optimization import OptimizationRequest, OptimizationResult
from schemas.recommendation import ActionType, Recommendation, RecommendationCategory, RecommendationPriority
from schemas.dashboard import DashboardSummary

__all__ = [
    # Tower
    "Tower",
    "TowerType",
    "TowerStatus",
    "NetworkConnection",
    # User
    "User",
    # Network
    "NetworkState",
    # Scenario
    "Scenario",
    "ScenarioRequest",
    "ScenarioEventType",
    # Prediction
    "PredictionResult",
    "CongestionRisk",
    # Optimization
    "OptimizationRequest",
    "OptimizationResult",
    # Recommendation
    "Recommendation",
    "ActionType",
    "RecommendationCategory",
    "RecommendationPriority",
    # Dashboard
    "DashboardSummary",
]

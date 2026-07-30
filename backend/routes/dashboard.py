"""
Dashboard Routes
================
HTTP interface for the operator dashboard KPI aggregation.

Endpoints
---------
GET /dashboard/summary
    Returns a DashboardSummary containing:
    - Tower counts and status breakdown
    - Average predicted load
    - Congestion alert count
    - QoS / QoE scores
    - Actionable recommendations (from DecisionEngine)
    - Executive summary briefing (from ExecutiveSummaryEngine via Gemini)

GET /dashboard/full
    Returns a FullDashboardResponse containing every pipeline output:
    - network        (NetworkState)
    - dashboard      (DashboardSummary — same as /summary)
    - predictions    (List[PredictionResult])
    - optimization   (OptimizationResult — last run from fixture)
    - recommendations (List[Recommendation])
    - executive_summary (str)

All business logic is delegated to the service layer.
This route file is intentionally thin: validate → call service → return schema.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends

from schemas.dashboard import DashboardSummary
from schemas.network import NetworkState
from schemas.optimization import OptimizationResult
from schemas.prediction import PredictionResult
from schemas.recommendation import Recommendation
from services.dashboard_service import DashboardService
from services.deps import (
    get_dashboard_service,
    get_network_service,
    get_optimization_service,
    get_prediction_service,
)
from services.network_service import NetworkService
from services.optimization_service import OptimizationService
from services.prediction_service import PredictionService

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


# ---------------------------------------------------------------------------
# Response schema for /dashboard/full
# ---------------------------------------------------------------------------


class FullDashboardResponse(BaseModel):
    """
    Complete pipeline snapshot for the operator dashboard.

    Aggregates every pipeline stage into a single response so the frontend
    can render the full dashboard from a single API call.
    """
    network: NetworkState = Field(..., description="Current network topology snapshot")
    dashboard: DashboardSummary = Field(..., description="Aggregated KPI summary")
    predictions: List[PredictionResult] = Field(
        default_factory=list,
        description="Per-tower congestion load forecasts",
    )
    optimization: Optional[OptimizationResult] = Field(
        None,
        description="Most recent QUBO optimization result (None if not yet run)",
    )
    recommendations: List[Recommendation] = Field(
        default_factory=list,
        description="Priority-sorted actionable recommendations from DecisionEngine",
    )
    executive_summary: Optional[str] = Field(
        None,
        description="LLM-generated executive briefing (None if Gemini unavailable)",
    )


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


@router.get(
    "/summary",
    response_model=DashboardSummary,
    summary="Get dashboard KPI summary",
    description=(
        "Returns an aggregated KPI snapshot including tower counts, congestion alerts, "
        "QoS/QoE scores, actionable recommendations from the Decision Engine, "
        "and an AI-generated executive briefing from ExecutiveSummaryEngine. "
        "Generated fresh on each request."
    ),
)
def get_dashboard_summary(
    service: DashboardService = Depends(get_dashboard_service),
) -> DashboardSummary:
    """Returns a fully-populated dashboard KPI snapshot."""
    logger.info("GET /dashboard/summary")
    return service.get_summary()


@router.get(
    "/full",
    response_model=FullDashboardResponse,
    summary="Get full pipeline dashboard",
    description=(
        "Returns every pipeline stage in a single response: "
        "NetworkState, DashboardSummary (with recommendations and executive summary), "
        "PredictionResult list, last OptimizationResult, "
        "Recommendation list, and the executive summary string. "
        "Designed for the frontend to render the complete dashboard from one call."
    ),
)
def get_full_dashboard(
    network_service: NetworkService = Depends(get_network_service),
    prediction_service: PredictionService = Depends(get_prediction_service),
    optimization_service: OptimizationService = Depends(get_optimization_service),
    dashboard_service: DashboardService = Depends(get_dashboard_service),
) -> FullDashboardResponse:
    """
    Returns a complete snapshot of every pipeline stage.

    Data sources:
        NetworkService      → network topology
        PredictionService   → per-tower load forecasts
        OptimizationService → last QUBO run result
        DashboardService    → aggregated KPIs + recommendations + executive summary
    """
    logger.info("GET /dashboard/full")

    # DashboardService already runs the full pipeline internally
    dashboard = dashboard_service.get_summary()

    # Fetch individual pipeline outputs for the full response
    network = network_service.get_network_state()
    predictions = prediction_service.get_predictions()

    optimization: Optional[OptimizationResult] = None
    try:
        optimization = optimization_service.get_last_result()
    except Exception as exc:
        logger.warning("GET /dashboard/full: could not fetch last optimization: %s", exc)

    return FullDashboardResponse(
        network=network,
        dashboard=dashboard,
        predictions=predictions,
        optimization=optimization,
        recommendations=dashboard.recent_recommendations,
        executive_summary=dashboard.executive_summary,
    )
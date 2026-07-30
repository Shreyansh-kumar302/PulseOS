"""
Dashboard Schema
================
Aggregated KPI snapshot model for the operator dashboard.

DashboardSummary is the top-level response for GET /dashboard/summary.
It is assembled by DashboardService from:
  - NetworkService           (tower counts)
  - PredictionService        (load averages, congestion alerts)
  - MetricsEngine            (QoS/QoE scores)
  - DecisionEngine           (recent_recommendations)
  - ExecutiveSummaryEngine   (executive_summary via Gemini)
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from schemas.recommendation import Recommendation


class DashboardSummary(BaseModel):
    """
    Aggregated operational KPI snapshot for the network operator dashboard.

    Generated fresh on each request by DashboardService.get_summary().
    """
    generated_at: datetime = Field(
        ..., description="UTC timestamp when this summary was computed"
    )
    total_towers: int = Field(..., ge=0, description="Total towers in the network")
    active_towers: int = Field(..., ge=0, description="Towers in ACTIVE status")
    towers_in_maintenance: int = Field(
        ..., ge=0, description="Towers in MAINTENANCE status"
    )
    avg_load_pct: Optional[float] = Field(
        None, ge=0, le=100,
        description="Average predicted load across all towers (null if no predictions)"
    )
    congestion_alerts: int = Field(
        ..., ge=0,
        description="Count of towers with HIGH or CRITICAL congestion risk"
    )
    qos_score: float = Field(
        ..., ge=0, le=100, description="Quality of Service score (0-100)"
    )
    qoe_score: float = Field(
        ..., ge=1, le=5, description="Quality of Experience MOS score (1-5)"
    )
    recent_recommendations: List[Recommendation] = Field(
        default_factory=list,
        description="Actionable recommendations from the Decision Engine, sorted by priority"
    )
    executive_summary: Optional[str] = Field(
        None,
        description="LLM-generated operational briefing from ExecutiveSummaryEngine (None if Gemini unavailable)"
    )

    model_config = {"from_attributes": True}

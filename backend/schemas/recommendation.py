"""
Recommendation Schema
=====================
Canonical model for an actionable network optimization recommendation.

Produced by DecisionEngine and consumed by:
  - routes/optimize.py          (future: attach to OptimizationResult)
  - services/dashboard_service  (recent_recommendations in DashboardSummary)
  - routes/dashboard.py         (surfaced in the operator dashboard)
  - AI Copilot                  (cited in natural-language explanations)
  - Explainable AI              (XAI reason generation)

Schema evolution
----------------
v2 (current): Added category, title, description, affected_towers,
              reasoning, expected_impact, suggested_actions, timestamp.
              action and target_tower_id are now Optional for compatibility.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ActionType(str, Enum):
    """
    Enumeration of operator-actionable network interventions.

    Extend this list as QuantumSON produces new action categories.
    """
    THROTTLE_NON_ESSENTIAL = "THROTTLE_NON_ESSENTIAL"
    LOAD_BALANCE = "LOAD_BALANCE"
    HANDOVER = "HANDOVER"
    POWER_ADJUST = "POWER_ADJUST"
    FREQUENCY_REALLOC = "FREQUENCY_REALLOC"


class RecommendationPriority(str, Enum):
    """Urgency tier for operator action queue ordering."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RecommendationCategory(str, Enum):
    """
    Operational category of the recommendation.

    Used by the dashboard to group and filter the action queue.
    """
    LOAD_BALANCING = "load_balancing"
    FREQUENCY_REASSIGNMENT = "frequency_reassignment"
    EMERGENCY_DEPLOYMENT = "emergency_deployment"
    ENERGY_SAVING = "energy_saving"
    MAINTENANCE_DISPATCH = "maintenance_dispatch"
    EMERGENCY_REPAIR = "emergency_repair"
    TRAFFIC_REROUTING = "traffic_rerouting"
    CAPACITY_EXPANSION = "capacity_expansion"
    MONITOR_ONLY = "monitor_only"
    NO_ACTION_REQUIRED = "no_action_required"


# ---------------------------------------------------------------------------
# Recommendation model
# ---------------------------------------------------------------------------


class Recommendation(BaseModel):
    """
    An actionable optimization recommendation surfaced to the network operator.

    Produced by DecisionEngine.recommend_actions() from any combination of
    NetworkState, Scenario, PredictionResult, OptimizationResult, and
    DashboardSummary.

    Fields
    ------
    id                Unique identifier, e.g. 'REC-A1B2C3D4'.
    priority          Urgency tier: critical → high → medium → low.
    category          Operational grouping (load_balancing, emergency_repair, …).
    title             Short human-readable label (one line).
    description       Full explanation of what this recommendation addresses.
    affected_towers   Tower IDs this recommendation applies to (empty = network-wide).
    confidence        Decision-engine confidence score [0.0, 1.0].
    reasoning         Machine-generated rationale citing the triggering data.
    expected_impact   Expected operational outcome if the action is taken.
    suggested_actions Ordered list of concrete steps for the operator.
    timestamp         UTC datetime when this recommendation was generated.

    Legacy fields (v1, kept for backward compatibility)
    ---
    action            The specific ActionType, if applicable (Optional).
    reason            Short one-line reason string (mirrors 'reasoning', Optional).
    target_tower_id   Single target tower (prefer 'affected_towers', Optional).
    """

    # --- Identity ---
    id: str = Field(
        ...,
        description="Unique recommendation identifier, e.g. 'REC-A1B2C3D4'",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC datetime when this recommendation was generated",
    )

    # --- Classification ---
    priority: RecommendationPriority = Field(
        ..., description="Urgency tier for action queue ordering"
    )
    category: RecommendationCategory = Field(
        ..., description="Operational category for dashboard grouping"
    )

    # --- Human-readable content ---
    title: str = Field(
        ...,
        max_length=120,
        description="Short one-line label visible in the operator action queue",
    )
    description: str = Field(
        ...,
        description="Full plain-language description of the issue and recommended action",
    )
    reasoning: str = Field(
        ...,
        description=(
            "Machine-generated rationale citing the exact data that triggered "
            "this recommendation (load %, tower IDs, scenario parameters, etc.)"
        ),
    )
    expected_impact: str = Field(
        ...,
        description=(
            "Expected operational outcome if the operator executes this recommendation"
        ),
    )
    suggested_actions: List[str] = Field(
        default_factory=list,
        description=(
            "Ordered list of concrete operational steps for the network engineer"
        ),
    )

    # --- Scope ---
    affected_towers: List[str] = Field(
        default_factory=list,
        description=(
            "Tower IDs this recommendation directly applies to. "
            "Empty list means network-wide scope."
        ),
    )

    # --- Score ---
    confidence: float = Field(
        ...,
        ge=0,
        le=1,
        description="Decision engine confidence score for this recommendation",
    )

    # --- Legacy v1 fields (kept for Copilot and dashboard backward compat) ---
    action: Optional[ActionType] = Field(
        None,
        description="The specific ActionType enum value, if applicable (legacy v1)",
    )
    reason: Optional[str] = Field(
        None,
        description="Short one-line reason string — mirrors 'reasoning' (legacy v1)",
    )
    target_tower_id: Optional[str] = Field(
        None,
        description=(
            "Primary target tower ID — prefer 'affected_towers' in v2 (legacy v1)"
        ),
    )

    model_config = {"from_attributes": True}

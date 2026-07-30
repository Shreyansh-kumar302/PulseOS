"""
Scenario Schemas
================
Request and response models for the Scenario Engine.

ScenarioRequest is the inbound HTTP contract.
Scenario is the fully-identified outbound response, with 'parameters'
populated by ScenarioEngine with the computed simulation effects.
"""
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ScenarioEventType(str, Enum):
    """
    Enumeration of all simulatable network event categories.

    Legacy values (pre-ScenarioEngine) are preserved for backward compatibility.
    Scenario Engine handlers exist for all values in the second group.
    """

    # --- Legacy stubs (pre-engine) --- kept for backward compatibility
    TOWER_OUTAGE = "tower_outage"
    HIGH_LOAD = "high_load"
    CONGESTION_SPIKE = "congestion_spike"
    INTERFERENCE = "interference"
    MAINTENANCE = "maintenance"

    # --- Scenario Engine — crowd / mass-event scenarios ---
    IPL_MATCH = "ipl_match"
    CONCERT = "concert"
    FESTIVAL = "festival"

    # --- Scenario Engine — weather scenarios ---
    HEAVY_RAIN = "heavy_rain"
    CYCLONE = "cyclone"

    # --- Scenario Engine — infrastructure failure scenarios ---
    TOWER_FAILURE = "tower_failure"
    FIBRE_CUT = "fibre_cut"
    POWER_OUTAGE = "power_outage"


class ScenarioRequest(BaseModel):
    """
    Inbound request payload to trigger a network scenario simulation.

    'affected_tower_ids' is optional — leave it empty to let the Scenario
    Engine auto-select appropriate towers from the live NetworkState.
    Atmospheric / city-wide events (HEAVY_RAIN, FESTIVAL) naturally affect
    all towers and do not require manual tower selection.

    'parameters' accepts numeric overrides for any of the scenario's default
    effect multipliers (e.g. {"traffic_multiplier": 5.0}). Unknown keys
    are silently ignored by the engine.
    """
    name: str = Field(..., description="Short human-readable scenario label")
    description: Optional[str] = Field(
        None, description="Detailed description of the simulation intent"
    )
    event_type: ScenarioEventType = Field(
        ..., description="Category of the network event to simulate"
    )
    affected_tower_ids: List[str] = Field(
        default_factory=list,
        description=(
            "IDs of towers to focus the scenario on. "
            "Leave empty to let the engine auto-select from the live network."
        ),
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Numeric overrides for scenario effect multipliers. "
            "Example: {\"traffic_multiplier\": 5.0, \"max_degraded_towers\": 5}"
        ),
    )


class Scenario(BaseModel):
    """
    A fully-executed network scenario — the response from ScenarioEngine.run().

    After ScenarioEngine processes a ScenarioRequest, it populates:
      - 'id':                a unique run identifier
      - 'affected_tower_ids': the towers that were actually affected
      - 'parameters':        the complete SimulationEffect as a flat dict,
                             containing all computed multipliers and summaries

    The 'parameters' dict serves as the simulation result carrier.
    It is intentionally untyped (Dict[str, Any]) so that new effect fields
    can be added to ScenarioEffect without a schema migration.
    """
    id: str = Field(..., description="Unique scenario run identifier, e.g. 'SCN-A1B2C3D4'")
    name: str
    description: Optional[str] = None
    event_type: ScenarioEventType
    affected_tower_ids: List[str] = Field(
        default_factory=list,
        description="IDs of all towers that were affected by this scenario run",
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Computed simulation effects — populated by ScenarioEngine",
    )

    model_config = {"from_attributes": True}

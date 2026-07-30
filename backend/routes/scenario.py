"""
Scenario Routes
===============
HTTP interface for network scenario simulation.

All business logic is delegated to ScenarioService.
This module is intentionally thin: validate -> call service -> return schema.

Extension point: ScenarioService.run_scenario() will delegate to
ScenarioEngine when it is implemented. This route file requires no changes.
"""
from fastapi import APIRouter, Depends

from schemas.scenario import Scenario, ScenarioRequest
from services.deps import get_scenario_service
from services.scenario_service import ScenarioService

router = APIRouter(prefix="/scenario", tags=["Scenario"])


@router.post(
    "/run",
    response_model=Scenario,
    summary="Run a network scenario",
    description=(
        "Executes a network scenario simulation against the current network state. "
        "Supported event types: ipl_match, concert, festival, heavy_rain, "
        "cyclone, tower_failure, fibre_cut, power_outage. "
        "Returns computed effects (traffic_multiplier, latency_increase_ms, "
        "towers_offline, towers_degraded, etc.) in the 'parameters' field."
    ),
)
def run_scenario(
    request: ScenarioRequest,
    service: ScenarioService = Depends(get_scenario_service),
) -> Scenario:
    """Triggers a network scenario simulation."""
    return service.run_scenario(request)
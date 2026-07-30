"""
Scenario Engine
===============
The primary business-logic component for network scenario simulation.

ScenarioEngine.run() is the single public entry point:
  - Input:  ScenarioRequest (what to simulate) + NetworkState (current state)
  - Output: Scenario (schema object with computed effects in .parameters)

The engine does NOT:
  - Predict congestion          →  PredictionEngine's responsibility
  - Run optimisation            →  QuantumSON / OptimizationService's responsibility
  - Persist results             →  future DatabaseConnection responsibility
  - Make LLM calls              →  GeminiService's responsibility (future)

It ONLY:
  - Validates the requested event type has a registered handler
  - Dispatches to the appropriate handler
  - Assembles the final Scenario response object

Dispatch is done via HANDLER_REGISTRY (a plain dict) — no isinstance chains,
no if/elif trees. Adding a new scenario never requires touching this file.
"""
import uuid
from typing import Optional

from schemas.network import NetworkState
from schemas.scenario import Scenario, ScenarioEventType, ScenarioRequest
from scenarios.effects import SCENARIO_DEFAULTS
from scenarios.handlers import HANDLER_REGISTRY


class ScenarioEngine:
    """
    Executes network scenario simulations by transforming a NetworkState
    according to the requested event type.

    Instantiate once per application lifecycle (it carries no mutable state).
    ScenarioService owns the instance and forwards ScenarioRequest + the
    live NetworkState from NetworkService.
    """

    def run(self, request: ScenarioRequest, network_state: NetworkState) -> Scenario:
        """
        Executes a scenario simulation and returns a fully-populated Scenario.

        Workflow:
          1. Look up the handler for request.event_type in HANDLER_REGISTRY.
          2. Retrieve the engineering baseline from SCENARIO_DEFAULTS.
          3. Call the handler — it merges user overrides, selects towers,
             and computes a ScenarioEffect.
          4. Build and return the Scenario schema object.

        Args:
            request:       Validated ScenarioRequest from the HTTP layer.
            network_state: Current NetworkState snapshot (from NetworkService).

        Returns:
            Scenario: Schema object with:
              - id:                  unique run identifier
              - affected_tower_ids:  union of offline + degraded towers
              - parameters:          flat ScenarioEffect dict (all computed values)

        Raises:
            ValueError: If event_type has no registered handler.
                        (Legacy TOWER_OUTAGE / HIGH_LOAD stubs are not
                        handled by the engine — use the newer typed variants.)
        """
        handler = HANDLER_REGISTRY.get(request.event_type)
        if handler is None:
            raise ValueError(
                f"No handler registered for scenario type '{request.event_type.value}'. "
                f"Supported types: {[e.value for e in HANDLER_REGISTRY]}"
            )

        defaults = SCENARIO_DEFAULTS.get(request.event_type, {})

        # Execute the handler — pure function, no side effects
        effect = handler(request, network_state, defaults)

        # Compute the final affected tower list: union of offline + degraded
        affected_tower_ids = _deduplicated_union(
            effect.towers_offline,
            effect.towers_degraded,
        )

        return Scenario(
            id=f"SCN-{uuid.uuid4().hex[:8].upper()}",
            name=request.name,
            description=request.description,
            event_type=request.event_type,
            affected_tower_ids=affected_tower_ids,
            parameters=effect.to_dict(),
        )

    def supported_event_types(self) -> list:
        """
        Returns a list of ScenarioEventType values that have registered handlers.

        Useful for validation endpoints and API documentation.
        """
        return list(HANDLER_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _deduplicated_union(list_a: list, list_b: list) -> list:
    """
    Returns an ordered, deduplicated union of two lists.

    Preserves the order of first appearance (list_a elements first).
    Used to merge towers_offline + towers_degraded without duplicates.
    """
    seen: set = set()
    result: list = []
    for item in list_a + list_b:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result

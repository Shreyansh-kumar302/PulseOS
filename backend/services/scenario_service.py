"""
Scenario Service
================
Orchestration layer for the Scenario Engine.

Sits between routes/scenario.py (HTTP layer) and:
  - scenarios/scenario_engine.py  (simulation logic)
  - services/network_service.py   (live NetworkState source)

Responsibility: fetch the live NetworkState and pass it to the engine.
The route and schema layers require no changes when the engine is updated.
"""
from schemas.scenario import Scenario, ScenarioRequest
from scenarios.scenario_engine import ScenarioEngine
from services.network_service import NetworkService


class ScenarioService:
    """
    Orchestrates network scenario simulation requests.

    Fetches the live NetworkState and delegates simulation to ScenarioEngine.
    NetworkService is injected to allow mocking in tests.
    """

    def __init__(self, network_service: NetworkService = None) -> None:
        self._network = network_service or NetworkService()
        self._engine = ScenarioEngine()

    def run_scenario(self, request: ScenarioRequest) -> Scenario:
        """
        Executes a scenario simulation against the current network state.

        Workflow:
          1. Fetch live NetworkState from NetworkService.
          2. Pass request + state to ScenarioEngine.run().
          3. Return the fully-populated Scenario schema object.

        Args:
            request: Validated ScenarioRequest from the HTTP layer.

        Returns:
            Scenario: Contains computed effects in the 'parameters' field.

        Raises:
            ValueError: If the event_type has no registered handler.
        """
        network_state = self._network.get_network_state()
        return self._engine.run(request, network_state)

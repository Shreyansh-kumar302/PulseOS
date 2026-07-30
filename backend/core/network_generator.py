"""
Network Generator
=================
Generates synthetic telecom network topologies for simulation and testing.

The generator produces a canonical NetworkState object so that all downstream
consumers (DigitalTwin, ScenarioEngine, OptimizationService) receive a
consistently-typed snapshot without any additional mapping.

TODO: Replace the hard-coded stub topology with a parametric generator
      driven by config.NUM_TOWERS, config.MAP_WIDTH, config.MAP_HEIGHT.
      Use a Poisson point process for realistic spatial distribution.
"""
from datetime import datetime, timezone

from config import DEFAULT_TOWER_CAPACITY
from schemas.network import NetworkState
from schemas.tower import NetworkConnection, Tower, TowerStatus, TowerType


class NetworkGenerator:
    """Generates synthetic telecom network topologies and user flows."""

    def generate(self) -> NetworkState:
        """
        Generates a minimal synthetic network topology.

        Returns a canonical NetworkState — not a raw dict. All fields
        conform to the Tower and NetworkConnection Pydantic schemas.

        TODO: Parametric generation using config.NUM_TOWERS / MAP_WIDTH.
        """
        towers = [
            Tower(
                id="T001",
                name="Downtown Macrocell 1",
                type=TowerType.MACRO,
                latitude=12.9716,
                longitude=77.5946,
                capacity=DEFAULT_TOWER_CAPACITY,
                status=TowerStatus.ACTIVE,
                tx_power_dbm=43.0,
                frequency_mhz=1800.0,
            ),
            Tower(
                id="T002",
                name="Suburban Microcell 2",
                type=TowerType.MICRO,
                latitude=12.9726,
                longitude=77.5956,
                capacity=150,
                status=TowerStatus.ACTIVE,
                tx_power_dbm=33.0,
                frequency_mhz=2100.0,
            ),
            Tower(
                id="T003",
                name="Suburban Macrocell 3",
                type=TowerType.MACRO,
                latitude=12.9736,
                longitude=77.5966,
                capacity=DEFAULT_TOWER_CAPACITY,
                status=TowerStatus.MAINTENANCE,
                tx_power_dbm=43.0,
                frequency_mhz=1800.0,
            ),
        ]

        connections = [
            NetworkConnection(
                source_id="T001",
                target_id="T002",
                connection_type="fiber",
                latency_ms=2.5,
                capacity_gbps=10.0,
            ),
            NetworkConnection(
                source_id="T002",
                target_id="T003",
                connection_type="fiber",
                latency_ms=3.0,
                capacity_gbps=5.0,
            ),
        ]

        return NetworkState(
            towers=towers,
            connections=connections,
            generated_at=datetime.now(timezone.utc),
        )

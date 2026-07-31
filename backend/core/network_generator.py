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
        Generates a detailed synthetic mesh network topology of 12 towers.
        """
        towers = [
            Tower(
                id="T001",
                name="Downtown Macrocell 1",
                type=TowerType.MACRO,
                latitude=12.9712,
                longitude=77.5940,
                capacity=DEFAULT_TOWER_CAPACITY,
                status=TowerStatus.ACTIVE,
                tx_power_dbm=43.0,
                frequency_mhz=1800.0,
            ),
            Tower(
                id="T002",
                name="Suburban Microcell 2",
                type=TowerType.MICRO,
                latitude=12.9725,
                longitude=77.5955,
                capacity=150,
                status=TowerStatus.ACTIVE,
                tx_power_dbm=33.0,
                frequency_mhz=2100.0,
            ),
            Tower(
                id="T003",
                name="Suburban Macrocell 3",
                type=TowerType.MACRO,
                latitude=12.9738,
                longitude=77.5968,
                capacity=DEFAULT_TOWER_CAPACITY,
                status=TowerStatus.ACTIVE,
                tx_power_dbm=43.0,
                frequency_mhz=1800.0,
            ),
            Tower(
                id="T004",
                name="Industrial Macrocell 4",
                type=TowerType.MACRO,
                latitude=12.9705,
                longitude=77.5935,
                capacity=300,
                status=TowerStatus.ACTIVE,
                tx_power_dbm=45.0,
                frequency_mhz=1800.0,
            ),
            Tower(
                id="T005",
                name="Downtown Microcell 5",
                type=TowerType.MICRO,
                latitude=12.9718,
                longitude=77.5948,
                capacity=120,
                status=TowerStatus.ACTIVE,
                tx_power_dbm=33.0,
                frequency_mhz=2600.0,
            ),
            Tower(
                id="T006",
                name="Residential Microcell 6",
                type=TowerType.MICRO,
                latitude=12.9742,
                longitude=77.5975,
                capacity=100,
                status=TowerStatus.ACTIVE,
                tx_power_dbm=30.0,
                frequency_mhz=2100.0,
            ),
            Tower(
                id="T007",
                name="Suburban Macrocell 7",
                type=TowerType.MACRO,
                latitude=12.9730,
                longitude=77.5938,
                capacity=DEFAULT_TOWER_CAPACITY,
                status=TowerStatus.ACTIVE,
                tx_power_dbm=43.0,
                frequency_mhz=1800.0,
            ),
            Tower(
                id="T008",
                name="Downtown Macrocell 8",
                type=TowerType.MACRO,
                latitude=12.9722,
                longitude=77.5962,
                capacity=DEFAULT_TOWER_CAPACITY,
                status=TowerStatus.ACTIVE,
                tx_power_dbm=43.0,
                frequency_mhz=1800.0,
            ),
            Tower(
                id="T009",
                name="Commercial Microcell 9",
                type=TowerType.MICRO,
                latitude=12.9708,
                longitude=77.5950,
                capacity=150,
                status=TowerStatus.ACTIVE,
                tx_power_dbm=33.0,
                frequency_mhz=2600.0,
            ),
            Tower(
                id="T010",
                name="Residential Macrocell 10",
                type=TowerType.MACRO,
                latitude=12.9748,
                longitude=77.5942,
                capacity=DEFAULT_TOWER_CAPACITY,
                status=TowerStatus.ACTIVE,
                tx_power_dbm=43.0,
                frequency_mhz=1800.0,
            ),
            Tower(
                id="T011",
                name="TechPark Macrocell 11",
                type=TowerType.MACRO,
                latitude=12.9735,
                longitude=77.5952,
                capacity=350,
                status=TowerStatus.ACTIVE,
                tx_power_dbm=46.0,
                frequency_mhz=1800.0,
            ),
            Tower(
                id="T012",
                name="Highway Microcell 12",
                type=TowerType.MICRO,
                latitude=12.9715,
                longitude=77.5972,
                capacity=100,
                status=TowerStatus.MAINTENANCE,
                tx_power_dbm=33.0,
                frequency_mhz=2100.0,
            ),
        ]

        connections = [
            NetworkConnection(
                source_id="T001",
                target_id="T005",
                connection_type="fiber",
                latency_ms=1.2,
                capacity_gbps=10.0,
            ),
            NetworkConnection(
                source_id="T005",
                target_id="T008",
                connection_type="fiber",
                latency_ms=1.5,
                capacity_gbps=10.0,
            ),
            NetworkConnection(
                source_id="T008",
                target_id="T002",
                connection_type="fiber",
                latency_ms=1.8,
                capacity_gbps=5.0,
            ),
            NetworkConnection(
                source_id="T002",
                target_id="T011",
                connection_type="fiber",
                latency_ms=2.1,
                capacity_gbps=10.0,
            ),
            NetworkConnection(
                source_id="T011",
                target_id="T003",
                connection_type="fiber",
                latency_ms=1.4,
                capacity_gbps=10.0,
            ),
            NetworkConnection(
                source_id="T003",
                target_id="T006",
                connection_type="wireless",
                latency_ms=4.5,
                capacity_gbps=1.0,
            ),
            NetworkConnection(
                source_id="T001",
                target_id="T009",
                connection_type="fiber",
                latency_ms=1.1,
                capacity_gbps=10.0,
            ),
            NetworkConnection(
                source_id="T009",
                target_id="T004",
                connection_type="fiber",
                latency_ms=2.3,
                capacity_gbps=10.0,
            ),
            NetworkConnection(
                source_id="T004",
                target_id="T007",
                connection_type="fiber",
                latency_ms=3.1,
                capacity_gbps=5.0,
            ),
            NetworkConnection(
                source_id="T007",
                target_id="T010",
                connection_type="fiber",
                latency_ms=2.5,
                capacity_gbps=5.0,
            ),
            NetworkConnection(
                source_id="T010",
                target_id="T011",
                connection_type="fiber",
                latency_ms=1.2,
                capacity_gbps=10.0,
            ),
            NetworkConnection(
                source_id="T008",
                target_id="T012",
                connection_type="wireless",
                latency_ms=5.2,
                capacity_gbps=1.0,
            ),
            NetworkConnection(
                source_id="T012",
                target_id="T006",
                connection_type="fiber",
                latency_ms=2.0,
                capacity_gbps=2.5,
            ),
        ]

        return NetworkState(
            towers=towers,
            connections=connections,
            generated_at=datetime.now(timezone.utc),
        )

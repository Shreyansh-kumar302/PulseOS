"""
Network Service
===============
Orchestration layer for network topology operations.

Sits between routes/network.py (HTTP layer) and the core engines:
  - core/network_generator.py  (synthetic topology generation)
  - core/digital_twin.py       (state synchronisation)

Routes must call this service; they must NOT directly instantiate
NetworkGenerator or DigitalTwin.
"""
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict

from core.digital_twin import DigitalTwin
from core.network_generator import NetworkGenerator
from schemas.network import NetworkState
from schemas.tower import NetworkConnection, Tower

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")


class NetworkService:
    """Orchestrates network topology generation and digital twin operations."""

    def __init__(self) -> None:
        self._generator = NetworkGenerator()
        self._twin = DigitalTwin()

    def get_network_state(self) -> NetworkState:
        """
        Returns the current network state loaded from the JSON fixture.

        The fixture (data/network.json) is the authoritative source of
        network state until a real database / telemetry stream is wired in.

        TODO: replace fixture read with a database query (via DatabaseConnection)
              once persistence is introduced.
        """
        fixture_path = os.path.join(_DATA_DIR, "network.json")
        with open(fixture_path, encoding="utf-8") as fh:
            raw: Dict[str, Any] = json.load(fh)

        towers = [Tower(**t) for t in raw["towers"]]
        connections = [NetworkConnection(**c) for c in raw["connections"]]
        return NetworkState(
            towers=towers,
            connections=connections,
            generated_at=datetime.now(timezone.utc),
        )

    def generate_network(self) -> NetworkState:
        """
        Generates a fresh synthetic network topology via NetworkGenerator.

        Returns a canonical NetworkState object — not a raw dict.
        """
        return self._generator.generate()

    def sync_digital_twin(self, telemetry: Dict[str, Any]) -> Dict[str, Any]:
        """
        Pushes real-world telemetry into the DigitalTwin and returns
        the updated state.

        Args:
            telemetry: Raw telemetry dict from the physical network layer.

        Returns:
            The synchronised twin state dict.

        TODO: accept NetworkState instead of a raw dict once the telemetry
              ingestion pipeline is defined.
        """
        return self._twin.sync_state(telemetry)

    def get_twin_state(self) -> Dict[str, Any]:
        """Returns the current DigitalTwin state snapshot."""
        return self._twin.get_state()

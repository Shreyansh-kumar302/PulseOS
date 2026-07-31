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
        Saves the generated state back to network.json to persist it.
        """
        state = self._generator.generate()
        fixture_path = os.path.join(_DATA_DIR, "network.json")
        
        towers_dict = [
            {
                "id": t.id,
                "name": t.name,
                "type": t.type.value if hasattr(t.type, "value") else t.type,
                "latitude": t.latitude,
                "longitude": t.longitude,
                "capacity": t.capacity,
                "status": t.status.value if hasattr(t.status, "value") else t.status,
                "tx_power_dbm": t.tx_power_dbm,
                "frequency_mhz": t.frequency_mhz,
                "current_users": getattr(t, "current_users", 0)
            }
            for t in state.towers
        ]
        connections_dict = [
            {
                "source_id": c.source_id,
                "target_id": c.target_id,
                "connection_type": c.connection_type,
                "latency_ms": c.latency_ms,
                "capacity_gbps": c.capacity_gbps
            }
            for c in state.connections
        ]

        with open(fixture_path, "w", encoding="utf-8") as fh:
            json.dump({
                "towers": towers_dict,
                "connections": connections_dict
            }, fh, indent=2)

        return state

    def sync_digital_twin(self, telemetry: Dict[str, Any]) -> NetworkState:
        """
        Pushes real-world telemetry into the DigitalTwin and updates network.json.
        """
        fixture_path = os.path.join(_DATA_DIR, "network.json")
        if os.path.exists(fixture_path):
            with open(fixture_path, encoding="utf-8") as fh:
                raw: Dict[str, Any] = json.load(fh)
        else:
            raw = {"towers": [], "connections": []}

        # Update towers based on telemetry dict keys (e.g. tower ID)
        for tower in raw.get("towers", []):
            tid = tower.get("id")
            if tid in telemetry:
                t_tel = telemetry[tid]
                if "status" in t_tel:
                    tower["status"] = t_tel["status"].lower()
                if "current_users" in t_tel:
                    tower["current_users"] = t_tel["current_users"]

        # Write back to network.json
        with open(fixture_path, "w", encoding="utf-8") as fh:
            json.dump(raw, fh, indent=2)

        # Call in-memory twin sync
        self._twin.sync_state(telemetry)

        # Build return state
        from schemas.tower import Tower, NetworkConnection
        towers = [Tower(**t) for t in raw["towers"]]
        connections = [NetworkConnection(**c) for c in raw["connections"]]
        return NetworkState(
            towers=towers,
            connections=connections,
            generated_at=datetime.now(timezone.utc),
        )

    def get_twin_state(self) -> Dict[str, Any]:
        """Returns the current DigitalTwin state snapshot."""
        return self._twin.get_state()

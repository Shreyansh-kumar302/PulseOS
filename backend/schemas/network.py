"""
Network Schema
==============
Canonical Pydantic model for a full network topology snapshot.

NetworkState is the primary data contract exchanged between:
  - core/network_generator.py  (producer)
  - core/digital_twin.py       (consumer/mutator)
  - services/network_service.py (orchestrator)
  - routes/network.py           (HTTP surface)
  - scenario engine             (future consumer)
  - optimization engine         (future consumer)
"""
from datetime import datetime, timezone
from typing import List

from pydantic import BaseModel, Field

from schemas.tower import NetworkConnection, Tower


class NetworkState(BaseModel):
    """
    Full point-in-time snapshot of the telecom network topology.

    Contains the complete set of towers and inter-tower connections.
    The 'generated_at' timestamp anchors the snapshot to a wall-clock
    moment, which is critical for the Digital Twin and Scenario Engine.
    """
    towers: List[Tower] = Field(
        default_factory=list,
        description="All base stations in the network"
    )
    connections: List[NetworkConnection] = Field(
        default_factory=list,
        description="Physical links between towers"
    )
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when this snapshot was produced"
    )

    model_config = {"from_attributes": True}

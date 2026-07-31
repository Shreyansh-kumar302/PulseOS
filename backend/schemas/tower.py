"""
Tower Schemas
=============
Canonical Pydantic models for telecom base stations and inter-tower links.

These resolve the three competing representations that existed across:
  - dataset/towers.csv       (latitude/longitude columns, capacity, status)
  - backend/data/network.json (coordinates array, no capacity field)
  - core/network_generator.py (latitude/longitude, edges with capacity_gbps)

Single canonical form: separate latitude/longitude fields, all optional RF
parameters included, connections as NetworkConnection objects.
"""
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TowerType(str, Enum):
    """Physical tier/class of the base station."""
    MACRO = "macro"
    MICRO = "micro"
    PICO = "pico"
    FEMTO = "femto"


class TowerStatus(str, Enum):
    """Operational lifecycle status of the tower."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    MAINTENANCE = "maintenance"


class Tower(BaseModel):
    """
    Canonical representation of a telecom base station (BTS / NodeB / gNB).

    This is the single source of truth for tower data across the backend.
    All services, engines, and routes MUST use this model.
    """
    id: str = Field(..., description="Unique tower identifier, e.g. 'T001'")
    name: Optional[str] = Field(None, description="Human-readable site name")
    type: TowerType = Field(..., description="Tower class/tier")
    latitude: float = Field(..., ge=-90, le=90, description="WGS-84 decimal degrees")
    longitude: float = Field(..., ge=-180, le=180, description="WGS-84 decimal degrees")
    capacity: int = Field(
        default=200, ge=0,
        description="Maximum simultaneous user connections"
    )
    status: TowerStatus = Field(
        default=TowerStatus.ACTIVE,
        description="Current operational lifecycle status"
    )
    tx_power_dbm: Optional[float] = Field(
        None, description="Transmission power in dBm"
    )
    frequency_mhz: Optional[float] = Field(
        None, ge=0, description="Primary operating frequency in MHz"
    )
    current_users: int = Field(
        default=0, ge=0,
        description="Number of active user connections"
    )

    model_config = {"from_attributes": True}


class NetworkConnection(BaseModel):
    """
    Directional physical link between two towers.

    Previously named 'edge' in network_generator.py; canonical term is
    'connection', consistent with the REST API response shape.
    """
    source_id: str = Field(..., description="ID of the originating tower")
    target_id: str = Field(..., description="ID of the destination tower")
    connection_type: str = Field(
        default="fiber",
        description="Physical medium: fiber, microwave, mmwave, etc."
    )
    latency_ms: Optional[float] = Field(
        None, ge=0, description="One-way propagation latency in milliseconds"
    )
    capacity_gbps: Optional[float] = Field(
        None, ge=0, description="Link throughput capacity in Gbps"
    )

    model_config = {"from_attributes": True}

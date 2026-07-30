"""
User Schema
===========
Canonical Pydantic model for a UE (User Equipment) connected to the network.
Derived from dataset/users.csv column definitions.
"""
from pydantic import BaseModel, Field


class User(BaseModel):
    """
    Represents a single connected subscriber device (UE).

    Columns from dataset/users.csv:
        user_id, connected_tower_id, signal_strength, data_usage_mb
    """
    id: str = Field(..., description="Unique user/device identifier, e.g. 'U001'")
    connected_tower_id: str = Field(
        ..., description="ID of the currently serving base station"
    )
    signal_strength: float = Field(
        ..., description="Received signal strength indicator (RSSI) in dBm — typically negative"
    )
    data_usage_mb: float = Field(
        ..., ge=0, description="Session data consumption in megabytes"
    )

    model_config = {"from_attributes": True}

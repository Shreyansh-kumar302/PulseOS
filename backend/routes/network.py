"""
Network Routes
==============
HTTP interface for network topology operations.

All business logic is delegated to NetworkService.
This module is intentionally thin: validate -> call service -> return schema.
"""
from fastapi import APIRouter, Depends

from schemas.network import NetworkState
from services.deps import get_network_service
from services.network_service import NetworkService

router = APIRouter(prefix="/network", tags=["Network"])


@router.get(
    "/state",
    response_model=NetworkState,
    summary="Get current network state",
    description="Returns the current network topology snapshot from the fixture store.",
)
def get_network_state(
    service: NetworkService = Depends(get_network_service),
) -> NetworkState:
    """Returns the current network topology and tower states."""
    return service.get_network_state()


@router.post(
    "/generate",
    response_model=NetworkState,
    summary="Generate synthetic network",
    description="Generates a fresh synthetic network topology via NetworkGenerator.",
)
def generate_network(
    service: NetworkService = Depends(get_network_service),
) -> NetworkState:
    """Generates a fresh synthetic network topology."""
    return service.generate_network()


@router.post(
    "/twin/sync",
    response_model=NetworkState,
    summary="Sync digital twin state",
    description="Updates the digital twin state with telemetry.",
)
def sync_digital_twin(
    telemetry: dict,
    service: NetworkService = Depends(get_network_service),
) -> NetworkState:
    """Syncs real-world telemetry with the digital twin."""
    return service.sync_digital_twin(telemetry)


@router.get(
    "/twin/state",
    summary="Get digital twin state",
    description="Returns the current synchronized digital twin state.",
)
def get_twin_state(
    service: NetworkService = Depends(get_network_service),
) -> dict:
    """Returns the current digital twin state."""
    return service.get_twin_state()

"""
Optimization Routes
===================
HTTP interface for QuantumSON optimization operations.

All business logic is delegated to OptimizationService.
This module is intentionally thin: validate -> call service -> return schema.

Extension point: when QuantumSON is delivered as a microservice, only
OptimizationService changes — this route file remains untouched.
"""
from fastapi import APIRouter, Depends

from schemas.optimization import OptimizationRequest, OptimizationResult
from services.deps import get_optimization_service
from services.optimization_service import OptimizationService

router = APIRouter(prefix="/optimize", tags=["Optimization"])


@router.post(
    "/run",
    response_model=OptimizationResult,
    summary="Run optimization",
    description=(
        "Triggers a QUBO optimization pass via the QuantumSON solver pipeline. "
        "Returns the solution vector and energy value."
    ),
)
def run_optimization(
    request: OptimizationRequest,
    service: OptimizationService = Depends(get_optimization_service),
) -> OptimizationResult:
    """Runs a QuantumSON QUBO optimization pass."""
    return service.run_optimization(request)


@router.get(
    "/last",
    response_model=OptimizationResult,
    summary="Get last optimization result",
    description="Returns the most recent optimization result from the fixture store.",
)
def get_last_result(
    service: OptimizationService = Depends(get_optimization_service),
) -> OptimizationResult:
    """Returns the most recent optimization result."""
    return service.get_last_result()
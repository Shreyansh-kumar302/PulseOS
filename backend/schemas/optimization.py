"""
Optimization Schemas
====================
Request and response models for the QuantumSON optimization pipeline.

OptimizationRequest -> OptimizationService -> QuboFormulation -> QpiAiSolver
                                                                     |
                                                              OptimizationResult

Extension point: when the external QuantumSON engine is integrated, replace
the solver call in OptimizationService with a network call to the QuantumSON
microservice. The request/response schema contract remains the same.
"""
from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, Field


class OptimizationRequest(BaseModel):
    """
    Parameters for triggering a QuantumSON QUBO optimization run.

    TODO: Add 'network_state: NetworkState' field once the optimizer is
    fully wired to real network topology inputs rather than synthetic
    random QUBO matrices.
    """
    num_variables: int = Field(
        default=10, ge=1, le=1000,
        description="QUBO problem dimensionality (number of binary decision variables)"
    )
    objective: str = Field(
        default="minimize_congestion",
        description="Optimization objective label passed to the solver"
        # TODO: convert to Literal["minimize_congestion", "minimize_energy",
        #       "maximize_qos"] once objective list is finalized with QuantumSON team
    )


class OptimizationResult(BaseModel):
    """
    Output of a completed QuantumSON optimization run.

    Consumed by:
      - routes/optimize.py          (HTTP response)
      - services/dashboard_service  (KPI aggregation, future)
      - ai/decision_engine.py       (recommendation context, future)
      - ai/explainer.py             (XAI explanation generation, future)
    """
    run_id: str = Field(..., description="Unique run identifier, e.g. 'OPT-A1B2C3D4'")
    timestamp: datetime = Field(..., description="UTC timestamp of run completion")
    algorithm: str = Field(default="qubo", description="Solver algorithm used")
    solver_status: str = Field(
        ..., description="Terminal status: 'success', 'failed', 'timeout'"
    )
    optimal_energy: float = Field(
        ..., description="QUBO energy value of the best solution found (lower is better)"
    )
    variables_assigned: Dict[str, int] = Field(
        ..., description="Binary variable assignments: {'x_0': 1, 'x_1': 0, ...}"
    )
    duration_ms: Optional[float] = Field(
        None, ge=0, description="Wall-clock solver duration in milliseconds"
    )

    model_config = {"from_attributes": True}

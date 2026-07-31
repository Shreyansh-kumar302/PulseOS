"""
Optimization Service
====================
Orchestration layer for the QuantumSON optimization pipeline.

Sits between routes/optimize.py (HTTP layer) and the optimization engines:
  - optimization/qubo.py    (QUBO matrix formulation)
  - optimization/qpiai.py   (QPIAI quantum/classical solver)

Extension point: when the external QuantumSON engine is delivered,
replace the run_optimization() implementation with an HTTP call to the
QuantumSON microservice. The OptimizationRequest / OptimizationResult
schema contract remains unchanged — only the transport changes.
"""
import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from optimization.qpiai import QpiAiSolver
from optimization.qubo import QuboFormulation
from schemas.optimization import OptimizationRequest, OptimizationResult

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")


def _parse_utc(ts_str: str) -> datetime:
    """Parses ISO-8601 with optional trailing 'Z'. Compatible with Python 3.8+."""
    return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))


class OptimizationService:
    """Orchestrates QUBO formulation and solver execution."""

    def __init__(self) -> None:
        self._qubo = QuboFormulation()
        self._solver = QpiAiSolver()

    def get_last_result(self) -> OptimizationResult:
        """
        Returns the most recent optimization result from the JSON fixture.

        TODO: replace with database query once persistence is introduced.
        """
        fixture_path = os.path.join(_DATA_DIR, "optimization.json")
        with open(fixture_path, encoding="utf-8") as fh:
            raw: Dict[str, Any] = json.load(fh)

        last = raw["optimization_results"][-1]
        return OptimizationResult(
            run_id=last["run_id"],
            timestamp=_parse_utc(last["timestamp"]),
            algorithm=last["algorithm"],
            solver_status=last["solver_status"],
            optimal_energy=last["optimal_energy"],
            variables_assigned=last["variables_assigned"],
        )

    def run_optimization(self, request: OptimizationRequest) -> OptimizationResult:
        """
        Runs a full QUBO optimization pass and returns a typed result.

        Pipeline:
            OptimizationRequest.num_variables
              -> QuboFormulation.build_matrix()
              -> QpiAiSolver.solve()
              -> OptimizationResult

        Args:
            request: Validated OptimizationRequest from the HTTP layer.

        Returns:
            OptimizationResult: Fully-typed, schema-validated result.
        """
        t_start = time.monotonic()

        qubo_matrix = self._qubo.build_matrix(request.num_variables)
        solver_output = self._solver.solve(qubo_matrix)

        duration_ms = round((time.monotonic() - t_start) * 1000, 2)

        return OptimizationResult(
            run_id=f"OPT-{uuid.uuid4().hex[:8].upper()}",
            timestamp=datetime.now(timezone.utc),
            algorithm="qubo",
            solver_status="success" if solver_output["success"] else "failed",
            optimal_energy=solver_output["energy"],
            variables_assigned={
                f"x_{i}": int(v) for i, v in enumerate(solver_output["solution"])
            },
            duration_ms=duration_ms,
        )

"""
Metrics Routes
==============
HTTP interface for QoS/QoE metric computation.

MetricsEngine is a pure stateless computation module. It is safe to use
as a module-level singleton (no DB or network calls). DashboardService
handles the aggregation use-case; this route handles the on-demand
parametric computation use-case.
"""
from fastapi import APIRouter, Depends, Query

from metrics.metrics_engine import MetricsEngine
from services.deps import get_metrics_engine

router = APIRouter(prefix="/metrics", tags=["Metrics"])


@router.get(
    "/qos",
    summary="Compute QoS and QoE",
    description=(
        "Computes Quality of Service (0-100) and Quality of Experience (1-5 MOS) "
        "scores for the specified network parameters."
    ),
)
def compute_qos_metrics(
    delay: float = Query(
        default=5.0, ge=0,
        description="Round-trip latency in milliseconds",
        examples=[5.0],
    ),
    packet_loss: float = Query(
        default=0.01, ge=0, le=1,
        description="Packet loss ratio in the range [0.0, 1.0]",
        examples=[0.01],
    ),
    engine: MetricsEngine = Depends(get_metrics_engine),
) -> dict:
    """Computes QoS and QoE scores for the given network parameters."""
    qos = engine.compute_qos(delay=delay, packet_loss=packet_loss)
    qoe = engine.compute_qoe(qos)
    return {
        "input": {"delay_ms": delay, "packet_loss": packet_loss},
        "qos_score": round(qos, 2),
        "qoe_score": qoe,
    }
"""
FastAPI Dependency Providers
============================
Centralised factory functions for FastAPI's Depends() system.

GeminiService is provided as a cached singleton (``@lru_cache``) because
creating the underlying SDK client on every request would be wasteful.
All other services remain per-request (stateless).

Usage in routes:
    from fastapi import Depends
    from services.deps import get_network_service
    from services.network_service import NetworkService

    @router.get("/state")
    def get_state(service: NetworkService = Depends(get_network_service)):
        return service.get_network_state()

Design notes:
- Services are instantiated fresh per request unless noted otherwise.
- DecisionEngine is fully stateless and safe to recreate per request.
- ExecutiveSummaryEngine wraps GeminiService which IS cached — so the
  underlying SDK client is reused across requests.
- DashboardService depends on NetworkService, PredictionService,
  MetricsEngine, DecisionEngine and ExecutiveSummaryEngine. FastAPI
  resolves the full dependency graph automatically.
- get_summary_engine() returns None (not raises) when GeminiService is
  unavailable so the rest of the dashboard pipeline degrades gracefully.
"""
import logging
from functools import lru_cache
from typing import Optional

from fastapi import Depends

from ai.copilot import Copilot
from ai.decision_engine import DecisionEngine
from ai.summary import ExecutiveSummaryEngine
from metrics.metrics_engine import MetricsEngine
from services.dashboard_service import DashboardService
from services.gemini_service import GeminiService, GeminiServiceError
from services.network_service import NetworkService
from services.optimization_service import OptimizationService
from services.prediction_service import PredictionService
from services.scenario_service import ScenarioService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Singleton providers
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_gemini_service() -> Optional[GeminiService]:
    """
    Provides the GeminiService singleton.

    ``@lru_cache`` ensures the underlying SDK client is initialised only once
    for the process lifetime.

    Returns None if ``GEMINI_API_KEY`` is unset or invalid.
    """
    try:
        return GeminiService()
    except Exception as exc:
        logger.warning("get_gemini_service(): GeminiService initialization failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Stateless per-request providers
# ---------------------------------------------------------------------------


def get_metrics_engine() -> MetricsEngine:
    """Provides a MetricsEngine instance (stateless, safe to recreate per request)."""
    return MetricsEngine()


@lru_cache(maxsize=1)
def get_network_service() -> NetworkService:
    """Provides a cached NetworkService singleton instance."""
    return NetworkService()


def get_prediction_service() -> PredictionService:
    """Provides a PredictionService instance."""
    return PredictionService()


def get_optimization_service() -> OptimizationService:
    """Provides an OptimizationService instance."""
    return OptimizationService()


def get_scenario_service(
    network_service: NetworkService = Depends(get_network_service),
) -> ScenarioService:
    """Provides a ScenarioService with its NetworkService dependency resolved."""
    return ScenarioService(network_service=network_service)


def get_decision_engine() -> DecisionEngine:
    """
    Provides a DecisionEngine instance.

    DecisionEngine is fully deterministic and stateless — safe to recreate
    on every request.  No GeminiService dependency.
    """
    return DecisionEngine()


def get_summary_engine(
    gemini_service: Optional[GeminiService] = Depends(get_gemini_service),
) -> Optional[ExecutiveSummaryEngine]:
    """
    Provides an ExecutiveSummaryEngine backed by the GeminiService singleton.

    Returns ``None`` (rather than raising) when GeminiService is unavailable
    so that routes and services can degrade gracefully — the dashboard still
    works without an AI summary if Gemini is unreachable.
    """
    if gemini_service is None:
        return None
    try:
        return ExecutiveSummaryEngine(gemini_service=gemini_service)
    except GeminiServiceError as exc:
        logger.warning(
            "get_summary_engine(): GeminiService unavailable — "
            "ExecutiveSummaryEngine will not be provided. Cause: %s", exc
        )
        return None


def get_dashboard_service(
    network_service: NetworkService = Depends(get_network_service),
    prediction_service: PredictionService = Depends(get_prediction_service),
    metrics_engine: MetricsEngine = Depends(get_metrics_engine),
    decision_engine: DecisionEngine = Depends(get_decision_engine),
    summary_engine: Optional[ExecutiveSummaryEngine] = Depends(get_summary_engine),
) -> DashboardService:
    """
    Provides a DashboardService with its full dependency graph resolved.

    FastAPI resolves all five sub-dependencies independently and injects
    them, enabling full testability with mock services.

    summary_engine may be None if GeminiService is unavailable — DashboardService
    handles this gracefully by omitting the executive_summary field.
    """
    return DashboardService(
        network_service=network_service,
        prediction_service=prediction_service,
        metrics_engine=metrics_engine,
        decision_engine=decision_engine,
        summary_engine=summary_engine,
    )


def get_copilot(
    gemini_service: Optional[GeminiService] = Depends(get_gemini_service),
) -> Copilot:
    """
    Provides a Copilot instance with GeminiService injected.

    The Copilot is intentionally NOT cached with ``@lru_cache`` because it
    maintains per-session conversation history.  Each HTTP request receives a
    fresh, stateless Copilot instance.

    For long-running sessions (e.g. WebSocket), instantiate Copilot once at
    the session layer and call its methods directly, bypassing this provider.
    """
    return Copilot(gemini_service=gemini_service)

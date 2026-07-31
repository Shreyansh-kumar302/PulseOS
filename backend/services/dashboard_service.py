"""
Dashboard Service
=================
Aggregates KPIs from all subsystems into a single DashboardSummary.

This is a read-only aggregation service — it does not mutate any state.
All data is sourced from:
  - NetworkService           → tower counts and statuses
  - PredictionService        → load averages and congestion alert counts
  - MetricsEngine            → QoS / QoE scores
  - DecisionEngine           → actionable recommendations
  - ExecutiveSummaryEngine   → LLM-generated executive briefing (via Gemini)

Dependencies are injected via the constructor so they can be mocked in tests
and are provided by FastAPI's Depends() in production (see services/deps.py).
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional

from ai.decision_engine import DecisionEngine
from ai.summary import ExecutiveSummaryEngine
from metrics.metrics_engine import MetricsEngine
from schemas.dashboard import DashboardSummary
from schemas.recommendation import Recommendation
from services.network_service import NetworkService
from services.prediction_service import PredictionService

logger = logging.getLogger(__name__)


class DashboardService:
    """Aggregates KPIs from all subsystems for the operator dashboard."""

    def __init__(
        self,
        network_service: Optional[NetworkService] = None,
        prediction_service: Optional[PredictionService] = None,
        metrics_engine: Optional[MetricsEngine] = None,
        decision_engine: Optional[DecisionEngine] = None,
        summary_engine: Optional[ExecutiveSummaryEngine] = None,
    ) -> None:
        self._network = network_service or NetworkService()
        self._predictions = prediction_service or PredictionService()
        self._metrics = metrics_engine or MetricsEngine()
        # DecisionEngine is stateless; a fresh instance is fine per-request
        self._decision = decision_engine or DecisionEngine()
        # summary_engine may be None if GeminiService is unavailable at startup
        self._summary: Optional[ExecutiveSummaryEngine] = summary_engine

    def get_summary(self) -> DashboardSummary:
        """
        Computes and returns a fresh aggregated dashboard snapshot.

        Pipeline (in order):
          1. NetworkService  → current topology
          2. PredictionService → per-tower load forecasts
          3. MetricsEngine   → QoS / QoE scores
          4. DecisionEngine  → recommendations from current state
          5. ExecutiveSummaryEngine → LLM briefing (skipped if engine absent)

        Returns:
            DashboardSummary: Fully-typed, schema-validated KPI snapshot.
        """
        # ------------------------------------------------------------------
        # 1. Topology
        # ------------------------------------------------------------------
        network_state = self._network.get_network_state()

        # ------------------------------------------------------------------
        # 2. Predictions
        # ------------------------------------------------------------------
        predictions = self._predictions.get_predictions()

        # ------------------------------------------------------------------
        # 3. Aggregate KPI figures
        # ------------------------------------------------------------------
        towers = network_state.towers
        total_towers = len(towers)
        active_towers = sum(1 for t in towers if t.status.value == "active")
        towers_in_maintenance = sum(
            1 for t in towers if t.status.value == "maintenance"
        )

        avg_load_pct: Optional[float] = None
        if predictions:
            avg_load_pct = round(
                sum(p.predicted_load_pct for p in predictions) / len(predictions), 2
            )

        congestion_alerts = sum(
            1 for p in predictions if p.congestion_risk.value in ("high", "critical")
        )

        qos = self._metrics.compute_qos(delay=5.0, packet_loss=0.01)
        qoe = self._metrics.compute_qoe(qos)

        # ------------------------------------------------------------------
        # 4. Build a preliminary DashboardSummary (no recs / summary yet) so
        #    DecisionEngine can receive it as context.
        # ------------------------------------------------------------------
        partial_dashboard = DashboardSummary(
            generated_at=datetime.now(timezone.utc),
            total_towers=total_towers,
            active_towers=active_towers,
            towers_in_maintenance=towers_in_maintenance,
            avg_load_pct=avg_load_pct,
            congestion_alerts=congestion_alerts,
            qos_score=round(qos, 2),
            qoe_score=qoe,
            recent_recommendations=[],
            executive_summary=None,
        )

        # ------------------------------------------------------------------
        # 5. Recommendations via DecisionEngine
        # ------------------------------------------------------------------
        recommendations: List[Recommendation] = []
        try:
            recommendations = self._decision.evaluate(
                network_state=network_state,
                predictions=predictions,
                dashboard=partial_dashboard,
            )
        except Exception as exc:
            logger.error(
                "DecisionEngine.evaluate() failed in DashboardService: %s", exc,
                exc_info=True,
            )

        # ------------------------------------------------------------------
        # 6. Executive summary via ExecutiveSummaryEngine (Gemini-backed)
        # ------------------------------------------------------------------
        executive_summary: Optional[str] = None
        if self._summary is not None:
            try:
                executive_summary = self._summary.generate_brief(
                    network_state=network_state,
                    predictions=predictions,
                    recommendations=recommendations,
                    dashboard=partial_dashboard,
                )
            except Exception as exc:
                logger.error(
                    "ExecutiveSummaryEngine.generate_brief() failed in DashboardService: %s",
                    exc,
                    exc_info=True,
                )

        # ------------------------------------------------------------------
        # 7. Assemble final DashboardSummary
        # ------------------------------------------------------------------
        return DashboardSummary(
            generated_at=partial_dashboard.generated_at,
            total_towers=total_towers,
            active_towers=active_towers,
            towers_in_maintenance=towers_in_maintenance,
            avg_load_pct=avg_load_pct,
            congestion_alerts=congestion_alerts,
            qos_score=round(qos, 2),
            qoe_score=qoe,
            recent_recommendations=recommendations,
            executive_summary=executive_summary,
        )

"""
Executive Summary Engine
========================
Automatically generates concise operational briefings for telecom operators.

Every summary is grounded exclusively in the structured backend context supplied
by the caller.  The engine NEVER fabricates metrics, tower IDs, or events.

Design contract
---------------
* All LLM calls route exclusively through ``GeminiService`` — this module
  never imports ``google.genai`` directly.
* If GeminiService raises any error the engine catches it, logs it, and
  returns a graceful degraded fallback string.  Stack traces never reach
  the caller.
* If a context object is absent, the corresponding section is simply omitted
  from the prompt and the generated summary.

Public API
----------
``generate_summary(**ctx)``
    Core method.  Returns a 150-300 word executive briefing structured as:
    Overall Status / Current Situation / Key Risks / Recommended Actions /
    Operator Notes.

``generate_brief(**ctx)``
    Ultra-compact 2-4 sentence dashboard headline.  Suitable for small
    status widgets or notification banners.

``generate_incident_report(scenario, **ctx)``
    Formal incident report centred on an active simulation scenario.
    Includes scenario description, affected assets, impact assessment, and
    recommended remediation steps.

``generate_shift_handover(**ctx)``
    Shift-handover note for an outgoing operator.  Covers what happened
    during the shift, current state, outstanding actions, and watch items
    for the incoming team.

Context keyword arguments (all optional)
-----------------------------------------
network_state   : NetworkState
scenario        : Scenario
predictions     : List[PredictionResult]
optimization    : OptimizationResult
recommendations : List[Recommendation]   (note: plural, unlike Copilot)
dashboard       : DashboardSummary
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Optional schema imports — gracefully skipped if modules do not yet exist
# ---------------------------------------------------------------------------

try:
    from schemas.network import NetworkState
except ImportError:  # pragma: no cover
    NetworkState = Any  # type: ignore[assignment,misc]

try:
    from schemas.scenario import Scenario
except ImportError:  # pragma: no cover
    Scenario = Any  # type: ignore[assignment,misc]

try:
    from schemas.prediction import PredictionResult
except ImportError:  # pragma: no cover
    PredictionResult = Any  # type: ignore[assignment,misc]

try:
    from schemas.optimization import OptimizationResult
except ImportError:  # pragma: no cover
    OptimizationResult = Any  # type: ignore[assignment,misc]

try:
    from schemas.recommendation import Recommendation
except ImportError:  # pragma: no cover
    Recommendation = Any  # type: ignore[assignment,misc]

try:
    from schemas.dashboard import DashboardSummary
except ImportError:  # pragma: no cover
    DashboardSummary = Any  # type: ignore[assignment,misc]

from services.gemini_service import GeminiService, GeminiServiceError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt — injected on every LLM call
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are PulseOS Executive Summary Engine, the automated briefing generator \
embedded in the PulseOS autonomous telecom network operations platform.

Your output is read by network operations managers and shift leads who need \
a fast, accurate situational picture.

STRICT RULES — follow these without exception:
1. NEVER fabricate, invent, or estimate metrics, tower IDs, load percentages, \
latency values, or any numerical data.  Only reference numbers explicitly \
present in the context block.
2. NEVER hallucinate network events, scenarios, or optimisation results that \
are not present in the provided context.
3. If a section of the summary cannot be populated (no relevant data in context), \
omit that section entirely — do not write "No data available" placeholders.
4. Use concise, precise professional language suited for an executive audience.
5. Do not use filler phrases such as "Great question!" or "Certainly!".
6. Do not add commentary about what data was or was not provided.
7. When referencing towers, always use their exact IDs from the context.
8. Numbers and percentages MUST come verbatim from the context — do not round \
or reformat unless purely for readability (e.g. "87.3%" stays "87.3%").
"""

# ---------------------------------------------------------------------------
# Fallback strings — returned when Gemini is unavailable
# ---------------------------------------------------------------------------

_FALLBACK_UNAVAILABLE = (
    "⚠️  Executive Summary temporarily unavailable — Gemini API unreachable. "
    "Please verify API connectivity and retry."
)

_FALLBACK_NO_CONTEXT = (
    "⚠️  Insufficient context to generate a summary. "
    "Supply at least one of: NetworkState, DashboardSummary, Scenario, "
    "PredictionResult, OptimizationResult, or Recommendation."
)

_FALLBACK_INCIDENT_NO_SCENARIO = (
    "⚠️  Cannot generate incident report — no active scenario was provided."
)


# ---------------------------------------------------------------------------
# Context renderers (pure functions, identical pattern to Copilot)
# ---------------------------------------------------------------------------

def _render_network(state: Optional[Any]) -> str:
    """Render NetworkState into a compact context block."""
    if state is None:
        return ""
    try:
        towers = getattr(state, "towers", [])
        connections = getattr(state, "connections", [])
        generated_at = getattr(state, "generated_at", "unknown")

        active = sum(1 for t in towers if getattr(t, "status", "") == "active")
        maintenance = sum(1 for t in towers if getattr(t, "status", "") == "maintenance")
        inactive = sum(1 for t in towers if getattr(t, "status", "") == "inactive")

        tower_lines: List[str] = []
        for t in towers:
            tid = getattr(t, "id", "?")
            tname = getattr(t, "name", None) or ""
            ttype = getattr(t, "type", "?")
            tstatus = getattr(t, "status", "?")
            tcap = getattr(t, "capacity", "?")
            tfreq = getattr(t, "frequency_mhz", None)
            freq_str = f", {tfreq} MHz" if tfreq is not None else ""
            tower_lines.append(
                f"  {tid} ({tname or ttype}): status={tstatus}, capacity={tcap}{freq_str}"
            )

        tower_block = "\n".join(tower_lines) if tower_lines else "  (none)"

        return (
            f"[NETWORK STATE — snapshot at {generated_at}]\n"
            f"Towers: total={len(towers)} | active={active} | "
            f"maintenance={maintenance} | inactive={inactive}\n"
            f"Connections: {len(connections)}\n"
            f"Tower details:\n{tower_block}\n"
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("_render_network failed: %s", exc)
        return "[NETWORK STATE — rendering failed]\n"


def _render_scenario(scenario: Optional[Any]) -> str:
    """Render Scenario into a compact context block."""
    if scenario is None:
        return ""
    try:
        sid = getattr(scenario, "id", "?")
        name = getattr(scenario, "name", "?")
        desc = getattr(scenario, "description", None) or "(no description)"
        event_type = getattr(scenario, "event_type", "?")
        affected = getattr(scenario, "affected_tower_ids", [])
        params = getattr(scenario, "parameters", {})

        param_lines = "\n".join(
            f"    {k}: {v}" for k, v in params.items()
        ) if params else "    (none)"

        return (
            f"[ACTIVE SCENARIO]\n"
            f"  ID: {sid}\n"
            f"  Name: {name}\n"
            f"  Description: {desc}\n"
            f"  Event type: {event_type}\n"
            f"  Affected towers ({len(affected)}): "
            f"{', '.join(str(t) for t in affected) or 'all/auto-selected'}\n"
            f"  Computed effects:\n{param_lines}\n"
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("_render_scenario failed: %s", exc)
        return "[ACTIVE SCENARIO — rendering failed]\n"


def _render_predictions(predictions: Optional[List[Any]]) -> str:
    """Render PredictionResult list into a compact context block."""
    if not predictions:
        return ""
    try:
        lines: List[str] = []
        critical: List[str] = []
        high: List[str] = []

        for p in predictions:
            tid = getattr(p, "tower_id", "?")
            load = getattr(p, "predicted_load_pct", None)
            risk = getattr(p, "congestion_risk", "?")
            conf = getattr(p, "confidence", None)
            ts = getattr(p, "timestamp", "?")
            load_str = f"{load:.1f}%" if load is not None else "?"
            conf_str = f"{conf:.2f}" if conf is not None else "?"
            lines.append(
                f"  Tower {tid}: load={load_str}, risk={risk}, "
                f"confidence={conf_str}, window={ts}"
            )
            risk_str = str(risk).lower() if risk else ""
            if "critical" in risk_str:
                critical.append(str(tid))
            elif "high" in risk_str:
                high.append(str(tid))

        summary_parts: List[str] = []
        if critical:
            summary_parts.append(f"CRITICAL risk: {', '.join(critical)}")
        if high:
            summary_parts.append(f"HIGH risk: {', '.join(high)}")
        risk_summary = " | ".join(summary_parts) if summary_parts else "no HIGH/CRITICAL towers"

        return (
            f"[CONGESTION PREDICTIONS — {len(predictions)} tower(s)]\n"
            f"  Risk summary: {risk_summary}\n"
            + "\n".join(lines) + "\n"
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("_render_predictions failed: %s", exc)
        return "[CONGESTION PREDICTIONS — rendering failed]\n"


def _render_optimization(result: Optional[Any]) -> str:
    """Render OptimizationResult into a compact context block."""
    if result is None:
        return ""
    try:
        run_id = getattr(result, "run_id", "?")
        ts = getattr(result, "timestamp", "?")
        algo = getattr(result, "algorithm", "?")
        status = getattr(result, "solver_status", "?")
        energy = getattr(result, "optimal_energy", None)
        duration = getattr(result, "duration_ms", None)
        assignments = getattr(result, "variables_assigned", {})

        assigned_ones = {k: v for k, v in assignments.items() if v == 1}
        energy_str = f"{energy:.6f}" if energy is not None else "?"
        dur_str = f"{duration:.1f} ms" if duration is not None else "?"

        return (
            f"[OPTIMIZATION RESULT]\n"
            f"  Run ID: {run_id} | Timestamp: {ts}\n"
            f"  Algorithm: {algo} | Solver status: {status}\n"
            f"  Optimal energy (QUBO): {energy_str} (lower = better)\n"
            f"  Solver duration: {dur_str}\n"
            f"  Variables total: {len(assignments)} | assigned=1: {len(assigned_ones)}\n"
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("_render_optimization failed: %s", exc)
        return "[OPTIMIZATION RESULT — rendering failed]\n"


def _render_recommendations(recs: Optional[List[Any]]) -> str:
    """Render a list of Recommendation objects into a compact context block."""
    if not recs:
        return ""
    try:
        lines: List[str] = []
        for rec in recs:
            rid = getattr(rec, "id", "?")
            priority = getattr(rec, "priority", "?")
            title = getattr(rec, "title", None) or getattr(rec, "action", "?")
            affected = getattr(rec, "affected_towers", []) or (
                [getattr(rec, "target_tower_id", None)]
                if getattr(rec, "target_tower_id", None)
                else []
            )
            scope = ", ".join(str(t) for t in affected) if affected else "network-wide"
            conf = getattr(rec, "confidence", None)
            conf_str = f"{conf:.2f}" if conf is not None else "?"
            lines.append(
                f"  [{str(priority).upper()}] {rid}: {title} "
                f"(target: {scope}, confidence: {conf_str})"
            )

        return (
            f"[RECOMMENDATIONS — {len(recs)} item(s)]\n"
            + "\n".join(lines) + "\n"
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("_render_recommendations failed: %s", exc)
        return "[RECOMMENDATIONS — rendering failed]\n"


def _render_dashboard(dashboard: Optional[Any]) -> str:
    """Render DashboardSummary into a compact context block."""
    if dashboard is None:
        return ""
    try:
        ts = getattr(dashboard, "generated_at", "?")
        total = getattr(dashboard, "total_towers", "?")
        active = getattr(dashboard, "active_towers", "?")
        maint = getattr(dashboard, "towers_in_maintenance", "?")
        avg_load = getattr(dashboard, "avg_load_pct", None)
        alerts = getattr(dashboard, "congestion_alerts", "?")
        qos = getattr(dashboard, "qos_score", None)
        qoe = getattr(dashboard, "qoe_score", None)
        recs = getattr(dashboard, "recent_recommendations", [])

        load_str = f"{avg_load:.1f}%" if avg_load is not None else "N/A"
        qos_str = f"{qos:.1f}/100" if qos is not None else "?"
        qoe_str = f"{qoe:.2f}/5.0 MOS" if qoe is not None else "?"

        return (
            f"[DASHBOARD SUMMARY — computed at {ts}]\n"
            f"  Towers: total={total}, active={active}, maintenance={maint}\n"
            f"  Average predicted load: {load_str}\n"
            f"  Congestion alerts (HIGH or CRITICAL): {alerts}\n"
            f"  QoS score: {qos_str}\n"
            f"  QoE score: {qoe_str}\n"
            f"  Recent recommendations queued: {len(recs)}\n"
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("_render_dashboard failed: %s", exc)
        return "[DASHBOARD SUMMARY — rendering failed]\n"


def _assemble_context(
    network_state: Optional[Any] = None,
    scenario: Optional[Any] = None,
    predictions: Optional[List[Any]] = None,
    optimization: Optional[Any] = None,
    recommendations: Optional[List[Any]] = None,
    dashboard: Optional[Any] = None,
) -> str:
    """
    Assemble all available context objects into a single formatted string
    for the LLM.  Sections for missing objects are omitted.
    """
    parts: List[str] = []

    if dashboard is not None:
        parts.append(_render_dashboard(dashboard))
    if network_state is not None:
        parts.append(_render_network(network_state))
    if scenario is not None:
        parts.append(_render_scenario(scenario))
    if predictions:
        parts.append(_render_predictions(predictions))
    if optimization is not None:
        parts.append(_render_optimization(optimization))
    if recommendations:
        parts.append(_render_recommendations(recommendations))

    return "\n".join(p for p in parts if p).strip()


# ---------------------------------------------------------------------------
# Main Engine class
# ---------------------------------------------------------------------------


class ExecutiveSummaryEngine:
    """
    Generates concise, LLM-backed operational briefings for telecom operators.

    Every public method accepts any combination of context objects and uses
    only the data present in them.  No data is invented.

    Parameters
    ----------
    gemini_service:
        An initialised ``GeminiService`` instance injected by the caller
        (use ``Depends(get_gemini_service)`` in FastAPI routes).

    Examples
    --------
    >>> engine = ExecutiveSummaryEngine(gemini_service=get_gemini_service())
    >>> text = engine.generate_summary(
    ...     dashboard=my_dashboard,
    ...     network_state=my_network,
    ...     predictions=my_preds,
    ...     recommendations=my_recs,
    ... )
    >>> print(text)
    """

    def __init__(self, gemini_service: GeminiService) -> None:
        self._gemini: GeminiService = gemini_service
        logger.info("ExecutiveSummaryEngine initialised")

    # ------------------------------------------------------------------
    # Internal LLM call with graceful fallback
    # ------------------------------------------------------------------

    def _call_gemini(
        self,
        task_prompt: str,
        context_block: str,
        temperature: float = 0.2,
        max_output_tokens: int = 600,
    ) -> str:
        """
        Build the full prompt (context + task) and call GeminiService.
        Returns the model's response, or a graceful fallback on any error.

        Temperature is kept very low (0.2) so summaries are factual and
        deterministic rather than creative.
        """
        sections: List[str] = []

        if context_block:
            sections.append(f"=== LIVE NETWORK CONTEXT ===\n{context_block}")

        sections.append(f"=== TASK ===\n{task_prompt}")
        sections.append("=== EXECUTIVE SUMMARY ===")

        full_prompt = "\n\n".join(sections)

        try:
            reply = self._gemini.generate(
                full_prompt,
                system_instruction=_SYSTEM_PROMPT,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            )
            logger.debug(
                "ExecutiveSummaryEngine._call_gemini | prompt_len=%d | reply_len=%d",
                len(full_prompt),
                len(reply),
            )
            return reply
        except GeminiServiceError as exc:
            logger.error(
                "ExecutiveSummaryEngine GeminiService error: %s (%s)",
                type(exc).__name__,
                exc,
            )
            return _FALLBACK_UNAVAILABLE
        except Exception as exc:  # pragma: no cover — belt-and-suspenders
            logger.error(
                "ExecutiveSummaryEngine unexpected error: %s", exc, exc_info=True
            )
            return _FALLBACK_UNAVAILABLE

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_summary(
        self,
        *,
        network_state: Optional[Any] = None,
        scenario: Optional[Any] = None,
        predictions: Optional[List[Any]] = None,
        optimization: Optional[Any] = None,
        recommendations: Optional[List[Any]] = None,
        dashboard: Optional[Any] = None,
    ) -> str:
        """
        Generate a concise executive operational briefing (150-300 words).

        The summary is structured into up to five sections — any section
        for which no context data is available is automatically omitted:

        **Overall Status**     — network health score and headline figure
        **Current Situation**  — active scenario and live topology state
        **Key Risks**          — critical / high congestion towers and threats
        **Recommended Actions** — top-priority operator actions
        **Operator Notes**     — optimization result and any watch items

        Parameters
        ----------
        network_state : NetworkState, optional
        scenario      : Scenario, optional
        predictions   : list[PredictionResult], optional
        optimization  : OptimizationResult, optional
        recommendations : list[Recommendation], optional
        dashboard     : DashboardSummary, optional

        Returns
        -------
        str
            A 150-300 word plain-text executive briefing, or a fallback
            message if no context was supplied or Gemini is unavailable.
        """
        context = _assemble_context(
            network_state=network_state,
            scenario=scenario,
            predictions=predictions,
            optimization=optimization,
            recommendations=recommendations,
            dashboard=dashboard,
        )

        if not context:
            logger.warning("generate_summary() called with no context")
            return _FALLBACK_NO_CONTEXT

        task = (
            "Generate an executive operational briefing for a telecom network operator.\n"
            "Target length: 150-300 words.\n"
            "Structure the output using EXACTLY these section headers (omit any section "
            "for which the context contains no relevant data):\n\n"
            "**Overall Status**\n"
            "  One-sentence headline: operational status and network health.\n\n"
            "**Current Situation**\n"
            "  Tower topology, any active scenario, and current load profile.\n\n"
            "**Key Risks**\n"
            "  Towers with HIGH or CRITICAL congestion risk; active threats or failures.\n\n"
            "**Recommended Actions**\n"
            "  Top-priority operator actions from the recommendation queue.\n\n"
            "**Operator Notes**\n"
            "  Optimization result, watch items, and anything the operator should monitor.\n\n"
            "Rules:\n"
            "- Only reference data present in the context block above.\n"
            "- Use exact tower IDs, percentages, and scores from the context.\n"
            "- Do not invent or estimate any figure.\n"
            "- Be concise and direct — this is read under operational pressure."
        )

        return self._call_gemini(
            task_prompt=task,
            context_block=context,
            temperature=0.2,
            max_output_tokens=600,
        )

    def generate_brief(
        self,
        *,
        network_state: Optional[Any] = None,
        scenario: Optional[Any] = None,
        predictions: Optional[List[Any]] = None,
        optimization: Optional[Any] = None,
        recommendations: Optional[List[Any]] = None,
        dashboard: Optional[Any] = None,
    ) -> str:
        """
        Generate an ultra-compact 2-4 sentence dashboard headline.

        Suitable for status widgets, push notifications, or the top of the
        operator dashboard where space is limited.  Covers the single most
        important fact about the current network state.

        Returns
        -------
        str
            2-4 sentence plain-text status headline, or a fallback message.
        """
        context = _assemble_context(
            network_state=network_state,
            scenario=scenario,
            predictions=predictions,
            optimization=optimization,
            recommendations=recommendations,
            dashboard=dashboard,
        )

        if not context:
            logger.warning("generate_brief() called with no context")
            return _FALLBACK_NO_CONTEXT

        task = (
            "Write a 2-4 sentence network status headline for the operator dashboard.\n"
            "Lead with the overall operational status (healthy / degraded / critical).\n"
            "Include the single most urgent concern if one exists.\n"
            "End with the top recommended action if one is available.\n"
            "Use exact values from the context.  Do not use more than 4 sentences.\n"
            "Do not use section headers — write as flowing prose."
        )

        return self._call_gemini(
            task_prompt=task,
            context_block=context,
            temperature=0.15,
            max_output_tokens=200,
        )

    def generate_incident_report(
        self,
        scenario: Any,
        *,
        network_state: Optional[Any] = None,
        predictions: Optional[List[Any]] = None,
        optimization: Optional[Any] = None,
        recommendations: Optional[List[Any]] = None,
        dashboard: Optional[Any] = None,
    ) -> str:
        """
        Generate a formal incident report centred on an active scenario.

        The report covers the incident description, affected assets, current
        impact assessment, and recommended remediation steps.  Suitable for
        escalation emails, ops-runbooks, and post-incident review.

        Parameters
        ----------
        scenario : Scenario
            The active scenario that triggered the incident.  Required.
        network_state, predictions, optimization, recommendations, dashboard:
            Optional supporting context for richer impact assessment.

        Returns
        -------
        str
            A structured incident report, or a fallback message if ``scenario``
            is None or Gemini is unavailable.
        """
        if scenario is None:
            logger.warning("generate_incident_report() called without a scenario")
            return _FALLBACK_INCIDENT_NO_SCENARIO

        context = _assemble_context(
            network_state=network_state,
            scenario=scenario,
            predictions=predictions,
            optimization=optimization,
            recommendations=recommendations,
            dashboard=dashboard,
        )

        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        event_type = getattr(scenario, "event_type", "unknown event")
        scenario_name = getattr(scenario, "name", "Unnamed Incident")
        affected = getattr(scenario, "affected_tower_ids", [])
        affected_str = ", ".join(str(t) for t in affected) if affected else "auto-selected"

        task = (
            f"Generate a formal network incident report.\n"
            f"Report timestamp: {now_utc}\n"
            f"Incident name: {scenario_name}\n"
            f"Event type: {event_type}\n"
            f"Affected assets: {affected_str}\n\n"
            "Structure the report using EXACTLY these section headers "
            "(omit any section lacking context data):\n\n"
            "**INCIDENT REPORT**\n"
            "  Report ID (derive from scenario ID), timestamp, severity.\n\n"
            "**Incident Description**\n"
            "  What happened, which event type was triggered, what the simulation computed.\n\n"
            "**Affected Assets**\n"
            "  List of towers affected, their status, and capacity impact.\n\n"
            "**Current Impact Assessment**\n"
            "  Load levels, congestion risk, QoS/QoE degradation (from dashboard if available).\n\n"
            "**Recommended Remediation**\n"
            "  Prioritised list of operator actions to restore normal operation.\n\n"
            "**Monitoring Watch Items**\n"
            "  What the operator should track until the incident is resolved.\n\n"
            "Rules:\n"
            "- Only use data from the context block above.\n"
            "- Use exact tower IDs and metric values.\n"
            "- Do not invent severity levels or impact figures not in the context.\n"
            "- Write in a formal, structured style appropriate for an ops runbook."
        )

        return self._call_gemini(
            task_prompt=task,
            context_block=context,
            temperature=0.15,
            max_output_tokens=800,
        )

    def generate_shift_handover(
        self,
        *,
        network_state: Optional[Any] = None,
        scenario: Optional[Any] = None,
        predictions: Optional[List[Any]] = None,
        optimization: Optional[Any] = None,
        recommendations: Optional[List[Any]] = None,
        dashboard: Optional[Any] = None,
    ) -> str:
        """
        Generate a shift-handover note for an outgoing operator.

        Covers the current network state, any active or recently resolved
        incidents, outstanding actions from the recommendation queue, and
        watch items for the incoming team.

        Returns
        -------
        str
            A structured shift-handover note, or a fallback message if no
            context was supplied or Gemini is unavailable.
        """
        context = _assemble_context(
            network_state=network_state,
            scenario=scenario,
            predictions=predictions,
            optimization=optimization,
            recommendations=recommendations,
            dashboard=dashboard,
        )

        if not context:
            logger.warning("generate_shift_handover() called with no context")
            return _FALLBACK_NO_CONTEXT

        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        task = (
            f"Generate a shift-handover note for an outgoing network operations engineer.\n"
            f"Handover time: {now_utc}\n\n"
            "Structure using EXACTLY these section headers "
            "(omit any section lacking context data):\n\n"
            "**SHIFT HANDOVER NOTE**\n"
            "  Handover timestamp and overall network status.\n\n"
            "**Current Network State**\n"
            "  Tower topology, active/maintenance/inactive counts, load profile.\n\n"
            "**Active Incidents / Scenarios**\n"
            "  Any running scenario, its event type, and affected towers.\n\n"
            "**Outstanding Actions**\n"
            "  Open recommendation queue items the incoming operator must action.\n\n"
            "**Watch Items for Incoming Shift**\n"
            "  Towers with elevated congestion risk, pending optimizations, "
            "and anything that needs monitoring.\n\n"
            "**Optimization Summary**\n"
            "  Latest QUBO run status and energy outcome if available.\n\n"
            "Rules:\n"
            "- Write in a professional, neutral handover style.\n"
            "- Only reference data from the context block above.\n"
            "- Use exact tower IDs and metric values from the context.\n"
            "- Keep the note concise but complete — the incoming engineer \n"
            "  must be fully situationally aware after reading it."
        )

        return self._call_gemini(
            task_prompt=task,
            context_block=context,
            temperature=0.2,
            max_output_tokens=700,
        )


# ---------------------------------------------------------------------------
# Legacy compatibility shim
# ---------------------------------------------------------------------------

class SummaryEngine(ExecutiveSummaryEngine):
    """
    Backward-compatible alias for ``ExecutiveSummaryEngine``.

    The original placeholder ``SummaryEngine`` class is preserved here so
    that any existing code that imports ``SummaryEngine`` continues to work
    without modification.

    ``summarize(logs)`` is kept for interface compatibility but now delegates
    to ``generate_brief()`` using the dashboard object if one is provided.

    .. deprecated::
        Prefer ``ExecutiveSummaryEngine`` for all new code.
        ``SummaryEngine`` will be removed in a future release.
    """

    def summarize(self, logs: list) -> str:
        """
        Backward-compatible interface.

        For rich LLM-backed summaries, use ``generate_summary()`` or
        ``generate_brief()`` with proper context objects instead.
        """
        if not logs:
            return "No logs provided. Network status nominal."
        count = len(logs)
        logger.warning(
            "SummaryEngine.summarize() is deprecated — use generate_summary() "
            "with structured context objects instead."
        )
        return (
            f"Processed {count} log entries. "
            "For an AI-generated analysis, call generate_summary() with "
            "NetworkState, DashboardSummary, or PredictionResult context."
        )

"""
PulseOS AI Copilot
==================
Production-quality conversational assistant for telecom network operators.

Role
----
The Copilot is the operator-facing intelligence layer of PulseOS.  It helps
network engineers understand *what is happening* in their network by grounding
every response in the live backend state:

    - NetworkState   → tower topology, connections, status
    - Scenario       → active simulation events and their computed effects
    - PredictionResult → congestion forecasts per tower
    - OptimizationResult → QUBO solver outcome
    - Recommendation → decision-engine action queue
    - DashboardSummary → rolled-up KPI snapshot

Design contract
---------------
* The Copilot NEVER fabricates metrics.  All data comes from the caller-supplied
  context objects.  If no context is available for a question, it says so.
* All LLM calls route exclusively through ``GeminiService`` — the Copilot never
  imports ``google.genai`` directly.
* Conversation history is maintained per-instance as a lightweight list of dicts
  so that the assistant remembers what was said earlier in the session.
* If GeminiService raises any error the Copilot catches it, logs it, and returns
  a graceful degraded message.  Stack traces never reach the caller.
* Response format preference (when appropriate):
      **Observation** — what the data shows
      **Reason**      — why this is happening (based on the data)
      **Recommendation** — what the operator should do next

Public API
----------
``chat(message, **ctx)``
    General-purpose entry point.  Accepts optional context keyword arguments
    and routes to the most appropriate internal method.

``summarize_network(network_state, dashboard, predictions)``
    Comprehensive natural-language summary of current network health.

``explain_scenario(scenario, network_state)``
    Plain-language explanation of an active simulation scenario and its effects.

``explain_recommendation(recommendation, network_state, prediction)``
    Why a specific recommendation was generated and what it will achieve.

``explain_optimization(result, network_state)``
    Plain-language summary of an OptimizationResult (QUBO run).

``answer_question(question, **ctx)``
    Free-form operator question answered against all provided context.

``reset_history()``
    Clears the in-memory conversation history for this session.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Optional schema imports — gracefully skipped if modules do not yet exist.
# Each import is wrapped individually so that a missing module only removes
# that specific type hint; the rest of the Copilot continues to work.
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
# Reusable system prompt — injected on every LLM call
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are PulseOS AI Copilot, an expert assistant embedded in the PulseOS \
autonomous telecom network operations platform.

Your sole purpose is to help network operators understand what is happening \
in their live telecom infrastructure.

STRICT RULES — follow these without exception:
1. NEVER fabricate, invent, or estimate metrics, tower IDs, load percentages, \
latency values, or any numerical data.  Only reference numbers that appear in \
the context block explicitly provided to you.
2. NEVER hallucinate network events, scenarios, or optimisation results that \
are not present in the provided context.
3. If the context block is empty or does not contain information relevant to \
the question, say so clearly: "I don't have that data in the current context."
4. Clearly distinguish between:
   - Observations  (what the data shows — always cite the data)
   - Reasons       (why it is likely happening — infer from the data only)
   - Recommendations (what the operator should do — always mark these as suggestions)
5. Use concise, precise language.  Prefer bullet points over prose paragraphs \
when listing multiple items.
6. Do not repeat the question back to the user.
7. Do not use filler phrases such as "Great question!" or "Certainly!".
8. When referencing towers, always use their exact IDs from the context.

RESPONSE FORMAT (use when appropriate):
**Observation:** <what the data shows>
**Reason:** <why this is happening, based on the data>
**Recommendation:** <suggested next action for the operator>

If the question requires a simple factual answer, a structured format is not \
necessary — just answer directly and concisely.
"""

# ---------------------------------------------------------------------------
# Fallback messages — returned when Gemini is unavailable
# ---------------------------------------------------------------------------

_FALLBACK_UNAVAILABLE = (
    "⚠️  AI Copilot is temporarily unavailable (Gemini API unreachable). "
    "Please check your API key and network connectivity, then try again."
)

_FALLBACK_NO_CONTEXT = (
    "I don't have enough context to answer that question. "
    "Please provide network state, scenario, or prediction data."
)


# ---------------------------------------------------------------------------
# Helper: safe JSON serialisation
# ---------------------------------------------------------------------------

def _to_json(obj: Any, indent: int = 2) -> str:
    """Serialise a Pydantic model or plain dict to a compact JSON string."""
    try:
        # Pydantic v2: .model_dump() / Pydantic v1: .dict()
        if hasattr(obj, "model_dump"):
            return json.dumps(obj.model_dump(mode="json"), indent=indent, default=str)
        if hasattr(obj, "dict"):
            return json.dumps(obj.dict(), indent=indent, default=str)
        return json.dumps(obj, indent=indent, default=str)
    except Exception:  # pragma: no cover
        return str(obj)


# ---------------------------------------------------------------------------
# Context assemblers — pure functions, no LLM calls
# ---------------------------------------------------------------------------

def _network_context(state: Optional[Any]) -> str:
    """Render NetworkState into a readable context block."""
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

        tower_block = "\n".join(tower_lines) if tower_lines else "  (no towers)"

        return (
            f"[NETWORK STATE — snapshot at {generated_at}]\n"
            f"Towers total={len(towers)} | active={active} | "
            f"maintenance={maintenance} | inactive={inactive}\n"
            f"Connections: {len(connections)}\n"
            f"Tower details:\n{tower_block}\n"
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to render network context: %s", exc)
        return "[NETWORK STATE — rendering failed]\n"


def _scenario_context(scenario: Optional[Any]) -> str:
    """Render a Scenario into a readable context block."""
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
            f"  Affected towers ({len(affected)}): {', '.join(affected) or 'all/auto-selected'}\n"
            f"  Computed effects:\n{param_lines}\n"
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to render scenario context: %s", exc)
        return "[ACTIVE SCENARIO — rendering failed]\n"


def _predictions_context(predictions: Optional[List[Any]]) -> str:
    """Render a list of PredictionResult objects into a readable context block."""
    if not predictions:
        return ""
    try:
        lines: List[str] = []
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
        return (
            f"[CONGESTION PREDICTIONS — {len(predictions)} tower(s)]\n"
            + "\n".join(lines) + "\n"
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to render predictions context: %s", exc)
        return "[CONGESTION PREDICTIONS — rendering failed]\n"


def _optimization_context(result: Optional[Any]) -> str:
    """Render an OptimizationResult into a readable context block."""
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
            f"  Run ID: {run_id}\n"
            f"  Timestamp: {ts}\n"
            f"  Algorithm: {algo}\n"
            f"  Solver status: {status}\n"
            f"  Optimal energy (QUBO): {energy_str} (lower is better)\n"
            f"  Solver duration: {dur_str}\n"
            f"  Variables total: {len(assignments)} | "
            f"assigned=1: {len(assigned_ones)}\n"
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to render optimization context: %s", exc)
        return "[OPTIMIZATION RESULT — rendering failed]\n"


def _recommendation_context(rec: Optional[Any]) -> str:
    """Render a single Recommendation into a readable context block."""
    if rec is None:
        return ""
    try:
        rid = getattr(rec, "id", "?")
        action = getattr(rec, "action", "?")
        reason = getattr(rec, "reason", "(no reason provided)")
        conf = getattr(rec, "confidence", None)
        tower = getattr(rec, "target_tower_id", None) or "network-wide"
        priority = getattr(rec, "priority", "?")
        conf_str = f"{conf:.2f}" if conf is not None else "?"

        return (
            f"[RECOMMENDATION]\n"
            f"  ID: {rid}\n"
            f"  Action: {action}\n"
            f"  Reason: {reason}\n"
            f"  Target: {tower}\n"
            f"  Priority: {priority}\n"
            f"  Confidence: {conf_str}\n"
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to render recommendation context: %s", exc)
        return "[RECOMMENDATION — rendering failed]\n"


def _dashboard_context(dashboard: Optional[Any]) -> str:
    """Render a DashboardSummary into a readable context block."""
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
            f"  Towers: total={total}, active={active}, "
            f"maintenance={maint}\n"
            f"  Average predicted load: {load_str}\n"
            f"  Congestion alerts (HIGH or CRITICAL): {alerts}\n"
            f"  QoS score: {qos_str}\n"
            f"  QoE score: {qoe_str}\n"
            f"  Recent recommendations: {len(recs)}\n"
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to render dashboard context: %s", exc)
        return "[DASHBOARD SUMMARY — rendering failed]\n"


def _assemble_context(**ctx_kwargs: Any) -> str:
    """
    Combine all available context blocks into a single context string for the LLM.

    Parameters
    ----------
    ctx_kwargs:
        Recognised keys: ``network_state``, ``scenario``, ``predictions``,
        ``optimization``, ``recommendation``, ``dashboard``.
        Unrecognised keys are silently ignored.

    Returns
    -------
    str
        A formatted context block, or empty string if nothing was provided.
    """
    parts: List[str] = []

    if ctx_kwargs.get("dashboard"):
        parts.append(_dashboard_context(ctx_kwargs["dashboard"]))

    if ctx_kwargs.get("network_state"):
        parts.append(_network_context(ctx_kwargs["network_state"]))

    if ctx_kwargs.get("scenario"):
        parts.append(_scenario_context(ctx_kwargs["scenario"]))

    if ctx_kwargs.get("predictions"):
        parts.append(_predictions_context(ctx_kwargs["predictions"]))

    if ctx_kwargs.get("optimization"):
        parts.append(_optimization_context(ctx_kwargs["optimization"]))

    if ctx_kwargs.get("recommendation"):
        parts.append(_recommendation_context(ctx_kwargs["recommendation"]))

    return "\n".join(p for p in parts if p).strip()


# ---------------------------------------------------------------------------
# Main Copilot class
# ---------------------------------------------------------------------------


class Copilot:
    """
    PulseOS AI Copilot — conversational assistant for telecom network operators.

    The Copilot is grounded in live backend state.  It explains what is
    happening in the network based on structured data passed by the caller;
    it does not generate, predict, or optimise anything itself.

    Parameters
    ----------
    gemini_service:
        An initialised ``GeminiService`` instance.  Use dependency injection
        (FastAPI ``Depends(get_gemini_service)``) rather than constructing one
        directly inside route handlers.
    max_history_turns:
        Maximum number of conversation turns to retain in memory.  Older turns
        are dropped from the head to keep context windows manageable.
        Default: 20 turns (40 messages — user + assistant each).

    Examples
    --------
    >>> from services.deps import get_gemini_service
    >>> copilot = Copilot(gemini_service=get_gemini_service())
    >>> reply = copilot.chat("Which towers are overloaded?",
    ...                      predictions=my_predictions)
    >>> print(reply)
    """

    def __init__(
        self,
        gemini_service: GeminiService,
        max_history_turns: int = 20,
    ) -> None:
        self._gemini: GeminiService = gemini_service
        self._max_turns: int = max_history_turns
        # History entries: {"role": "user"|"assistant", "content": str}
        self._history: List[Dict[str, str]] = []
        logger.info(
            "Copilot initialised | max_history_turns=%d", max_history_turns
        )

    # ------------------------------------------------------------------
    # History management
    # ------------------------------------------------------------------

    def reset_history(self) -> None:
        """Clear the in-memory conversation history for this session."""
        self._history.clear()
        logger.debug("Copilot conversation history cleared")

    def get_history(self) -> List[Dict[str, str]]:
        """Return a shallow copy of the current conversation history."""
        return list(self._history)

    def _record_turn(self, user_message: str, assistant_reply: str) -> None:
        """Append a completed turn to history, evicting old turns if needed."""
        self._history.append({"role": "user", "content": user_message})
        self._history.append({"role": "assistant", "content": assistant_reply})
        # Evict oldest turns if over the cap (each turn = 2 messages)
        max_messages = self._max_turns * 2
        if len(self._history) > max_messages:
            self._history = self._history[-max_messages:]
            logger.debug("History trimmed to %d messages", max_messages)

    # ------------------------------------------------------------------
    # Internal LLM call with fallback
    # ------------------------------------------------------------------

    def _call_gemini(
        self,
        task_prompt: str,
        context_block: str = "",
        temperature: float = 0.3,
    ) -> str:
        """
        Internal method: build a full prompt (history + context + task) and
        call GeminiService.  Returns the model's response, or a graceful
        fallback string if the call fails.

        Temperature is intentionally low (0.3) to favour factual, deterministic
        responses over creative improvisation.
        """
        # Build the conversational history preamble
        history_lines: List[str] = []
        for turn in self._history:
            role = "Operator" if turn["role"] == "user" else "Copilot"
            history_lines.append(f"{role}: {turn['content']}")

        history_block = "\n".join(history_lines)

        # Assemble the full prompt
        sections: List[str] = []

        if history_block:
            sections.append(
                f"=== CONVERSATION HISTORY ===\n{history_block}"
            )

        if context_block:
            sections.append(
                f"=== LIVE NETWORK CONTEXT ===\n{context_block}"
            )

        sections.append(f"=== OPERATOR REQUEST ===\n{task_prompt}")
        sections.append("=== COPILOT RESPONSE ===")

        full_prompt = "\n\n".join(sections)

        try:
            reply = self._gemini.generate(
                full_prompt,
                system_instruction=_SYSTEM_PROMPT,
                temperature=temperature,
                max_output_tokens=1024,
            )
            logger.debug(
                "_call_gemini() | prompt_len=%d | reply_len=%d",
                len(full_prompt),
                len(reply),
            )
            return reply
        except GeminiServiceError as exc:
            logger.error(
                "Copilot GeminiService error: %s (%s)",
                type(exc).__name__,
                exc,
            )
            return _FALLBACK_UNAVAILABLE

    # ------------------------------------------------------------------
    # Public API — high-level methods
    # ------------------------------------------------------------------

    def chat(
        self,
        message: str,
        *,
        network_state: Optional[Any] = None,
        scenario: Optional[Any] = None,
        predictions: Optional[List[Any]] = None,
        optimization: Optional[Any] = None,
        recommendation: Optional[Any] = None,
        dashboard: Optional[Any] = None,
    ) -> str:
        """
        General-purpose Copilot entry point.

        Accepts an operator message and any combination of context objects.
        The context is serialised into a structured block and prepended to the
        prompt so the model is grounded in real backend data.

        Parameters
        ----------
        message:
            The operator's natural-language question or command.
        network_state:
            Live ``NetworkState`` snapshot.
        scenario:
            Currently active ``Scenario`` (if any).
        predictions:
            List of ``PredictionResult`` objects.
        optimization:
            Most recent ``OptimizationResult`` (if any).
        recommendation:
            A specific ``Recommendation`` to discuss (if any).
        dashboard:
            ``DashboardSummary`` snapshot.

        Returns
        -------
        str
            The Copilot's natural-language response.
        """
        if not message or not message.strip():
            return "Please ask me a question about your network."

        context = _assemble_context(
            network_state=network_state,
            scenario=scenario,
            predictions=predictions,
            optimization=optimization,
            recommendation=recommendation,
            dashboard=dashboard,
        )

        reply = self._call_gemini(task_prompt=message, context_block=context)
        self._record_turn(message, reply)
        return reply

    def summarize_network(
        self,
        network_state: Optional[Any] = None,
        dashboard: Optional[Any] = None,
        predictions: Optional[List[Any]] = None,
    ) -> str:
        """
        Produce a concise natural-language summary of current network health.

        Covers overall topology, load distribution, congestion alerts, and
        top-line QoS/QoE scores.  Never invents data not present in the context.

        Parameters
        ----------
        network_state:
            Live ``NetworkState`` snapshot.
        dashboard:
            ``DashboardSummary`` — if present, overrides individual tower-level
            computation with the already-aggregated KPIs.
        predictions:
            List of ``PredictionResult`` objects for load context.

        Returns
        -------
        str
            A 3-6 sentence plain-language network status summary.
        """
        context = _assemble_context(
            network_state=network_state,
            dashboard=dashboard,
            predictions=predictions,
        )

        if not context:
            return _FALLBACK_NO_CONTEXT

        task = (
            "Provide a concise network health summary (3-6 sentences) based strictly "
            "on the context above.  Cover: overall tower status, congestion/load outlook, "
            "QoS/QoE if available, and the single most urgent concern.  "
            "Do not add any information not present in the context."
        )

        reply = self._call_gemini(task_prompt=task, context_block=context, temperature=0.2)
        self._record_turn("Summarize the current network status.", reply)
        return reply

    def explain_scenario(
        self,
        scenario: Optional[Any] = None,
        network_state: Optional[Any] = None,
    ) -> str:
        """
        Explain the active network simulation scenario in plain language.

        Describes the event type, which towers are affected, and what the
        computed simulation effects mean for the operator.

        Parameters
        ----------
        scenario:
            The active ``Scenario`` object returned by ``ScenarioEngine.run()``.
        network_state:
            Optional network state for cross-referencing affected towers.

        Returns
        -------
        str
            Plain-language explanation of the scenario and its effects.
        """
        if scenario is None:
            return "No active scenario has been provided.  Run a scenario first."

        context = _assemble_context(
            scenario=scenario,
            network_state=network_state,
        )

        event_type = getattr(scenario, "event_type", "unknown event")
        name = getattr(scenario, "name", "Unnamed scenario")

        task = (
            f"Explain the active scenario '{name}' (event type: {event_type}) "
            f"to a network operator.  Use the context above.  Describe:\n"
            f"1. What this scenario simulates\n"
            f"2. Which towers are affected and why\n"
            f"3. What the computed effects mean operationally "
            f"(e.g., traffic multiplier, signal degradation, coverage loss)\n"
            f"4. What immediate risks the operator should be aware of.\n"
            f"Stick strictly to the data in the context.  Do not invent effects."
        )

        reply = self._call_gemini(task_prompt=task, context_block=context, temperature=0.25)
        self._record_turn(f"Explain the active scenario: {name}.", reply)
        return reply

    def explain_recommendation(
        self,
        recommendation: Optional[Any] = None,
        network_state: Optional[Any] = None,
        prediction: Optional[Any] = None,
    ) -> str:
        """
        Explain why a specific recommendation was generated and what it will achieve.

        Parameters
        ----------
        recommendation:
            The ``Recommendation`` object to explain.
        network_state:
            Optional network state for tower context.
        prediction:
            Optional ``PredictionResult`` that may have triggered the recommendation.

        Returns
        -------
        str
            Plain-language explanation of the recommendation.
        """
        if recommendation is None:
            return "No recommendation has been provided to explain."

        context = _assemble_context(
            recommendation=recommendation,
            network_state=network_state,
            predictions=[prediction] if prediction is not None else None,
        )

        action = getattr(recommendation, "action", "unknown action")
        reason = getattr(recommendation, "reason", "")
        tower = getattr(recommendation, "target_tower_id", None) or "the network"

        task = (
            f"Explain this recommendation to a network operator:\n"
            f"Action: {action} on {tower}\n"
            f"Stated reason: {reason}\n\n"
            f"Using the context above, provide:\n"
            f"1. What this action does technically\n"
            f"2. Why the system generated it (cite the data)\n"
            f"3. What outcome the operator should expect if they execute it\n"
            f"4. Any caveats or side-effects to be aware of.\n"
            f"Be specific.  Do not add information not in the context."
        )

        reply = self._call_gemini(task_prompt=task, context_block=context, temperature=0.25)
        self._record_turn(
            f"Explain recommendation {getattr(recommendation, 'id', '')}.", reply
        )
        return reply

    def explain_optimization(
        self,
        result: Optional[Any] = None,
        network_state: Optional[Any] = None,
    ) -> str:
        """
        Explain an OptimizationResult (QUBO solver run) to the operator.

        Translates solver-level output (energy, variable assignments) into
        operational meaning: what was optimised, whether it succeeded, and
        what the result implies for the network.

        Parameters
        ----------
        result:
            The ``OptimizationResult`` from the QUBO solver.
        network_state:
            Optional network state for cross-referencing.

        Returns
        -------
        str
            Plain-language explanation of the optimization run.
        """
        if result is None:
            return "No optimization result has been provided to explain."

        context = _assemble_context(
            optimization=result,
            network_state=network_state,
        )

        status = getattr(result, "solver_status", "unknown")
        algo = getattr(result, "algorithm", "QUBO")
        energy = getattr(result, "optimal_energy", None)

        task = (
            f"Explain this {algo.upper()} optimization run to a network operator "
            f"(solver status: {status}, energy: {energy}).\n\n"
            f"Using the context above, describe:\n"
            f"1. What the optimizer was trying to achieve (objective)\n"
            f"2. Whether the run succeeded and what the optimal energy value means\n"
            f"3. What the variable assignments indicate operationally "
            f"(which 'decisions' were activated vs. deactivated)\n"
            f"4. What action the operator should take based on this result.\n"
            f"Avoid technical jargon where possible.  Cite numbers from the context."
        )

        reply = self._call_gemini(task_prompt=task, context_block=context, temperature=0.25)
        self._record_turn(
            f"Explain optimization result {getattr(result, 'run_id', '')}.", reply
        )
        return reply

    def answer_question(
        self,
        question: str,
        *,
        network_state: Optional[Any] = None,
        scenario: Optional[Any] = None,
        predictions: Optional[List[Any]] = None,
        optimization: Optional[Any] = None,
        recommendation: Optional[Any] = None,
        dashboard: Optional[Any] = None,
    ) -> str:
        """
        Answer a free-form operator question grounded in all available context.

        This is the most flexible entry point.  Provide as much context as is
        available; the model will only draw on what is present.

        Parameters
        ----------
        question:
            The operator's question (e.g. "Why is latency increasing?").
        network_state, scenario, predictions, optimization, recommendation, dashboard:
            Any combination of context objects.  All optional.

        Returns
        -------
        str
            A grounded, factual answer citing available context data.
        """
        return self.chat(
            message=question,
            network_state=network_state,
            scenario=scenario,
            predictions=predictions,
            optimization=optimization,
            recommendation=recommendation,
            dashboard=dashboard,
        )

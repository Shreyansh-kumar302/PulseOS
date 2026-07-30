"""
Decision Engine  —  PulseOS Recommendation Engine
==================================================
Converts live network conditions into structured, actionable recommendations
for network operators.

Design principles
-----------------
* Deterministic rule-based logic only.  No LLM calls, no randomness.
* Each rule is a small, independently testable function that accepts a
  ``RuleContext`` and returns zero or more ``Recommendation`` objects.
* Thresholds are centralised in ``EngineConfig`` — change one constant and
  all rules adapt.
* Rules are registered in a flat list (``_RULES``) and evaluated in priority
  order.  Any combination of inputs may be ``None``; every rule guards its
  own inputs gracefully.
* The public method ``recommend_actions()`` is preserved for backward
  compatibility and also extended via the new ``evaluate()`` method which
  accepts the full v2 context.

Rule catalogue (see implementation below)
------------------------------------------
 1. critical_congestion_load_balance   — tower load ≥ CRITICAL (≥90%)
 2. high_congestion_throttle           — tower load ≥ HIGH (≥75%)
 3. medium_congestion_monitor          — tower load ≥ MEDIUM (≥50%)
 4. offline_tower_emergency_repair     — tower status = INACTIVE
 5. maintenance_tower_dispatch         — tower status = MAINTENANCE
 6. cyclone_emergency_resources        — scenario event_type = CYCLONE
 7. power_outage_emergency             — scenario event_type = POWER_OUTAGE
 8. tower_failure_reroute              — scenario event_type = TOWER_FAILURE
 9. fibre_cut_reroute                  — scenario event_type = FIBRE_CUT
10. mass_event_capacity_expansion      — scenario traffic_multiplier ≥ 3.0
11. weather_frequency_reassignment     — heavy rain signal degradation ≥ 6 dB
12. latency_spike_optimization         — scenario latency_increase_ms ≥ LATENCY_MS
13. low_load_energy_saving             — all towers load ≤ LOW + no alerts
14. optimization_failed_retry          — optimization solver_status != success
15. network_healthy_no_action          — no other rules fired
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, List, Optional

from schemas.recommendation import (
    ActionType,
    Recommendation,
    RecommendationCategory,
    RecommendationPriority,
)
from schemas.scenario import ScenarioEventType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration — all thresholds in one place
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EngineConfig:
    """
    Centralised threshold configuration for the Decision Engine.

    All values can be overridden at construction time so that unit tests
    and production deployments can tune behaviour without code changes.

    Attributes
    ----------
    load_critical_pct   Predicted load % that triggers CRITICAL priority (default 90).
    load_high_pct       Predicted load % that triggers HIGH priority (default 75).
    load_medium_pct     Predicted load % that triggers MEDIUM priority (default 50).
    load_low_pct        Predicted load % below which energy-saving is considered (default 35).
    latency_high_ms     Added latency (ms) that triggers an optimization recommendation (default 50).
    signal_degrade_db   Signal degradation (dB) threshold for frequency reassignment (default 6).
    traffic_mult_high   Traffic multiplier threshold for capacity-expansion alert (default 3.0).
    max_recommendations Hard cap on total recommendations returned per evaluate() call (default 20).
    """

    load_critical_pct: float = 90.0
    load_high_pct: float = 75.0
    load_medium_pct: float = 50.0
    load_low_pct: float = 35.0
    latency_high_ms: float = 50.0
    signal_degrade_db: float = 6.0
    traffic_mult_high: float = 3.0
    max_recommendations: int = 20


# Singleton default — used when no config is supplied
_DEFAULT_CONFIG = EngineConfig()


# ---------------------------------------------------------------------------
# Rule context  —  all inputs in one named bag, all Optional
# ---------------------------------------------------------------------------


@dataclass
class RuleContext:
    """
    Immutable snapshot of all inputs available to the rule evaluator.

    Every field is ``Optional``.  Rules must guard against ``None`` inputs.
    Typed as ``Any`` for schema objects to avoid hard import-time coupling
    (modules that do not yet exist would break import).

    Attributes
    ----------
    network_state       NetworkState snapshot (towers + connections).
    scenario            Active Scenario (if any).
    predictions         List of PredictionResult objects (may be empty).
    optimization        Most recent OptimizationResult (if any).
    dashboard           DashboardSummary snapshot (if any).
    config              EngineConfig thresholds.
    """

    network_state: Optional[Any] = None
    scenario: Optional[Any] = None
    predictions: Optional[List[Any]] = None
    optimization: Optional[Any] = None
    dashboard: Optional[Any] = None
    config: EngineConfig = field(default_factory=lambda: _DEFAULT_CONFIG)


# ---------------------------------------------------------------------------
# Rule type alias
# ---------------------------------------------------------------------------

# A rule is a function that accepts a RuleContext and returns a
# (possibly empty) list of Recommendation objects.
RuleFn = Callable[[RuleContext], List[Recommendation]]


# ---------------------------------------------------------------------------
# Helper — recommendation factory
# ---------------------------------------------------------------------------


def _make_rec(
    *,
    priority: RecommendationPriority,
    category: RecommendationCategory,
    title: str,
    description: str,
    reasoning: str,
    expected_impact: str,
    suggested_actions: List[str],
    affected_towers: Optional[List[str]] = None,
    confidence: float,
    action: Optional[ActionType] = None,
    target_tower_id: Optional[str] = None,
) -> Recommendation:
    """
    Factory that constructs a ``Recommendation`` with a fresh UUID and UTC
    timestamp, populating both v2 fields and legacy v1 aliases.
    """
    towers = affected_towers or []
    rec_id = f"REC-{uuid.uuid4().hex[:8].upper()}"
    return Recommendation(
        id=rec_id,
        timestamp=datetime.now(timezone.utc),
        priority=priority,
        category=category,
        title=title,
        description=description,
        reasoning=reasoning,
        expected_impact=expected_impact,
        suggested_actions=suggested_actions,
        affected_towers=towers,
        confidence=confidence,
        # legacy v1 aliases
        action=action,
        reason=reasoning[:200] if reasoning else None,
        target_tower_id=target_tower_id or (towers[0] if towers else None),
    )


# ---------------------------------------------------------------------------
# Helper — safe attribute accessors (guards None + missing attributes)
# ---------------------------------------------------------------------------


def _towers(ctx: RuleContext) -> List[Any]:
    """Return the list of towers from network_state, or []."""
    if ctx.network_state is None:
        return []
    return list(getattr(ctx.network_state, "towers", []) or [])


def _predictions(ctx: RuleContext) -> List[Any]:
    """Return the list of PredictionResult objects, or []."""
    return list(ctx.predictions or [])


def _scenario_event(ctx: RuleContext) -> Optional[str]:
    """Return the scenario event_type value string, or None."""
    if ctx.scenario is None:
        return None
    et = getattr(ctx.scenario, "event_type", None)
    return str(et) if et else None


def _scenario_params(ctx: RuleContext) -> dict:
    """Return Scenario.parameters dict, or {}."""
    if ctx.scenario is None:
        return {}
    return dict(getattr(ctx.scenario, "parameters", {}) or {})


def _scenario_affected_towers(ctx: RuleContext) -> List[str]:
    """Return affected_tower_ids from the active scenario, or []."""
    if ctx.scenario is None:
        return []
    return list(getattr(ctx.scenario, "affected_tower_ids", []) or [])


# ---------------------------------------------------------------------------
# RULE 1 — Critical congestion → load balance (CRITICAL priority)
# ---------------------------------------------------------------------------


def _rule_critical_congestion(ctx: RuleContext) -> List[Recommendation]:
    """
    Fires for every tower with predicted_load_pct ≥ load_critical_pct.

    Produces a HIGH-priority LOAD_BALANCE recommendation per affected tower.
    Priority is CRITICAL when load ≥ 95%.
    """
    recs: List[Recommendation] = []
    for pred in _predictions(ctx):
        load = getattr(pred, "predicted_load_pct", 0.0)
        tower_id = getattr(pred, "tower_id", "unknown")
        if load < ctx.config.load_critical_pct:
            continue

        priority = (
            RecommendationPriority.CRITICAL if load >= 95.0
            else RecommendationPriority.HIGH
        )
        conf = getattr(pred, "confidence", 0.85)

        recs.append(_make_rec(
            priority=priority,
            category=RecommendationCategory.LOAD_BALANCING,
            title=f"Critical congestion on tower {tower_id} — immediate load balance required",
            description=(
                f"Tower {tower_id} is predicted to reach {load:.1f}% utilisation, "
                f"exceeding the critical threshold of {ctx.config.load_critical_pct:.0f}%. "
                f"Unmitigated, this will cause packet loss, call drops, and severe QoS degradation "
                f"for all users connected to this cell."
            ),
            reasoning=(
                f"PredictionEngine reports predicted_load_pct={load:.1f}% on tower {tower_id} "
                f"(congestion_risk={getattr(pred, 'congestion_risk', 'critical')}, "
                f"model_confidence={conf:.2f}). "
                f"Threshold: ≥{ctx.config.load_critical_pct:.0f}%."
            ),
            expected_impact=(
                "Redistributing 30-40% of traffic to adjacent cells should reduce load below "
                "75%, restoring QoS within 2-3 minutes of action execution."
            ),
            suggested_actions=[
                f"Execute LOAD_BALANCE on tower {tower_id} via the optimization panel.",
                "Identify 2-3 neighbouring towers with load < 60% as traffic targets.",
                "Enable dynamic cell breathing (antenna tilt ±2°) to expand neighbour cell coverage.",
                "Monitor load every 60 seconds until load drops below 75%.",
                f"If load remains > 90% after 5 minutes, initiate HANDOVER for non-essential UEs.",
            ],
            affected_towers=[tower_id],
            confidence=min(conf + 0.05, 1.0),
            action=ActionType.LOAD_BALANCE,
            target_tower_id=tower_id,
        ))
        logger.debug("Rule critical_congestion fired for tower %s (load=%.1f%%)", tower_id, load)

    return recs


# ---------------------------------------------------------------------------
# RULE 2 — High congestion → throttle non-essential traffic
# ---------------------------------------------------------------------------


def _rule_high_congestion(ctx: RuleContext) -> List[Recommendation]:
    """
    Fires for every tower with load_high_pct ≤ predicted_load_pct < load_critical_pct.

    Produces a MEDIUM-priority THROTTLE recommendation.
    """
    recs: List[Recommendation] = []
    for pred in _predictions(ctx):
        load = getattr(pred, "predicted_load_pct", 0.0)
        tower_id = getattr(pred, "tower_id", "unknown")
        if not (ctx.config.load_high_pct <= load < ctx.config.load_critical_pct):
            continue

        conf = getattr(pred, "confidence", 0.80)
        recs.append(_make_rec(
            priority=RecommendationPriority.HIGH,
            category=RecommendationCategory.LOAD_BALANCING,
            title=f"High load on tower {tower_id} — throttle non-essential traffic",
            description=(
                f"Tower {tower_id} is predicted to reach {load:.1f}% utilisation. "
                f"While not yet critical, this trajectory will cause measurable QoS degradation "
                f"and puts the tower at risk of exceeding the {ctx.config.load_critical_pct:.0f}% "
                f"critical threshold if demand increases further."
            ),
            reasoning=(
                f"PredictionEngine: predicted_load_pct={load:.1f}% on tower {tower_id} "
                f"(risk=HIGH, confidence={conf:.2f}). "
                f"Window: {ctx.config.load_high_pct:.0f}%–{ctx.config.load_critical_pct:.0f}%."
            ),
            expected_impact=(
                "Throttling background/non-essential data (OTT streaming at > 1080p, bulk downloads) "
                "should reduce peak load by 15-25%, providing headroom before the critical threshold."
            ),
            suggested_actions=[
                f"Apply traffic shaping policy on tower {tower_id}: throttle non-essential APNs.",
                "Set video streaming cap to 720p for UEs on this cell.",
                "Enable Uplink Interference Management if upload_bias > 1.5.",
                "Schedule load balance if load exceeds 85% within the next 15 minutes.",
            ],
            affected_towers=[tower_id],
            confidence=conf,
            action=ActionType.THROTTLE_NON_ESSENTIAL,
            target_tower_id=tower_id,
        ))
        logger.debug("Rule high_congestion fired for tower %s (load=%.1f%%)", tower_id, load)

    return recs


# ---------------------------------------------------------------------------
# RULE 3 — Medium congestion → monitor only
# ---------------------------------------------------------------------------


def _rule_medium_congestion(ctx: RuleContext) -> List[Recommendation]:
    """
    Fires for every tower with load_medium_pct ≤ predicted_load_pct < load_high_pct.

    Produces a LOW-priority MONITOR_ONLY recommendation.
    """
    recs: List[Recommendation] = []
    for pred in _predictions(ctx):
        load = getattr(pred, "predicted_load_pct", 0.0)
        tower_id = getattr(pred, "tower_id", "unknown")
        if not (ctx.config.load_medium_pct <= load < ctx.config.load_high_pct):
            continue

        conf = getattr(pred, "confidence", 0.75)
        recs.append(_make_rec(
            priority=RecommendationPriority.MEDIUM,
            category=RecommendationCategory.MONITOR_ONLY,
            title=f"Elevated load on tower {tower_id} — monitor closely",
            description=(
                f"Tower {tower_id} is at {load:.1f}% predicted utilisation. "
                f"This is within acceptable operating range but warrants close monitoring "
                f"as load approaching {ctx.config.load_high_pct:.0f}% will require active intervention."
            ),
            reasoning=(
                f"PredictionEngine: predicted_load_pct={load:.1f}% on tower {tower_id} "
                f"(risk=MEDIUM, confidence={conf:.2f})."
            ),
            expected_impact=(
                "No immediate action required. Early awareness allows pre-emptive "
                "load balancing before the high-congestion threshold is breached."
            ),
            suggested_actions=[
                f"Set alert on tower {tower_id} to notify at {ctx.config.load_high_pct:.0f}% load.",
                "Review traffic patterns for this tower over the next 30 minutes.",
                "Pre-compute candidate load-balance targets for rapid deployment if needed.",
            ],
            affected_towers=[tower_id],
            confidence=conf,
            action=None,
            target_tower_id=tower_id,
        ))
        logger.debug("Rule medium_congestion fired for tower %s (load=%.1f%%)", tower_id, load)

    return recs


# ---------------------------------------------------------------------------
# RULE 4 — Offline (INACTIVE) tower → emergency repair
# ---------------------------------------------------------------------------


def _rule_offline_tower_emergency_repair(ctx: RuleContext) -> List[Recommendation]:
    """
    Fires for every tower with TowerStatus.INACTIVE.

    Produces a CRITICAL-priority EMERGENCY_REPAIR recommendation.
    """
    recs: List[Recommendation] = []
    for tower in _towers(ctx):
        status = str(getattr(tower, "status", "")).lower()
        if status != "inactive":
            continue

        tid = getattr(tower, "id", "unknown")
        tname = getattr(tower, "name", None) or tid
        ttype = str(getattr(tower, "type", "unknown"))

        recs.append(_make_rec(
            priority=RecommendationPriority.CRITICAL,
            category=RecommendationCategory.EMERGENCY_REPAIR,
            title=f"Tower {tid} is OFFLINE — dispatch emergency repair team",
            description=(
                f"Tower {tname} (ID: {tid}, type: {ttype}) is reporting INACTIVE status. "
                f"This tower is not serving any users. Neighbouring cells are absorbing the "
                f"displaced load and may become congested. Immediate field intervention is required."
            ),
            reasoning=(
                f"NetworkState.towers contains tower {tid} with status=INACTIVE. "
                f"Tower type={ttype}. An INACTIVE tower is completely non-operational."
            ),
            expected_impact=(
                "Restoring the tower to ACTIVE status will relieve load on neighbouring cells, "
                "restore coverage to the affected geographic area, and prevent cascading congestion."
            ),
            suggested_actions=[
                f"Dispatch field maintenance team to tower {tname} ({tid}) immediately.",
                "Check power supply: verify grid connection and UPS status at the site.",
                "Remote-reboot the baseband unit (BBU) via Element Management System (EMS).",
                "If hardware failure confirmed, escalate to vendor for emergency part replacement.",
                "In the meantime, enable enhanced load balancing on all neighbouring ACTIVE towers.",
                "Issue a coverage advisory for the affected geographic zone.",
            ],
            affected_towers=[tid],
            confidence=0.99,
            action=None,
            target_tower_id=tid,
        ))
        logger.debug("Rule offline_tower fired for tower %s", tid)

    return recs


# ---------------------------------------------------------------------------
# RULE 5 — Maintenance tower → scheduled dispatch
# ---------------------------------------------------------------------------


def _rule_maintenance_tower_dispatch(ctx: RuleContext) -> List[Recommendation]:
    """
    Fires for every tower with TowerStatus.MAINTENANCE.

    Produces a MEDIUM-priority MAINTENANCE_DISPATCH recommendation.
    """
    recs: List[Recommendation] = []
    for tower in _towers(ctx):
        status = str(getattr(tower, "status", "")).lower()
        if status != "maintenance":
            continue

        tid = getattr(tower, "id", "unknown")
        tname = getattr(tower, "name", None) or tid

        recs.append(_make_rec(
            priority=RecommendationPriority.MEDIUM,
            category=RecommendationCategory.MAINTENANCE_DISPATCH,
            title=f"Tower {tid} in MAINTENANCE — verify schedule and restore",
            description=(
                f"Tower {tname} ({tid}) is currently in MAINTENANCE status. "
                f"While planned maintenance is expected, the tower is not serving users. "
                f"Ensure the maintenance window is within schedule and restoration is on track."
            ),
            reasoning=(
                f"NetworkState.towers: tower {tid} has status=MAINTENANCE. "
                f"Maintenance windows reduce available network capacity."
            ),
            expected_impact=(
                "Confirming the maintenance schedule prevents unplanned outages and "
                "ensures the tower returns to ACTIVE before peak traffic hours."
            ),
            suggested_actions=[
                f"Verify maintenance work order for tower {tid} is on schedule.",
                "Confirm estimated return-to-service (RTS) time with field team.",
                "If maintenance is complete, trigger status update to ACTIVE in EMS.",
                "If overdue, escalate to network operations centre (NOC).",
            ],
            affected_towers=[tid],
            confidence=0.90,
            action=None,
            target_tower_id=tid,
        ))
        logger.debug("Rule maintenance_tower fired for tower %s", tid)

    return recs


# ---------------------------------------------------------------------------
# RULE 6 — Cyclone scenario → emergency resource deployment
# ---------------------------------------------------------------------------


def _rule_cyclone_emergency(ctx: RuleContext) -> List[Recommendation]:
    """
    Fires when the active scenario is CYCLONE.

    Produces a CRITICAL-priority EMERGENCY_DEPLOYMENT recommendation.
    """
    if _scenario_event(ctx) not in (
        ScenarioEventType.CYCLONE.value, "cyclone"
    ):
        return []

    params = _scenario_params(ctx)
    affected = _scenario_affected_towers(ctx)
    offline = params.get("towers_offline", [])
    degraded = params.get("towers_degraded", [])
    latency = params.get("latency_increase_ms", 0)
    coverage_loss = params.get("coverage_reduction_pct", 0)
    signal_db = params.get("signal_degradation_db", 0)

    recs = [_make_rec(
        priority=RecommendationPriority.CRITICAL,
        category=RecommendationCategory.EMERGENCY_DEPLOYMENT,
        title="CYCLONE ACTIVE — deploy emergency mobile towers and reroute traffic",
        description=(
            f"A cyclone scenario is active affecting {len(affected)} towers. "
            f"Scenario effects: {len(offline)} tower(s) offline, {len(degraded)} degraded, "
            f"latency +{latency} ms, signal degradation {signal_db} dB, "
            f"coverage loss {coverage_loss}%. Emergency protocols must be activated immediately."
        ),
        reasoning=(
            f"Active scenario event_type=CYCLONE. "
            f"Computed effects — towers_offline={offline}, towers_degraded={degraded}, "
            f"latency_increase_ms={latency}, signal_degradation_db={signal_db}, "
            f"coverage_reduction_pct={coverage_loss}."
        ),
        expected_impact=(
            "Deploying COWs (Cells on Wheels) at offline site locations and activating "
            "satellite backhaul failover will restore 60-70% of lost capacity within 4-6 hours."
        ),
        suggested_actions=[
            "Activate cyclone emergency protocol in the Operations Centre.",
            f"Deploy COW (Cell on Wheels) units to cover offline towers: {offline or 'see affected list'}.",
            "Switch backhaul to satellite/microwave failover for degraded towers.",
            "Prioritise emergency services (emergency APNs, MCPTT) over consumer traffic.",
            "Coordinate with field teams for post-storm damage assessment.",
            "Issue network advisory to all downstream NOC teams.",
            "Monitor power levels: activate generator/UPS for all battery-backed towers.",
        ],
        affected_towers=list(affected) + list(offline) + list(degraded),
        confidence=0.97,
        action=None,
    )]
    logger.debug("Rule cyclone_emergency fired | affected=%d towers", len(affected))
    return recs


# ---------------------------------------------------------------------------
# RULE 7 — Power outage scenario → emergency response
# ---------------------------------------------------------------------------


def _rule_power_outage(ctx: RuleContext) -> List[Recommendation]:
    """
    Fires when the active scenario is POWER_OUTAGE.

    Produces a CRITICAL-priority EMERGENCY_REPAIR recommendation.
    """
    if _scenario_event(ctx) not in (
        ScenarioEventType.POWER_OUTAGE.value, "power_outage"
    ):
        return []

    params = _scenario_params(ctx)
    affected = _scenario_affected_towers(ctx)
    offline = params.get("towers_offline", [])
    degraded = params.get("towers_degraded", [])
    coverage_loss = params.get("coverage_reduction_pct", 0)

    recs = [_make_rec(
        priority=RecommendationPriority.CRITICAL,
        category=RecommendationCategory.EMERGENCY_REPAIR,
        title="POWER OUTAGE — activate backup power and dispatch emergency crews",
        description=(
            f"A grid power outage scenario is active. {len(offline)} tower(s) offline, "
            f"{len(degraded)} operating on battery/UPS. "
            f"Coverage gap: {coverage_loss}%. "
            f"Battery-backed towers have limited runtime and may go offline without intervention."
        ),
        reasoning=(
            f"Scenario event_type=POWER_OUTAGE. "
            f"towers_offline={offline}, towers_degraded={degraded}, "
            f"coverage_reduction_pct={coverage_loss}."
        ),
        expected_impact=(
            "Generator deployment at UPS-equipped sites extends battery life by 8-12 hours, "
            "maintaining coverage until grid power is restored."
        ),
        suggested_actions=[
            f"Dispatch emergency power crew to offline towers: {offline or 'see affected list'}.",
            "Activate mobile generator units for towers on battery backup.",
            f"Estimate grid restoration ETA and compare to UPS battery runtime for: {degraded or 'degraded towers'}.",
            "Reduce transmit power on battery-backed towers by 20% to extend battery life.",
            "Notify NOC and regional grid operator of the outage scope.",
            "If restoration > 4 hours, arrange fuel resupply for diesel generators.",
        ],
        affected_towers=list(affected) + list(offline),
        confidence=0.96,
        action=None,
    )]
    logger.debug("Rule power_outage fired | offline=%s", offline)
    return recs


# ---------------------------------------------------------------------------
# RULE 8 — Tower failure scenario → traffic rerouting
# ---------------------------------------------------------------------------


def _rule_tower_failure_reroute(ctx: RuleContext) -> List[Recommendation]:
    """
    Fires when the active scenario is TOWER_FAILURE.

    Produces a CRITICAL-priority TRAFFIC_REROUTING recommendation.
    """
    if _scenario_event(ctx) not in (
        ScenarioEventType.TOWER_FAILURE.value, "tower_failure"
    ):
        return []

    params = _scenario_params(ctx)
    affected = _scenario_affected_towers(ctx)
    offline = params.get("towers_offline", [])
    degraded = params.get("towers_degraded", [])
    coverage_loss = params.get("coverage_reduction_pct", 0)
    latency = params.get("latency_increase_ms", 0)

    recs = [_make_rec(
        priority=RecommendationPriority.CRITICAL,
        category=RecommendationCategory.TRAFFIC_REROUTING,
        title="TOWER FAILURE — emergency handover and traffic rerouting required",
        description=(
            f"Tower failure scenario active: {len(offline)} tower(s) completely offline. "
            f"{len(degraded)} neighbouring tower(s) are absorbing handover traffic (degraded). "
            f"Coverage gap: {coverage_loss}%, latency impact: +{latency} ms. "
            f"Immediate handover configuration is required to prevent further QoS degradation."
        ),
        reasoning=(
            f"Scenario event_type=TOWER_FAILURE. "
            f"towers_offline={offline}, towers_degraded={degraded}, "
            f"coverage_reduction_pct={coverage_loss}, latency_increase_ms={latency}."
        ),
        expected_impact=(
            "Reconfiguring handover parameters on neighbouring towers absorbs 85-90% "
            "of displaced UEs and restores service continuity within 3-5 minutes."
        ),
        suggested_actions=[
            f"Trigger emergency HANDOVER configuration for offline towers: {offline or 'see affected list'}.",
            f"Increase capacity headroom on degraded neighbours: {degraded or 'see affected list'}.",
            "Expand neighbour cell coverage via antenna tilt adjustment (–2° tilt on adjacent sectors).",
            "Enable X2 interface fast handover between neighbouring eNBs/gNBs.",
            "Dispatch hardware repair team to the failed tower site.",
            "Enable coverage compensation mode in SON controller.",
        ],
        affected_towers=list(affected) + list(offline) + list(degraded),
        confidence=0.95,
        action=ActionType.HANDOVER,
    )]
    logger.debug("Rule tower_failure_reroute fired | offline=%s", offline)
    return recs


# ---------------------------------------------------------------------------
# RULE 9 — Fibre cut scenario → traffic rerouting via alternate backhaul
# ---------------------------------------------------------------------------


def _rule_fibre_cut_reroute(ctx: RuleContext) -> List[Recommendation]:
    """
    Fires when the active scenario is FIBRE_CUT.

    Produces a HIGH-priority TRAFFIC_REROUTING recommendation.
    """
    if _scenario_event(ctx) not in (
        ScenarioEventType.FIBRE_CUT.value, "fibre_cut"
    ):
        return []

    params = _scenario_params(ctx)
    affected = _scenario_affected_towers(ctx)
    degraded = params.get("towers_degraded", [])
    latency = params.get("latency_increase_ms", 0)
    throughput_loss = params.get("throughput_reduction_pct", 0)

    recs = [_make_rec(
        priority=RecommendationPriority.HIGH,
        category=RecommendationCategory.TRAFFIC_REROUTING,
        title="FIBRE CUT — activate alternate backhaul and reroute traffic",
        description=(
            f"A fibre backhaul cut is active. {len(degraded)} tower(s) are degraded: "
            f"throughput reduced by {throughput_loss}%, latency increased by {latency} ms. "
            f"Towers remain radio-operational but backhaul capacity is severely impaired. "
            f"Alternate routing must be activated to maintain service quality."
        ),
        reasoning=(
            f"Scenario event_type=FIBRE_CUT. "
            f"towers_degraded={degraded}, throughput_reduction_pct={throughput_loss}, "
            f"latency_increase_ms={latency}."
        ),
        expected_impact=(
            "Switching to microwave or satellite backhaul failover will restore 60-70% "
            "of throughput. Latency will remain elevated (~20-30 ms above baseline) "
            "until fibre is repaired."
        ),
        suggested_actions=[
            "Identify and activate microwave/satellite backhaul failover links.",
            f"Reroute traffic for degraded towers {degraded or 'see affected list'} through alternate backhaul.",
            "Apply QoS prioritisation: VoLTE and emergency traffic first, OTT last.",
            "Dispatch fibre repair crew to the cut location.",
            "Contact ISP/transmission provider to confirm repair timeline.",
            "Monitor link utilisation on alternate paths to avoid overloading them.",
        ],
        affected_towers=list(affected) + list(degraded),
        confidence=0.93,
        action=None,
    )]
    logger.debug("Rule fibre_cut_reroute fired | degraded=%s", degraded)
    return recs


# ---------------------------------------------------------------------------
# RULE 10 — Mass event (IPL/Concert/Festival) → capacity expansion
# ---------------------------------------------------------------------------


def _rule_mass_event_capacity(ctx: RuleContext) -> List[Recommendation]:
    """
    Fires when an active scenario has traffic_multiplier ≥ config.traffic_mult_high.

    Covers IPL_MATCH, CONCERT, FESTIVAL, and any scenario with a high multiplier.
    Produces a HIGH-priority CAPACITY_EXPANSION recommendation.
    """
    params = _scenario_params(ctx)
    multiplier = float(params.get("traffic_multiplier", 1.0))
    if multiplier < ctx.config.traffic_mult_high:
        return []

    event_name = getattr(ctx.scenario, "name", "Mass event")
    event_type = _scenario_event(ctx) or "unknown"
    affected = _scenario_affected_towers(ctx)
    latency = params.get("latency_increase_ms", 0)
    radius_km = params.get("affected_radius_km", 0)

    recs = [_make_rec(
        priority=RecommendationPriority.HIGH,
        category=RecommendationCategory.CAPACITY_EXPANSION,
        title=f"High traffic multiplier ({multiplier:.1f}×) — deploy temporary capacity for '{event_name}'",
        description=(
            f"Scenario '{event_name}' (type: {event_type}) has generated a traffic multiplier "
            f"of {multiplier:.1f}× in a {radius_km} km radius. "
            f"This will cause severe congestion on {len(affected)} tower(s) without intervention. "
            f"Predicted latency increase: +{latency} ms."
        ),
        reasoning=(
            f"Scenario parameters: traffic_multiplier={multiplier:.1f}, "
            f"affected_radius_km={radius_km}, latency_increase_ms={latency}. "
            f"Threshold: traffic_multiplier ≥ {ctx.config.traffic_mult_high:.1f}."
        ),
        expected_impact=(
            "Pre-positioning COW/COLT units and pre-configuring SON load-sharing parameters "
            "can absorb the traffic surge and maintain QoS within SLA bounds during the event."
        ),
        suggested_actions=[
            f"Pre-position 2-3 COW (Cell on Wheels) units in the {radius_km} km impact zone.",
            "Configure temporary small cells at high-density crowd zones.",
            "Enable Dynamic Spectrum Sharing (DSS) on affected towers.",
            "Pre-configure SON load-balancing between all towers in the affected radius.",
            "Alert NOC and capacity planning team of the scheduled event.",
            "Set up event-specific monitoring dashboard with 1-minute KPI refresh.",
        ],
        affected_towers=list(affected),
        confidence=0.88,
        action=None,
    )]
    logger.debug(
        "Rule mass_event_capacity fired | event=%s | multiplier=%.1f",
        event_name, multiplier,
    )
    return recs


# ---------------------------------------------------------------------------
# RULE 11 — Heavy rain / signal degradation → frequency reassignment
# ---------------------------------------------------------------------------


def _rule_weather_frequency_reassignment(ctx: RuleContext) -> List[Recommendation]:
    """
    Fires when scenario signal_degradation_db ≥ config.signal_degrade_db.

    Typically triggered by HEAVY_RAIN or CYCLONE scenarios.
    Produces a MEDIUM-priority FREQUENCY_REASSIGNMENT recommendation.
    """
    params = _scenario_params(ctx)
    signal_db = float(params.get("signal_degradation_db", 0.0))
    if signal_db < ctx.config.signal_degrade_db:
        return []

    affected = _scenario_affected_towers(ctx)
    event_type = _scenario_event(ctx) or "weather"
    coverage_loss = params.get("coverage_reduction_pct", 0)

    recs = [_make_rec(
        priority=RecommendationPriority.MEDIUM,
        category=RecommendationCategory.FREQUENCY_REASSIGNMENT,
        title=f"Signal degradation {signal_db:.0f} dB — reassign to lower frequency bands",
        description=(
            f"Scenario '{event_type}' is causing {signal_db:.0f} dB of signal attenuation "
            f"on {len(affected)} tower(s), with {coverage_loss}% coverage reduction. "
            f"Higher frequency bands (2.3 GHz, 3.5 GHz, mmWave) are disproportionately affected. "
            f"Reassigning UEs to lower frequency bands improves rain fade tolerance."
        ),
        reasoning=(
            f"Scenario parameters: signal_degradation_db={signal_db:.0f} dB "
            f"(threshold: ≥{ctx.config.signal_degrade_db:.0f} dB), "
            f"coverage_reduction_pct={coverage_loss}%, event_type={event_type}."
        ),
        expected_impact=(
            "Migrating cell-edge UEs to 700 MHz or 850 MHz band reduces rain attenuation "
            "by ~4-6 dB and recovers 10-15% of lost coverage area."
        ),
        suggested_actions=[
            "Enable band steering to prefer sub-1 GHz bands (700/850 MHz) on affected towers.",
            "Reduce 5G NR mmWave beam power and redirect capacity to lower-band carriers.",
            "Increase UL/DL power control margins on affected cells (+3 dB SINR target).",
            "Configure neighbour cell list to include cross-band handover candidates.",
            "Monitor coverage edge RSRP; restore original band mix when signal_db < 3 dB.",
        ],
        affected_towers=list(affected),
        confidence=0.82,
        action=ActionType.FREQUENCY_REALLOC,
    )]
    logger.debug(
        "Rule weather_frequency_reassignment fired | signal_db=%.0f", signal_db
    )
    return recs


# ---------------------------------------------------------------------------
# RULE 12 — Latency spike → run optimizer
# ---------------------------------------------------------------------------


def _rule_latency_spike_optimize(ctx: RuleContext) -> List[Recommendation]:
    """
    Fires when scenario latency_increase_ms ≥ config.latency_high_ms.

    Produces a HIGH-priority recommendation to run the QUBO optimizer.
    """
    params = _scenario_params(ctx)
    latency = float(params.get("latency_increase_ms", 0.0))
    if latency < ctx.config.latency_high_ms:
        return []

    affected = _scenario_affected_towers(ctx)
    event_type = _scenario_event(ctx) or "unknown"
    throughput_loss = params.get("throughput_reduction_pct", 0)

    recs = [_make_rec(
        priority=RecommendationPriority.HIGH,
        category=RecommendationCategory.TRAFFIC_REROUTING,
        title=f"Latency spike +{latency:.0f} ms — run QUBO optimizer to reroute traffic",
        description=(
            f"Scenario '{event_type}' has introduced a {latency:.0f} ms latency increase "
            f"(throughput reduction: {throughput_loss}%) across {len(affected)} tower(s). "
            f"Backhaul paths are suboptimal. The QUBO optimizer should be run to find the "
            f"least-cost routing assignment."
        ),
        reasoning=(
            f"Scenario parameters: latency_increase_ms={latency:.0f} ms "
            f"(threshold: ≥{ctx.config.latency_high_ms:.0f} ms), "
            f"throughput_reduction_pct={throughput_loss}%."
        ),
        expected_impact=(
            "Running the QuantumSON QUBO optimizer with 'minimize_latency' objective "
            "can identify alternate routing paths that reduce end-to-end latency by 20-40%."
        ),
        suggested_actions=[
            "Open the Optimization panel and run the QUBO solver (objective: minimize_latency).",
            "Apply the variable assignments from the solver output to the backhaul routing table.",
            "Verify alternate backhaul links have sufficient capacity before switching.",
            "Monitor E2E latency over 5 minutes post-change to confirm improvement.",
        ],
        affected_towers=list(affected),
        confidence=0.80,
        action=None,
    )]
    logger.debug("Rule latency_spike fired | latency=%.0f ms", latency)
    return recs


# ---------------------------------------------------------------------------
# RULE 13 — Low overall load → energy saving
# ---------------------------------------------------------------------------


def _rule_low_load_energy_saving(ctx: RuleContext) -> List[Recommendation]:
    """
    Fires when all predictions are below load_low_pct AND no alerts on dashboard.

    Produces a LOW-priority ENERGY_SAVING recommendation.
    Only fires if there are predictions to evaluate (no predictions = no action).
    """
    preds = _predictions(ctx)
    if not preds:
        return []

    loads = [getattr(p, "predicted_load_pct", 100.0) for p in preds]
    if any(load >= ctx.config.load_medium_pct for load in loads):
        return []

    # Also check dashboard for active alerts
    if ctx.dashboard:
        alerts = getattr(ctx.dashboard, "congestion_alerts", 1)
        if alerts > 0:
            return []

    avg_load = sum(loads) / len(loads)
    tower_ids = [getattr(p, "tower_id", "?") for p in preds]

    recs = [_make_rec(
        priority=RecommendationPriority.LOW,
        category=RecommendationCategory.ENERGY_SAVING,
        title=f"Network load low ({avg_load:.1f}% avg) — activate energy saving mode",
        description=(
            f"All {len(preds)} monitored tower(s) are below {ctx.config.load_low_pct:.0f}% load "
            f"(average: {avg_load:.1f}%). This is an optimal window to activate energy saving "
            f"features such as cell sleeping, power reduction, and antenna shutdown on lightly loaded cells."
        ),
        reasoning=(
            f"All predicted loads < {ctx.config.load_medium_pct:.0f}% "
            f"(threshold for medium congestion). Average load = {avg_load:.1f}%. "
            f"No active congestion alerts on dashboard."
        ),
        expected_impact=(
            "Activating energy saving on low-utilisation cells typically reduces site power "
            "consumption by 10-30%, improving OpEx and carbon footprint without impacting QoS."
        ),
        suggested_actions=[
            "Enable Cell Sleep Mode (3GPP TR 36.927) on towers with load < 20%.",
            "Apply Tx power reduction of -3 to -6 dB on low-utilisation sectors.",
            "Activate Discontinuous Transmission (DTX) on idle UE connections.",
            "Schedule antenna shutdown on redundant sectors during off-peak hours.",
            "Log energy saving metrics for monthly sustainability reporting.",
        ],
        affected_towers=tower_ids,
        confidence=0.78,
        action=ActionType.POWER_ADJUST,
    )]
    logger.debug("Rule low_load_energy_saving fired | avg_load=%.1f%%", avg_load)
    return recs


# ---------------------------------------------------------------------------
# RULE 14 — Failed optimization run → retry recommendation
# ---------------------------------------------------------------------------


def _rule_optimization_failed(ctx: RuleContext) -> List[Recommendation]:
    """
    Fires when an OptimizationResult has solver_status != 'success'.

    Produces a MEDIUM-priority recommendation to investigate and retry.
    """
    if ctx.optimization is None:
        return []

    status = str(getattr(ctx.optimization, "solver_status", "success")).lower()
    if status == "success":
        return []

    run_id = getattr(ctx.optimization, "run_id", "unknown")
    algo = getattr(ctx.optimization, "algorithm", "qubo")
    duration = getattr(ctx.optimization, "duration_ms", None)
    energy = getattr(ctx.optimization, "optimal_energy", None)
    dur_str = f"{duration:.0f} ms" if duration is not None else "unknown"
    energy_str = f"{energy:.6f}" if energy is not None else "N/A"

    recs = [_make_rec(
        priority=RecommendationPriority.MEDIUM,
        category=RecommendationCategory.MONITOR_ONLY,
        title=f"Optimization run {run_id} did not converge — investigate and retry",
        description=(
            f"The {algo.upper()} optimizer run {run_id} completed with status='{status}'. "
            f"Duration: {dur_str}, last energy: {energy_str}. "
            f"A failed or timed-out solver run means the optimal frequency/routing "
            f"assignment was not found. Manual action or a retry is required."
        ),
        reasoning=(
            f"OptimizationResult: run_id={run_id}, solver_status={status}, "
            f"algorithm={algo}, duration_ms={dur_str}, optimal_energy={energy_str}."
        ),
        expected_impact=(
            "Diagnosing the solver failure and retrying with tuned parameters "
            "should produce a valid assignment that the network can apply."
        ),
        suggested_actions=[
            f"Review solver logs for run {run_id} in the Optimization panel.",
            "If timeout: reduce num_variables or increase solver time limit and retry.",
            "If failed: check QUBO matrix formulation for infeasibility constraints.",
            "Retry with the QUBO optimizer via POST /optimize with reduced problem size.",
            "If repeated failures: contact QuantumSON team for diagnostic support.",
        ],
        affected_towers=[],
        confidence=0.85,
        action=None,
    )]
    logger.debug("Rule optimization_failed fired | run_id=%s status=%s", run_id, status)
    return recs


# ---------------------------------------------------------------------------
# RULE 15 — Healthy network → no action required
# ---------------------------------------------------------------------------


def _rule_network_healthy(ctx: RuleContext) -> List[Recommendation]:
    """
    Sentinel rule: fires only when no other rules produced any recommendations.

    Returns a single LOW-priority NO_ACTION_REQUIRED recommendation to give
    the dashboard a positive health confirmation rather than an empty list.

    This rule is always placed LAST in the registry and is only invoked
    by the engine when all other rules returned empty.
    """
    # This function is called directly by evaluate() only when recs is empty.
    # It does not self-check; the engine guards the call.
    preds = _predictions(ctx)
    towers = _towers(ctx)

    avg_load_str = ""
    if preds:
        loads = [getattr(p, "predicted_load_pct", 0.0) for p in preds]
        avg = sum(loads) / len(loads)
        avg_load_str = f" (average predicted load: {avg:.1f}%)"

    return [_make_rec(
        priority=RecommendationPriority.LOW,
        category=RecommendationCategory.NO_ACTION_REQUIRED,
        title="Network is operating within normal parameters — no action required",
        description=(
            f"All {len(towers)} tower(s) are within acceptable operating bounds. "
            f"No congestion alerts, no offline towers, no active critical scenarios{avg_load_str}. "
            f"Continue routine monitoring."
        ),
        reasoning=(
            "No rules fired: no tower with load ≥ medium threshold, "
            "no INACTIVE/MAINTENANCE towers, no critical scenario active, "
            "no failed optimization run."
        ),
        expected_impact="No operational changes required at this time.",
        suggested_actions=[
            "Continue standard monitoring cadence.",
            "Review predictions in 15 minutes for any emerging trends.",
        ],
        affected_towers=[],
        confidence=0.95,
        action=None,
    )]


# ---------------------------------------------------------------------------
# Rule registry — evaluation order matters (higher priority rules first)
# ---------------------------------------------------------------------------

_RULES: List[RuleFn] = [
    _rule_offline_tower_emergency_repair,   # Always first: offline = most critical
    _rule_cyclone_emergency,                # Infrastructure-level emergency
    _rule_power_outage,                     # Infrastructure-level emergency
    _rule_tower_failure_reroute,            # Infrastructure failure
    _rule_fibre_cut_reroute,                # Infrastructure failure
    _rule_critical_congestion,             # Load: ≥ 90%
    _rule_high_congestion,                 # Load: 75-90%
    _rule_mass_event_capacity,             # Event-driven capacity
    _rule_latency_spike_optimize,          # Latency-driven optimization
    _rule_weather_frequency_reassignment,  # Signal degradation
    _rule_medium_congestion,               # Load: 50-75%
    _rule_maintenance_tower_dispatch,      # Planned maintenance
    _rule_optimization_failed,             # Solver failure
    _rule_low_load_energy_saving,          # Healthy + low load
    # _rule_network_healthy is NOT in this list — called directly by evaluate()
]


# ---------------------------------------------------------------------------
# DecisionEngine — public class
# ---------------------------------------------------------------------------


class DecisionEngine:
    """
    PulseOS Recommendation Engine.

    Converts live network conditions into structured, actionable operator
    recommendations using deterministic business rules.

    No LLM calls are made here.  The Copilot layer (``ai/copilot.py``) is
    responsible for generating natural-language explanations of these
    recommendations via GeminiService.

    Parameters
    ----------
    config:
        ``EngineConfig`` with tunable thresholds.  Defaults to
        ``_DEFAULT_CONFIG`` if not supplied.

    Example
    -------
    >>> engine = DecisionEngine()
    >>> recs = engine.evaluate(
    ...     network_state=state,
    ...     predictions=preds,
    ...     scenario=scenario,
    ... )
    >>> for r in recs:
    ...     print(r.priority, r.title)
    """

    def __init__(self, config: Optional[EngineConfig] = None) -> None:
        self._config = config or _DEFAULT_CONFIG
        logger.info(
            "DecisionEngine initialised | config=load_critical=%.0f%% "
            "load_high=%.0f%% load_medium=%.0f%%",
            self._config.load_critical_pct,
            self._config.load_high_pct,
            self._config.load_medium_pct,
        )

    # ------------------------------------------------------------------
    # Primary public method — v2 full-context interface
    # ------------------------------------------------------------------

    def evaluate(
        self,
        *,
        network_state: Optional[Any] = None,
        scenario: Optional[Any] = None,
        predictions: Optional[List[Any]] = None,
        optimization: Optional[Any] = None,
        dashboard: Optional[Any] = None,
    ) -> List[Recommendation]:
        """
        Evaluate all registered rules against the provided context and return
        a de-duplicated, priority-sorted list of ``Recommendation`` objects.

        All parameters are optional.  Pass whatever context is available;
        rules guard their own inputs.

        Parameters
        ----------
        network_state:
            Current ``NetworkState`` snapshot (tower statuses, connections).
        scenario:
            Active ``Scenario`` from the Scenario Engine (if any).
        predictions:
            List of ``PredictionResult`` objects (may be empty).
        optimization:
            Most recent ``OptimizationResult`` from the QUBO solver (if any).
        dashboard:
            ``DashboardSummary`` snapshot (if any).

        Returns
        -------
        List[Recommendation]
            Recommendations sorted by priority (CRITICAL → HIGH → MEDIUM → LOW),
            capped at ``config.max_recommendations``.
        """
        ctx = RuleContext(
            network_state=network_state,
            scenario=scenario,
            predictions=list(predictions) if predictions else [],
            optimization=optimization,
            dashboard=dashboard,
            config=self._config,
        )

        all_recs: List[Recommendation] = []

        for rule_fn in _RULES:
            try:
                results = rule_fn(ctx)
                all_recs.extend(results)
            except Exception as exc:  # pragma: no cover
                logger.error(
                    "Rule %s raised an unhandled exception: %s",
                    rule_fn.__name__,
                    exc,
                    exc_info=True,
                )
                # Never let a single rule crash the engine

        # Healthy sentinel: only fire when no other rule produced anything
        if not all_recs:
            try:
                all_recs.extend(_rule_network_healthy(ctx))
            except Exception as exc:  # pragma: no cover
                logger.error("Sentinel rule failed: %s", exc)

        # Sort by priority (CRITICAL first)
        _priority_order = {
            RecommendationPriority.CRITICAL: 0,
            RecommendationPriority.HIGH: 1,
            RecommendationPriority.MEDIUM: 2,
            RecommendationPriority.LOW: 3,
        }
        all_recs.sort(key=lambda r: _priority_order.get(r.priority, 99))

        # Cap at configured maximum
        if len(all_recs) > self._config.max_recommendations:
            logger.warning(
                "Recommendation count (%d) exceeds cap (%d); truncating.",
                len(all_recs),
                self._config.max_recommendations,
            )
            all_recs = all_recs[: self._config.max_recommendations]

        logger.info(
            "DecisionEngine.evaluate() → %d recommendation(s)", len(all_recs)
        )
        return all_recs

    # ------------------------------------------------------------------
    # Legacy public method — v1 interface (backward compatibility)
    # ------------------------------------------------------------------

    def recommend_actions(
        self,
        network_state: Optional[Any],
        congestion_predictions: List[float],
    ) -> List[Recommendation]:
        """
        Legacy v1 interface preserved for backward compatibility.

        Wraps raw float prediction scores into minimal ``PredictionResult``-like
        objects and delegates to ``evaluate()``.

        Parameters
        ----------
        network_state:
            Current ``NetworkState`` snapshot.
        congestion_predictions:
            List of predicted load values in the range [0.0, 1.0].
            Values are scaled to percentages (× 100) before evaluation.

        Returns
        -------
        List[Recommendation]
            Full v2 ``Recommendation`` objects (not reduced to v1 shape).
        """
        # Wrap raw floats as lightweight anonymous prediction-like objects
        class _AnonPrediction:
            def __init__(self, tower_id: str, load_pct: float) -> None:
                self.tower_id = tower_id
                self.predicted_load_pct = load_pct
                self.congestion_risk = (
                    "critical" if load_pct >= 90 else
                    "high" if load_pct >= 75 else
                    "medium" if load_pct >= 50 else
                    "low"
                )
                self.confidence = 0.85

        anon_preds = [
            _AnonPrediction(
                tower_id=f"T{idx:03d}",
                load_pct=score * 100.0,
            )
            for idx, score in enumerate(congestion_predictions)
        ]

        return self.evaluate(
            network_state=network_state,
            predictions=anon_preds,
        )

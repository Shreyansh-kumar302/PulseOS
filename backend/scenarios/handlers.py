"""
Scenario Handlers
=================
Pure handler functions — one per ScenarioEventType.

Each handler:
  1. Merges user-provided parameter overrides with scenario defaults.
  2. Selects the appropriate towers from the live NetworkState.
  3. Computes a ScenarioEffect with all simulation results populated.
  4. Generates a human-readable operator summary.

Design rules:
  - Handlers are pure functions (no side effects, no I/O).
  - All numeric decisions come from the merged config — no magic numbers
    inside handler bodies. Defaults live in effects.SCENARIO_DEFAULTS.
  - Tower selection is deterministic (sorted by ID, no randomness).
  - Unknown keys in ScenarioRequest.parameters are silently ignored.

Adding a new scenario:
  1. Add the ScenarioEventType value to schemas/scenario.py.
  2. Add its defaults to SCENARIO_DEFAULTS in scenarios/effects.py.
  3. Write a handler function here following the existing pattern.
  4. Register it in HANDLER_REGISTRY at the bottom of this file.
"""
from typing import Any, Callable, Dict, List

from schemas.network import NetworkState
from schemas.scenario import ScenarioEventType, ScenarioRequest
from schemas.tower import TowerStatus
from scenarios.effects import SCENARIO_DEFAULTS, ScenarioEffect


# ---------------------------------------------------------------------------
# Private utilities
# ---------------------------------------------------------------------------

def _merge_config(
    defaults: Dict[str, Any],
    user_params: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Merges user-provided parameter overrides into the scenario defaults.

    Only keys that already exist in 'defaults' are accepted.
    Unknown user keys are silently ignored (prevents parameter injection).
    Values are coerced to the same type as the default to catch bad input.
    """
    config = dict(defaults)
    for key, default_value in defaults.items():
        if key in user_params:
            try:
                config[key] = type(default_value)(user_params[key])
            except (TypeError, ValueError):
                pass  # leave the default intact if coercion fails
    return config


def _select_towers(
    network: NetworkState,
    count: int,
    preferred_ids: List[str],
    require_active: bool = True,
) -> List[str]:
    """
    Deterministically selects up to 'count' towers for a scenario effect.

    Selection priority:
      1. Caller-specified 'preferred_ids' (validated against live network).
      2. Auto-selected from live network, sorted by ID (deterministic).

    Args:
        network:        Current NetworkState snapshot.
        count:          Maximum number of towers to select.
        preferred_ids:  Tower IDs requested by the caller. May be empty.
        require_active: When auto-selecting, restrict to ACTIVE towers only.

    Returns:
        List of tower IDs, length <= count.
    """
    if count <= 0:
        return []

    if preferred_ids:
        existing_ids = {t.id for t in network.towers}
        valid = [tid for tid in preferred_ids if tid in existing_ids]
        return valid[:count]

    # Auto-select: sort by ID for a deterministic, reproducible result
    candidates = sorted(network.towers, key=lambda t: t.id)
    if require_active:
        candidates = [t for t in candidates if t.status == TowerStatus.ACTIVE]

    return [t.id for t in candidates[:count]]


def _fmt_list(ids: List[str]) -> str:
    """Formats a list of tower IDs for display in summary strings."""
    if not ids:
        return "none"
    return ", ".join(ids)


# ---------------------------------------------------------------------------
# Crowd / mass-event handlers
# ---------------------------------------------------------------------------

def handle_ipl_match(
    request: ScenarioRequest,
    network: NetworkState,
    defaults: Dict[str, Any],
) -> ScenarioEffect:
    """
    IPL Match — dense crowd, heavy multimedia consumption.

    Models 40,000–80,000 spectators concentrated in a 2 km stadium radius.
    Extreme download demand (live scores, highlight clips) and moderate
    upload (social media, WhatsApp Status) create heavy asymmetric load.
    Signal interference from dense device proximity degrades SNR slightly.
    """
    config = _merge_config(defaults, request.parameters)

    degraded = _select_towers(
        network,
        count=int(config["max_degraded_towers"]),
        preferred_ids=request.affected_tower_ids,
        require_active=True,
    )

    summary = (
        f"IPL match simulation: {len(degraded)} tower(s) under heavy localised load "
        f"[{_fmt_list(degraded)}]. "
        f"Traffic: {config['traffic_multiplier']:.1f}× | "
        f"Bandwidth demand: +{config['bandwidth_demand_increase_pct']:.0f}% | "
        f"Upload bias: {config['upload_bias']:.1f}× | "
        f"Latency: +{config['latency_increase_ms']:.0f} ms | "
        f"Signal: −{config['signal_degradation_db']:.1f} dB | "
        f"Energy: {config['energy_multiplier']:.1f}× | "
        f"Radius: {config['affected_radius_km']:.1f} km."
    )

    return ScenarioEffect(
        traffic_multiplier=config["traffic_multiplier"],
        bandwidth_demand_increase_pct=config["bandwidth_demand_increase_pct"],
        upload_bias=config["upload_bias"],
        throughput_reduction_pct=config["throughput_reduction_pct"],
        latency_increase_ms=config["latency_increase_ms"],
        signal_degradation_db=config["signal_degradation_db"],
        coverage_reduction_pct=config["coverage_reduction_pct"],
        energy_multiplier=config["energy_multiplier"],
        affected_radius_km=config["affected_radius_km"],
        towers_offline=[],
        towers_degraded=degraded,
        summary=summary,
    )


def handle_concert(
    request: ScenarioRequest,
    network: NetworkState,
    defaults: Dict[str, Any],
) -> ScenarioEffect:
    """
    Concert — dense crowd, heavily upload-biased traffic.

    Models 20,000–30,000 attendees at a venue. The defining characteristic
    is simultaneous live-streaming (Instagram Reels, YouTube Live) which
    produces a strongly upload-biased traffic pattern — unlike IPL where
    download (content consumption) dominates.
    """
    config = _merge_config(defaults, request.parameters)

    degraded = _select_towers(
        network,
        count=int(config["max_degraded_towers"]),
        preferred_ids=request.affected_tower_ids,
        require_active=True,
    )

    summary = (
        f"Concert simulation: {len(degraded)} tower(s) experiencing upload-heavy load "
        f"[{_fmt_list(degraded)}]. "
        f"Traffic: {config['traffic_multiplier']:.1f}× | "
        f"Upload bias: {config['upload_bias']:.1f}× (live-streaming) | "
        f"Latency: +{config['latency_increase_ms']:.0f} ms | "
        f"Signal: −{config['signal_degradation_db']:.1f} dB (crowd multipath) | "
        f"Energy: {config['energy_multiplier']:.1f}× | "
        f"Radius: {config['affected_radius_km']:.1f} km."
    )

    return ScenarioEffect(
        traffic_multiplier=config["traffic_multiplier"],
        bandwidth_demand_increase_pct=config["bandwidth_demand_increase_pct"],
        upload_bias=config["upload_bias"],
        throughput_reduction_pct=config["throughput_reduction_pct"],
        latency_increase_ms=config["latency_increase_ms"],
        signal_degradation_db=config["signal_degradation_db"],
        coverage_reduction_pct=config["coverage_reduction_pct"],
        energy_multiplier=config["energy_multiplier"],
        affected_radius_km=config["affected_radius_km"],
        towers_offline=[],
        towers_degraded=degraded,
        summary=summary,
    )


def handle_festival(
    request: ScenarioRequest,
    network: NetworkState,
    defaults: Dict[str, Any],
) -> ScenarioEffect:
    """
    Festival — city-wide distributed traffic increase.

    Models a major city-wide celebration (Diwali, New Year, Navratri).
    Unlike the stadium scenarios, traffic increase is distributed across
    all active towers rather than concentrated at a single location.
    Social media posting (photos, reels) drives moderate upload demand.
    """
    config = _merge_config(defaults, request.parameters)

    # City-wide: affect all active towers, ignore preferred_ids for scope
    degraded = _select_towers(
        network,
        count=int(config["max_degraded_towers"]),
        preferred_ids=request.affected_tower_ids,
        require_active=True,
    )

    summary = (
        f"Festival simulation (city-wide): {len(degraded)} tower(s) under distributed load "
        f"[{_fmt_list(degraded)}]. "
        f"Traffic: {config['traffic_multiplier']:.1f}× across network | "
        f"Bandwidth demand: +{config['bandwidth_demand_increase_pct']:.0f}% | "
        f"Upload bias: {config['upload_bias']:.1f}× | "
        f"Latency: +{config['latency_increase_ms']:.0f} ms | "
        f"Coverage reduction: {config['coverage_reduction_pct']:.0f}% | "
        f"Energy: {config['energy_multiplier']:.1f}×."
    )

    return ScenarioEffect(
        traffic_multiplier=config["traffic_multiplier"],
        bandwidth_demand_increase_pct=config["bandwidth_demand_increase_pct"],
        upload_bias=config["upload_bias"],
        throughput_reduction_pct=config["throughput_reduction_pct"],
        latency_increase_ms=config["latency_increase_ms"],
        signal_degradation_db=config["signal_degradation_db"],
        coverage_reduction_pct=config["coverage_reduction_pct"],
        energy_multiplier=config["energy_multiplier"],
        affected_radius_km=config["affected_radius_km"],
        towers_offline=[],
        towers_degraded=degraded,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Weather handlers
# ---------------------------------------------------------------------------

def handle_heavy_rain(
    request: ScenarioRequest,
    network: NetworkState,
    defaults: Dict[str, Any],
) -> ScenarioEffect:
    """
    Heavy Rain — atmospheric signal attenuation, reduced coverage.

    Models ~80 mm/hr rainfall. Applies ITU-R P.838 rain attenuation:
    approximately 6 dB signal loss on 2.4 GHz links. Higher frequencies
    (mmWave 5G bands) experience significantly worse attenuation.
    Mobile traffic decreases slightly as people stay indoors.
    All towers are affected as this is an atmospheric event.
    """
    config = _merge_config(defaults, request.parameters)

    degraded = _select_towers(
        network,
        count=int(config["max_degraded_towers"]),
        preferred_ids=request.affected_tower_ids,
        require_active=True,
    )

    summary = (
        f"Heavy rain simulation (~80 mm/hr): {len(degraded)} tower(s) affected "
        f"[{_fmt_list(degraded)}]. "
        f"Signal: −{config['signal_degradation_db']:.1f} dB (ITU-R P.838 rain attenuation) | "
        f"Coverage: −{config['coverage_reduction_pct']:.0f}% | "
        f"Throughput: −{config['throughput_reduction_pct']:.0f}% (ARQ retransmissions) | "
        f"Latency: +{config['latency_increase_ms']:.0f} ms | "
        f"Traffic: {config['traffic_multiplier']:.1f}× (mobile usage drops indoors) | "
        f"Radius: {config['affected_radius_km']:.0f} km."
    )

    return ScenarioEffect(
        traffic_multiplier=config["traffic_multiplier"],
        bandwidth_demand_increase_pct=config["bandwidth_demand_increase_pct"],
        upload_bias=config["upload_bias"],
        throughput_reduction_pct=config["throughput_reduction_pct"],
        latency_increase_ms=config["latency_increase_ms"],
        signal_degradation_db=config["signal_degradation_db"],
        coverage_reduction_pct=config["coverage_reduction_pct"],
        energy_multiplier=config["energy_multiplier"],
        affected_radius_km=config["affected_radius_km"],
        towers_offline=[],
        towers_degraded=degraded,
        summary=summary,
    )


def handle_cyclone(
    request: ScenarioRequest,
    network: NetworkState,
    defaults: Dict[str, Any],
) -> ScenarioEffect:
    """
    Cyclone — structural damage, power disruption, severe degradation.

    Models a Category 3–4 cyclone (200+ km/h sustained winds).
    Multiple failure modes operate simultaneously:
      - Physical antenna/tower damage → towers offline
      - Grid power loss → battery backup only (limited runtime)
      - Extreme atmospheric attenuation → 18 dB signal degradation
      - Backhaul rerouting → 80 ms latency increase
      - Emergency communications → traffic spike despite damage
    """
    config = _merge_config(defaults, request.parameters)

    n_offline = int(config["max_offline_towers"])
    n_degraded = int(config["max_degraded_towers"])

    # Offline towers: structural failures — from beginning of sorted list
    offline = _select_towers(
        network,
        count=n_offline,
        preferred_ids=request.affected_tower_ids[:n_offline],
        require_active=True,
    )

    # Degraded towers: remaining active towers in affected area
    all_candidates = _select_towers(
        network,
        count=n_offline + n_degraded,
        preferred_ids=[],
        require_active=True,
    )
    degraded = [tid for tid in all_candidates if tid not in offline][:n_degraded]

    summary = (
        f"Cyclone simulation (Category 3–4): "
        f"{len(offline)} tower(s) OFFLINE [{_fmt_list(offline)}], "
        f"{len(degraded)} tower(s) degraded [{_fmt_list(degraded)}]. "
        f"Signal: −{config['signal_degradation_db']:.0f} dB | "
        f"Coverage: −{config['coverage_reduction_pct']:.0f}% | "
        f"Latency: +{config['latency_increase_ms']:.0f} ms (backhaul rerouting) | "
        f"Throughput: −{config['throughput_reduction_pct']:.0f}% | "
        f"Energy: {config['energy_multiplier']:.1f}× (battery backup only) | "
        f"Emergency traffic: {config['traffic_multiplier']:.1f}× | "
        f"Radius: {config['affected_radius_km']:.0f} km."
    )

    return ScenarioEffect(
        traffic_multiplier=config["traffic_multiplier"],
        bandwidth_demand_increase_pct=config["bandwidth_demand_increase_pct"],
        upload_bias=config["upload_bias"],
        throughput_reduction_pct=config["throughput_reduction_pct"],
        latency_increase_ms=config["latency_increase_ms"],
        signal_degradation_db=config["signal_degradation_db"],
        coverage_reduction_pct=config["coverage_reduction_pct"],
        energy_multiplier=config["energy_multiplier"],
        affected_radius_km=config["affected_radius_km"],
        towers_offline=offline,
        towers_degraded=degraded,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Infrastructure failure handlers
# ---------------------------------------------------------------------------

def handle_tower_failure(
    request: ScenarioRequest,
    network: NetworkState,
    defaults: Dict[str, Any],
) -> ScenarioEffect:
    """
    Tower Failure — single site outage with neighbour overload.

    A single tower experiences a hardware fault (power amplifier failure,
    baseband unit crash, antenna collapse). All connected UEs must
    perform emergency handover to adjacent towers, which become overloaded
    and exhibit increased latency and reduced throughput.

    Selection logic:
      - First tower specified (or auto-selected) → goes offline
      - Next two active towers → degraded (absorbing handover load)
    """
    config = _merge_config(defaults, request.parameters)

    n_offline = int(config["max_offline_towers"])
    n_degraded = int(config["max_degraded_towers"])

    # The failing tower — first in the preferred list, or auto-select first
    offline = _select_towers(
        network,
        count=n_offline,
        preferred_ids=request.affected_tower_ids,
        require_active=True,
    )

    # Neighbouring towers that absorb the load — must NOT include the failed one
    all_active = _select_towers(
        network,
        count=n_offline + n_degraded,
        preferred_ids=[],
        require_active=True,
    )
    degraded = [tid for tid in all_active if tid not in offline][:n_degraded]

    summary = (
        f"Tower failure simulation: "
        f"Tower [{_fmt_list(offline)}] is OFFLINE. "
        f"Adjacent towers [{_fmt_list(degraded)}] absorbing handover load. "
        f"Traffic on neighbours: {config['traffic_multiplier']:.1f}× | "
        f"Throughput: −{config['throughput_reduction_pct']:.0f}% | "
        f"Latency: +{config['latency_increase_ms']:.0f} ms | "
        f"Coverage gap: −{config['coverage_reduction_pct']:.0f}% | "
        f"Energy on neighbours: {config['energy_multiplier']:.1f}×."
    )

    return ScenarioEffect(
        traffic_multiplier=config["traffic_multiplier"],
        bandwidth_demand_increase_pct=config["bandwidth_demand_increase_pct"],
        upload_bias=config["upload_bias"],
        throughput_reduction_pct=config["throughput_reduction_pct"],
        latency_increase_ms=config["latency_increase_ms"],
        signal_degradation_db=config["signal_degradation_db"],
        coverage_reduction_pct=config["coverage_reduction_pct"],
        energy_multiplier=config["energy_multiplier"],
        affected_radius_km=config["affected_radius_km"],
        towers_offline=offline,
        towers_degraded=degraded,
        summary=summary,
    )


def handle_fibre_cut(
    request: ScenarioRequest,
    network: NetworkState,
    defaults: Dict[str, Any],
) -> ScenarioEffect:
    """
    Fibre Cut — backhaul severance, extreme latency, no towers offline.

    A physical cut in the optical fibre backhaul connecting towers to
    the core network. Towers remain powered and their radio interfaces
    continue operating — but backhaul is impaired.

    Traffic is rerouted through alternate paths (longer routes, microwave
    fallback, satellite backup) with significantly higher latency.
    Effective throughput drops because alternate-path bandwidth is lower.
    No tower goes fully offline — this is a backhaul, not a site failure.
    """
    config = _merge_config(defaults, request.parameters)

    # Towers on the cut fibre segment
    degraded = _select_towers(
        network,
        count=int(config["max_degraded_towers"]),
        preferred_ids=request.affected_tower_ids,
        require_active=True,
    )

    summary = (
        f"Fibre cut simulation: backhaul severed affecting "
        f"{len(degraded)} tower(s) [{_fmt_list(degraded)}]. "
        f"All towers REMAIN ONLINE (radio unaffected). "
        f"Latency: +{config['latency_increase_ms']:.0f} ms (alternate path rerouting) | "
        f"Throughput: −{config['throughput_reduction_pct']:.0f}% (limited fallback capacity) | "
        f"Coverage edge: −{config['coverage_reduction_pct']:.0f}% | "
        f"Radius: {config['affected_radius_km']:.0f} km."
    )

    return ScenarioEffect(
        traffic_multiplier=config["traffic_multiplier"],
        bandwidth_demand_increase_pct=config["bandwidth_demand_increase_pct"],
        upload_bias=config["upload_bias"],
        throughput_reduction_pct=config["throughput_reduction_pct"],
        latency_increase_ms=config["latency_increase_ms"],
        signal_degradation_db=config["signal_degradation_db"],
        coverage_reduction_pct=config["coverage_reduction_pct"],
        energy_multiplier=config["energy_multiplier"],
        affected_radius_km=config["affected_radius_km"],
        towers_offline=[],
        towers_degraded=degraded,
        summary=summary,
    )


def handle_power_outage(
    request: ScenarioRequest,
    network: NetworkState,
    defaults: Dict[str, Any],
) -> ScenarioEffect:
    """
    Power Outage — grid failure, towers offline, emergency load redistribution.

    A zone-level grid failure cuts power to multiple towers.
    Towers without battery backup / generator go immediately offline.
    Towers with UPS continue operating in degraded mode (limited runtime,
    reduced transmission power to conserve energy).
    Emergency communications cause a traffic spike on surviving towers.

    Selection logic:
      - First n towers (by ID) → offline (no backup power)
      - Next m towers → degraded (on battery/generator)
    """
    config = _merge_config(defaults, request.parameters)

    n_offline = int(config["max_offline_towers"])
    n_degraded = int(config["max_degraded_towers"])

    # Towers that lose power entirely
    offline = _select_towers(
        network,
        count=n_offline,
        preferred_ids=request.affected_tower_ids[:n_offline],
        require_active=True,
    )

    # Towers on battery/generator — must exclude offline towers
    all_candidates = _select_towers(
        network,
        count=n_offline + n_degraded,
        preferred_ids=[],
        require_active=True,
    )
    degraded = [tid for tid in all_candidates if tid not in offline][:n_degraded]

    summary = (
        f"Power outage simulation: "
        f"{len(offline)} tower(s) OFFLINE (no backup power) [{_fmt_list(offline)}], "
        f"{len(degraded)} tower(s) on battery/generator [{_fmt_list(degraded)}]. "
        f"Coverage gap: −{config['coverage_reduction_pct']:.0f}% | "
        f"Emergency traffic: {config['traffic_multiplier']:.1f}× on surviving towers | "
        f"Latency: +{config['latency_increase_ms']:.0f} ms (rerouting) | "
        f"Energy: {config['energy_multiplier']:.1f}× (grid unavailable) | "
        f"Radius: {config['affected_radius_km']:.1f} km."
    )

    return ScenarioEffect(
        traffic_multiplier=config["traffic_multiplier"],
        bandwidth_demand_increase_pct=config["bandwidth_demand_increase_pct"],
        upload_bias=config["upload_bias"],
        throughput_reduction_pct=config["throughput_reduction_pct"],
        latency_increase_ms=config["latency_increase_ms"],
        signal_degradation_db=config["signal_degradation_db"],
        coverage_reduction_pct=config["coverage_reduction_pct"],
        energy_multiplier=config["energy_multiplier"],
        affected_radius_km=config["affected_radius_km"],
        towers_offline=offline,
        towers_degraded=degraded,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------
#
# Maps each ScenarioEventType to its handler function.
# ScenarioEngine dispatches via this registry — O(1) lookup, no if-chains.
#
# To add a new scenario:
#   1. Add enum value to schemas/scenario.py ScenarioEventType
#   2. Add defaults to scenarios/effects.py SCENARIO_DEFAULTS
#   3. Write a handler function above following the existing pattern
#   4. Register it here

HandlerFn = Callable[
    [ScenarioRequest, NetworkState, Dict[str, Any]],
    ScenarioEffect,
]

HANDLER_REGISTRY: Dict[ScenarioEventType, HandlerFn] = {
    ScenarioEventType.IPL_MATCH: handle_ipl_match,
    ScenarioEventType.CONCERT: handle_concert,
    ScenarioEventType.FESTIVAL: handle_festival,
    ScenarioEventType.HEAVY_RAIN: handle_heavy_rain,
    ScenarioEventType.CYCLONE: handle_cyclone,
    ScenarioEventType.TOWER_FAILURE: handle_tower_failure,
    ScenarioEventType.FIBRE_CUT: handle_fibre_cut,
    ScenarioEventType.POWER_OUTAGE: handle_power_outage,
}

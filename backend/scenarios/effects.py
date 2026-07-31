"""
Scenario Effects
================
Internal data models for scenario simulation results.

ScenarioEffect is a dataclass that captures every computed consequence
of running a network scenario. It lives entirely inside the scenarios/
package — it is never serialised directly to the HTTP API.

ScenarioEngine converts a ScenarioEffect to a plain dict via .to_dict()
and stores it in Scenario.parameters before returning to the caller.

SCENARIO_DEFAULTS
-----------------
Maps each ScenarioEventType to its default effect configuration.

All numeric values are grounded in real-world telecom engineering:
  - Traffic multipliers sourced from 3GPP TR 36.814 dense deployment studies
  - Rain attenuation: ITU-R P.838 model (6 dB at 80 mm/hr on 2.4 GHz)
  - Signal degradation: practical field measurements from GSMA Intelligence
  - Latency increases: measured backhaul rerouting delays

Every default value is overridable via ScenarioRequest.parameters:
    {"traffic_multiplier": 5.0, "max_degraded_towers": 5}

Handler config keys (max_degraded_towers, max_offline_towers) control
how many towers the engine selects to apply effects to. They are not
persisted in ScenarioEffect — they are consumed by handlers only.
"""
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

from schemas.scenario import ScenarioEventType


# ---------------------------------------------------------------------------
# ScenarioEffect  —  internal simulation result model
# ---------------------------------------------------------------------------

@dataclass
class ScenarioEffect:
    """
    Computed effects of a scenario simulation run.

    All values represent deltas/multipliers relative to the baseline
    (undisturbed) network state:
      - traffic_multiplier = 2.0  →  twice the baseline traffic
      - signal_degradation_db = 6  →  6 dB loss on top of free-space path loss
      - coverage_reduction_pct = 20  →  20% reduction in usable coverage area

    This is an internal model. It is always serialised through to_dict()
    before being stored in Scenario.parameters.
    """

    # ---- Traffic & load ----
    traffic_multiplier: float = 1.0
    """Multiplier on overall user traffic volume (1.0 = no change)."""

    bandwidth_demand_increase_pct: float = 0.0
    """Percentage increase in bandwidth demand (can be negative for demand drops)."""

    upload_bias: float = 1.0
    """Ratio of upload to baseline; >1 indicates upload-heavy traffic pattern."""

    throughput_reduction_pct: float = 0.0
    """Percentage reduction in effective backhaul/link throughput capacity."""

    # ---- Signal & coverage ----
    latency_increase_ms: float = 0.0
    """Additional end-to-end latency in milliseconds caused by this scenario."""

    signal_degradation_db: float = 0.0
    """Signal attenuation in dB added on top of normal path loss."""

    coverage_reduction_pct: float = 0.0
    """Percentage reduction in geographic coverage area."""

    # ---- Infrastructure ----
    towers_offline: List[str] = field(default_factory=list)
    """Tower IDs completely taken offline by this scenario."""

    towers_degraded: List[str] = field(default_factory=list)
    """Tower IDs experiencing degraded (but operational) performance."""

    # ---- Energy ----
    energy_multiplier: float = 1.0
    """Relative change in energy consumption (0.0 = no power, 1.0 = normal)."""

    # ---- Geographic scope ----
    affected_radius_km: float = 0.0
    """Approximate radius in km of the scenario's geographic impact zone."""

    # ---- Human-readable output ----
    summary: str = ""
    """Operator-facing summary of the simulation result."""

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialises the effect to a flat dict suitable for Scenario.parameters.

        List fields (towers_offline, towers_degraded) are preserved as lists.
        """
        return asdict(self)


# ---------------------------------------------------------------------------
# SCENARIO_DEFAULTS  —  per-scenario engineering baselines
# ---------------------------------------------------------------------------
#
# Key naming convention:
#   Fields that map directly to ScenarioEffect attributes → match attribute name
#   Handler-only config keys → prefixed semantics (max_degraded_towers, etc.)
#
# All values can be overridden at request time via ScenarioRequest.parameters.

SCENARIO_DEFAULTS: Dict[ScenarioEventType, Dict[str, Any]] = {

    # ------------------------------------------------------------------
    # IPL_MATCH
    # A major cricket fixture draws 40,000–80,000 spectators into a
    # 2 km stadium radius. Dense device concentration drives heavy
    # multimedia consumption (live scores, highlights, social media).
    # ------------------------------------------------------------------
    ScenarioEventType.IPL_MATCH: {
        "traffic_multiplier": 3.5,
        "bandwidth_demand_increase_pct": 250.0,
        "upload_bias": 1.3,           # score updates + social media
        "throughput_reduction_pct": 0.0,
        "latency_increase_ms": 15.0,  # backhaul congestion
        "signal_degradation_db": 2.0, # device-to-device interference
        "coverage_reduction_pct": 0.0,
        "energy_multiplier": 1.4,
        "affected_radius_km": 2.0,
        # handler config
        "max_degraded_towers": 3,
        "max_offline_towers": 0,
    },

    # ------------------------------------------------------------------
    # CONCERT
    # 20,000–30,000 attendees at an outdoor/indoor venue. Heavy
    # simultaneous live-streaming to Instagram Reels, YouTube, etc.
    # makes this strongly upload-biased compared to IPL.
    # ------------------------------------------------------------------
    ScenarioEventType.CONCERT: {
        "traffic_multiplier": 2.8,
        "bandwidth_demand_increase_pct": 180.0,
        "upload_bias": 2.5,           # dominant live-streaming
        "throughput_reduction_pct": 0.0,
        "latency_increase_ms": 20.0,  # upload buffers + retrans
        "signal_degradation_db": 3.0, # multipath from crowd movement
        "coverage_reduction_pct": 0.0,
        "energy_multiplier": 1.3,
        "affected_radius_km": 1.0,
        # handler config
        "max_degraded_towers": 2,
        "max_offline_towers": 0,
    },

    # ------------------------------------------------------------------
    # FESTIVAL
    # City-wide celebration (Diwali, Navratri, New Year). Traffic is
    # distributed across all towers rather than localised. Moderate
    # load increase with heightened social media posting.
    # ------------------------------------------------------------------
    ScenarioEventType.FESTIVAL: {
        "traffic_multiplier": 1.8,
        "bandwidth_demand_increase_pct": 80.0,
        "upload_bias": 1.5,           # photos, reels, video calls
        "throughput_reduction_pct": 0.0,
        "latency_increase_ms": 8.0,
        "signal_degradation_db": 0.0,
        "coverage_reduction_pct": 5.0,  # slight degradation from load
        "energy_multiplier": 1.2,
        "affected_radius_km": 10.0,    # city-wide
        # handler config — affect all available active towers
        "max_degraded_towers": 20,
        "max_offline_towers": 0,
    },

    # ------------------------------------------------------------------
    # HEAVY_RAIN
    # Rainfall ~80 mm/hr. ITU-R P.838 rain attenuation model:
    # ~0.01 dB/km/mm_hr at 2.4 GHz → ~6 dB over a 7 km cell radius.
    # Higher frequencies (5G mmWave) are more severely impacted.
    # People tend to remain indoors, slightly reducing mobile traffic.
    # ------------------------------------------------------------------
    ScenarioEventType.HEAVY_RAIN: {
        "traffic_multiplier": 0.9,     # mobile usage drops slightly
        "bandwidth_demand_increase_pct": 0.0,
        "upload_bias": 1.0,
        "throughput_reduction_pct": 10.0,  # retransmissions consume capacity
        "latency_increase_ms": 5.0,        # ARQ retransmissions
        "signal_degradation_db": 6.0,      # ITU-R P.838 rain attenuation
        "coverage_reduction_pct": 15.0,    # cell edge users lose signal
        "energy_multiplier": 1.1,          # more retransmissions = more Tx power
        "affected_radius_km": 50.0,        # weather system radius
        # handler config — atmospheric effect hits all towers
        "max_degraded_towers": 20,
        "max_offline_towers": 0,
    },

    # ------------------------------------------------------------------
    # CYCLONE
    # Category 3–4 (200+ km/h winds). Physical tower damage,
    # power grid disruption, and severe atmospheric attenuation combine.
    # Emergency communications traffic spikes as civilians seek contact.
    # Structural failures take 1–2 towers completely offline.
    # ------------------------------------------------------------------
    ScenarioEventType.CYCLONE: {
        "traffic_multiplier": 1.3,     # emergency comms spike
        "bandwidth_demand_increase_pct": 30.0,
        "upload_bias": 1.2,            # emergency video + location shares
        "throughput_reduction_pct": 25.0,
        "latency_increase_ms": 80.0,   # rerouting over degraded backhaul
        "signal_degradation_db": 18.0, # wind/rain attenuation + antenna tilt
        "coverage_reduction_pct": 45.0,
        "energy_multiplier": 0.5,      # grid down, battery backup only
        "affected_radius_km": 100.0,
        # handler config
        "max_degraded_towers": 4,
        "max_offline_towers": 2,
    },

    # ------------------------------------------------------------------
    # TOWER_FAILURE
    # Single tower hardware fault (power amplifier failure, antenna
    # collapse, baseband unit crash). UEs must hand over to adjacent
    # towers, which absorb the extra load and become overloaded.
    # ------------------------------------------------------------------
    ScenarioEventType.TOWER_FAILURE: {
        "traffic_multiplier": 1.5,     # neighbour load after handovers
        "bandwidth_demand_increase_pct": 0.0,
        "upload_bias": 1.0,
        "throughput_reduction_pct": 15.0,  # congestion on neighbours
        "latency_increase_ms": 12.0,       # longer signal paths post-HO
        "signal_degradation_db": 0.0,
        "coverage_reduction_pct": 20.0,    # coverage gap at failed site
        "energy_multiplier": 1.1,          # neighbour towers work harder
        "affected_radius_km": 0.5,
        # handler config: 1 tower fails, 2 adjacent absorb load
        "max_degraded_towers": 2,
        "max_offline_towers": 1,
    },

    # ------------------------------------------------------------------
    # FIBRE_CUT
    # Physical severance of the fibre backhaul connecting towers to the
    # core network. Towers remain powered and transmitting but backhaul
    # is impaired — traffic is rerouted through alternate paths (longer
    # routes, microwave fallback) causing severe latency increase.
    # No tower goes fully offline, but throughput is seriously degraded.
    # ------------------------------------------------------------------
    ScenarioEventType.FIBRE_CUT: {
        "traffic_multiplier": 1.0,
        "bandwidth_demand_increase_pct": 0.0,
        "upload_bias": 1.0,
        "throughput_reduction_pct": 40.0,  # alternate path capacity is lower
        "latency_increase_ms": 65.0,       # rerouting via suboptimal paths
        "signal_degradation_db": 0.0,      # RF layer unaffected
        "coverage_reduction_pct": 10.0,    # edge users suffer more on congested links
        "energy_multiplier": 1.05,         # slight increase from retransmissions
        "affected_radius_km": 5.0,         # towers along the cut segment
        # handler config: no towers offline, 3 on the cut segment degraded
        "max_degraded_towers": 3,
        "max_offline_towers": 0,
    },

    # ------------------------------------------------------------------
    # POWER_OUTAGE
    # Grid failure in a zone. Towers without battery backup go offline
    # immediately. Towers with UPS/generator remain operational but are
    # subject to fuel constraints and load-shedding. Emergency comms
    # demand increases as residents try to contact family.
    # ------------------------------------------------------------------
    ScenarioEventType.POWER_OUTAGE: {
        "traffic_multiplier": 1.2,         # emergency comms demand
        "bandwidth_demand_increase_pct": 20.0,
        "upload_bias": 1.0,
        "throughput_reduction_pct": 0.0,
        "latency_increase_ms": 25.0,        # rerouting around offline towers
        "signal_degradation_db": 0.0,
        "coverage_reduction_pct": 35.0,     # significant coverage gap
        "energy_multiplier": 0.0,           # affected towers have no power
        "affected_radius_km": 3.0,
        # handler config: 2 offline, 2 on battery (degraded)
        "max_degraded_towers": 2,
        "max_offline_towers": 2,
    },
}

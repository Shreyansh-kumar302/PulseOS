"""
Metrics Engine
==============
Computes QoS (Quality of Service) and QoE (Quality of Experience) metrics
from raw network telemetry parameters.

This is a pure computation module with no external state. It can be safely
instantiated as a module-level singleton.

Extension point: add 'compute_throughput()', 'compute_jitter()', and
'compute_availability()' methods as telemetry data becomes available.
"""


class MetricsEngine:
    """Computes QoS, QoE, and throughput metrics for reporting."""

    def compute_qos(self, delay: float, packet_loss: float) -> float:
        """
        Calculates a Quality of Service score on a 0-100 scale.

        Args:
            delay:        Round-trip latency in milliseconds (>= 0).
            packet_loss:  Packet loss ratio in the range [0.0, 1.0].

        Returns:
            float: QoS score clamped to [0, 100]. Higher is better.

        Penalty model:
            loss_penalty  = packet_loss * 500  (1% loss → -5 pts)
            delay_penalty = delay * 0.1         (10 ms  → -1 pt)
        """
        loss_penalty: float = packet_loss * 500
        delay_penalty: float = delay * 0.1
        return max(0.0, min(100.0, 100.0 - loss_penalty - delay_penalty))

    def compute_qoe(self, qos: float) -> float:
        """
        Maps a QoS score to a Mean Opinion Score (MOS) on the 1-5 ITU-T P.800 scale.

        Args:
            qos: QoS score in [0, 100].

        Returns:
            float: MOS value in {1.5, 3.0, 4.0, 4.5}.

        TODO: replace step function with a continuous regression model
              calibrated against real subjective quality surveys.
        """
        if qos > 90:
            return 4.5
        if qos > 80:
            return 4.0
        if qos > 60:
            return 3.0
        return 1.5

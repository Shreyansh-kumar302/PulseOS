class MetricsEngine:
    """Computes QoS, QoE, and throughput metrics for reporting."""
    def __init__(self):
        pass

    def compute_qos(self, delay, packet_loss):
        """Calculates Quality of Service metric between 0 and 100."""
        loss_penalty = packet_loss * 500
        delay_penalty = delay * 0.1
        qos = max(0, min(100, 100 - loss_penalty - delay_penalty))
        return qos

    def compute_qoe(self, qos):
        """Calculates Quality of Experience index (1-5 MOS scale)."""
        if qos > 90:
            return 4.5
        elif qos > 80:
            return 4.0
        elif qos > 60:
            return 3.0
        else:
            return 1.5

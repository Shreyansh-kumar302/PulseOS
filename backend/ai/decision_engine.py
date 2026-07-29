class DecisionEngine:
    """Evaluates recommended optimization actions based on prediction outcomes."""
    def __init__(self):
        pass

    def recommend_actions(self, network_state, congestion_predictions):
        """Recommends action based on prediction state."""
        recommendations = []
        for pred in congestion_predictions:
            if pred > 0.8:
                recommendations.append({
                    "action": "THROTTLE_NON_ESSENTIAL",
                    "reason": f"High predicted load: {pred:.2f}",
                    "confidence": 0.92
                })
        return recommendations

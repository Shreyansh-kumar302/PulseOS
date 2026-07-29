class NetworkGenerator:
    """Generates synthetic telecom network topologies and user flows."""
    def __init__(self):
        pass

    def generate(self):
        return {
            "nodes": [
                {"id": "T001", "latitude": 12.9716, "longitude": 77.5946, "type": "macro"},
                {"id": "T002", "latitude": 12.9726, "longitude": 77.5956, "type": "micro"},
                {"id": "T003", "latitude": 12.9736, "longitude": 77.5966, "type": "macro"}
            ],
            "edges": [
                {"source": "T001", "target": "T002", "capacity_gbps": 10},
                {"source": "T002", "target": "T003", "capacity_gbps": 5}
            ]
        }

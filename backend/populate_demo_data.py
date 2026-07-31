import json
import os
import random
from datetime import datetime, timedelta

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Generate realistic telecom tower network (10 towers in a city, e.g., Bangalore)
towers = []
base_lat, base_lon = 12.9716, 77.5946
statuses = ["active", "active", "active", "active", "active", "maintenance", "inactive"]
types = ["macro", "micro", "micro", "macro", "pico", "macro", "micro"]

for i in range(1, 11):
    t_type = types[i % len(types)]
    cap = 500 if t_type == "macro" else (150 if t_type == "micro" else 50)
    towers.append({
        "id": f"T{i:03d}",
        "name": f"BLR_{t_type.capitalize()}_{i:03d}",
        "type": t_type,
        "latitude": base_lat + random.uniform(-0.05, 0.05),
        "longitude": base_lon + random.uniform(-0.05, 0.05),
        "capacity": cap,
        "status": statuses[i % len(statuses)],
        "tx_power_dbm": 43.0 if t_type == "macro" else 33.0,
        "frequency_mhz": random.choice([1800.0, 2100.0, 2600.0, 3500.0])
    })

# Connections (mesh-like)
connections = []
for i in range(len(towers)):
    for j in range(i + 1, min(i + 4, len(towers))):
        connections.append({
            "source_id": towers[i]["id"],
            "target_id": towers[j]["id"],
            "connection_type": random.choice(["fiber", "microwave"]),
            "latency_ms": round(random.uniform(1.5, 5.0), 2),
            "capacity_gbps": random.choice([5.0, 10.0, 25.0])
        })

network_data = {
    "towers": towers,
    "connections": connections
}

with open(os.path.join(DATA_DIR, "network.json"), "w") as f:
    json.dump(network_data, f, indent=2)


# Predictions
predictions = []
now = datetime.utcnow()
for t in towers:
    for h in range(12):
        ts = now + timedelta(hours=h)
        load = random.uniform(10.0, 95.0)
        if t["status"] != "active":
            load = 0.0
        predictions.append({
            "target_tower": t["id"],
            "timestamp": ts.isoformat() + "Z",
            "predicted_load_pct": round(load, 2)
        })

prediction_data = {
    "predictions": predictions
}

with open(os.path.join(DATA_DIR, "prediction.json"), "w") as f:
    json.dump(prediction_data, f, indent=2)


# Optimization
optimization = {
    "optimization_results": [
        {
            "run_id": "OPT-DEMO123",
            "timestamp": now.isoformat() + "Z",
            "algorithm": "qubo",
            "solver_status": "success",
            "optimal_energy": -42.5,
            "variables_assigned": {"x_0": 1, "x_1": 0}
        }
    ]
}

with open(os.path.join(DATA_DIR, "optimization.json"), "w") as f:
    json.dump(optimization, f, indent=2)


# Scenarios
scenarios = {
    "scenarios": [
        {
            "id": "SCN-001",
            "name": "Evening Peak Congestion",
            "description": "Simulates 18:00-21:00 peak traffic load in downtown area.",
            "duration_minutes": 180,
            "effects": [
                {"type": "traffic_spike", "target": "T001", "magnitude": 1.8},
                {"type": "traffic_spike", "target": "T004", "magnitude": 1.5}
            ]
        },
        {
            "id": "SCN-002",
            "name": "Fiber Cut - Suburb A",
            "description": "Simulates a complete loss of the primary fiber backhaul.",
            "duration_minutes": 60,
            "effects": [
                {"type": "link_failure", "target": "T002-T005"},
                {"type": "latency_increase", "target": "T005", "magnitude": 45.0}
            ]
        }
    ]
}

with open(os.path.join(DATA_DIR, "scenarios.json"), "w") as f:
    json.dump(scenarios, f, indent=2)

print("Demo data generated successfully.")

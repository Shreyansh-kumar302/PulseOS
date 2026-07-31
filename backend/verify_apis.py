import os
os.environ["GEMINI_API_KEY"] = "mock_key_for_testing"

from fastapi.testclient import TestClient
from app import app
import json

client = TestClient(app)

endpoints_to_test = [
    ("GET", "/"),
    ("GET", "/network/state"),
    ("POST", "/optimize/run", {}),
    ("GET", "/metrics/qos?delay=5.0&packet_loss=0.01"),
    ("POST", "/scenario/run", {"name": "Test Scenario", "event_type": "concert", "duration_minutes": 60, "magnitude": 1.5}),
    ("GET", "/dashboard/summary"),
    ("GET", "/dashboard/full"),
    ("GET", "/prediction/")
]

success = []
failed = []

for item in endpoints_to_test:
    method = item[0]
    endpoint = item[1]
    
    try:
        if method == "GET":
            response = client.get(endpoint)
        elif method == "POST":
            response = client.post(endpoint, json=item[2])
            
        if response.status_code == 200:
            success.append(endpoint)
        else:
            failed.append(f"{endpoint} ({response.status_code}): {response.text}")
    except Exception as e:
        failed.append(f"{endpoint} (Exception): {str(e)}")

print("Verified APIs:")
for s in success:
    print(f"OK: {s}")

if failed:
    print("\nFailed APIs:")
    for f in failed:
        print(f"FAIL: {f}")

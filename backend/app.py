from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.network import router as network_router
from routes.optimize import router as optimize_router
from routes.metrics import router as metrics_router
from routes.scenario import router as scenario_router
from routes.dashboard import router as dashboard_router
from routes.prediction import router as prediction_router
from routes.copilot import router as copilot_router

app = FastAPI(
    title="PulseOS Backend",
    description="AI-Powered Autonomous Telecom Operations Platform API",
    version="1.0.0"
)

# NOTE: allow_credentials=True is incompatible with allow_origins=["*"].
# Using explicit origins for development. Replace with env-var-driven list in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(network_router)
app.include_router(optimize_router)
app.include_router(metrics_router)
app.include_router(scenario_router)
app.include_router(dashboard_router)
app.include_router(prediction_router)
app.include_router(copilot_router)

@app.get("/", tags=["Health"])
def health_check():
    return {"status": "ok", "service": "PulseOS Backend"}
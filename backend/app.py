from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.network import router as network_router
from routes.optimize import router as optimize_router
from routes.metrics import router as metrics_router
from routes.scenario import router as scenario_router
from routes.dashboard import router as dashboard_router

app = FastAPI(
    title="PulseOS Backend",
    version="1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(network_router)
app.include_router(optimize_router)
app.include_router(metrics_router)
app.include_router(scenario_router)
app.include_router(dashboard_router)

@app.get("/")
def home():
    return {"message": "PulseOS Backend Running"}
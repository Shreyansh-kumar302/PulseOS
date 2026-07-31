from fastapi import FastAPI

from routes.network import router as network_router
from routes.dashboard import router as dashboard_router

app = FastAPI(
    title="PulseOS Backend",
    version="1.0.0"
)

# Include Routes
app.include_router(network_router)
app.include_router(dashboard_router)


@app.get("/")
def home():
    return {
        "message": "Welcome to PulseOS Backend 🚀"
    }
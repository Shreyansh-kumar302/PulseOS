from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import sys

# Add the current directory to sys.path so python can resolve imports easily
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from routes.network import router as network_router
from routes.dashboard import router as dashboard_router
from routes.prediction import router as prediction_router
from routes.copilot import router as copilot_router
from routes.optimize import router as optimize_router

app = FastAPI(
    title="PulseOS Backend",
    description="AI-Powered Autonomous Telecom Operations Platform API",
    version="1.0.0"
)

# Enable CORS middleware so frontend can query endpoints
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routes
app.include_router(network_router)
app.include_router(dashboard_router)
app.include_router(prediction_router)
app.include_router(copilot_router)
app.include_router(optimize_router)


@app.get("/", tags=["Health"])
def health_check():
    return {"status": "ok", "service": "PulseOS Backend"}

if __name__ == '__main__':
    uvicorn.run("app:app", host="127.0.0.1", port=5000, reload=True)

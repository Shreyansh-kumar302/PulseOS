from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import sys

# Add the current directory to sys.path so python can resolve imports easily
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from routes.network import router as network_router
from routes.dashboard import router as dashboard_router

app = FastAPI(
    title="PulseOS Backend",
    version="1.0.0"
)

# Enable CORS middleware so frontend can query endpoints
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routes
app.include_router(network_router)
app.include_router(dashboard_router)


@app.get("/")
def home():
    return {
        "message": "Welcome to PulseOS Backend 🚀"
    }

if __name__ == '__main__':
    uvicorn.run("app:app", host="127.0.0.1", port=5000, reload=True)
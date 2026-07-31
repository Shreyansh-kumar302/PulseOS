from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
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
    allow_origins=["*"], # Allow all origins in production deployment
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


@app.get("/api/health", tags=["Health"])
def health_check():
    return {"status": "ok", "service": "PulseOS Backend"}

# Mount frontend production build directory
frontend_dist_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "dist")

if os.path.exists(frontend_dist_path):
    # Mount assets folder
    assets_path = os.path.join(frontend_dist_path, "assets")
    if os.path.exists(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="static")

    # Serve index.html as a catchall for client-side routing
    @app.get("/{catchall:path}", include_in_schema=False)
    def serve_frontend(catchall: str):
        return FileResponse(os.path.join(frontend_dist_path, "index.html"))
else:
    # Fallback status if assets are not built yet
    @app.get("/", tags=["Health"])
    def root_fallback():
        return {"status": "running", "message": "API is active. Frontend static assets not built yet. Run 'npm run build' inside frontend."}

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    # Run server bound to all adapters for external container connectivity
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)

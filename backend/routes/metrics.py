from fastapi import APIRouter

router = APIRouter(
    prefix="/metrics",
    tags=["Metrics"]
)

@router.get("/")
def metrics():
    return {
        "status":"Metrics API Working"
    }
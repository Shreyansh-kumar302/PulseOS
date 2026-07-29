from fastapi import APIRouter

router = APIRouter(
    prefix="/optimize",
    tags=["Optimization"]
)

@router.post("/")
def optimize():
    return {
        "status":"Optimization API Working"
    }
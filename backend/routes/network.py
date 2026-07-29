from fastapi import APIRouter

router = APIRouter(
    prefix="/network",
    tags=["Network"]
)

@router.get("/generate")
def generate_network():
    return {
        "status":"Network API Working"
    }
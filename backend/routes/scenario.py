from fastapi import APIRouter

router = APIRouter(
    prefix="/scenario",
    tags=["Scenario"]
)

@router.post("/")
def scenario():
    return {
        "status":"Scenario API Working"
    }
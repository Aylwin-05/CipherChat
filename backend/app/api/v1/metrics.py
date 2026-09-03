from app.metrics import get_snapshot
from fastapi import APIRouter

router = APIRouter(
    prefix="/metrics",
    tags=["Observability"],
)


@router.get("")
async def app_metrics():
    return get_snapshot()

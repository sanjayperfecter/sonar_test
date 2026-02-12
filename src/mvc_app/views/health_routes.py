from fastapi import APIRouter

from src.mvc_app.controllers.health_controller import get_health

router = APIRouter()


@router.get("/health", tags=["health"])
def health():
    return get_health()


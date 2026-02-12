from fastapi import APIRouter, HTTPException

from src.mvc_app.controllers.user_controller import user_controller
from src.mvc_app.models.user import UserCreate, UserRead

router = APIRouter()


@router.post("", response_model=UserRead, status_code=201)
def create_user(payload: UserCreate) -> UserRead:
    return user_controller.create_user(payload)


@router.get("", response_model=list[UserRead])
def list_users() -> list[UserRead]:
    return user_controller.list_users()


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: str) -> UserRead:
    user = user_controller.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


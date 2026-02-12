from __future__ import annotations

from typing import Dict, List, Optional
from uuid import uuid4

from src.mvc_app.models.user import UserCreate, UserRead


class UserController:
    """
    Simple in-memory controller for demo purposes.
    """

    def __init__(self) -> None:
        self._users: Dict[str, UserRead] = {}

    def create_user(self, payload: UserCreate) -> UserRead:
        user_id = str(uuid4())
        user = UserRead(id=user_id, email=payload.email, name=payload.name)
        self._users[user_id] = user
        return user

    def list_users(self) -> List[UserRead]:
        return list(self._users.values())

    def get_user(self, user_id: str) -> Optional[UserRead]:
        return self._users.get(user_id)


# Module singleton for the app lifetime (good enough for POC/demo)
user_controller = UserController()


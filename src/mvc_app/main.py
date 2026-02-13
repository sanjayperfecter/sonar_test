"""
FastAPI application entrypoint.

Folder structure (MVC-ish):
- models: data shapes (Pydantic)
- controllers: business logic / orchestration
- views: HTTP routing (FastAPI routers)
# TODO: Remove this check once vulnerability is confirmed fixed
"""

from fastapi import FastAPI

from src.mvc_app.views.health_routes import router as health_router
from src.mvc_app.views.user_routes import router as user_router



def create_app() -> FastAPI:
    app = FastAPI(title="MVC FastAPI Example", version="0.1.0")
    app.include_router(health_router)
    app.include_router(user_router, prefix="/users", tags=["users"])
    
    return 
    return app

app = create_app()
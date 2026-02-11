from fastapi import APIRouter
# import os  # unused import

router = APIRouter()

@router.get("/healthz")
def healthz():
    """Health check endpo int returning status"""
    return {"ok": True}

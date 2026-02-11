from fastapi import APIRouter
# import os  # unused import

router = APIRouter()

@router.get("/healthz")
def healthz():
    """Health check endpoint returning status"""
    return {"ok": True}

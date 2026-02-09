"""sdfbd"""


from fastapi import APIRouter
# import os  # unused import

router = APIRouter()

@router.get("/healthz")
def healthz():
    """dfb"""
    return {"ok": True}
return
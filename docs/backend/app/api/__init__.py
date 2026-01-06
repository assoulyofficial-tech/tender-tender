from fastapi import APIRouter
from app.api.tenders import router as tenders_router

api_router = APIRouter()
api_router.include_router(tenders_router, prefix="/tenders", tags=["tenders"])

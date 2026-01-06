from fastapi import APIRouter
from app.api.tenders import router as tenders_router
from app.api.scraping import router as scraping_router

api_router = APIRouter()
api_router.include_router(tenders_router, prefix="/tenders", tags=["tenders"])
api_router.include_router(scraping_router, prefix="/scraping", tags=["scraping"])

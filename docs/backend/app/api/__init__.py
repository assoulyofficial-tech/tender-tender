from fastapi import APIRouter
from app.api.tenders import router as tenders_router
from app.api.scraping import router as scraping_router
from app.api.extraction import router as extraction_router
from app.api.analysis import router as analysis_router
from app.api.deep_analysis import router as deep_analysis_router

api_router = APIRouter()
api_router.include_router(tenders_router, prefix="/tenders", tags=["tenders"])
api_router.include_router(scraping_router, prefix="/scraping", tags=["scraping"])
api_router.include_router(extraction_router, prefix="/extraction", tags=["extraction"])
api_router.include_router(analysis_router, prefix="/analysis", tags=["analysis"])
api_router.include_router(deep_analysis_router, prefix="/deep-analysis", tags=["deep-analysis"])

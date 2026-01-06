"""
Scraping API endpoints.
Manual trigger for tender scraping.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.scraper import TenderScraper, ScrapeResult, PLAYWRIGHT_AVAILABLE
from app.services.scraper_db import ScraperDBService, document_store

router = APIRouter()


# Request/Response schemas
class ScrapeRequest(BaseModel):
    target_date: Optional[str] = None  # Format: YYYY-MM-DD, defaults to yesterday
    category: str = "Fournitures"
    max_pages: int = 10
    headless: bool = True


class ScrapeResponse(BaseModel):
    success: bool
    message: str
    target_date: str
    tenders_found: int
    created: int
    updated: int
    skipped: int
    errors: list[str]
    duration_seconds: float
    documents_in_memory: int
    memory_usage_bytes: int


class ScrapeStatusResponse(BaseModel):
    playwright_available: bool
    scraper_ready: bool
    documents_in_memory: int
    memory_usage_bytes: int


# Global scrape state (simple, for single-instance)
_scrape_in_progress = False
_last_scrape_result: Optional[dict] = None


@router.get("/status", response_model=ScrapeStatusResponse)
def get_scrape_status():
    """Check scraper status and readiness."""
    return ScrapeStatusResponse(
        playwright_available=PLAYWRIGHT_AVAILABLE,
        scraper_ready=PLAYWRIGHT_AVAILABLE and not _scrape_in_progress,
        documents_in_memory=document_store.count,
        memory_usage_bytes=document_store.size
    )


@router.post("/trigger", response_model=ScrapeResponse)
async def trigger_scrape(
    request: ScrapeRequest,
    db: Session = Depends(get_db)
):
    """
    Manually trigger tender scraping.
    
    - **target_date**: Date to scrape (YYYY-MM-DD), defaults to yesterday
    - **category**: Tender category (default: Fournitures)
    - **max_pages**: Maximum pagination pages to scrape
    - **headless**: Run browser in headless mode
    """
    global _scrape_in_progress, _last_scrape_result
    
    if not PLAYWRIGHT_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Playwright not installed. Run: pip install playwright && playwright install chromium"
        )
    
    if _scrape_in_progress:
        raise HTTPException(
            status_code=409,
            detail="Scrape already in progress"
        )
    
    # Parse target date
    if request.target_date:
        try:
            target_date = datetime.strptime(request.target_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid date format. Use YYYY-MM-DD"
            )
    else:
        target_date = datetime.now() - timedelta(days=1)
    
    _scrape_in_progress = True
    
    try:
        # Run scraper
        scraper = TenderScraper(headless=request.headless)
        result: ScrapeResult = await scraper.scrape(
            target_date=target_date,
            category=request.category,
            max_pages=request.max_pages
        )
        
        # Store documents in memory
        for tender in result.tenders:
            for doc in tender.documents:
                document_store.store(tender.reference, doc.filename, doc.content)
        
        # Save to database
        db_service = ScraperDBService(db)
        db_result = db_service.save_scrape_result(result)
        
        # Combine results
        response = ScrapeResponse(
            success=result.success and len(db_result["errors"]) == 0,
            message=f"Scraped {len(result.tenders)} tenders for {target_date.date()}",
            target_date=target_date.strftime("%Y-%m-%d"),
            tenders_found=len(result.tenders),
            created=db_result["created"],
            updated=db_result["updated"],
            skipped=db_result["skipped"],
            errors=result.errors + db_result["errors"],
            duration_seconds=result.duration_seconds,
            documents_in_memory=document_store.count,
            memory_usage_bytes=document_store.size
        )
        
        _last_scrape_result = response.model_dump()
        return response
        
    finally:
        _scrape_in_progress = False


@router.get("/last-result")
def get_last_result():
    """Get result of the last scrape run."""
    if _last_scrape_result is None:
        raise HTTPException(
            status_code=404,
            detail="No scrape has been run yet"
        )
    return _last_scrape_result


@router.post("/clear-memory")
def clear_document_memory():
    """Clear in-memory document store."""
    count = document_store.count
    size = document_store.size
    document_store.clear()
    return {
        "cleared": True,
        "documents_removed": count,
        "bytes_freed": size
    }


@router.get("/documents/{reference}")
def get_tender_documents_in_memory(reference: str):
    """Get list of documents in memory for a tender."""
    docs = document_store.get_all_for_tender(reference)
    return {
        "reference": reference,
        "documents": [
            {"filename": name, "size": len(content)}
            for name, content in docs.items()
        ],
        "total_size": sum(len(c) for c in docs.values())
    }

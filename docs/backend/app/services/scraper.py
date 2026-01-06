"""
Tender Scraper Service for marchespublics.gov.ma
Uses Playwright for browser automation.

User can replace/extend the scraping logic in this file.
"""

import asyncio
import re
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, field
from uuid import uuid4

# Playwright import (user must have it installed)
try:
    from playwright.async_api import async_playwright, Page, Browser
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


@dataclass
class ScrapedDocument:
    """In-memory document representation."""
    filename: str
    content: bytes  # Raw file content in memory
    file_type: str
    file_size: int
    download_url: str


@dataclass
class ScrapedTender:
    """Scraped tender data before DB insertion."""
    reference: str
    title: str
    organization: str
    category: str = "Fournitures"
    publication_date: Optional[datetime] = None
    deadline: Optional[datetime] = None
    opening_date: Optional[datetime] = None
    budget_estimate: Optional[float] = None
    caution_amount: Optional[float] = None
    source_url: str = ""
    source_id: Optional[str] = None
    documents: list[ScrapedDocument] = field(default_factory=list)


@dataclass
class ScrapeResult:
    """Result of a scraping run."""
    success: bool
    tenders: list[ScrapedTender]
    errors: list[str]
    scraped_at: datetime
    target_date: datetime
    duration_seconds: float


class TenderScraper:
    """
    Scraper for marchespublics.gov.ma
    
    Usage:
        scraper = TenderScraper()
        result = await scraper.scrape(target_date=datetime.now() - timedelta(days=1))
    """
    
    BASE_URL = "https://www.marchespublics.gov.ma"
    SEARCH_URL = f"{BASE_URL}/pmmp/spages/Appel_Offre.aspx"
    
    def __init__(self, headless: bool = True, timeout: int = 30000):
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError(
                "Playwright is not installed. Run: pip install playwright && playwright install chromium"
            )
        self.headless = headless
        self.timeout = timeout
        self._browser: Optional[Browser] = None
    
    async def _init_browser(self):
        """Initialize Playwright browser."""
        playwright = await async_playwright().start()
        self._browser = await playwright.chromium.launch(headless=self.headless)
    
    async def _close_browser(self):
        """Close browser."""
        if self._browser:
            await self._browser.close()
            self._browser = None
    
    async def scrape(
        self,
        target_date: Optional[datetime] = None,
        category: str = "Fournitures",
        max_pages: int = 10
    ) -> ScrapeResult:
        """
        Scrape tenders for a specific date.
        
        Args:
            target_date: Date to scrape (defaults to yesterday)
            category: Tender category (default: Fournitures)
            max_pages: Maximum pagination pages to scrape
            
        Returns:
            ScrapeResult with scraped tenders and any errors
        """
        start_time = datetime.now()
        
        if target_date is None:
            target_date = datetime.now() - timedelta(days=1)
        
        tenders: list[ScrapedTender] = []
        errors: list[str] = []
        
        try:
            await self._init_browser()
            
            page = await self._browser.new_page()
            page.set_default_timeout(self.timeout)
            
            # Navigate to search page
            await page.goto(self.SEARCH_URL)
            
            # Apply filters (category: Fournitures, date)
            await self._apply_filters(page, target_date, category)
            
            # Scrape paginated results
            page_num = 1
            while page_num <= max_pages:
                page_tenders, has_next = await self._scrape_page(page, target_date)
                tenders.extend(page_tenders)
                
                if not has_next:
                    break
                    
                # Navigate to next page
                await self._goto_next_page(page, page_num + 1)
                page_num += 1
            
            # Download documents for each tender (in memory)
            for tender in tenders:
                try:
                    await self._download_documents(page, tender)
                except Exception as e:
                    errors.append(f"Failed to download docs for {tender.reference}: {str(e)}")
            
            await page.close()
            
        except Exception as e:
            errors.append(f"Scraping failed: {str(e)}")
        finally:
            await self._close_browser()
        
        duration = (datetime.now() - start_time).total_seconds()
        
        return ScrapeResult(
            success=len(errors) == 0,
            tenders=tenders,
            errors=errors,
            scraped_at=datetime.now(),
            target_date=target_date,
            duration_seconds=duration
        )
    
    async def _apply_filters(self, page: Page, target_date: datetime, category: str):
        """
        Apply search filters on the marchespublics.gov.ma page.
        
        NOTE: This is a placeholder. User should implement actual filter logic
        based on the website's form structure.
        """
        # Example filter application (adjust selectors as needed):
        # 
        # # Select category dropdown
        # await page.select_option('#ddlCategorie', label=category)
        # 
        # # Set date filter
        # date_str = target_date.strftime('%d/%m/%Y')
        # await page.fill('#txtDateDebut', date_str)
        # await page.fill('#txtDateFin', date_str)
        # 
        # # Click search button
        # await page.click('#btnRechercher')
        # await page.wait_for_load_state('networkidle')
        
        # Placeholder: wait for page to load
        await page.wait_for_load_state('networkidle')
    
    async def _scrape_page(
        self, 
        page: Page, 
        target_date: datetime
    ) -> tuple[list[ScrapedTender], bool]:
        """
        Scrape tenders from current results page.
        
        NOTE: This is a placeholder. User should implement actual parsing logic.
        
        Returns:
            Tuple of (list of scraped tenders, has_next_page)
        """
        tenders: list[ScrapedTender] = []
        
        # Example scraping logic (adjust selectors as needed):
        #
        # rows = await page.query_selector_all('table.results tbody tr')
        # 
        # for row in rows:
        #     reference = await row.query_selector('.reference')
        #     title = await row.query_selector('.title')
        #     org = await row.query_selector('.organization')
        #     deadline = await row.query_selector('.deadline')
        #     link = await row.query_selector('a.details')
        #     
        #     tender = ScrapedTender(
        #         reference=await reference.inner_text() if reference else "",
        #         title=await title.inner_text() if title else "",
        #         organization=await org.inner_text() if org else "",
        #         deadline=self._parse_date(await deadline.inner_text()) if deadline else None,
        #         source_url=await link.get_attribute('href') if link else "",
        #     )
        #     tenders.append(tender)
        #
        # # Check for next page
        # next_btn = await page.query_selector('.pagination .next:not(.disabled)')
        # has_next = next_btn is not None
        
        has_next = False  # Placeholder
        
        return tenders, has_next
    
    async def _goto_next_page(self, page: Page, page_num: int):
        """Navigate to next pagination page."""
        # Example:
        # await page.click(f'.pagination a[data-page="{page_num}"]')
        # await page.wait_for_load_state('networkidle')
        pass
    
    async def _download_documents(self, page: Page, tender: ScrapedTender):
        """
        Download tender documents into memory.
        
        NOTE: This is a placeholder. User should implement actual download logic.
        """
        # Example download logic:
        #
        # # Navigate to tender detail page
        # await page.goto(tender.source_url)
        # 
        # # Find document links
        # doc_links = await page.query_selector_all('.documents a[href*=".pdf"]')
        # 
        # for link in doc_links:
        #     url = await link.get_attribute('href')
        #     filename = await link.inner_text()
        #     
        #     # Download file into memory
        #     async with page.context.request as request:
        #         response = await request.get(url)
        #         content = await response.body()
        #         
        #         doc = ScrapedDocument(
        #             filename=filename,
        #             content=content,
        #             file_type=self._detect_file_type(filename),
        #             file_size=len(content),
        #             download_url=url
        #         )
        #         tender.documents.append(doc)
        pass
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string from website."""
        formats = [
            '%d/%m/%Y',
            '%d-%m-%Y',
            '%Y-%m-%d',
            '%d/%m/%Y %H:%M',
        ]
        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue
        return None
    
    def _detect_file_type(self, filename: str) -> str:
        """Detect document type from filename."""
        filename_lower = filename.lower()
        if 'rc' in filename_lower or 'reglement' in filename_lower:
            return 'rc'
        elif 'cps' in filename_lower or 'cahier' in filename_lower:
            return 'cps'
        elif 'annexe' in filename_lower:
            return 'annexe'
        return 'other'


# Convenience function for CLI usage
async def run_scraper(
    target_date: Optional[datetime] = None,
    headless: bool = True
) -> ScrapeResult:
    """Run the scraper with given parameters."""
    scraper = TenderScraper(headless=headless)
    return await scraper.scrape(target_date=target_date)

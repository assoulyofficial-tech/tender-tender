#!/usr/bin/env python3
"""
CLI for Tender AI Platform.
Run scraping from command line.

Usage:
    python -m app.cli scrape --date 2024-01-15
    python -m app.cli scrape --yesterday
    python -m app.cli status
"""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta

from app.services.scraper import run_scraper, PLAYWRIGHT_AVAILABLE
from app.services.scraper_db import ScraperDBService, document_store
from app.database import SessionLocal


def cmd_scrape(args):
    """Run scraper command."""
    if not PLAYWRIGHT_AVAILABLE:
        print("ERROR: Playwright not installed.")
        print("Run: pip install playwright && playwright install chromium")
        sys.exit(1)
    
    # Determine target date
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            print(f"ERROR: Invalid date format: {args.date}")
            print("Use YYYY-MM-DD format")
            sys.exit(1)
    elif args.yesterday:
        target_date = datetime.now() - timedelta(days=1)
    else:
        target_date = datetime.now() - timedelta(days=1)
    
    print(f"Starting scrape for: {target_date.date()}")
    print(f"Category: {args.category}")
    print(f"Headless: {not args.visible}")
    print("-" * 40)
    
    # Run scraper
    result = asyncio.run(run_scraper(
        target_date=target_date,
        headless=not args.visible
    ))
    
    print(f"\nScrape completed in {result.duration_seconds:.2f}s")
    print(f"Tenders found: {len(result.tenders)}")
    
    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for err in result.errors:
            print(f"  - {err}")
    
    # Store in memory
    for tender in result.tenders:
        for doc in tender.documents:
            document_store.store(tender.reference, doc.filename, doc.content)
    
    print(f"\nDocuments in memory: {document_store.count}")
    print(f"Memory usage: {document_store.size / 1024 / 1024:.2f} MB")
    
    # Save to database
    if args.save:
        print("\nSaving to database...")
        db = SessionLocal()
        try:
            db_service = ScraperDBService(db)
            db_result = db_service.save_scrape_result(result)
            print(f"  Created: {db_result['created']}")
            print(f"  Updated: {db_result['updated']}")
            print(f"  Skipped: {db_result['skipped']}")
            if db_result['errors']:
                print(f"  DB Errors: {len(db_result['errors'])}")
        finally:
            db.close()
    else:
        print("\nSkipping database save (use --save to persist)")
    
    # Summary
    print("\n" + "=" * 40)
    print("Scraped tenders:")
    for tender in result.tenders[:10]:  # Show first 10
        print(f"  [{tender.reference}] {tender.title[:50]}...")
    if len(result.tenders) > 10:
        print(f"  ... and {len(result.tenders) - 10} more")


def cmd_status(args):
    """Show scraper status."""
    print("Tender Scraper Status")
    print("=" * 40)
    print(f"Playwright available: {PLAYWRIGHT_AVAILABLE}")
    print(f"Documents in memory: {document_store.count}")
    print(f"Memory usage: {document_store.size / 1024 / 1024:.2f} MB")


def main():
    parser = argparse.ArgumentParser(
        description="Tender AI Platform CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Scrape command
    scrape_parser = subparsers.add_parser("scrape", help="Run tender scraper")
    scrape_parser.add_argument(
        "--date", "-d",
        help="Target date (YYYY-MM-DD)"
    )
    scrape_parser.add_argument(
        "--yesterday", "-y",
        action="store_true",
        help="Scrape yesterday's tenders (default)"
    )
    scrape_parser.add_argument(
        "--category", "-c",
        default="Fournitures",
        help="Tender category (default: Fournitures)"
    )
    scrape_parser.add_argument(
        "--visible", "-v",
        action="store_true",
        help="Show browser window (non-headless)"
    )
    scrape_parser.add_argument(
        "--save", "-s",
        action="store_true",
        help="Save results to database"
    )
    scrape_parser.set_defaults(func=cmd_scrape)
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Show scraper status")
    status_parser.set_defaults(func=cmd_status)
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == "__main__":
    main()

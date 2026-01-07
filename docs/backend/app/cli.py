#!/usr/bin/env python3
"""
CLI for Tender AI Platform.
Run scraping, extraction, and analysis from command line.

Usage:
    python -m app.cli scrape --date 2024-01-15
    python -m app.cli scrape --yesterday
    python -m app.cli extract --tender-id UUID
    python -m app.cli extract --pending
    python -m app.cli analyze --tender-id UUID
    python -m app.cli analyze --pending
    python -m app.cli deep-analyze --tender-id UUID
    python -m app.cli status
"""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta
from uuid import UUID

from app.services.scraper import run_scraper, PLAYWRIGHT_AVAILABLE
from app.services.scraper_db import ScraperDBService, document_store
from app.services.extraction_db import ExtractionDBService
from app.services.ai_db import AIDBService
from app.services.deep_analysis_db import DeepAnalysisDBService
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


def cmd_extract(args):
    """Run text extraction command."""
    print("Text Extraction Pipeline")
    print("=" * 40)
    
    db = SessionLocal()
    try:
        service = ExtractionDBService(db)
        
        if args.tender_id:
            try:
                tender_id = UUID(args.tender_id)
            except ValueError:
                print(f"ERROR: Invalid UUID: {args.tender_id}")
                sys.exit(1)
            
            print(f"Extracting from tender: {tender_id}")
            result = service.process_tender(tender_id)
            
            if "error" in result:
                print(f"ERROR: {result['error']}")
                sys.exit(1)
            
            print(f"\nResults for: {result['reference']}")
            print(f"  Successful: {result['success_count']}")
            print(f"  Failed: {result['error_count']}")
            
            for doc in result['documents']:
                status = "✓" if doc['success'] else "✗"
                method = f"({doc['method']})" if doc['method'] else ""
                print(f"  {status} {doc['filename']} {method}")
                if doc['error']:
                    print(f"      Error: {doc['error']}")
                elif doc['text_length']:
                    print(f"      Extracted: {doc['text_length']} chars, {doc['page_count'] or '?'} pages")
        
        elif args.pending:
            print(f"Processing pending documents (limit: {args.limit})")
            result = service.process_pending_documents(limit=args.limit)
            
            print(f"\nProcessed: {result['total']} documents")
            print(f"  Successful: {result['success']}")
            print(f"  Failed: {result['failed']}")
        
        else:
            print("Specify --tender-id UUID or --pending")
            sys.exit(1)
            
    finally:
        db.close()


def cmd_analyze(args):
    """Run AI analysis command."""
    print("AI Analysis Pipeline (DeepSeek)")
    print("=" * 40)
    
    db = SessionLocal()
    try:
        service = AIDBService(db)
        
        if not service.is_configured():
            print("ERROR: DeepSeek API key not configured.")
            print("Set DEEPSEEK_API_KEY in your .env file")
            sys.exit(1)
        
        if args.tender_id:
            try:
                tender_id = UUID(args.tender_id)
            except ValueError:
                print(f"ERROR: Invalid UUID: {args.tender_id}")
                sys.exit(1)
            
            print(f"Analyzing tender: {tender_id}")
            result = asyncio.run(service.analyze_tender(tender_id))
            
            if "error" in result:
                print(f"ERROR: {result['error']}")
                sys.exit(1)
            
            print(f"\nResults for: {result['reference']}")
            print(f"  Documents analyzed: {result['documents_analyzed']}")
            print(f"  Fields extracted: {result['fields_extracted']}")
            
            if result['errors']:
                print(f"\nErrors:")
                for err in result['errors']:
                    print(f"  - {err}")
        
        elif args.pending:
            print(f"Analyzing pending tenders (limit: {args.limit})")
            result = asyncio.run(service.analyze_pending_tenders(limit=args.limit))
            
            print(f"\nResults:")
            print(f"  Total pending: {result['total_pending']}")
            print(f"  Analyzed: {result['analyzed']}")
            
            if result['errors']:
                print(f"\nErrors ({len(result['errors'])}):")
                for err in result['errors'][:5]:
                    print(f"  - {err}")
                if len(result['errors']) > 5:
                    print(f"  ... and {len(result['errors']) - 5} more")
        
        else:
            print("Specify --tender-id UUID or --pending")
            sys.exit(1)
            
    finally:
        db.close()


def cmd_deep_analyze(args):
    """Run deep analysis command (on-demand)."""
    print("Deep Analysis Pipeline (DeepSeek)")
    print("=" * 40)
    print("Note: Deep analysis is normally triggered on-demand when user opens a tender.")
    print("")
    
    db = SessionLocal()
    try:
        service = DeepAnalysisDBService(db)
        
        if not service.is_configured():
            print("ERROR: DeepSeek API key not configured.")
            print("Set DEEPSEEK_API_KEY in your .env file")
            sys.exit(1)
        
        if not args.tender_id:
            print("ERROR: Deep analysis requires --tender-id UUID")
            print("(No batch mode - this is an on-demand analysis)")
            sys.exit(1)
        
        try:
            tender_id = UUID(args.tender_id)
        except ValueError:
            print(f"ERROR: Invalid UUID: {args.tender_id}")
            sys.exit(1)
        
        # Check if already analyzed
        if not args.force:
            existing = service.get_deep_analysis(tender_id)
            if existing:
                print(f"Tender already has deep analysis.")
                print(f"  Lots found: {len(existing.get('lots', []))}")
                print(f"  Has execution dates: {existing.get('execution_dates') is not None}")
                print(f"  Confidence: {existing.get('confidence_score', 0):.2f}")
                print("\nUse --force to re-analyze.")
                return
        
        print(f"Running deep analysis for: {tender_id}")
        result = asyncio.run(service.perform_deep_analysis(tender_id))
        
        if "error" in result:
            print(f"ERROR: {result['error']}")
            sys.exit(1)
        
        print(f"\nResults for: {result.get('reference', tender_id)}")
        print(f"  Fields extracted: {result['fields_extracted']}")
        print(f"  Lots found: {result['lots_found']}")
        print(f"  Has execution dates: {result['has_execution_dates']}")
        print(f"  Confidence score: {result['confidence_score']:.2f}")
        
        # Show some details
        analysis = result.get('analysis', {})
        if analysis.get('contract_type'):
            print(f"\n  Contract type: {analysis['contract_type']}")
        if analysis.get('procedure_type'):
            print(f"  Procedure type: {analysis['procedure_type']}")
        if analysis.get('award_criteria'):
            print(f"  Award criteria: {analysis['award_criteria']}")
        
        if result['lots_found'] > 0:
            print(f"\n  Lots:")
            for lot in analysis.get('lots', [])[:5]:
                print(f"    - Lot {lot.get('lot_number', '?')}: {lot.get('title', 'N/A')}")
            if result['lots_found'] > 5:
                print(f"    ... and {result['lots_found'] - 5} more")
                
    finally:
        db.close()


def cmd_status(args):
    """Show platform status."""
    print("Tender AI Platform Status")
    print("=" * 40)
    print(f"Playwright available: {PLAYWRIGHT_AVAILABLE}")
    print(f"Documents in memory: {document_store.count}")
    print(f"Memory usage: {document_store.size / 1024 / 1024:.2f} MB")
    
    # Check extraction dependencies
    deps = {
        "PyMuPDF (PDF)": "fitz",
        "python-docx (DOCX)": "docx",
        "openpyxl (XLSX)": "openpyxl",
        "xlrd (XLS)": "xlrd",
        "PaddleOCR": "paddleocr",
        "httpx (HTTP)": "httpx",
    }
    
    print("\nExtraction dependencies:")
    for name, module in deps.items():
        try:
            __import__(module)
            print(f"  ✓ {name}")
        except ImportError:
            print(f"  ✗ {name} (not installed)")
    
    # Check AI configuration
    from app.config import settings
    print("\nAI Configuration:")
    if settings.deepseek_api_key:
        print(f"  ✓ DeepSeek API configured")
        print(f"    Model: {settings.deepseek_model}")
        print(f"  ✓ Deep Analysis available")
    else:
        print(f"  ✗ DeepSeek API key not set")
        print("    Set DEEPSEEK_API_KEY in .env")


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
    
    # Extract command
    extract_parser = subparsers.add_parser("extract", help="Extract text from documents")
    extract_parser.add_argument(
        "--tender-id", "-t",
        help="Tender UUID to process"
    )
    extract_parser.add_argument(
        "--pending", "-p",
        action="store_true",
        help="Process all pending documents"
    )
    extract_parser.add_argument(
        "--limit", "-l",
        type=int,
        default=50,
        help="Max documents to process (default: 50)"
    )
    extract_parser.set_defaults(func=cmd_extract)
    
    # Analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Run AI analysis (Avis)")
    analyze_parser.add_argument(
        "--tender-id", "-t",
        help="Tender UUID to analyze"
    )
    analyze_parser.add_argument(
        "--pending", "-p",
        action="store_true",
        help="Analyze all pending tenders"
    )
    analyze_parser.add_argument(
        "--limit", "-l",
        type=int,
        default=10,
        help="Max tenders to analyze (default: 10)"
    )
    analyze_parser.set_defaults(func=cmd_analyze)
    
    # Deep Analyze command
    deep_analyze_parser = subparsers.add_parser("deep-analyze", help="Run deep analysis (on-demand)")
    deep_analyze_parser.add_argument(
        "--tender-id", "-t",
        required=True,
        help="Tender UUID to deep analyze"
    )
    deep_analyze_parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force re-analysis even if already analyzed"
    )
    deep_analyze_parser.set_defaults(func=cmd_deep_analyze)
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Show platform status")
    status_parser.set_defaults(func=cmd_status)
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == "__main__":
    main()

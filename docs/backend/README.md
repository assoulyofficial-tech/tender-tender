# Tender AI Platform - Backend

FastAPI backend for the Tender AI Platform V1.

## Prerequisites

- Python 3.11+
- PostgreSQL 14+

## Quick Start

### 1. Create PostgreSQL Database

```bash
# Connect to PostgreSQL
psql -U postgres

# Create database
CREATE DATABASE tender_db;

# Exit
\q
```

### 2. Setup Python Environment

```bash
cd docs/backend

# Create virtual environment
python -m venv venv

# Activate (Linux/Mac)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
# Copy example env
cp .env.example .env

# Edit .env with your database credentials if different
```

### 4. Run Database Migrations

```bash
# Generate initial migration
alembic revision --autogenerate -m "Initial tables"

# Apply migrations
alembic upgrade head
```

### 5. Start Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Root info |
| `/health` | GET | Health check |
| `/docs` | GET | Swagger UI |
| `/api/tenders` | GET | List tenders (paginated) |
| `/api/tenders/{id}` | GET | Get tender details |
| `/api/scraping/status` | GET | Scraper status & readiness |
| `/api/scraping/trigger` | POST | Trigger manual scrape |
| `/api/scraping/last-result` | GET | Get last scrape result |
| `/api/scraping/clear-memory` | POST | Clear in-memory documents |
| `/api/scraping/documents/{ref}` | GET | Get tender docs in memory |
| `/api/extraction/trigger` | POST | Trigger text extraction |
| `/api/extraction/tender/{id}` | POST | Extract for specific tender |
| `/api/extraction/pending` | POST | Process pending documents |
| `/api/analysis/status` | GET | Check AI analysis config |
| `/api/analysis/tender/{id}` | POST | Run Avis analysis |
| `/api/analysis/pending` | POST | Analyze pending tenders |
| `/api/deep-analysis/status/{id}` | GET | Check deep analysis status |
| `/api/deep-analysis/{id}` | GET | Get deep analysis results |
| `/api/deep-analysis/{id}` | POST | Trigger deep analysis (on-demand) |
| `/api/deep-analysis/{id}/lots` | GET | Get lot items |
| `/api/deep-analysis/{id}/execution` | GET | Get execution dates |
| `/api/deep-analysis/{id}/provenance` | GET | Get field provenance |
| `/api/ask/status` | GET | Check Ask AI config |
| `/api/ask/tender/{id}/summary` | GET | Get tender context summary |
| `/api/ask/tender/{id}/suggestions` | GET | Get suggested questions |
| `/api/ask/tender/{id}` | POST | Ask a question about tender |
| `/api/ask/tender/{id}/quick` | POST | Quick ask (no history) |

### Trigger Scraping

```bash
# Scrape yesterday's tenders
curl -X POST http://localhost:8000/api/scraping/trigger \
  -H "Content-Type: application/json" \
  -d '{"category": "Fournitures"}'

# Scrape specific date
curl -X POST http://localhost:8000/api/scraping/trigger \
  -H "Content-Type: application/json" \
  -d '{"target_date": "2024-01-15", "category": "Fournitures"}'
```

### Trigger Text Extraction

```bash
# Extract from specific tender
curl -X POST http://localhost:8000/api/extraction/tender/{tender-uuid}

# Process all pending documents
curl -X POST "http://localhost:8000/api/extraction/pending?limit=50"

# Trigger with optional tender_id
curl -X POST http://localhost:8000/api/extraction/trigger \
  -H "Content-Type: application/json" \
  -d '{"tender_id": "uuid-here"}'
```

### CLI Usage

```bash
# Scrape yesterday (default)
python -m app.cli scrape

# Scrape specific date and save to DB
python -m app.cli scrape --date 2024-01-15 --save

# Scrape with visible browser
python -m app.cli scrape --visible

# Extract text from a tender's documents
python -m app.cli extract --tender-id UUID

# Process all pending documents
python -m app.cli extract --pending --limit 50

# Check status (includes extraction deps)
python -m app.cli status
```

### Query Parameters for `/api/tenders`

- `search` - Search in title, reference, organization
- `status` - Filter by status (open, closed, awarded, cancelled)
- `category` - Filter by category
- `page` - Page number (default: 1)
- `page_size` - Items per page (default: 20, max: 100)

## Database Schema

### Tables

1. **tenders** - Main tender metadata
2. **tender_documents** - Attached documents (PDFs, etc.)
3. **tender_fields** - Extracted fields with provenance
4. **processing_states** - Pipeline processing status

### Enums

- `TenderStatus`: open, closed, awarded, cancelled
- `DocumentType`: rc, cps, annexe, other
- `OCRStatus`: pending, processing, completed, failed
- `ProcessingStatus`: pending, scraping, downloading, ocr, analyzing, completed, failed
- `FieldSource`: scraped, ocr, ai, manual

## Text Extraction Pipeline

### Supported Formats

| Format | Method | Notes |
|--------|--------|-------|
| PDF (digital) | PyMuPDF | Direct text extraction |
| PDF (scanned) | PaddleOCR | Automatic fallback |
| DOCX | python-docx | Paragraphs + tables |
| DOC | - | Not supported (convert to DOCX) |
| XLSX | openpyxl | All sheets |
| XLS | xlrd | All sheets |

### OCR Configuration

- Engine: PaddleOCR (local, CPU-only)
- Language: French (`lang='fr'`)
- Fallback: Only when digital extraction fails

### Installation Notes

```bash
# PaddlePaddle (CPU)
pip install paddlepaddle

# PaddleOCR
pip install paddleocr

# Note: First OCR run will download models (~150MB)
```

## AI Analysis Pipeline (Step 4)

### Configuration

Add your DeepSeek API key to `.env`:

```bash
DEEPSEEK_API_KEY=your-api-key-here
DEEPSEEK_MODEL=deepseek-chat  # default
```

### Extracted Metadata (Avis Schema)

| Field | Type | Description |
|-------|------|-------------|
| `keywords_fr` | list | French keywords |
| `keywords_ar` | list | Arabic keywords |
| `keywords_en` | list | English keywords |
| `eligibility_criteria` | list | Eligibility requirements |
| `submission_requirements` | list | What to submit |
| `technical_requirements` | list | Technical specs |
| `required_documents` | list | Documents needed |
| `submission_address` | string | Where to submit |
| `opening_location` | string | Bid opening location |
| `lots` | json | Multiple lots info |
| `notes` | string | Additional notes |

### Override Rules

1. **Website deadline override**: Deadline from website takes precedence over document
2. **Annex override**: Annex documents can override main document values

### API Endpoints

```bash
# Check AI status
curl http://localhost:8000/api/analysis/status

# Analyze specific tender
curl -X POST http://localhost:8000/api/analysis/tender/{uuid}

# Analyze pending tenders
curl -X POST "http://localhost:8000/api/analysis/pending?limit=10"
```

### CLI Usage

```bash
# Analyze specific tender
python -m app.cli analyze --tender-id UUID

# Analyze all pending tenders
python -m app.cli analyze --pending --limit 10

# Check status (shows AI config)
python -m app.cli status
```

## Deep Analysis Pipeline (Step 5)

### Trigger

Deep analysis is triggered **on-demand** when a user opens a tender (not background).

### Extracted Data (Universal Fields Schema)

| Category | Fields |
|----------|--------|
| **Contract** | contract_type, procedure_type, award_criteria |
| **Financial** | payment_terms, advance_payment, retention_percentage, currency |
| **Guarantees** | bid_guarantee, performance_guarantee, advance_guarantee |
| **Technical** | technical_specifications, quality_standards, environmental_requirements |
| **Eligibility** | minimum_experience_years, required_certifications, required_equipment, minimum_turnover |
| **Lots** | lot_number, title, description, quantity, unit, estimated_value |
| **Execution** | start_date, end_date, duration_days, duration_months, milestones |
| **Contact** | contracting_authority, contact_name, contact_email, contact_phone |

### Rules

1. **Annex reconciliation**: Annex documents can override main document values
2. **Field provenance tracking**: Each field tracks its source document, confidence, and location
3. **No background execution**: Runs synchronously when user views tender

### API Endpoints

```bash
# Check if tender needs deep analysis
curl http://localhost:8000/api/deep-analysis/status/{uuid}

# Get existing deep analysis
curl http://localhost:8000/api/deep-analysis/{uuid}

# Trigger deep analysis (on-demand)
curl -X POST http://localhost:8000/api/deep-analysis/{uuid}

# Force re-analysis
curl -X POST "http://localhost:8000/api/deep-analysis/{uuid}?force=true"

# Get lot items
curl http://localhost:8000/api/deep-analysis/{uuid}/lots

# Get execution dates
curl http://localhost:8000/api/deep-analysis/{uuid}/execution

# Get field provenance
curl http://localhost:8000/api/deep-analysis/{uuid}/provenance
```

### CLI Usage

```bash
# Deep analyze a tender (on-demand)
python -m app.cli deep-analyze --tender-id UUID

# Force re-analysis
python -m app.cli deep-analyze --tender-id UUID --force

# Check status (shows deep analysis config)
python -m app.cli status
```

## Ask AI Feature (Step 6)

### Behavior

- **Multilingual**: Accepts French, Moroccan Darija, Arabic, English
- **Full context**: Uses all tender documents and analysis
- **Source citations**: Every answer includes document citations

### Supported Languages

| Language | Code | Example Question |
|----------|------|------------------|
| French | `fr` | "Quels documents dois-je fournir ?" |
| Darija | `ar-ma` | "شنو هي الوثائق اللي خاصني نقدم؟" |
| Arabic | `ar` | "ما هي الوثائق المطلوبة؟" |
| English | `en` | "What documents do I need to submit?" |

### API Endpoints

```bash
# Check Ask AI status
curl http://localhost:8000/api/ask/status

# Get tender summary (documents available)
curl http://localhost:8000/api/ask/tender/{uuid}/summary

# Get suggested questions
curl "http://localhost:8000/api/ask/tender/{uuid}/suggestions?language=fr"
curl "http://localhost:8000/api/ask/tender/{uuid}/suggestions?language=ar-ma"

# Ask a question
curl -X POST http://localhost:8000/api/ask/tender/{uuid} \
  -H "Content-Type: application/json" \
  -d '{"question": "Quels sont les documents requis ?"}'

# Ask with conversation history
curl -X POST http://localhost:8000/api/ask/tender/{uuid} \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Et les délais ?",
    "conversation_history": [
      {"question": "Quels documents ?", "answer": "Les documents requis sont..."}
    ]
  }'

# Quick ask (simple)
curl -X POST "http://localhost:8000/api/ask/tender/{uuid}/quick?question=Quel%20budget"
```

### CLI Usage

```bash
# Ask a single question
python -m app.cli ask --tender-id UUID --question "Quels documents ?"

# Interactive mode (conversation)
python -m app.cli ask --tender-id UUID

# Example Darija question
python -m app.cli ask --tender-id UUID --question "شنو هي الشروط؟"
```

### Response Format

```json
{
  "answer": "Les documents requis sont: ...",
  "language_detected": "fr",
  "citations": [
    {
      "document_name": "RC_AO_2024.pdf",
      "section": "Article 5",
      "quote": "Le soumissionnaire doit fournir..."
    }
  ],
  "confidence": 0.85,
  "follow_up_suggestions": [
    "Quel est le délai de soumission ?",
    "Quelles sont les garanties demandées ?"
  ]
}
```

## Project Structure

```
docs/backend/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI app
│   ├── config.py        # Settings
│   ├── database.py      # DB connection
│   ├── cli.py           # CLI commands
│   ├── models/          # SQLAlchemy models
│   │   ├── __init__.py
│   │   └── tender.py
│   ├── schemas/         # Pydantic schemas
│   │   ├── __init__.py
│   │   └── tender.py
│   ├── services/        # Business logic
│   │   ├── __init__.py
│   │   ├── scraper.py
│   │   ├── scraper_db.py
│   │   ├── extractor.py        # Text extraction
│   │   ├── extraction_db.py    # Extraction DB
│   │   ├── ai_analyzer.py      # Avis AI (Step 4)
│   │   ├── ai_db.py            # Avis DB integration
│   │   ├── deep_analyzer.py    # Deep AI (Step 5)
│   │   ├── deep_analysis_db.py # Deep DB integration
│   │   ├── ask_ai.py           # Ask AI service (Step 6)
│   │   └── ask_ai_db.py        # Ask AI DB integration
│   └── api/             # API routes
│       ├── __init__.py
│       ├── tenders.py
│       ├── scraping.py
│       ├── extraction.py
│       ├── analysis.py
│       ├── deep_analysis.py
│       └── ask_ai.py
├── alembic/             # Migrations
├── alembic.ini
├── requirements.txt
└── README.md
```

## Next Steps (Future Prompts)

- [x] Step 1: Database schema & API
- [x] Step 2: Scraping module
- [x] Step 3: Text extraction pipeline (OCR)
- [x] Step 4: AI analysis (DeepSeek) - Avis metadata
- [x] Step 5: Deep analysis (on-demand) - Universal fields, lots, execution dates
- [x] Step 6: Ask AI - Conversational Q&A (French, Darija)
- [ ] Step 7: Background job queue

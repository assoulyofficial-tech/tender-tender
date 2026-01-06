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

## Project Structure

```
docs/backend/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI app
│   ├── config.py        # Settings
│   ├── database.py      # DB connection
│   ├── models/          # SQLAlchemy models
│   │   ├── __init__.py
│   │   └── tender.py
│   ├── schemas/         # Pydantic schemas
│   │   ├── __init__.py
│   │   └── tender.py
│   └── api/             # API routes
│       ├── __init__.py
│       └── tenders.py
├── alembic/             # Migrations
├── alembic.ini
├── requirements.txt
└── README.md
```

## Next Steps (Future Prompts)

- [ ] Step 2: Scraping module
- [ ] Step 3: OCR pipeline (PaddleOCR)
- [ ] Step 4: AI analysis (DeepSeek)
- [ ] Step 5: Background job queue

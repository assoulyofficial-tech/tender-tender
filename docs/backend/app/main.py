from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api import api_router

app = FastAPI(
    title="Tender AI Platform",
    description="Backend API for Tender AI Platform - V1",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "1.0.0"}


@app.get("/")
def root():
    """Root endpoint."""
    return {
        "message": "Tender AI Platform API",
        "docs": "/docs",
        "health": "/health"
    }

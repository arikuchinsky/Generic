"""FastAPI application entry point for the Legal Document Polisher."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import examples, polish, rules


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown lifecycle."""
    # Startup
    settings.jobs_dir.mkdir(parents=True, exist_ok=True)
    yield
    # Shutdown (cleanup old jobs if needed)


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(polish.router)
app.include_router(examples.router)
app.include_router(rules.router)


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "app": settings.app_name}

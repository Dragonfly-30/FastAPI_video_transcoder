import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.database import Base, engine
from app.core.exceptions import JobNotFoundError, AppException
from app.services.storage_service import get_storage_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initializes database tables and MinIO storage on startup."""
    # 1. Database table bootstrap
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Initialized database tables")
    except Exception as e:
        logger.warning(f"Could not initialize database tables during startup: {e}")

    # 2. MinIO storage bucket verification
    try:
        storage = get_storage_service()
        storage.ensure_bucket_exists()
        logger.info(f"Initialized MinIO bucket: '{settings.MINIO_BUCKET_NAME}'")
    except Exception as e:
        logger.warning(f"Could not initialize MinIO bucket during startup: {e}")
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="Asynchronous video transcoding service using FastAPI, MinIO, Celery, and FFmpeg.",
    lifespan=lifespan,
)


@app.exception_handler(JobNotFoundError)
async def job_not_found_exception_handler(request: Request, exc: JobNotFoundError):
    """Translates domain JobNotFoundError into HTTP 404 response."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": exc.message},
    )


@app.exception_handler(AppException)
async def general_app_exception_handler(request: Request, exc: AppException):
    """Translates generic application exceptions into HTTP 400 response."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": exc.message},
    )


@app.get("/health", tags=["Health"])
def health_check():
    """Health check endpoint for container orchestrators."""
    return {"status": "healthy", "service": settings.PROJECT_NAME}


app.include_router(api_v1_router, prefix=settings.API_V1_STR)

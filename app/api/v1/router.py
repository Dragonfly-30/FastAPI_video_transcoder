from fastapi import APIRouter

from app.api.v1.uploads import router as uploads_router
from app.api.v1.jobs import router as jobs_router

api_v1_router = APIRouter()

api_v1_router.include_router(uploads_router)
api_v1_router.include_router(jobs_router)

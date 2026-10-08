import uuid
from fastapi import APIRouter, Depends, status

from app.schemas.job import JobCreateRequest, JobResponse
from app.services.job_service import JobService, get_job_service

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(
    payload: JobCreateRequest,
    job_service: JobService = Depends(get_job_service),
) -> JobResponse:
    """Creates a new video transcoding job and enqueues it to the worker."""
    return job_service.create_transcoding_job(payload)


@router.get("/{job_id}", response_model=JobResponse)
def get_job(
    job_id: uuid.UUID,
    job_service: JobService = Depends(get_job_service),
) -> JobResponse:
    """Retrieves the status and result of a transcoding job."""
    return job_service.get_job_status(job_id)

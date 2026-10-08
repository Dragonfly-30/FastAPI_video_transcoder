import uuid
from typing import Optional
from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import JobNotFoundError
from app.models.job import JobStatus
from app.repositories.job_repository import JobRepository
from app.schemas.job import JobCreateRequest, JobResponse
from app.services.storage_service import StorageService, get_storage_service
from app.worker.tasks import transcode_video_task


class JobService:
    def __init__(self, repo: JobRepository, storage: StorageService) -> None:
        self.repo = repo
        self.storage = storage

    def create_transcoding_job(self, job_in: JobCreateRequest) -> JobResponse:
        """Creates a new job in PostgreSQL with status PENDING,
        then enqueues the transcoding task in Celery.
        """
        job = self.repo.create(job_in)
        # Dispatch background job to Celery worker
        transcode_video_task.delay(str(job.id))
        return JobResponse.model_validate(job)

    def get_job_status(self, job_id: uuid.UUID) -> JobResponse:
        """Retrieves job state from the database.
        If completed, generates a temporary presigned download URL for the output.
        """
        job = self.repo.get_by_id(job_id)
        if not job:
            raise JobNotFoundError(f"Transcoding job with ID '{job_id}' not found")

        response = JobResponse.model_validate(job)

        # If job is completed, generate a presigned download URL
        if job.status == JobStatus.COMPLETED.value and job.output_key:
            response.download_url = self.storage.generate_presigned_download_url(job.output_key)

        return response


def get_job_service(
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
) -> JobService:
    """Dependency injector providing JobService with repository and storage dependencies."""
    repo = JobRepository(db)
    return JobService(repo=repo, storage=storage)

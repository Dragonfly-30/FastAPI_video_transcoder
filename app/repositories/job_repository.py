import uuid
from typing import Optional
from sqlalchemy.orm import Session

from app.models.job import TranscodingJob, JobStatus
from app.schemas.job import JobCreateRequest


class JobRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, job_in: JobCreateRequest) -> TranscodingJob:
        job = TranscodingJob(
            id=uuid.uuid4(),
            original_filename=job_in.original_filename,
            input_key=job_in.input_key,
            target_quality=job_in.target_quality.value,
            status=JobStatus.PENDING.value,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get_by_id(self, job_id: uuid.UUID) -> Optional[TranscodingJob]:
        return self.db.query(TranscodingJob).filter(TranscodingJob.id == job_id).first()

    def update_status(
        self,
        job_id: uuid.UUID,
        status: JobStatus,
        error_message: Optional[str] = None,
    ) -> Optional[TranscodingJob]:
        job = self.get_by_id(job_id)
        if not job:
            return None
        job.status = status.value
        if error_message is not None:
            job.error_message = error_message
        self.db.commit()
        self.db.refresh(job)
        return job

    def complete_job(self, job_id: uuid.UUID, output_key: str) -> Optional[TranscodingJob]:
        job = self.get_by_id(job_id)
        if not job:
            return None
        job.status = JobStatus.COMPLETED.value
        job.output_key = output_key
        job.error_message = None
        self.db.commit()
        self.db.refresh(job)
        return job

    def mark_failed(self, job_id: uuid.UUID, error_message: str) -> Optional[TranscodingJob]:
        return self.update_status(job_id, JobStatus.FAILED, error_message=error_message)

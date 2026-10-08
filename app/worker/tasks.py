import logging
import os
import tempfile
import uuid
from pathlib import Path

from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.core.exceptions import InvalidMediaFileError, FFmpegExecutionError
from app.models.job import JobStatus
from app.repositories.job_repository import JobRepository
from app.services.storage_service import get_storage_service
from app.worker.transcoder import Transcoder

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=2)
def transcode_video_task(self, job_id_str: str) -> dict:
    """Background task orchestrating the complete video transcoding pipeline:
    1. Sets DB status to PROCESSING.
    2. Downloads raw video into an isolated temporary workspace.
    3. Runs FFprobe validation and FFmpeg transcoding.
    4. Uploads the transcoded file to MinIO under 'transcoded/{job_id}/...'.
    5. Sets DB status to COMPLETED (or FAILED if invalid/error).
    6. Ensures local scratch workspace is wiped on completion.
    """
    job_id = uuid.UUID(job_id_str)
    db = SessionLocal()
    repo = JobRepository(db)

    try:
        job = repo.get_by_id(job_id)
        if not job:
            logger.error(f"Job not found for ID: {job_id}")
            return {"job_id": job_id_str, "status": "not_found"}

        logger.info(f"Transitioning job {job_id} to PROCESSING")
        repo.update_status(job_id, JobStatus.PROCESSING)

        storage_service = get_storage_service()
        transcoder = Transcoder()

        with tempfile.TemporaryDirectory(prefix=f"transcode_{job_id}_") as temp_dir:
            # Prepare paths
            input_filename = Path(job.input_key).name
            local_input = os.path.join(temp_dir, f"in_{input_filename}")

            output_basename = Path(f"{job.target_quality}_{job.original_filename}").with_suffix(".mp4").name
            local_output = os.path.join(temp_dir, f"out_{output_basename}")
            output_s3_key = f"transcoded/{job.id}/{output_basename}"

            # Step 1: Download input
            logger.info(f"Downloading raw video: {job.input_key} -> {local_input}")
            storage_service.download_file(job.input_key, local_input)

            # Step 2: Transcode with FFmpeg
            logger.info(f"Transcoding video to {job.target_quality}")
            transcoder.transcode(
                input_path=local_input,
                output_path=local_output,
                target_quality=job.target_quality,
            )

            # Step 3: Upload transcoded output
            logger.info(f"Uploading transcoded video to MinIO: {output_s3_key}")
            storage_service.upload_file(local_output, output_s3_key)

            # Step 4: Mark completed
            repo.complete_job(job_id, output_key=output_s3_key)
            logger.info(f"Job {job_id} successfully completed")

            return {
                "job_id": str(job_id),
                "status": JobStatus.COMPLETED.value,
                "output_key": output_s3_key,
            }

    except (InvalidMediaFileError, FFmpegExecutionError) as e:
        logger.error(f"Media processing failure for job {job_id}: {e}")
        repo.mark_failed(job_id, error_message=str(e))
        return {
            "job_id": str(job_id),
            "status": JobStatus.FAILED.value,
            "error": str(e),
        }

    except Exception as e:
        logger.exception(f"Unexpected error processing job {job_id}: {e}")
        repo.mark_failed(job_id, error_message=f"Internal processing failure: {e}")
        raise e

    finally:
        db.close()

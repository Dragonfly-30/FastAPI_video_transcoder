import uuid
from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from app.models.job import JobStatus, VideoQuality
from app.schemas.job import (
    PresignedUrlRequest,
    PresignedUrlResponse,
    JobCreateRequest,
    JobResponse,
)


def test_presigned_url_request_valid():
    req = PresignedUrlRequest(filename="intro.mp4")
    assert req.filename == "intro.mp4"


def test_presigned_url_request_empty():
    with pytest.raises(ValidationError):
        PresignedUrlRequest(filename="")


def test_job_create_request_defaults_and_validation():
    req = JobCreateRequest(
        original_filename="intro.mp4",
        input_key="raw/123-intro.mp4",
    )
    assert req.target_quality == VideoQuality.Q_720P

    # Invalid quality
    with pytest.raises(ValidationError):
        JobCreateRequest(
            original_filename="intro.mp4",
            input_key="raw/123-intro.mp4",
            target_quality="4k",
        )


def test_job_response_serialization():
    job_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    res = JobResponse(
        id=job_id,
        original_filename="test.mp4",
        target_quality=VideoQuality.Q_1080P,
        status=JobStatus.COMPLETED,
        input_key="raw/test.mp4",
        output_key="transcoded/test-1080p.mp4",
        download_url="https://minio/download",
        created_at=now,
        updated_at=now,
    )
    assert res.id == job_id
    assert res.status == JobStatus.COMPLETED
    assert res.download_url == "https://minio/download"

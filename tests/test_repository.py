import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.job import JobStatus, VideoQuality
from app.schemas.job import JobCreateRequest
from app.repositories.job_repository import JobRepository


@pytest.fixture
def db_session():
    # SQLite in-memory engine for unit testing repository without PostgreSQL
    test_engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=test_engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_create_and_get_job(db_session):
    repo = JobRepository(db_session)
    job_in = JobCreateRequest(
        original_filename="sample.mp4",
        input_key="raw/sample.mp4",
        target_quality=VideoQuality.Q_720P,
    )
    job = repo.create(job_in)

    assert job.id is not None
    assert job.original_filename == "sample.mp4"
    assert job.status == JobStatus.PENDING.value
    assert job.target_quality == "720p"

    fetched = repo.get_by_id(job.id)
    assert fetched is not None
    assert fetched.id == job.id


def test_update_status_and_complete_job(db_session):
    repo = JobRepository(db_session)
    job = repo.create(
        JobCreateRequest(
            original_filename="clip.mov",
            input_key="raw/clip.mov",
            target_quality=VideoQuality.Q_1080P,
        )
    )

    # Transition to PROCESSING
    updated = repo.update_status(job.id, JobStatus.PROCESSING)
    assert updated.status == JobStatus.PROCESSING.value

    # Complete job
    completed = repo.complete_job(job.id, output_key="transcoded/clip-1080p.mp4")
    assert completed.status == JobStatus.COMPLETED.value
    assert completed.output_key == "transcoded/clip-1080p.mp4"
    assert completed.error_message is None


def test_mark_failed_job(db_session):
    repo = JobRepository(db_session)
    job = repo.create(
        JobCreateRequest(
            original_filename="corrupted.mp4",
            input_key="raw/corrupted.mp4",
        )
    )

    failed = repo.mark_failed(job.id, error_message="FFmpeg exited with non-zero status")
    assert failed.status == JobStatus.FAILED.value
    assert failed.error_message == "FFmpeg exited with non-zero status"

import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.job import JobStatus, VideoQuality


class PresignedUrlRequest(BaseModel):
    filename: str = Field(..., min_length=1, description="Original filename with extension (e.g., sample.mp4)")


class PresignedUrlResponse(BaseModel):
    upload_url: str = Field(..., description="Presigned S3/MinIO PUT URL for direct upload")
    object_key: str = Field(..., description="Storage key where the uploaded raw file will reside")


class JobCreateRequest(BaseModel):
    original_filename: str = Field(..., min_length=1, description="Original filename of the uploaded video")
    input_key: str = Field(..., min_length=1, description="Storage object key returned by the upload presigned URL")
    target_quality: VideoQuality = Field(default=VideoQuality.Q_720P, description="Target video quality/resolution")


class JobResponse(BaseModel):
    id: uuid.UUID
    original_filename: str
    target_quality: VideoQuality
    status: JobStatus
    input_key: str
    output_key: Optional[str] = None
    download_url: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

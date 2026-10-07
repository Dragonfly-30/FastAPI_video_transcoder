import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, String, Text, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.types import TypeDecorator, CHAR

from app.core.database import Base


class GUID(TypeDecorator):
    """Platform-independent GUID type.
    Uses PostgreSQL's UUID type, otherwise uses CHAR(36) for SQLite/other databases.
    """
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        if not isinstance(value, uuid.UUID):
            return str(uuid.UUID(value))
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            return uuid.UUID(value)
        return value


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class VideoQuality(str, enum.Enum):
    Q_360P = "360p"
    Q_480P = "480p"
    Q_720P = "720p"
    Q_1080P = "1080p"


class TranscodingJob(Base):
    __tablename__ = "transcoding_jobs"

    id = Column(GUID, primary_key=True, default=uuid.uuid4, index=True)
    original_filename = Column(String(255), nullable=False)
    target_quality = Column(String(50), nullable=False)
    status = Column(String(50), default=JobStatus.PENDING.value, nullable=False, index=True)
    input_key = Column(String(512), nullable=False)
    output_key = Column(String(512), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<TranscodingJob id={self.id} status={self.status} target={self.target_quality}>"

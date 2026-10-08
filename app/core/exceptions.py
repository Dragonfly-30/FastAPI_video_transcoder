class AppException(Exception):
    """Base application exception."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class JobNotFoundError(AppException):
    """Raised when a requested transcoding job does not exist."""
    pass


class StorageOperationError(AppException):
    """Raised when an S3 / MinIO operation fails."""
    pass


class TranscodingError(AppException):
    """Base exception for video processing failures."""
    pass


class InvalidMediaFileError(TranscodingError):
    """Raised when an uploaded file is not a valid video or cannot be probed."""
    pass


class FFmpegExecutionError(TranscodingError):
    """Raised when FFmpeg subprocess returns a non-zero exit code or times out."""
    pass

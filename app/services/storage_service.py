import os
import re
import uuid
from pathlib import Path
from typing import Optional, Tuple
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import settings


def sanitize_filename(filename: str) -> str:
    """Strips path traversal sequences and unsafe characters from filenames."""
    clean_name = Path(filename).name
    # Keep alphanumeric, dots, hyphens, and underscores
    clean_name = re.sub(r"[^\w.\-]", "_", clean_name)
    return clean_name or "video.mp4"


class StorageService:
    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        bucket_name: Optional[str] = None,
        secure: Optional[bool] = None,
        expiry_seconds: Optional[int] = None,
    ) -> None:
        self.endpoint = endpoint_url or settings.MINIO_ENDPOINT
        self.access_key = access_key or settings.MINIO_ACCESS_KEY
        self.secret_key = secret_key or settings.MINIO_SECRET_KEY
        self.bucket_name = bucket_name or settings.MINIO_BUCKET_NAME
        self.secure = secure if secure is not None else settings.MINIO_SECURE
        self.expiry_seconds = expiry_seconds or settings.PRESIGNED_URL_EXPIRY_SECONDS

        # Format endpoint with scheme if missing
        if not self.endpoint.startswith("http://") and not self.endpoint.startswith("https://"):
            scheme = "https://" if self.secure else "http://"
            self.endpoint = f"{scheme}{self.endpoint}"

        self.s3_client = boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
            ),
        )

    def ensure_bucket_exists(self) -> None:
        """Verifies if the target bucket exists, creating it if it does not."""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            # 404 or NoSuchBucket indicates bucket does not exist
            if error_code in ("404", "NoSuchBucket"):
                self.s3_client.create_bucket(Bucket=self.bucket_name)
            else:
                raise

    def generate_presigned_upload_url(
        self, filename: str, expires_in: Optional[int] = None
    ) -> Tuple[str, str]:
        """Generates a presigned PUT URL and isolated object key for raw uploads."""
        clean_filename = sanitize_filename(filename)
        upload_id = uuid.uuid4()
        object_key = f"raw/{upload_id}/{clean_filename}"

        url = self.s3_client.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": self.bucket_name,
                "Key": object_key,
            },
            ExpiresIn=expires_in or self.expiry_seconds,
        )
        return url, object_key

    def generate_presigned_download_url(
        self, object_key: str, expires_in: Optional[int] = None
    ) -> str:
        """Generates a presigned GET URL for downloading transcoded outputs."""
        return self.s3_client.generate_presigned_url(
            ClientMethod="get_object",
            Params={
                "Bucket": self.bucket_name,
                "Key": object_key,
            },
            ExpiresIn=expires_in or self.expiry_seconds,
        )

    def download_file(self, object_key: str, local_path: str) -> None:
        """Downloads an object from MinIO to a local scratch file."""
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        self.s3_client.download_file(self.bucket_name, object_key, local_path)

    def upload_file(
        self, local_path: str, object_key: str, content_type: str = "video/mp4"
    ) -> None:
        """Uploads a local file to MinIO under the specified object key."""
        self.s3_client.upload_file(
            local_path,
            self.bucket_name,
            object_key,
            ExtraArgs={"ContentType": content_type},
        )


_storage_service: Optional[StorageService] = None


def get_storage_service() -> StorageService:
    """Dependency provider returning the StorageService instance."""
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service

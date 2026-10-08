from fastapi import APIRouter, Depends

from app.schemas.job import PresignedUrlRequest, PresignedUrlResponse
from app.services.storage_service import StorageService, get_storage_service

router = APIRouter(prefix="/uploads", tags=["Uploads"])


@router.post("/presigned-url", response_model=PresignedUrlResponse)
def get_upload_presigned_url(
    payload: PresignedUrlRequest,
    storage: StorageService = Depends(get_storage_service),
) -> PresignedUrlResponse:
    """Generates a presigned S3/MinIO PUT URL and object key for direct client upload."""
    upload_url, object_key = storage.generate_presigned_upload_url(payload.filename)
    return PresignedUrlResponse(upload_url=upload_url, object_key=object_key)

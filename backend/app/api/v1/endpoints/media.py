"""
GramCare – Media upload endpoints (MinIO / S3)

POST /api/v1/media/presign         – get presigned upload URL
POST /api/v1/media/{id}/complete   – mark upload complete
GET  /api/v1/media/{id}/download   – get presigned download URL
"""

import uuid


from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import load_encounter_or_404
from app.core.deps import CHWOrAbove, CurrentUser, get_db
from app.models.models import MediaAttachment
from app.schemas.schemas import PresignedUploadRequest, PresignedUploadResponse
from app.services.storage_service import get_presigned_download, get_presigned_upload
from app.utils.audit import log_action
from app.utils.sync import record_change

router = APIRouter(prefix="/media", tags=["Media"])

# Allowed content types
ALLOWED_TYPES = {
    "image/jpeg", "image/png", "image/webp",
    "audio/ogg", "audio/mpeg", "audio/wav",
    "application/pdf",
}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


@router.post("/presign", response_model=PresignedUploadResponse, status_code=status.HTTP_201_CREATED)
async def presign_upload(
    body: PresignedUploadRequest,
    current_user: CHWOrAbove,
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a presigned URL so the client can upload directly to MinIO.
    A MediaAttachment record is created with upload_completed=False.
    """
    if body.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"Content type not allowed: {body.content_type}")

    if body.file_size_bytes > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"File too large. Max {MAX_FILE_SIZE // (1024*1024)} MB.")

    await load_encounter_or_404(db, current_user, body.encounter_id)

    # Build S3 key
    attachment_id = uuid.uuid4()
    ext = body.file_name.rsplit(".", 1)[-1] if "." in body.file_name else "bin"
    if not ext.isalnum() or len(ext) > 8:
        ext = "bin"
    file_key = f"encounters/{body.encounter_id}/{attachment_id}.{ext}"

    # Get presigned URL from MinIO
    upload_url = await get_presigned_upload(file_key, body.content_type, expires_seconds=3600)

    # Create attachment record
    attachment = MediaAttachment(
        id=attachment_id,
        encounter_id=body.encounter_id,
        uploader_id=current_user.id,
        file_key=file_key,
        file_type=body.content_type,
        file_size_bytes=body.file_size_bytes,
        upload_completed=False,
    )
    db.add(attachment)
    await db.commit()

    return PresignedUploadResponse(
        upload_url=upload_url,
        file_key=file_key,
        attachment_id=attachment_id,
        expires_in_seconds=3600,
    )


@router.post("/{attachment_id}/complete")
async def mark_upload_complete(
    attachment_id: uuid.UUID,
    checksum_sha256: str = None,
    current_user: CHWOrAbove = None,
    db: AsyncSession = Depends(get_db),
):
    """Client calls this after uploading directly to MinIO to confirm completion."""
    result = await db.execute(
        select(MediaAttachment).where(MediaAttachment.id == attachment_id)
    )
    attachment = result.scalar_one_or_none()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found.")
    if attachment.uploader_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the uploader can complete this upload.")

    if not attachment.upload_completed:
        attachment.upload_completed = True
        if checksum_sha256:
            attachment.checksum_sha256 = checksum_sha256
        # Link the file onto its encounter so it reaches the doctor via sync.
        encounter = await load_encounter_or_404(db, current_user, attachment.encounter_id)
        if (attachment.file_type or "").startswith("audio/"):
            encounter.voice_note_url = attachment.file_key
        elif (attachment.file_type or "").startswith("image/"):
            encounter.photo_urls = [*(encounter.photo_urls or []), attachment.file_key]
        await record_change(db, "encounters", encounter, "update", current_user.id)
        await log_action(db, current_user.id, "update", "media_attachment", str(attachment_id))
        await db.commit()
    return {"ok": True, "file_key": attachment.file_key}


@router.get("/{attachment_id}/download")
async def get_download_url(
    attachment_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Generate a presigned download URL valid for 15 minutes."""
    result = await db.execute(
        select(MediaAttachment).where(MediaAttachment.id == attachment_id)
    )
    attachment = result.scalar_one_or_none()
    if not attachment or not attachment.upload_completed:
        raise HTTPException(status_code=404, detail="Attachment not found or not yet uploaded.")
    await load_encounter_or_404(db, current_user, attachment.encounter_id)

    download_url = await get_presigned_download(attachment.file_key, expires_seconds=900)
    await log_action(db, current_user.id, "read", "media_attachment", str(attachment_id))
    await db.commit()
    return {"download_url": download_url, "content_type": attachment.file_type}

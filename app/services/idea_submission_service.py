"""Idea Submission service — public feature feedback storage + image upload.

Public users POST an idea (no auth). Admins list/patch ideas. Images are
stored in MinIO under ``idea_submissions/<submission_id>/<uuid>.<ext>``;
only the storage key is persisted in ``idea_submission_images``.
"""

from __future__ import annotations

import io
import mimetypes
import uuid
from typing import Optional, Sequence

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import IdeaSubmission, IdeaSubmissionImage
from app.services.storage_service import storage_service

ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/heic",
    "image/heif",
}
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB per image
MAX_IMAGES_PER_SUBMISSION = 5


def _extension_for(content_type: Optional[str], file_name: Optional[str]) -> str:
    """Pick a safe file extension, prefer content-type, fall back to name."""
    ext = ""
    if content_type:
        guess = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if guess:
            ext = guess
    if not ext and file_name and "." in file_name:
        ext = "." + file_name.rsplit(".", 1)[-1].lower()
    return ext or ".bin"


async def create_submission(
    session: AsyncSession,
    *,
    contributor_name: str,
    description: str,
    contributor_phone: Optional[str] = None,
    contributor_email: Optional[str] = None,
    contributor_department: Optional[str] = None,
    title: Optional[str] = None,
    current_pain: Optional[str] = None,
    expected_benefit: Optional[str] = None,
    reference_system: Optional[str] = None,
    category: str = "feature",
    submitter_ip: Optional[str] = None,
    submitter_user_agent: Optional[str] = None,
) -> IdeaSubmission:
    submission = IdeaSubmission(
        contributor_name=contributor_name.strip(),
        contributor_phone=(contributor_phone or "").strip() or None,
        contributor_email=(contributor_email or "").strip() or None,
        contributor_department=(contributor_department or "").strip() or None,
        title=(title or "").strip() or None,
        description=description.strip(),
        current_pain=(current_pain or "").strip() or None,
        expected_benefit=(expected_benefit or "").strip() or None,
        reference_system=(reference_system or "").strip() or None,
        category=category,
        status="new",
        submitter_ip=submitter_ip,
        submitter_user_agent=submitter_user_agent,
    )
    session.add(submission)
    await session.flush()
    return submission


async def attach_image(
    session: AsyncSession,
    submission: IdeaSubmission,
    *,
    data: bytes,
    file_name: Optional[str],
    content_type: Optional[str],
) -> IdeaSubmissionImage:
    """Validate, upload to MinIO, persist the metadata row."""
    if not data:
        raise ValueError("Tệp rỗng — vui lòng chọn ảnh hợp lệ.")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError(
            f"Ảnh vượt quá {MAX_IMAGE_BYTES // (1024 * 1024)}MB. "
            "Vui lòng nén lại hoặc chọn ảnh nhỏ hơn."
        )
    norm_type = (content_type or "").lower().split(";")[0].strip()
    if norm_type and norm_type not in ALLOWED_IMAGE_TYPES:
        raise ValueError(
            "Định dạng ảnh không hỗ trợ. Chỉ chấp nhận JPG, PNG, WEBP, GIF, HEIC."
        )

    # Count existing images for cap enforcement.
    existing = await session.execute(
        select(func.count(IdeaSubmissionImage.id)).where(
            IdeaSubmissionImage.submission_id == submission.id
        )
    )
    if existing.scalar_one() >= MAX_IMAGES_PER_SUBMISSION:
        raise ValueError(
            f"Tối đa {MAX_IMAGES_PER_SUBMISSION} ảnh cho mỗi góp ý."
        )

    ext = _extension_for(norm_type, file_name)
    object_name = f"idea_submissions/{submission.id}/{uuid.uuid4().hex}{ext}"
    try:
        storage_service.upload_stream(
            object_name=object_name,
            stream=io.BytesIO(data),
            length=len(data),
            content_type=norm_type or "application/octet-stream",
        )
    except Exception as e:
        logger.exception(f"Failed to upload idea image to storage: {e}")
        raise

    image = IdeaSubmissionImage(
        submission_id=submission.id,
        storage_key=object_name,
        file_name=(file_name or "").strip()[:300] or None,
        content_type=norm_type or None,
        size_bytes=len(data),
    )
    session.add(image)
    await session.flush()
    return image


async def get_submission(
    session: AsyncSession, submission_id: uuid.UUID
) -> Optional[IdeaSubmission]:
    stmt = (
        select(IdeaSubmission)
        .where(IdeaSubmission.id == submission_id)
        .options(selectinload(IdeaSubmission.images))
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_submissions(
    session: AsyncSession,
    *,
    status: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[Sequence[IdeaSubmission], int]:
    base = select(IdeaSubmission).options(selectinload(IdeaSubmission.images))
    count_q = select(func.count(IdeaSubmission.id))

    if status:
        base = base.where(IdeaSubmission.status == status)
        count_q = count_q.where(IdeaSubmission.status == status)
    if category:
        base = base.where(IdeaSubmission.category == category)
        count_q = count_q.where(IdeaSubmission.category == category)
    if search:
        like = f"%{search.strip()}%"
        base = base.where(
            (IdeaSubmission.description.ilike(like))
            | (IdeaSubmission.contributor_name.ilike(like))
            | (IdeaSubmission.title.ilike(like))
        )
        count_q = count_q.where(
            (IdeaSubmission.description.ilike(like))
            | (IdeaSubmission.contributor_name.ilike(like))
            | (IdeaSubmission.title.ilike(like))
        )

    total = (await session.execute(count_q)).scalar_one()
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    rows = (
        await session.execute(
            base.order_by(IdeaSubmission.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return rows, total


async def update_submission(
    session: AsyncSession,
    submission: IdeaSubmission,
    *,
    status: Optional[str] = None,
    admin_notes: Optional[str] = None,
    category: Optional[str] = None,
) -> IdeaSubmission:
    if status is not None:
        submission.status = status
    if admin_notes is not None:
        submission.admin_notes = admin_notes
    if category is not None:
        submission.category = category
    await session.flush()
    return submission


async def delete_submission(
    session: AsyncSession, submission: IdeaSubmission
) -> None:
    """Delete submission row + its MinIO objects (best-effort)."""
    keys = [img.storage_key for img in submission.images]
    await session.delete(submission)
    await session.flush()
    for key in keys:
        try:
            storage_service.delete_object(key)
        except Exception as e:  # storage failure should not block DB delete
            logger.warning(f"Failed to delete idea image {key}: {e}")


def build_image_url(image: IdeaSubmissionImage) -> Optional[str]:
    """Best-effort presigned URL for an image. Returns None on failure."""
    try:
        return storage_service.get_download_url(image.storage_key, expires_seconds=3600)
    except Exception as e:
        logger.warning(f"Could not presign URL for {image.storage_key}: {e}")
        return None

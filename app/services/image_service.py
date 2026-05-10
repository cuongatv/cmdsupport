"""
Image extraction service — extract images from PDF and DOCX files.
Uploads extracted images to MinIO and maps them to text chunks.
"""

import io
from typing import Optional

from loguru import logger

from app.services.storage_service import storage_service


def _mime_from_ext(ext: str) -> str:
    """Map extension to MIME type."""
    return {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "bmp": "image/bmp",
        "tiff": "image/tiff",
        "webp": "image/webp",
        "svg": "image/svg+xml",
    }.get(ext.lower(), "image/png")


class ImageInfo:
    """Metadata about an extracted image."""
    def __init__(
        self,
        minio_key: str,
        page_number: Optional[int],
        image_index: int,
        caption: Optional[str] = None,
    ):
        self.minio_key = minio_key
        self.page_number = page_number
        self.image_index = image_index
        self.caption = caption


def extract_images_from_pdf(
    file_data: bytes,
    source_id: str,
) -> list[ImageInfo]:
    """
    Extract all images from a PDF file and upload to MinIO.
    Returns list of ImageInfo with MinIO keys.
    """
    import fitz  # PyMuPDF

    images: list[ImageInfo] = []
    try:
        doc = fitz.open(stream=file_data, filetype="pdf")
    except Exception as e:
        logger.warning(f"Failed to open PDF for image extraction: {e}")
        return images

    image_index = 0
    for page_num in range(len(doc)):
        page = doc[page_num]
        image_list = page.get_images(full=True)

        for img_ref in image_list:
            try:
                xref = img_ref[0]
                base_image = doc.extract_image(xref)
                if not base_image:
                    continue

                img_bytes = base_image["image"]
                img_ext = base_image.get("ext", "png")

                # Skip very small images (likely icons/decorators)
                if len(img_bytes) < 2048:
                    continue

                # Upload to MinIO
                object_name = f"sources/{source_id}/images/page{page_num + 1}_{image_index}.{img_ext}"
                storage_service.upload_file(
                    object_name=object_name,
                    data=img_bytes,
                    content_type=_mime_from_ext(img_ext),
                )

                images.append(ImageInfo(
                    minio_key=object_name,
                    page_number=page_num + 1,
                    image_index=image_index,
                ))
                image_index += 1

            except Exception as e:
                logger.warning(f"Failed to extract image {img_ref} from page {page_num}: {e}")
                continue

    doc.close()
    logger.info(f"Extracted {len(images)} images from PDF (source {source_id})")
    return images


def extract_images_from_docx(
    file_data: bytes,
    source_id: str,
) -> list[ImageInfo]:
    """
    Extract all images from a DOCX file and upload to MinIO.
    """
    from docx import Document

    images: list[ImageInfo] = []
    try:
        doc = Document(io.BytesIO(file_data))
    except Exception as e:
        logger.warning(f"Failed to open DOCX for image extraction: {e}")
        return images

    for idx, rel in enumerate(doc.part.rels.values()):
        if "image" in rel.reltype:
            try:
                img_blob = rel.target_part.blob
                content_type = rel.target_part.content_type or "image/png"
                ext = content_type.split("/")[-1]
                if ext == "svg+xml":
                    ext = "svg"

                # Skip tiny images
                if len(img_blob) < 2048:
                    continue

                object_name = f"sources/{source_id}/images/docx_{idx}.{ext}"
                storage_service.upload_file(
                    object_name=object_name,
                    data=img_blob,
                    content_type=content_type,
                )

                images.append(ImageInfo(
                    minio_key=object_name,
                    page_number=None,  # DOCX doesn't have page numbers easily
                    image_index=idx,
                ))

            except Exception as e:
                logger.warning(f"Failed to extract DOCX image {idx}: {e}")
                continue

    logger.info(f"Extracted {len(images)} images from DOCX (source {source_id})")
    return images


def extract_images(
    file_data: bytes,
    file_name: str,
    source_id: str,
) -> list[ImageInfo]:
    """Auto-detect file type and extract images."""
    lower = file_name.lower()
    if lower.endswith(".pdf"):
        return extract_images_from_pdf(file_data, source_id)
    elif lower.endswith(".docx"):
        return extract_images_from_docx(file_data, source_id)
    else:
        logger.debug(f"No image extraction for file type: {file_name}")
        return []

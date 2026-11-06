import logging
import mimetypes
from uuid import uuid4

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
_IMAGE_SIGNATURES = {
    "image/jpeg": lambda data: data.startswith(b"\xff\xd8\xff"),
    "image/png": lambda data: data.startswith(b"\x89PNG\r\n\x1a\n"),
    "image/webp": lambda data: len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP",
}
MAX_IMAGE_SIZE = 5 * 1024 * 1024


def upload_public_image(content: bytes, content_type: str, prefix: str) -> str:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError("Supabase Storage is not configured")
    signature_check = _IMAGE_SIGNATURES.get(content_type)
    if signature_check is None or not signature_check(content):
        raise ValueError("仅支持有效的 JPG、PNG 或 WebP 图片")
    if len(content) > MAX_IMAGE_SIZE:
        raise ValueError("图片不能超过 5 MB")

    extension = mimetypes.guess_extension(content_type) or ".img"
    if extension == ".jpe":
        extension = ".jpg"
    object_path = f"{prefix}/{uuid4().hex}{extension}"
    base_url = settings.supabase_url.rstrip("/")
    bucket = settings.supabase_storage_bucket
    try:
        response = httpx.put(
            f"{base_url}/storage/v1/object/{bucket}/{object_path}",
            headers={
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "apikey": settings.supabase_service_role_key,
                "Content-Type": content_type,
                "x-upsert": "false",
            },
            content=content,
            timeout=20,
        )
        response.raise_for_status()
    except httpx.HTTPError as error:
        logger.warning("Supabase Storage upload failed: %s", type(error).__name__)
        raise RuntimeError("Supabase Storage upload failed") from None
    return f"{base_url}/storage/v1/object/public/{bucket}/{object_path}"


def delete_public_image(image_url: str) -> None:
    settings = get_settings()
    base_url = settings.supabase_url.rstrip("/")
    public_prefix = f"{base_url}/storage/v1/object/public/{settings.supabase_storage_bucket}/"
    if not image_url.startswith(public_prefix):
        raise ValueError("Image URL does not belong to the configured storage bucket")
    object_path = image_url.removeprefix(public_prefix)
    try:
        response = httpx.delete(
            f"{base_url}/storage/v1/object/{settings.supabase_storage_bucket}/{object_path}",
            headers={
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "apikey": settings.supabase_service_role_key,
            },
            timeout=20,
        )
        response.raise_for_status()
    except httpx.HTTPError as error:
        logger.warning("Supabase Storage delete failed: %s", type(error).__name__)
        raise RuntimeError("Supabase Storage delete failed") from None

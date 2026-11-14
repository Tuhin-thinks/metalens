"""Small JPEG thumbnails for photos, built from the embedded preview and cached on disk."""

import hashlib
import io
import uuid
from pathlib import Path

from PIL import Image, ImageOps

from get_focal_length import get_preview_bytes

THUMB_CACHE_DIR = Path(__file__).resolve().parent / ".cache"
THUMB_SIDE = 800  # longest side in pixels
JPEG_QUALITY = 85
JPEG_SUFFIXES = {".jpg", ".jpeg"}


def _cache_file(path: Path) -> Path:
    """Return the cache file for a photo. The key includes mtime, so edits refresh it."""
    key = f"{path.resolve()}|{path.stat().st_mtime_ns}|{THUMB_SIDE}"
    return THUMB_CACHE_DIR / f"{hashlib.sha256(key.encode()).hexdigest()[:16]}.jpg"


def _build(path: Path) -> bytes:
    """Decode the photo's embedded preview (or the JPEG itself) and shrink it."""
    source = path.read_bytes() if path.suffix.lower() in JPEG_SUFFIXES else get_preview_bytes(path)
    with Image.open(io.BytesIO(source)) as image:
        image = ImageOps.exif_transpose(image)  # apply the camera's orientation
        image.thumbnail((THUMB_SIDE, THUMB_SIDE))
        out = io.BytesIO()
        image.convert("RGB").save(out, "JPEG", quality=JPEG_QUALITY)
    return out.getvalue()


def make_thumbnail(path: Path) -> bytes:
    """Return a JPEG thumbnail of a photo, reading the disk cache when present.

    Args:
        path: Photo file (.ARW uses its embedded preview; .JPG/.JPEG is read directly).

    Returns:
        JPEG bytes no larger than THUMB_SIDE on each side.

    Raises:
        ValueError: If the photo has no usable preview (from `get_preview_bytes`).
    """
    cache = _cache_file(path)
    if cache.exists():
        return cache.read_bytes()
    data = _build(path)
    THUMB_CACHE_DIR.mkdir(exist_ok=True)
    tmp = cache.parent / f"{cache.name}.{uuid.uuid4().hex}.tmp"  # unique: workers may write the same photo
    tmp.write_bytes(data)
    tmp.replace(cache)  # atomic on the same volume
    return data

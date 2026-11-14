"""Small JPEG thumbnails for photos, built from the embedded preview and cached on disk."""

import hashlib
import io
import uuid
from pathlib import Path
from typing import NamedTuple

from PIL import Image

from get_focal_length import get_preview_bytes

THUMB_CACHE_DIR = Path(__file__).resolve().parent / ".cache"
THUMB_VERSION = "v2"  # bump when the thumbnail content changes (v2: orientation applied)
THUMB_SIDE = 800  # longest side in pixels
JPEG_QUALITY = 85
JPEG_SUFFIXES = {".jpg", ".jpeg"}

# EXIF Orientation -> transform that makes the stored pixels upright.
# The embedded RAW preview carries no EXIF, so the orientation must come from the RAW's tags.
ORIENTATION_TRANSPOSE = {
    2: Image.Transpose.FLIP_LEFT_RIGHT,
    3: Image.Transpose.ROTATE_180,
    4: Image.Transpose.FLIP_TOP_BOTTOM,
    5: Image.Transpose.TRANSPOSE,
    6: Image.Transpose.ROTATE_270,  # "Rotate 90 CW"
    7: Image.Transpose.TRANSVERSE,
    8: Image.Transpose.ROTATE_90,  # "Rotate 270 CW"
}


class Photo(NamedTuple):
    """A photo to thumbnail: its file and EXIF orientation (1-8)."""

    path: Path
    orientation: int


def _cache_file(photo: Photo) -> Path:
    """Return the cache file for a photo. The key includes mtime, so edits refresh it."""
    key = f"{THUMB_VERSION}|{photo.path.resolve()}|{photo.path.stat().st_mtime_ns}|{THUMB_SIDE}"
    return THUMB_CACHE_DIR / f"{hashlib.sha256(key.encode()).hexdigest()[:16]}.jpg"


def _build(photo: Photo) -> bytes:
    """Decode the photo's embedded preview (or the JPEG itself), rotate it upright and shrink it.

    Raises:
        ValueError: If the orientation is not an EXIF value from 1 to 8.
    """
    source = photo.path.read_bytes() if photo.path.suffix.lower() in JPEG_SUFFIXES else get_preview_bytes(photo.path)
    with Image.open(io.BytesIO(source)) as image:
        if photo.orientation != 1:
            if photo.orientation not in ORIENTATION_TRANSPOSE:
                raise ValueError(f"Invalid EXIF orientation {photo.orientation}: {photo.path}")
            image = image.transpose(ORIENTATION_TRANSPOSE[photo.orientation])
        image.thumbnail((THUMB_SIDE, THUMB_SIDE))
        out = io.BytesIO()
        image.convert("RGB").save(out, "JPEG", quality=JPEG_QUALITY)
    return out.getvalue()


def make_thumbnail(photo: Photo) -> bytes:
    """Return an upright JPEG thumbnail of a photo, reading the disk cache when present.

    Args:
        photo: File and EXIF orientation. .ARW uses its embedded preview; .JPG/.JPEG is read directly.

    Returns:
        JPEG bytes no larger than THUMB_SIDE on each side.

    Raises:
        ValueError: If the photo has no usable preview or an invalid orientation.
    """
    cache = _cache_file(photo)
    if cache.exists():
        return cache.read_bytes()
    data = _build(photo)
    THUMB_CACHE_DIR.mkdir(exist_ok=True)
    tmp = cache.parent / f"{cache.name}.{uuid.uuid4().hex}.tmp"  # unique: workers may write the same photo
    tmp.write_bytes(data)
    tmp.replace(cache)  # atomic on the same volume
    return data

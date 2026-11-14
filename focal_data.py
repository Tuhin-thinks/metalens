"""Load image records (focal length, timestamp) and group bursts for the notebooks.

An image that lacks a mandatory tag is skipped with a warning naming the file and
the missing tag, so the rest of the folder still loads. Invalid values still fail fast.

Records are cached per (directory, depth) in the project's .cache/ folder. A
cache entry is reused until it is more than one day old, and it is checked only
when a loader is called, i.e. when a script or notebook starts.
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from get_focal_length import find_files, get_exif

log = logging.getLogger(__name__)

IMAGE_SUFFIXES = {".arw", ".jpg", ".jpeg"}

TAGS = ["FocalLength", "DateTimeOriginal", "Orientation#", "FNumber"]  # '#' asks exiftool for the numeric EXIF value

# Conventional focal length bands (mm). A value on an edge goes to the lower band.
FOCAL_BAND_EDGES = [0, 35, 70, 105, 200]
FOCAL_BAND_LABELS = ["Wide (≤35 mm)", "Standard (35–70 mm)", "Short tele (70–105 mm)", "Telephoto (105 mm+)"]

CACHE_DIR = Path(__file__).resolve().parent / ".cache"
CACHE_MAX_AGE = timedelta(days=1)
CACHE_PREFIX = "records_v5"  # bump when the stored record layout changes
# A cache built with different tags is rebuilt, not reused.
SETTINGS = {"tags": TAGS}


def _scan(directory: str, depth: int) -> list[dict]:
    """Read every image under a directory with exiftool.

    Args:
        directory: Root folder to scan (passed to `find_files`).
        depth: Levels of subfolders to scan (0 = only the folder itself).

    Returns:
        One record per image that has every mandatory tag: file, focal_mm,
        datetime (DateTimeOriginal), orientation (EXIF 1-8) and aperture (f-number).

    Raises:
        ValueError: If no images are found, exiftool returns a different number
            of entries than files sent, or a value is in an unexpected format.
    """
    images = [f for f in find_files(directory, depth) if f.suffix.lower() in IMAGE_SUFFIXES]
    if not images:
        raise ValueError(f"No image files found in {directory} at depth {depth}")

    entries = get_exif(images, TAGS)
    if len(entries) != len(images):
        raise ValueError(f"exiftool returned {len(entries)} entries for {len(images)} images")

    records = []
    for entry in entries:
        source = entry["SourceFile"]
        missing = [tag for tag in TAGS if tag.removesuffix("#") not in entry]
        if missing:
            log.warning("Skipping %s: no %s in its metadata", source, ", ".join(missing))
            continue
        records.append({
            "file": source,
            "focal_mm": float(entry["FocalLength"].removesuffix(" mm")),
            "datetime": entry["DateTimeOriginal"],
            "orientation": entry["Orientation"],  # EXIF value 1-8, see viewer.thumbnails
            "aperture": float(entry["FNumber"]),
        })
    return records


def _cache_file(directory: str, depth: int) -> Path:
    """Return the cache file for a directory and depth (one file per combination)."""
    key = f"{Path(directory).resolve()}|{depth}"
    return CACHE_DIR / f"{CACHE_PREFIX}_{hashlib.sha256(key.encode()).hexdigest()[:16]}.json"


def load_records(directory: str, depth: int) -> pd.DataFrame:
    """Return one row per image under a directory, using the cache when fresh.

    The cache is reused if it was updated less than one day ago and was built
    with the current SETTINGS; otherwise the folder is rescanned with exiftool
    and the cache is rewritten.

    Args:
        directory: Root folder to scan.
        depth: Levels of subfolders to scan (0 = only the folder itself).

    Returns:
        DataFrame with columns file, focal_mm, datetime, orientation (EXIF 1-8)
        and aperture (f-number).

    Raises:
        ValueError: From `_scan`, or if a cache file exists but is malformed.
            A malformed cache is not silently replaced; delete it to rebuild.
    """
    cache = _cache_file(directory, depth)
    if cache.exists():
        data = json.loads(cache.read_text())
        age = datetime.now(timezone.utc) - datetime.fromisoformat(data["updated_at"])
        if age < CACHE_MAX_AGE and data["settings"] == SETTINGS:
            return pd.DataFrame(data["records"])

    now = datetime.now(timezone.utc)
    records = _scan(directory, depth)
    CACHE_DIR.mkdir(exist_ok=True)
    payload = {
        "directory": str(Path(directory).resolve()),
        "depth": depth,
        "updated_at": now.isoformat(),
        "settings": SETTINGS,
        "records": records,
    }
    tmp = cache.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=1))
    tmp.replace(cache)  # atomic on the same volume: no partially written cache
    return pd.DataFrame(records)


def load_focal_mm(directory: str, depth: int) -> np.ndarray:
    """Return the focal length in millimetres of every image (not collapsed by burst).

    Args:
        directory: Root folder to scan.
        depth: Levels of subfolders to scan (0 = only the folder itself).

    Returns:
        One float per image.
    """
    return load_records(directory, depth)["focal_mm"].to_numpy()


def group_bursts(records: pd.DataFrame) -> pd.DataFrame:
    """Collapse each burst into one row, keeping its first frame.

    A burst is a run of consecutive files (in path order) in the same folder
    with an identical DateTimeOriginal, i.e. frames shot within the same second.
    Single shots are bursts of one frame.

    The camera's own sequence tags are not used: on this camera they disagree
    with the timestamps (for example, drive-mode frames numbered 2 and up that
    were taken seconds apart), so they cannot reliably mark a burst.

    Known limits of this rule: a burst that crosses a second boundary is split
    in two, and two single shots taken within the same second are merged.

    Args:
        records: Output of `load_records`.

    Returns:
        DataFrame with one row per burst: file, focal_mm, datetime, orientation and
        aperture of its first frame, and frames (number of frames in the burst).
    """
    frames = records.sort_values("file", kind="stable").reset_index(drop=True)
    folder = frames["file"].str.rsplit("/", n=1).str[0]
    same_burst = (frames["datetime"] == frames["datetime"].shift()) & (folder == folder.shift())
    frames["burst"] = (~same_burst).cumsum()
    return frames.groupby("burst").agg(
        file=("file", "first"),
        focal_mm=("focal_mm", "first"),
        datetime=("datetime", "first"),
        orientation=("orientation", "first"),
        aperture=("aperture", "first"),
        frames=("file", "size"),
    ).reset_index(drop=True)


def focal_band(focal_mm: pd.Series) -> pd.Series:
    """Return the focal length band (FOCAL_BAND_LABELS) of each value, as an ordered category."""
    return pd.cut(focal_mm, bins=FOCAL_BAND_EDGES, labels=FOCAL_BAND_LABELS)


def filter_frames(frames: pd.DataFrame, focal: tuple[float, float], aperture: tuple[float, float]) -> pd.DataFrame:
    """Return the rows inside both ranges, sorted by file.

    Args:
        frames: DataFrame with focal_mm and aperture columns (records or burst rows).
        focal: (low, high) focal length in mm, both inclusive.
        aperture: (low, high) f-number, both inclusive.

    Returns:
        Matching rows with a fresh 0-based index.
    """
    low, high = focal
    f_low, f_high = aperture
    inside = frames["focal_mm"].between(low, high) & frames["aperture"].between(f_low, f_high)
    return frames[inside].sort_values("file").reset_index(drop=True)

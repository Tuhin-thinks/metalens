"""Load image records (focal length, timestamp) and group bursts for the notebooks.

Fails fast: every image must carry the mandatory tags below. The only
exceptions are the files listed in EXPLICITLY_EXCLUDED, named here so they stay
visible.

Records are cached per (directory, depth) in the project's .cache/ folder. A
cache entry is reused until it is more than one day old, and it is checked only
when a loader is called, i.e. when a script or notebook starts.
"""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from get_focal_length import find_files, get_exif

IMAGE_SUFFIXES = {".arw", ".jpg", ".jpeg"}

# Images excluded on purpose: an edited export with no camera metadata.
EXPLICITLY_EXCLUDED = {"D:/DCIM/13961019/DSC02365_edited.jpg"}

TAGS = ["FocalLength", "DateTimeOriginal"]

CACHE_DIR = Path(__file__).resolve().parent / ".cache"
CACHE_MAX_AGE = timedelta(days=1)
CACHE_PREFIX = "records_v3"  # bump when the stored record layout changes
# A cache built with different tags or exclusions is rebuilt, not reused.
SETTINGS = {"tags": TAGS, "excluded": sorted(EXPLICITLY_EXCLUDED)}


def _scan(directory: str, depth: int) -> list[dict]:
    """Read every image under a directory with exiftool.

    Args:
        directory: Root folder to scan (passed to `find_files`).
        depth: Levels of subfolders to scan (0 = only the folder itself).

    Returns:
        One record per image: file, focal_mm and datetime (DateTimeOriginal).

    Raises:
        ValueError: If no images are found, exiftool returns a different number
            of entries than files sent, an image lacks a mandatory tag, or a
            value is in an unexpected format.
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
        if source in EXPLICITLY_EXCLUDED:
            continue
        for key in TAGS:
            if key not in entry:
                raise ValueError(f"Image has no {key}: {source}")
        records.append({
            "file": source,
            "focal_mm": float(entry["FocalLength"].removesuffix(" mm")),
            "datetime": entry["DateTimeOriginal"],
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
        DataFrame with columns file, focal_mm and datetime.

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
        DataFrame with one row per burst: file, focal_mm and datetime of its
        first frame, and frames (number of frames in the burst).
    """
    frames = records.sort_values("file", kind="stable").reset_index(drop=True)
    folder = frames["file"].str.rsplit("/", n=1).str[0]
    same_burst = (frames["datetime"] == frames["datetime"].shift()) & (folder == folder.shift())
    frames["burst"] = (~same_burst).cumsum()
    return frames.groupby("burst").agg(
        file=("file", "first"),
        focal_mm=("focal_mm", "first"),
        datetime=("datetime", "first"),
        frames=("file", "size"),
    ).reset_index(drop=True)

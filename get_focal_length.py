"""Extract focal length metadata from images in a directory tree using exiftool."""

import argparse
import json
import subprocess
from pathlib import Path


def find_files(directory: str, depth: int = 0) -> list[Path]:
    """Return every file under a directory, descending at most `depth` levels.

    Args:
        directory: Root folder to scan.
        depth: 0 scans only the root folder, 1 also its subfolders, and so on.

    Returns:
        Paths of all files found within the allowed depth.
    """
    root = Path(directory)
    if not root.is_dir():
        raise ValueError(f"Not a directory: {directory}")
    files = []
    for dirpath, dirnames, filenames in root.walk():
        files.extend(dirpath / name for name in filenames)
        if len(dirpath.relative_to(root).parts) >= depth:
            dirnames.clear()  # prune: do not descend any further
    return files


def _run_exiftool(args: list[str], stdin: str | None = None, text: bool = True) -> subprocess.CompletedProcess:
    """Run exiftool.exe with the given arguments and return the completed process.

    Args:
        args: Arguments placed after the executable name.
        stdin: Text sent to exiftool's standard input, or None.
        text: True decodes stdout and stderr as text; False keeps raw bytes.

    Returns:
        The completed process. Its exit code is not checked here; callers decide.
    """
    return subprocess.run(["exiftool.exe", *args], input=stdin, capture_output=True, text=text)


def get_exif(paths: list[Path], tags: list[str]) -> list[dict]:
    """Return exiftool metadata for files, one dict per file.

    File paths are sent to exiftool through stdin (`-@ -`), so large folders do
    not hit the command-line length limit. Requires exiftool.exe on PATH.

    Args:
        paths: Files to inspect.
        tags: exiftool tag names, for example ["FocalLength", "Sony:SequenceNumber"].

    Returns:
        One dict per file with "SourceFile" and the requested tags. A tag the
        file does not have is absent from its dict.

    Raises:
        ValueError: If exiftool does not return valid JSON (for example, the
            directory was missing). The message includes exiftool's error output.
    """
    if not paths:
        return []
    result = _run_exiftool(
        [*[f"-{tag}" for tag in tags], "-json", "-@", "-"],
        stdin="\n".join(str(p) for p in paths),
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as err:
        raise ValueError(f"exiftool returned invalid JSON: {result.stderr.strip()}") from err


def get_preview_bytes(path: Path) -> bytes:
    """Return the JPEG preview embedded in a RAW file, without decoding the RAW.

    Sony ARW files carry a full-size JPEG. Reading it is far cheaper than
    decoding the sensor data. `PreviewImage` is tried first, then `JpgFromRaw`.

    Args:
        path: Image file to read the preview from.

    Returns:
        The raw JPEG bytes.

    Raises:
        ValueError: If exiftool fails or the file has no embedded preview.
    """
    for tag in ("PreviewImage", "JpgFromRaw"):
        result = _run_exiftool(["-b", f"-{tag}", str(path)], text=False)
        if result.returncode != 0:
            raise ValueError(f"exiftool failed on {path}: {result.stderr.decode(errors='replace').strip()}")
        if result.stdout:
            return result.stdout
    raise ValueError(f"No embedded preview in {path}")


def main() -> None:
    """Parse arguments and print each file's focal length."""
    parser = argparse.ArgumentParser(
        description="Print focal length of images in a directory tree."
    )
    parser.add_argument("directory", help="Folder containing the images")
    parser.add_argument("-d", "--depth", type=int, default=0, help="Levels of subfolders to scan (default: 0)")
    args = parser.parse_args()

    for entry in get_exif(find_files(args.directory, args.depth), ["FocalLength"]):
        print(entry["SourceFile"], entry.get("FocalLength"))


if __name__ == "__main__":
    main()

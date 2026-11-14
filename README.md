# Get Raw Image Information

**Find out which focal lengths you really shoot with, and browse your photos by focal range, without loading a single RAW file.**

Point it at a folder of Sony `.ARW` (or `.JPG`) photos. It reads the camera metadata with `exiftool`, shows you your most-used focal lengths, groups them into clusters, and lets you slide through a focal range to view the matching photos.

![Focal length overview](images/01-focal-length-overview.png)

## What you can do with it

- **See your real lens habits.** A histogram of focal lengths, the most-used focal length, and its share of your photos.
- **Count bursts as one shot.** Frames taken in the same second are collapsed into one, so a 10-frame burst does not skew the numbers.
- **Find your shooting "modes" automatically.** DBSCAN groups focal lengths that cluster together (for example, a 18–35 mm wide-angle group and a 130–135 mm telephoto group), with photo counts and shares.
- **Browse photos by focal range.** Drag a slider to pick, say, 100–120 mm and page through the matching photos, eight at a time, with the file name and focal length under each thumbnail.
- **Look at the photos as they were shot.** Thumbnails are rotated upright from the camera's own orientation tag, including portrait shots.
- **Stay fast on big folders.** Metadata is cached for a day. Thumbnails come from each RAW's embedded JPEG preview (no RAW decoding), are cached on disk, and load in the background near the page you are viewing, within a 2 GiB memory cap.
- **Choose your own eps.** Five notebooks walk through how the DBSCAN `eps` value was picked (k-distance elbow, density valleys, largest gap, HDBSCAN) and show the focal-length distribution after bursts are merged.

![Browse by focal range, landscapes](images/03-browse-landscapes-page-7.png)

![Browse by focal range, portraits](images/04-browse-upright-portraits-page-14.png)

![DBSCAN groups](images/02-dbscan-burst-groups.png)

## Quick start

Requirements: Windows (or any OS with `exiftool` on the PATH), [uv](https://docs.astral.sh/uv/), Python 3.13 (uv installs it).

```powershell
uv sync
uv run streamlit run app.py -- D:\DCIM
```

Then open the URL Streamlit prints. The folder argument is the default directory shown in the app. Change the directory and subfolder depth in the app to scan other folders.

### Command line

Print the focal length of every image in a folder:

```powershell
uv run python get_focal_length.py D:\DCIM --depth 1
```

## How it works

| Piece | Role |
|---|---|
| `get_focal_length.py` | Runs `exiftool` in one batch per folder: focal length, timestamps, orientation, and the embedded preview JPEG. |
| `focal_data.py` | Loads one row per image, caches it in `.cache/` for a day, groups bursts, and filters by focal range. |
| `app.py` | Streamlit dashboard: statistics, DBSCAN groups, and the browser. |
| `viewer/` | Browser backend: paging, thumbnail generation and disk cache, memory-capped background buffer, and the Streamlit section. |
| `notebooks/` | Exploration notebooks 01–05 for choosing `eps` and describing the distribution. |

Key choices:

- **Preview, not RAW.** A Sony `.ARW` file embeds a 1920×1080 JPEG. Reading that takes milliseconds, while decoding the RAW takes seconds.
- **Orientation from the RAW tags.** The embedded preview has no EXIF block, so the orientation is read from the RAW and applied to the thumbnail.
- **Fail fast.** A missing mandatory tag, a bad orientation value, or an unreadable preview raises an error. Nothing is silently skipped, except the one edited JPEG listed in `focal_data.py`.

## Tested with

Hardware and software:

- Windows 11, Python 3.13 (managed by uv)
- exiftool 13.63
- Pillow 13.0.0, Streamlit 1.67.0, pandas, scikit-learn (DBSCAN and HDBSCAN)

Data:

- A real photo collection of about 885 Sony `.ARW` and `.JPG` files in nested folders, scanned at subfolder depth 1 (877 bursts after grouping).
- Orientation tags over the collection: 547 normal, 335 rotated 270° CW, 3 rotated 90° CW, and 1 image without camera metadata (an edited JPEG, skipped with a warning).

Checks that were run:

- The CLI on the real folder.
- The record cache: a fresh scan, a cache hit, and a rebuild when the settings change.
- Burst grouping and the focal range filter.
- All five notebooks executed end to end with exit code 0.
- The Streamlit app headlessly with Streamlit's `AppTest` on the real folder: default view, a 100–120 mm range (51 bursts), and paging with Next.
- Thumbnails of two rotated RAW files checked against their orientation tags: upright portrait output at 450×800.
- The thumbnail buffer with a fake loader and a small cap: the cap is never exceeded, the nearest photos load first, the farthest are evicted first, the visible page is never evicted, and a background error is re-raised.

Not done yet:

- No automated test suite is committed. The checks above were run as scratch scripts.
- The memory plateau at the 2 GiB cap has not been measured while paging through the whole folder in a browser.
- The three rotated-90° photos have not been checked by eye.

## Known limits

- **DBSCAN at `eps` 3 mm chains nearby focal lengths.** On the test collection, the default settings merge 18–83 mm into one large group. Use the notebooks to pick a different `eps` or switch to HDBSCAN.
- **Bursts are grouped by identical timestamps.** A burst that crosses a second boundary is split. Two single shots in the same second are merged.
- **Cold thumbnails are slow.** Building one thumbnail takes about 0.36 s, mostly `exiftool` start-up. The disk cache makes later views fast.

## Project layout

```
app.py                 Streamlit dashboard
get_focal_length.py    exiftool wrapper and CLI
focal_data.py          records, cache, burst grouping, focal-range filter
viewer/                photo browser (paging, thumbnails, buffer, UI)
notebooks/             01–05 exploration notebooks
images/                screenshots for this README
```

Caches are written to `.cache/` and `viewer/.cache/` and are ignored by git.

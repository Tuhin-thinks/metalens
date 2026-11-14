# Get Raw Image Information

**Find out which focal lengths and apertures you really shoot with, and browse your photos by both, without loading a single RAW file.**

Point it at a folder of Sony `.ARW` (or `.JPG`) photos. It reads the camera metadata with `exiftool`, shows your most-used focal lengths and apertures, groups focal lengths into clusters, and lets you filter by focal length and aperture together to view the matching photos.

![Focal length overview](images/01-focal-length-overview.png)

## What you can do with it

- **See your real lens habits.** A histogram of focal lengths, the most-used focal length, and its share of your photos.
- **See which apertures you use.** The most-used f-stop, a bar chart per f-stop, and a table of focal length band by f-stop.
- **Count bursts as one shot.** Frames taken in the same second are collapsed into one, so a 10-frame burst does not skew the numbers.
- **Find your shooting "modes" automatically.** DBSCAN groups focal lengths that cluster together (for example, a 18–35 mm wide-angle group and a 130–135 mm telephoto group), with photo counts and shares.
- **Filter by focal length and aperture together.** Drag the focal length slider to 100–120 mm and the aperture slider to f/5.6–f/8, then page through the matching photos, eight at a time. Each thumbnail shows its file name, focal length and f-number.
- **Look at the photos as they were shot.** Thumbnails are rotated upright from the camera's own orientation tag, including portrait shots.
- **Open any photo full screen.** Use the expand icon in the corner of a thumbnail; press Esc to return.
- **Copy a photo's file path.** Use the copy icon in the corner of a thumbnail to paste the path into another tool.
- **Stay fast on big folders.** Metadata is cached for a day. Thumbnails come from each RAW's embedded JPEG preview (no RAW decoding), are cached on disk, and load in the background near the page you are viewing, within a 2 GiB memory cap.
- **Choose your own eps.** Four notebooks walk through how the DBSCAN `eps` value was picked (k-distance elbow, density valleys, largest gap, HDBSCAN), and one shows the focal-length distribution after bursts are merged.
- **Understand your aperture habits.** Two notebooks show the f-stops used, with and without burst merging, the wide/mid/stopped-down split, and how the f-number relates to focal length across the lens's range.

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
| `focal_data.py` | Loads one row per image, caches it in `.cache/` for a day, groups bursts, shares the focal bands, and filters by focal length and aperture range. |
| `app.py` | Streamlit dashboard: focal length and aperture statistics, DBSCAN groups, and the browser. |
| `viewer/` | Browser backend: paging, thumbnail generation and disk cache, memory-capped background buffer, and the Streamlit section. |
| `notebooks/` | Notebooks 01–07: choosing `eps` (01–04), the focal-length distribution (05), and aperture (06–07). |

Key choices:

- **Preview, not RAW.** A Sony `.ARW` file embeds a 1920×1080 JPEG. Reading that takes milliseconds, while decoding the RAW takes seconds.
- **Orientation from the RAW tags.** The embedded preview has no EXIF block, so the orientation is read from the RAW and applied to the thumbnail.
- **Fail fast, with one exception.** A bad value (orientation, focal length, f-number) or an unreadable preview raises an error. An image without a mandatory tag is skipped with a logged warning that names the file and the missing tag, so one edited JPEG does not stop a folder from loading.

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
- Aperture: 885 records with an f-number on every one, 16 distinct f-stops, 877 bursts.
- Burst grouping and the focal length and aperture filter (both ranges inclusive).
- Streamlit's browser with `AppTest` on the real folder, combined filter: 100–120 mm with f/5.6–f/8 gives 36 photos, equal to an independent pandas mask. Every caption on the page is inside both ranges.
- The app's aperture statistics against pandas: most-used f/5.6 at 19.8% of photos.
- Notebooks 06 and 07 executed end to end with exit code 0. Notebook 05's outputs were unchanged after its focal bands moved into `focal_data.py`.
- All notebooks 01–04 executed end to end with exit code 0.
- The Streamlit app headlessly with Streamlit's `AppTest` on the real folder: default view, a 100–120 mm range (51 bursts), and paging with Next.
- Thumbnails of two rotated RAW files checked against their orientation tags: upright portrait output at 450×800.
- The thumbnail buffer with a fake loader and a small cap: the cap is never exceeded, the nearest photos load first, the farthest are evicted first, the visible page is never evicted, and a background error is re-raised.

Not done yet:

- No automated test suite is committed. The checks above were run as scratch scripts.
- The memory plateau at the 2 GiB cap has not been measured while paging through the whole folder in a browser.
- The thumbnail tile's buttons (copy, full screen, Esc) have not been clicked through in a browser. Automated checks cover only that the tiles render.
- The three rotated-90° photos have not been checked by eye.

## Known limits

- **DBSCAN at `eps` 3 mm chains nearby focal lengths.** On the test collection, the default settings merge 18–83 mm into one large group. Use the notebooks to pick a different `eps` or switch to HDBSCAN.
- **Bursts are grouped by identical timestamps.** A burst that crosses a second boundary is split. Two single shots in the same second are merged.
- **A burst's aperture is its first frame's.** Frames in one burst can have different f-numbers, and only the first is used.
- **The lens limits in notebook 07 are references.** The f/3.5 and f/5.6 lines come from the lens name (18–135 mm F3.5–5.6), not from the photos. The per-photo `MaxApertureValue` tag would give the exact limit, and is not read yet.
- **Cold thumbnails are slow.** Building one thumbnail takes about 0.36 s, mostly `exiftool` start-up. The disk cache makes later views fast.
- **Copying needs a secure page.** The copy icon uses the browser clipboard, which works on `localhost` or HTTPS. Over plain HTTP from another machine it tries a text-selection copy, which some browsers block; a failure is shown under the photo.

## Project layout

```
app.py                 Streamlit dashboard
get_focal_length.py    exiftool wrapper and CLI
focal_data.py          records, cache, burst grouping, focal and aperture filter
viewer/                photo browser (paging, thumbnails, buffer, UI)
notebooks/             01–07 exploration notebooks
images/                screenshots for this README
```

Caches are written to `.cache/` and `viewer/.cache/` and are ignored by git.

"""Streamlit section: browse photos by focal length and aperture, one page of eight at a time."""

import math
from pathlib import Path

import pandas as pd
import streamlit as st

from focal_data import filter_frames
from viewer.buffer import ThumbnailBuffer
from viewer.copy_image import copyable_image
from viewer.paging import PAGE_SIZE, page_count, paginate
from viewer.thumbnails import Photo

COLUMNS = 4


@st.fragment
def render_browser(records: pd.DataFrame, bursts: pd.DataFrame) -> None:
    """Show focal length and aperture sliders and the matching photos, one page at a time.

    Only the photos on the current page are shown. The rest are loaded in the
    background, nearest to the page first, within the buffer's memory cap.

    Args:
        records: One row per photo.
        bursts: One row per burst (its first frame), used when bursts are counted once.
    """
    st.header("Browse by focal length and aperture")
    count_bursts = st.checkbox("Count each burst once", value=True)
    frames = bursts if count_bursts else records

    focal_col, aperture_col = st.columns(2)
    focal = _focal_slider(focal_col, frames)
    aperture = _aperture_slider(aperture_col, frames)

    key = (count_bursts, *focal, *aperture)
    if st.session_state.get("browse_key") != key:  # a new selection starts at the first page
        st.session_state.browse_key = key
        st.session_state.page = 0

    matches = filter_frames(frames, focal, aperture)
    st.metric("Photos in range", len(matches))
    _aperture_chart(frames, focal)
    pages = page_count(len(matches))
    if pages == 0:
        st.info("No photos in this range.")
        return

    page = st.session_state.page
    prev_col, label_col, next_col = st.columns([1, 2, 1])
    prev_col.button("Previous", disabled=page == 0, on_click=_move_page, args=(-1, pages))
    label_col.write(f"Page {page + 1} of {pages}")
    next_col.button("Next", disabled=page == pages - 1, on_click=_move_page, args=(1, pages))

    buffer = _buffer_for(key, matches)
    buffer.focus(page * PAGE_SIZE)
    cols = st.columns(COLUMNS)
    try:
        for offset, row in enumerate(paginate(matches, page).itertuples()):
            with cols[offset % COLUMNS]:
                copyable_image(
                    buffer.get(page * PAGE_SIZE + offset),
                    Path(row.file),
                    caption=f"{Path(row.file).name} · {row.focal_mm:g} mm · f/{row.aperture:g}",
                )
    except (OSError, ValueError) as err:
        st.error(str(err))


def _focal_slider(column, frames: pd.DataFrame) -> tuple[int, int]:
    """Slider for the focal length range in mm, spanning the data."""
    low_bound, high_bound = math.floor(frames.focal_mm.min()), math.ceil(frames.focal_mm.max())
    return column.slider("Focal length (mm)", low_bound, high_bound, (low_bound, high_bound), step=1)


def _aperture_slider(column, frames: pd.DataFrame) -> tuple[float, float]:
    """Select-slider for the f-number range, over the f-stops present in the data."""
    stops = sorted(frames.aperture.unique())
    return column.select_slider(
        "Aperture (f-number)",
        options=stops,
        value=(stops[0], stops[-1]),
        format_func=lambda v: f"f/{v:g}",
    )


def _aperture_chart(frames: pd.DataFrame, focal: tuple[int, int]) -> None:
    """Bar chart of photos per f-stop inside the focal range, to show which apertures were used."""
    low, high = focal
    counts = frames[frames.focal_mm.between(low, high)].aperture.value_counts().sort_index()
    st.bar_chart(pd.Series(counts.to_numpy(), index=[f"f/{v:g}" for v in counts.index]))


def _move_page(step: int, pages: int) -> None:
    """Button callback: move the page by `step`, staying inside 0..pages-1."""
    st.session_state.page = min(max(st.session_state.page + step, 0), pages - 1)


def _buffer_for(key: tuple, matches: pd.DataFrame) -> ThumbnailBuffer:
    """Return the thumbnail buffer for the current selection, replacing the previous one."""
    if st.session_state.get("buffer_key") != key:
        if "buffer" in st.session_state:
            st.session_state.buffer.close()
        photos = [Photo(Path(f), o) for f, o in zip(matches["file"], matches["orientation"])]
        st.session_state.buffer = ThumbnailBuffer(photos)
        st.session_state.buffer_key = key
    return st.session_state.buffer

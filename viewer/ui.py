"""Streamlit section: browse photos by focal range, one page of eight at a time."""

import math
from pathlib import Path

import pandas as pd
import streamlit as st

from focal_data import in_focal_range
from viewer.buffer import ThumbnailBuffer
from viewer.paging import PAGE_SIZE, page_count, paginate

COLUMNS = 4


@st.fragment
def render_browser(records: pd.DataFrame, bursts: pd.DataFrame) -> None:
    """Show a focal-range slider and the matching photos, one page at a time.

    Only the photos on the current page are shown. The rest are loaded in the
    background, nearest to the page first, within the buffer's memory cap.

    Args:
        records: One row per photo.
        bursts: One row per burst (its first frame), used when bursts are counted once.
    """
    st.header("Browse by focal range")
    count_bursts = st.checkbox("Count each burst once", value=True)
    frames = bursts if count_bursts else records

    low_bound, high_bound = math.floor(frames.focal_mm.min()), math.ceil(frames.focal_mm.max())
    low, high = st.slider("Focal range (mm)", low_bound, high_bound, (low_bound, high_bound), step=1)

    key = (count_bursts, low, high)
    if st.session_state.get("browse_key") != key:  # a new selection starts at the first page
        st.session_state.browse_key = key
        st.session_state.page = 0

    matches = in_focal_range(frames, low, high)
    st.metric("Photos in range", len(matches))
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
                st.image(
                    buffer.get(page * PAGE_SIZE + offset),
                    caption=f"{Path(row.file).name} · {row.focal_mm:g} mm",
                )
    except (OSError, ValueError) as err:
        st.error(str(err))


def _move_page(step: int, pages: int) -> None:
    """Button callback: move the page by `step`, staying inside 0..pages-1."""
    st.session_state.page = min(max(st.session_state.page + step, 0), pages - 1)


def _buffer_for(key: tuple, matches: pd.DataFrame) -> ThumbnailBuffer:
    """Return the thumbnail buffer for the current selection, replacing the previous one."""
    if st.session_state.get("buffer_key") != key:
        if "buffer" in st.session_state:
            st.session_state.buffer.close()
        st.session_state.buffer = ThumbnailBuffer([Path(f) for f in matches["file"]])
        st.session_state.buffer_key = key
    return st.session_state.buffer

"""Pure paging helpers for the photo browser (no Streamlit imports)."""

import math

import pandas as pd

PAGE_SIZE = 8  # photos shown on one page


def page_count(total: int, size: int = PAGE_SIZE) -> int:
    """Return how many pages hold `total` items (0 when there are none).

    Args:
        total: Number of items.
        size: Items per page.

    Returns:
        ceil(total / size).
    """
    return math.ceil(total / size)


def paginate(frames: pd.DataFrame, page: int, size: int = PAGE_SIZE) -> pd.DataFrame:
    """Return the rows of one page.

    Args:
        frames: All rows, in display order.
        page: 0-based page number.
        size: Rows per page.

    Returns:
        At most `size` rows. The last page may hold fewer.

    Raises:
        ValueError: If `page` is negative or past the last page.
    """
    if not 0 <= page < max(page_count(len(frames), size), 1):
        raise ValueError(f"Page {page} out of range for {len(frames)} rows")
    start = page * size
    return frames.iloc[start:start + size]

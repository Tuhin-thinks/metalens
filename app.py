"""Streamlit app: focal-length and aperture statistics, DBSCAN groups and a photo browser.

Run with:
    uv run streamlit run app.py -- <directory>
"""

import sys

import numpy as np
import pandas as pd
import streamlit as st
from sklearn.cluster import DBSCAN

from focal_data import focal_band, group_bursts, load_records
from viewer.ui import render_browser


def group_focal(focal: np.ndarray, eps: float, min_samples: int) -> tuple[pd.DataFrame, np.ndarray]:
    """Group focal lengths with DBSCAN and summarise each group.

    Args:
        focal: Focal lengths in mm, one per photo.
        eps: DBSCAN neighbourhood radius in mm.
        min_samples: Points needed within `eps` to form a group (counts the point itself).

    Returns:
        A summary DataFrame indexed by group name ("Group n" or "Noise") with
        Photos, Min mm, Max mm and Share % columns, and the raw DBSCAN labels
        (-1 = noise) for each photo.
    """
    labels = DBSCAN(eps=eps, min_samples=min_samples).fit_predict(focal.reshape(-1, 1))
    frame = pd.DataFrame({"mm": focal, "group": labels})
    summary = frame.groupby("group")["mm"].agg(Photos="count", **{"Min mm": "min", "Max mm": "max"})
    summary.index = [f"Group {g}" if g >= 0 else "Noise" for g in summary.index]
    summary["Share %"] = (summary["Photos"] / summary["Photos"].sum() * 100).round(1)
    return summary.sort_values("Min mm"), labels


def show_stats(focal: np.ndarray) -> None:
    """Show the most used focal length and a bar chart of photos per focal length."""
    counts = pd.Series(focal).value_counts()
    col1, col2 = st.columns(2)
    col1.metric("Most used focal length", f"{counts.index[0]:g} mm")
    col2.metric("Share of photos", f"{counts.iloc[0] / counts.sum() * 100:.1f}%")
    st.bar_chart(counts.sort_index())


def show_aperture(records: pd.DataFrame) -> None:
    """Show the most used aperture, a bar chart per f-stop and a focal band by f-stop table."""
    counts = records["aperture"].value_counts().sort_index()
    col1, col2 = st.columns(2)
    col1.metric("Most used aperture", f"f/{counts.idxmax():g}")
    col2.metric("Share at that aperture", f"{counts.max() / counts.sum() * 100:.1f}%")
    st.bar_chart(pd.Series(counts.to_numpy(), index=[f"f/{v:g}" for v in counts.index]))

    table = pd.crosstab(focal_band(records["focal_mm"]), records["aperture"])
    table.columns = [f"f/{v:g}" for v in table.columns]
    st.subheader("Focal length band by aperture")
    st.dataframe(table)


def show_groups(focal: np.ndarray, eps: float, min_samples: int) -> None:
    """Show the DBSCAN groups as a table, a bar chart and one expander per group."""
    st.subheader("DBSCAN groups")
    summary, labels = group_focal(focal, eps, min_samples)
    st.dataframe(summary)
    st.bar_chart(summary["Photos"])

    for g in sorted(set(labels)):
        members = focal[labels == g]
        name = f"Group {g}" if g >= 0 else "Noise"
        with st.expander(f"{name}: {len(members)} photos"):
            st.dataframe(pd.Series(members).value_counts().sort_index().to_frame("Photos"))


def main() -> None:
    """Read the inputs, load the photos and show every section."""
    default_dir = sys.argv[1] if len(sys.argv) > 1 else ""
    st.title("Focal Length Analysis")

    path_col, depth_col = st.columns([3, 1])
    directory = path_col.text_input("Image directory", value=default_dir)
    depth = int(depth_col.number_input("Subfolder depth", min_value=0, max_value=20, value=0, step=1))

    eps_col, min_col = st.columns(2)
    eps = eps_col.number_input("DBSCAN eps (mm)", min_value=0.1, value=3.0, step=0.5)
    min_samples = int(min_col.number_input("DBSCAN min_samples", min_value=1, value=20, step=1))

    if not directory:
        return
    try:
        records = load_records(directory, depth)
    except ValueError as err:
        st.error(str(err))
        return

    focal = records["focal_mm"].to_numpy()
    show_stats(focal)
    show_aperture(records)
    show_groups(focal, eps, min_samples)
    render_browser(records, group_bursts(records))


main()

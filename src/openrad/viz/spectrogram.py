"""Render a Spectrogram as a static PNG heatmap (time x energy, color = counts).

No GUI needed: matplotlib's non-interactive Agg backend renders headlessly,
which fits a CLI/library-first tool. Color uses a single-hue sequential ramp,
light to dark (never a rainbow/jet colormap), since counts are a magnitude,
not a category — see openrad's data-viz palette.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap, LogNorm

from openrad.core.models import Spectrogram

plt.switch_backend("Agg")

# Single-hue blue sequential ramp, light -> dark.
_SEQUENTIAL_BLUE_STEPS = [
    "#cde2fb",
    "#b7d3f6",
    "#9ec5f4",
    "#86b6ef",
    "#6da7ec",
    "#5598e7",
    "#3987e5",
    "#2a78d6",
    "#256abf",
    "#1c5cab",
    "#184f95",
    "#104281",
    "#0d366b",
]
_CHART_SURFACE = "#fcfcfb"
_PRIMARY_INK = "#0b0b0b"
_SECONDARY_INK = "#52514e"
_MUTED_INK = "#898781"

SEQUENTIAL_CMAP = LinearSegmentedColormap.from_list(
    "openrad_sequential_blue", _SEQUENTIAL_BLUE_STEPS
)


def render_spectrogram_png(
    spectrogram: Spectrogram,
    path: str | Path,
    *,
    energy_axis: bool = True,
    dpi: int = 150,
) -> None:
    """Render `spectrogram` to a PNG heatmap at `path`.

    The X axis is frame index (time-ordered); the Y axis is energy in keV by
    default, or raw channel number if `energy_axis` is False. Color is
    log-scaled counts, since a real spectrum spans orders of magnitude
    between background and a source peak.
    """
    if not spectrogram.frames:
        raise ValueError("cannot render an empty spectrogram (no frames)")

    counts = np.array([frame.counts for frame in spectrogram.frames], dtype=float)
    data = counts.T  # channels on the y-axis, frames on the x-axis
    channel_count = data.shape[0]

    if energy_axis:
        y_max = spectrogram.energy_of_channel(channel_count - 1)
        y_label = "energy (keV)"
    else:
        y_max = float(channel_count - 1)
        y_label = "channel"
    extent = (0.0, float(len(spectrogram.frames)), 0.0, y_max)

    positive = data[data > 0]
    vmin = float(positive.min()) if positive.size else 1.0
    vmax = max(vmin * 10, float(data.max()))

    fig, ax = plt.subplots(figsize=(10, 5), facecolor=_CHART_SURFACE)
    ax.set_facecolor(_CHART_SURFACE)
    image = ax.imshow(
        data,
        aspect="auto",
        origin="lower",
        extent=extent,
        cmap=SEQUENTIAL_CMAP,
        norm=LogNorm(vmin=vmin, vmax=vmax),
    )

    ax.set_title(spectrogram.name, color=_PRIMARY_INK)
    ax.set_xlabel("frame", color=_SECONDARY_INK)
    ax.set_ylabel(y_label, color=_SECONDARY_INK)
    ax.tick_params(colors=_MUTED_INK)
    for spine in ax.spines.values():
        spine.set_color(_MUTED_INK)

    colorbar = fig.colorbar(image, ax=ax)
    colorbar.set_label("counts", color=_SECONDARY_INK)
    colorbar.ax.tick_params(colors=_MUTED_INK)

    fig.tight_layout()
    fig.savefig(path, dpi=dpi, facecolor=_CHART_SURFACE)
    plt.close(fig)

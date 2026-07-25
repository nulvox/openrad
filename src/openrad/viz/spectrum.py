"""Render a single Spectrum as a static PNG line plot (energy x counts).

Companion to viz/spectrogram.py's heatmap renderer, for the common case of
inspecting one accumulated spectrum rather than a time series.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt

from openrad.core.models import Spectrum

plt.switch_backend("Agg")

_CHART_SURFACE = "#fcfcfb"
_PRIMARY_INK = "#0b0b0b"
_SECONDARY_INK = "#52514e"
_MUTED_INK = "#898781"
_LINE_COLOR = "#2a78d6"


def render_spectrum_png(
    spectrum: Spectrum,
    path: str | Path,
    *,
    energy_axis: bool = True,
    dpi: int = 150,
) -> None:
    """Render `spectrum` to a PNG line plot at `path`.

    The X axis is energy in keV by default, or raw channel number if
    `energy_axis` is False. The Y axis is counts per channel.
    """
    if not spectrum.counts:
        raise ValueError("cannot render an empty spectrum (no counts)")

    if energy_axis:
        x = [spectrum.energy_of_channel(ch) for ch in range(len(spectrum.counts))]
        x_label = "energy (keV)"
    else:
        x = list(range(len(spectrum.counts)))
        x_label = "channel"

    fig, ax = plt.subplots(figsize=(10, 5), facecolor=_CHART_SURFACE)
    ax.set_facecolor(_CHART_SURFACE)
    ax.plot(x, spectrum.counts, color=_LINE_COLOR, linewidth=1)

    ax.set_title(spectrum.name, color=_PRIMARY_INK)
    ax.set_xlabel(x_label, color=_SECONDARY_INK)
    ax.set_ylabel("counts", color=_SECONDARY_INK)
    ax.tick_params(colors=_MUTED_INK)
    for spine in ax.spines.values():
        spine.set_color(_MUTED_INK)

    fig.tight_layout()
    fig.savefig(path, dpi=dpi, facecolor=_CHART_SURFACE)
    plt.close(fig)

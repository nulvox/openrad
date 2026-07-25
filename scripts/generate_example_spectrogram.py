"""Regenerate examples/spectrogram/*.spe: a synthetic source passing by.

Simulates 12 frames of background radiation with a Cs-137-like 662 keV peak
that ramps up then fades, for demoing/testing `openrad spectrogram`. Run with:

    python scripts/generate_example_spectrogram.py

Requires the "viz" extra (numpy) — see pyproject.toml.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from openrad.core.models import Spectrum
from openrad.storage.spe import write_spe

CHANNELS = 256
FRAMES = 12
LIVE_TIME_S = 30.0
CALIBRATION = (0.0, 3.0, 0.0)  # keV per channel
PEAK_CHANNEL = 220  # ~660 keV, near Cs-137's 661.7 keV line
PEAK_WIDTH = 4.0
PEAK_MAX_INTENSITY = 400.0
BACKGROUND_RATE = 8.0
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "examples" / "spectrogram"


def _make_frame(rng: np.random.Generator, index: int) -> Spectrum:
    channels = np.arange(CHANNELS)
    progress = index / (FRAMES - 1)  # 0 -> 1 across the run
    intensity = PEAK_MAX_INTENSITY * np.exp(-((progress - 0.5) ** 2) / (2 * 0.15**2))

    background = rng.poisson(BACKGROUND_RATE, size=CHANNELS).astype(float)
    peak = intensity * np.exp(-((channels - PEAK_CHANNEL) ** 2) / (2 * PEAK_WIDTH**2))
    counts = rng.poisson(np.clip(background + peak, 0, None)).astype(int).tolist()

    start_time = datetime(2026, 1, 1, 9, 0, 0) + timedelta(seconds=index * LIVE_TIME_S)
    return Spectrum(
        counts=counts,
        live_time_s=LIVE_TIME_S,
        real_time_s=LIVE_TIME_S,
        start_time=start_time,
        calibration=CALIBRATION,
        name=f"frame-{index:02d}",
    )


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed=42)
    for index in range(FRAMES):
        write_spe(_make_frame(rng, index), OUTPUT_DIR / f"frame_{index:02d}.spe")
    print(f"Wrote {FRAMES} frames to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from openrad.core.models import Spectrum
from openrad.viz.spectrum import render_spectrum_png

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _sample_spectrum() -> Spectrum:
    return Spectrum(
        counts=[max(0, 10 - abs(i - 16)) for i in range(32)],
        live_time_s=10.0,
        real_time_s=10.0,
        start_time=datetime(2026, 1, 1, 0, 0, 0),
        calibration=(0.0, 3.0, 0.0),
        name="test-spectrum",
    )


def test_render_spectrum_png_writes_valid_png(tmp_path: Path) -> None:
    path = tmp_path / "out.png"
    render_spectrum_png(_sample_spectrum(), path)

    assert path.exists()
    assert path.read_bytes()[:8] == PNG_MAGIC
    assert path.stat().st_size > 0


def test_render_spectrum_png_channel_axis(tmp_path: Path) -> None:
    path = tmp_path / "out.png"
    render_spectrum_png(_sample_spectrum(), path, energy_axis=False)

    assert path.read_bytes()[:8] == PNG_MAGIC


def test_render_spectrum_png_rejects_empty_spectrum(tmp_path: Path) -> None:
    empty = Spectrum(
        counts=[],
        live_time_s=10.0,
        real_time_s=10.0,
        start_time=datetime(2026, 1, 1, 0, 0, 0),
    )

    with pytest.raises(ValueError, match="empty spectrum"):
        render_spectrum_png(empty, tmp_path / "out.png")

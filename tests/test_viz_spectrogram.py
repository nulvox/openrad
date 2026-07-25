from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from openrad.core.models import Spectrogram, SpectrogramFrame
from openrad.viz.spectrogram import render_spectrogram_png

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _sample_spectrogram() -> Spectrogram:
    spectrogram = Spectrogram(name="test", calibration=(0.0, 3.0, 0.0))
    for i in range(5):
        counts = [max(0, 10 - abs(i - 2) * 2 + c % 3) for c in range(32)]
        spectrogram.add(SpectrogramFrame(timestamp=datetime(2026, 1, 1, 0, 0, i), counts=counts))
    return spectrogram


def test_render_spectrogram_png_writes_valid_png(tmp_path: Path) -> None:
    path = tmp_path / "out.png"
    render_spectrogram_png(_sample_spectrogram(), path)

    assert path.exists()
    assert path.read_bytes()[:8] == PNG_MAGIC
    assert path.stat().st_size > 0


def test_render_spectrogram_png_channel_axis(tmp_path: Path) -> None:
    path = tmp_path / "out.png"
    render_spectrogram_png(_sample_spectrogram(), path, energy_axis=False)

    assert path.read_bytes()[:8] == PNG_MAGIC


def test_render_spectrogram_png_rejects_empty_spectrogram(tmp_path: Path) -> None:
    empty = Spectrogram(name="empty", calibration=(0.0, 3.0, 0.0))

    with pytest.raises(ValueError, match="empty spectrogram"):
        render_spectrogram_png(empty, tmp_path / "out.png")

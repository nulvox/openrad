from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from openrad.core.models import Spectrum
from openrad.storage.spe import write_spe
from openrad.storage.spectrogram import load_spectrogram_dir


def _write_frame(directory: Path, index: int, counts: list[int]) -> None:
    spectrum = Spectrum(
        counts=counts,
        live_time_s=10.0,
        real_time_s=10.0,
        start_time=datetime(2026, 1, 1, 0, 0, index),
        calibration=(0.0, 3.0, 0.0),
        name=f"frame-{index}",
    )
    write_spe(spectrum, directory / f"frame_{index:02d}.spe")


def test_load_spectrogram_dir_orders_frames_by_filename(tmp_path: Path) -> None:
    _write_frame(tmp_path, 0, [1, 2, 3])
    _write_frame(tmp_path, 1, [4, 5, 6])

    spectrogram = load_spectrogram_dir(tmp_path, name="test-spectrogram")

    assert spectrogram.name == "test-spectrogram"
    assert len(spectrogram.frames) == 2
    assert spectrogram.frames[0].counts == [1, 2, 3]
    assert spectrogram.frames[1].counts == [4, 5, 6]
    assert spectrogram.calibration == (0.0, 3.0, 0.0)


def test_load_spectrogram_dir_defaults_name_to_directory_name(tmp_path: Path) -> None:
    _write_frame(tmp_path, 0, [1, 2, 3])

    spectrogram = load_spectrogram_dir(tmp_path)

    assert spectrogram.name == tmp_path.name


def test_load_spectrogram_dir_rejects_mismatched_channel_counts(tmp_path: Path) -> None:
    _write_frame(tmp_path, 0, [1, 2, 3])
    _write_frame(tmp_path, 1, [4, 5])

    with pytest.raises(ValueError, match="channels"):
        load_spectrogram_dir(tmp_path)


def test_load_spectrogram_dir_rejects_empty_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no .spe files"):
        load_spectrogram_dir(tmp_path)

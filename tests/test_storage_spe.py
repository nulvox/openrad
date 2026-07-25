from __future__ import annotations

from datetime import datetime
from pathlib import Path

from openrad.core.models import Spectrum
from openrad.storage.spe import read_spe, write_spe


def test_spe_roundtrip(tmp_path: Path) -> None:
    spectrum = Spectrum(
        counts=[0, 3, 10, 4, 1],
        live_time_s=299.5,
        real_time_s=300.0,
        start_time=datetime(2026, 1, 1, 12, 0, 0),
        calibration=(0.0, 3.0, 0.0),
        name="test-spectrum",
    )
    path = tmp_path / "spectrum.spe"
    write_spe(spectrum, path)

    loaded = read_spe(path)
    assert loaded.counts == spectrum.counts
    assert loaded.live_time_s == spectrum.live_time_s
    assert loaded.real_time_s == spectrum.real_time_s
    assert loaded.start_time == spectrum.start_time
    assert loaded.name == spectrum.name
    assert loaded.calibration[1] == spectrum.calibration[1]


def test_spe_file_has_expected_sections(tmp_path: Path) -> None:
    spectrum = Spectrum(
        counts=[1, 2, 3],
        live_time_s=10.0,
        real_time_s=10.0,
        start_time=datetime(2026, 1, 1, 0, 0, 0),
    )
    path = tmp_path / "spectrum.spe"
    write_spe(spectrum, path)

    text = path.read_text()
    for section in ("$SPEC_ID:", "$DATE_MEA:", "$MEAS_TIM:", "$DATA:", "$MCA_CAL:"):
        assert section in text

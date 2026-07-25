from __future__ import annotations

from datetime import datetime

from openrad.core.models import Spectrogram, SpectrogramFrame


def test_spectrogram_add_and_energy_of_channel() -> None:
    spectrogram = Spectrogram(name="test", calibration=(0.0, 3.0, 0.0))
    spectrogram.add(SpectrogramFrame(timestamp=datetime(2026, 1, 1), counts=[1, 2, 3]))

    assert len(spectrogram.frames) == 1
    assert spectrogram.frames[0].counts == [1, 2, 3]
    assert spectrogram.energy_of_channel(10) == 30.0

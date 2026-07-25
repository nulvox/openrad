from __future__ import annotations

from datetime import datetime

from openrad.analysis.identify import find_peaks, identify
from openrad.analysis.isotopes import GammaLine, Isotope
from openrad.core.models import Spectrum


def _spectrum_with_peak(channel: int, height: int, *, n_channels: int = 200) -> Spectrum:
    counts = [5] * n_channels
    counts[channel] = height
    return Spectrum(
        counts=counts,
        live_time_s=100.0,
        real_time_s=100.0,
        start_time=datetime(2026, 1, 1, 0, 0, 0),
        calibration=(0.0, 3.0, 0.0),  # 3 keV/channel
        name="test",
    )


def test_find_peaks_detects_significant_spike() -> None:
    spectrum = _spectrum_with_peak(channel=100, height=500)

    peaks = find_peaks(spectrum)

    assert len(peaks) == 1
    assert peaks[0].channel == 100
    assert peaks[0].energy_kev == 300.0
    assert peaks[0].counts == 500


def test_find_peaks_ignores_flat_background() -> None:
    spectrum = Spectrum(
        counts=[5] * 200,
        live_time_s=100.0,
        real_time_s=100.0,
        start_time=datetime(2026, 1, 1, 0, 0, 0),
    )

    assert find_peaks(spectrum) == []


def test_identify_ranks_matching_isotope_highest() -> None:
    # 300 keV peak (channel 100) matches Cs-137-like's only line exactly.
    spectrum = _spectrum_with_peak(channel=100, height=500)
    library = [
        Isotope("Cs137-like", [GammaLine(300.0, 0.85)]),
        Isotope("Co60-like", [GammaLine(1173.2, 0.999), GammaLine(1332.5, 0.999)]),
    ]

    candidates = identify(spectrum, library, tolerance_kev=5.0)

    assert candidates[0].isotope == "Cs137-like"
    assert candidates[0].score == 1.0
    assert "Co60-like" not in [c.isotope for c in candidates]


def test_identify_partial_match_scores_below_full_match() -> None:
    # Only one of Co60-like's two lines has a matching peak.
    spectrum = _spectrum_with_peak(channel=100, height=500)  # 300 keV
    library = [
        Isotope("Full", [GammaLine(300.0, 0.5)]),
        Isotope("Partial", [GammaLine(300.0, 0.5), GammaLine(900.0, 0.5)]),
    ]

    candidates = identify(spectrum, library, tolerance_kev=5.0)

    scores = {c.isotope: c.score for c in candidates}
    assert scores["Full"] == 1.0
    assert scores["Partial"] == 0.5

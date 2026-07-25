"""Peak detection and isotope candidate matching for gamma spectra.

This is deliberately simple: local-maxima peak finding plus energy
matching against a reference gamma-line library (see isotopes.py). It's
meant to give a "does this look like isotope X" starting point, not a
definitive lab-grade identification (no continuum subtraction, no peak
fitting, no coincidence-summing correction).
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from openrad.analysis.isotopes import Isotope
from openrad.core.models import Spectrum


@dataclass(frozen=True)
class Peak:
    channel: int
    energy_kev: float
    counts: int


@dataclass(frozen=True)
class Candidate:
    isotope: str
    score: float  # fraction of the isotope's total line intensity that was matched, 0-1
    matched_lines_kev: list[float]


def find_peaks(
    spectrum: Spectrum,
    *,
    window: int = 5,
    min_sigma: float = 3.0,
    min_channel: int = 3,
) -> list[Peak]:
    """Find statistically significant local maxima in `spectrum.counts`.

    A channel is a peak if it's the tallest within +/- `window` channels
    and exceeds its local background (the median of a wider surrounding
    region) by `min_sigma` Poisson standard deviations.
    """
    counts = spectrum.counts
    n = len(counts)
    peaks: list[Peak] = []

    for i in range(min_channel, n):
        value = counts[i]
        if value <= 0:
            continue

        lo, hi = max(0, i - window), min(n, i + window + 1)
        if value != max(counts[lo:hi]):
            continue

        bg_lo, bg_hi = max(0, i - 4 * window), min(n, i + 4 * window + 1)
        background_region = [
            c for j, c in enumerate(counts[bg_lo:bg_hi], start=bg_lo) if not (lo <= j < hi)
        ]
        background = _median(background_region) if background_region else 0.0

        if value - background < min_sigma * sqrt(max(background, 1.0)):
            continue

        energy_kev = spectrum.energy_of_channel(i)
        if energy_kev < 0:
            # A calibration fit can extrapolate to negative energies for
            # the lowest channels (see storage/theremino.py) — not a real
            # gamma line, so not a useful "peak" for isotope matching.
            continue

        peaks.append(Peak(channel=i, energy_kev=energy_kev, counts=value))

    return peaks


def _median(values: list[int]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def identify(
    spectrum: Spectrum,
    library: list[Isotope],
    *,
    tolerance_kev: float = 10.0,
    top_n: int = 5,
    peaks: list[Peak] | None = None,
) -> list[Candidate]:
    """Rank isotopes in `library` by how much of their gamma-line intensity
    matches peaks found in `spectrum`.

    score = (summed intensity of an isotope's lines with a matching peak
    within `tolerance_kev`) / (summed intensity of all its lines). An
    isotope with one strong line that matches scores much higher than one
    with many lines only partially matched.
    """
    if peaks is None:
        peaks = find_peaks(spectrum)
    peak_energies = [p.energy_kev for p in peaks]

    candidates: list[Candidate] = []
    for isotope in library:
        total_intensity = sum(line.intensity for line in isotope.lines)
        if total_intensity <= 0:
            continue

        matched_lines = [
            line
            for line in isotope.lines
            if any(abs(line.energy_kev - e) <= tolerance_kev for e in peak_energies)
        ]
        if not matched_lines:
            continue

        matched_intensity = sum(line.intensity for line in matched_lines)
        candidates.append(
            Candidate(
                isotope=isotope.name,
                score=matched_intensity / total_intensity,
                matched_lines_kev=[line.energy_kev for line in matched_lines],
            )
        )

    # Break score ties in favor of more matched lines: an isotope confirmed
    # by two independent peaks is stronger evidence than a single-line
    # coincidence, even if both happen to fully cover their own line list.
    candidates.sort(key=lambda c: (c.score, len(c.matched_lines_kev)), reverse=True)
    return candidates[:top_n]

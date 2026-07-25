"""Read Theremino MCA "Pulse Height Histogram" text exports.

Theremino MCA (https://www.theremino.com/) is a popular hobbyist gamma
spectroscopy front-end. Its histogram export lists each bin as an
"Energy(KeV), Counts" pair rather than raw channel calibration
coefficients, and the per-bin energy step is not perfectly constant
(rounding to one decimal, internal bin-width adjustments). We recover the
closest linear calibration via least squares so the data fits Spectrum's
quadratic calibration model, rather than reproducing exact bin edges.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from openrad.core.models import Spectrum


def read_theremino(path: str | Path) -> Spectrum:
    """Parse a Theremino MCA pulse-height histogram export into a Spectrum."""
    path = Path(path)
    lines = path.read_text().splitlines()

    fields = _parse_header_fields(lines)
    start_time = datetime.strptime(fields["Started at"], "%Y/%m/%d %H:%M:%S")
    total_time_s = float(fields["Total time"].split()[0])

    energies, counts = _parse_histogram(lines)
    calibration = _fit_linear_calibration(energies)

    return Spectrum(
        counts=counts,
        live_time_s=total_time_s,
        real_time_s=total_time_s,
        start_time=start_time,
        calibration=calibration,
        name=path.stem,
    )


def _parse_header_fields(lines: list[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in lines:
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if key and value:
            fields[key] = value
    return fields


def _parse_histogram(lines: list[str]) -> tuple[list[float], list[int]]:
    energies: list[float] = []
    counts: list[int] = []
    for line in lines:
        if "," not in line:
            continue
        energy_str, _, counts_str = line.partition(",")
        try:
            energy = float(energy_str.strip())
            count = int(counts_str.strip())
        except ValueError:
            continue
        energies.append(energy)
        counts.append(count)
    return energies, counts


def _fit_linear_calibration(energies: list[float]) -> tuple[float, float, float]:
    """Least-squares fit of energy = a0 + a1*channel over the exported bins."""
    n = len(energies)
    if n < 2:
        return (0.0, 1.0, 0.0)

    channels = range(n)
    sum_x = sum(channels)
    sum_y = sum(energies)
    sum_xy = sum(x * y for x, y in zip(channels, energies, strict=True))
    sum_x2 = sum(x * x for x in channels)

    denom = n * sum_x2 - sum_x * sum_x
    if denom == 0:
        return (energies[0], 1.0, 0.0)

    a1 = (n * sum_xy - sum_x * sum_y) / denom
    a0 = (sum_y - a1 * sum_x) / n
    return (a0, a1, 0.0)

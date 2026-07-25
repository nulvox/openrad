"""Read/write gamma spectra in the ORTEC/IAEA ASCII .spe format.

.spe is the de facto lingua franca of hobbyist gamma spectroscopy tools
(Theremino MCA, Gamma Spectacular, Becquerel, ...). We deliberately support
it before the heavier ANSI N42.42 XML standard, which can be added later as
an interop exporter (e.g. for InterSpec) without changing this module.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from openrad.core.models import Spectrum


def write_spe(spectrum: Spectrum, path: str | Path) -> None:
    """Write a Spectrum to the ORTEC/IAEA .spe ASCII format."""
    lines = [
        "$SPEC_ID:",
        spectrum.name,
        "$DATE_MEA:",
        spectrum.start_time.strftime("%m/%d/%Y %H:%M:%S"),
        "$MEAS_TIM:",
        f"{spectrum.live_time_s:.2f} {spectrum.real_time_s:.2f}",
        "$DATA:",
        f"0 {len(spectrum.counts) - 1}",
        *(str(count) for count in spectrum.counts),
        "$MCA_CAL:",
        "3",
        " ".join(f"{c:.6E}" for c in spectrum.calibration),
        "keV",
    ]
    Path(path).write_text("\n".join(lines) + "\n")


def read_spe(path: str | Path) -> Spectrum:
    """Parse an ORTEC/IAEA .spe ASCII file back into a Spectrum."""
    sections = _split_sections(Path(path).read_text())

    name = sections["SPEC_ID"][0] if sections.get("SPEC_ID") else "spectrum"
    start_time = datetime.strptime(sections["DATE_MEA"][0], "%m/%d/%Y %H:%M:%S")
    live_time_s, real_time_s = (float(v) for v in sections["MEAS_TIM"][0].split())

    data_lines = sections["DATA"]
    counts = [int(v) for v in data_lines[1:]]  # data_lines[0] is "first_ch last_ch"

    calibration = (0.0, 3.0, 0.0)
    if "MCA_CAL" in sections and len(sections["MCA_CAL"]) >= 2:
        values = [float(v) for v in sections["MCA_CAL"][1].split()]
        padded = (values + [0.0, 0.0, 0.0])[:3]
        calibration = (padded[0], padded[1], padded[2])

    return Spectrum(
        counts=counts,
        live_time_s=live_time_s,
        real_time_s=real_time_s,
        start_time=start_time,
        calibration=calibration,
        name=name,
    )


def _split_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("$") and line.endswith(":"):
            current = line[1:-1]
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return sections

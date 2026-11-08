"""Read and write gamma spectra in the ANSI N42.42 XML format.

Provides interoperability with institutional gamma-spectroscopy tools such
as Sandia's InterSpec (https://github.com/sandialabs/InterSpec), using the
ANSI N42.42-2006 schema (`http://physics.nist.gov/N42/2006/N42`) while
reading both 2006 and 2011 N42 dialects.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from xml.dom import minidom
from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement, tostring

from openrad.core.models import Spectrum

N42_2006_NAMESPACE = "http://physics.nist.gov/N42/2006/N42"
N42_2011_NAMESPACE = "http://physics.nist.gov/N42/2011/N42"

_ISO_DURATION_RE = re.compile(
    r"^PT(?:(?P<hours>\d+(?:\.\d+)?)H)?(?:(?P<minutes>\d+(?:\.\d+)?)M)?(?:(?P<seconds>\d+(?:\.\d+)?)S)?$"
)


def _format_duration_seconds(seconds: float) -> str:
    return f"PT{seconds:.3f}S"


def _parse_duration_seconds(text: str | None) -> float:
    if not text:
        return 0.0
    stripped = text.strip()
    match = _ISO_DURATION_RE.match(stripped)
    if not match:
        return 0.0
    hours = float(match.group("hours") or 0.0)
    minutes = float(match.group("minutes") or 0.0)
    seconds = float(match.group("seconds") or 0.0)
    return hours * 3600.0 + minutes * 60.0 + seconds


def write_n42(spectrum: Spectrum, path: str | Path) -> None:
    """Write a `Spectrum` as an ANSI N42.42-2006 XML document."""
    root = Element(
        "RadInstrumentData",
        {
            "xmlns": N42_2006_NAMESPACE,
            "n42DocUUID": f"openrad-{spectrum.name}",
        },
    )

    info = SubElement(root, "RadInstrumentInformation", {"id": "openrad-instrument"})
    SubElement(info, "RadInstrumentManufacturerName").text = "openrad"
    SubElement(info, "RadInstrumentModelName").text = spectrum.name

    ecal = SubElement(root, "EnergyCalibration", {"id": "openrad-ecal"})
    SubElement(ecal, "CoefficientValues").text = " ".join(
        f"{c:.6E}" for c in spectrum.calibration
    )

    meas = SubElement(root, "RadMeasurement", {"id": "openrad-measurement"})
    SubElement(meas, "MeasurementClassCode").text = "Foreground"
    SubElement(meas, "StartDateTime").text = spectrum.start_time.isoformat()
    SubElement(meas, "RealTimeDuration").text = _format_duration_seconds(spectrum.real_time_s)

    spec_el = SubElement(
        meas,
        "Spectrum",
        {
            "id": spectrum.name,
            "energyCalibrationReference": "openrad-ecal",
        },
    )
    SubElement(spec_el, "LiveTimeDuration").text = _format_duration_seconds(spectrum.live_time_s)
    SubElement(spec_el, "ChannelData").text = " ".join(str(c) for c in spectrum.counts)

    pretty = minidom.parseString(tostring(root, encoding="unicode")).toprettyxml(indent="  ")
    Path(path).write_text(pretty)


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _find_first_by_local(root: Element, local_tag: str) -> Element | None:
    for el in root.iter():
        if _local_name(el.tag) == local_tag:
            return el
    return None


def read_n42(path: str | Path) -> Spectrum:
    """Parse an ANSI N42.42 XML file (2006 or 2011) into a `Spectrum`."""
    file_path = Path(path)
    root = ElementTree.parse(file_path).getroot()

    channel_el = _find_first_by_local(root, "ChannelData")
    if channel_el is None or not channel_el.text:
        raise ValueError(f"no <ChannelData> found in {file_path}")
    counts = [int(round(float(tok))) for tok in channel_el.text.split()]

    spec_el = _find_first_by_local(root, "Spectrum")
    name = (
        spec_el.attrib.get("id", "").strip()
        if spec_el is not None
        else ""
    ) or file_path.stem

    live_el = _find_first_by_local(root, "LiveTimeDuration")
    real_el = _find_first_by_local(root, "RealTimeDuration")
    live_time_s = _parse_duration_seconds(live_el.text if live_el is not None else None)
    real_time_s = _parse_duration_seconds(real_el.text if real_el is not None else None)
    if real_time_s == 0.0 and live_time_s > 0.0:
        real_time_s = live_time_s
    if live_time_s == 0.0 and real_time_s > 0.0:
        live_time_s = real_time_s

    start_el = _find_first_by_local(root, "StartDateTime")
    if start_el is not None and start_el.text:
        raw_start = start_el.text.strip()
        if raw_start.endswith("Z"):
            raw_start = raw_start[:-1] + "+00:00"
        start_time = datetime.fromisoformat(raw_start)
    else:
        start_time = datetime.now(timezone.utc)

    calibration: tuple[float, float, float] = (0.0, 3.0, 0.0)
    coeff_el = _find_first_by_local(root, "CoefficientValues")
    if coeff_el is not None and coeff_el.text:
        coeffs = [float(v) for v in coeff_el.text.split()]
        padded = (coeffs + [0.0, 0.0, 0.0])[:3]
        calibration = (padded[0], padded[1], padded[2])

    return Spectrum(
        counts=counts,
        live_time_s=live_time_s,
        real_time_s=real_time_s,
        start_time=start_time,
        calibration=calibration,
        name=name,
    )

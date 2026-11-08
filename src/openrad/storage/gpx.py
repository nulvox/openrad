"""Read and write survey Tracks as GPX 1.1, the standard GPS track format.

dose_rate and cps are carried as namespaced <extensions>, so the file still
opens cleanly in any GPX-compatible tool (maps, GIS software) even though
those tools won't understand the radiological data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from xml.dom import minidom
from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement, tostring

from openrad.core.models import Track, TrackPoint

GPX_NAMESPACE = "http://www.topografix.com/GPX/1/1"
OPENRAD_NAMESPACE = "https://github.com/openrad/openrad/gpx-extensions/v1"

_NS = {
    "gpx": GPX_NAMESPACE,
    "openrad": OPENRAD_NAMESPACE,
}


def write_gpx(track: Track, path: str | Path) -> None:
    """Write a Track to a GPX 1.1 file, with dose_rate/cps as custom extensions."""
    gpx = Element(
        "gpx",
        {
            "version": "1.1",
            "creator": "openrad",
            "xmlns": GPX_NAMESPACE,
            "xmlns:openrad": OPENRAD_NAMESPACE,
        },
    )
    trk = SubElement(gpx, "trk")
    SubElement(trk, "name").text = track.name
    trkseg = SubElement(trk, "trkseg")

    for point in track.points:
        trkpt = SubElement(
            trkseg,
            "trkpt",
            {"lat": f"{point.latitude:.7f}", "lon": f"{point.longitude:.7f}"},
        )
        SubElement(trkpt, "time").text = point.timestamp.isoformat()
        extensions = SubElement(trkpt, "extensions")
        SubElement(extensions, "openrad:dose_rate").text = f"{point.dose_rate:.4f}"
        SubElement(extensions, "openrad:cps").text = f"{point.cps:.4f}"

    pretty = minidom.parseString(tostring(gpx, encoding="unicode")).toprettyxml(indent="  ")
    Path(path).write_text(pretty)


def read_gpx(path: str | Path) -> Track:
    """Parse a GPX 1.1 file back into a Track, reading openrad extensions when present."""
    file_path = Path(path)
    root = ElementTree.parse(file_path).getroot()

    name_el = root.find(".//gpx:trk/gpx:name", _NS)
    if name_el is None:
        name_el = root.find(".//trk/name")
    name = (name_el.text or "").strip() if name_el is not None else ""
    if not name:
        name = file_path.stem

    trkpts = root.findall(".//gpx:trkpt", _NS)
    if not trkpts:
        trkpts = root.findall(".//trkpt")

    points: list[TrackPoint] = []
    for trkpt in trkpts:
        lat = float(trkpt.attrib["lat"])
        lon = float(trkpt.attrib["lon"])

        time_el = trkpt.find("gpx:time", _NS)
        if time_el is None:
            time_el = trkpt.find("time")
        if time_el is not None and time_el.text:
            raw_time = time_el.text.strip()
            if raw_time.endswith("Z"):
                raw_time = raw_time[:-1] + "+00:00"
            timestamp = datetime.fromisoformat(raw_time)
        else:
            timestamp = datetime.now(timezone.utc)

        dose_el = trkpt.find("gpx:extensions/openrad:dose_rate", _NS)
        if dose_el is None:
            dose_el = trkpt.find("extensions/dose_rate")
        dose_rate = float(dose_el.text.strip()) if dose_el is not None and dose_el.text else 0.0

        cps_el = trkpt.find("gpx:extensions/openrad:cps", _NS)
        if cps_el is None:
            cps_el = trkpt.find("extensions/cps")
        cps = float(cps_el.text.strip()) if cps_el is not None and cps_el.text else 0.0

        points.append(
            TrackPoint(
                timestamp=timestamp,
                latitude=lat,
                longitude=lon,
                dose_rate=dose_rate,
                cps=cps,
            )
        )

    return Track(name=name, points=points)

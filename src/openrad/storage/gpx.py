"""Write survey Tracks out as GPX 1.1, the standard GPS track format.

dose_rate and cps are carried as namespaced <extensions>, so the file still
opens cleanly in any GPX-compatible tool (maps, GIS software) even though
those tools won't understand the radiological data.
"""

from __future__ import annotations

from pathlib import Path
from xml.dom import minidom
from xml.etree.ElementTree import Element, SubElement, tostring

from openrad.core.models import Track

GPX_NAMESPACE = "http://www.topografix.com/GPX/1/1"
OPENRAD_NAMESPACE = "https://github.com/openrad/openrad/gpx-extensions/v1"


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

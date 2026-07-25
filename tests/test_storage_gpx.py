from __future__ import annotations

from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

from openrad.core.models import Track, TrackPoint
from openrad.storage.gpx import write_gpx

NS = {"gpx": "http://www.topografix.com/GPX/1/1"}


def test_gpx_write_produces_valid_xml_with_all_points(tmp_path: Path) -> None:
    track = Track(name="test-track")
    track.add(TrackPoint(datetime(2026, 1, 1, 0, 0, 0), 52.52, 13.405, 0.12, 5.0))
    track.add(TrackPoint(datetime(2026, 1, 1, 0, 0, 1), 52.5201, 13.4051, 0.13, 6.0))

    path = tmp_path / "track.gpx"
    write_gpx(track, path)

    tree = ElementTree.parse(path)
    points = tree.findall(".//gpx:trkpt", NS)
    assert len(points) == 2
    assert points[0].attrib["lat"] == "52.5200000"
    assert points[0].attrib["lon"] == "13.4050000"


def test_gpx_empty_track_has_no_points(tmp_path: Path) -> None:
    track = Track(name="empty-track")
    path = tmp_path / "track.gpx"
    write_gpx(track, path)

    tree = ElementTree.parse(path)
    assert tree.findall(".//gpx:trkpt", NS) == []

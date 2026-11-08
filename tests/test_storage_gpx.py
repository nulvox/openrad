from __future__ import annotations

from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

from openrad.core.models import Track, TrackPoint
from openrad.storage.gpx import read_gpx, write_gpx

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


def test_gpx_roundtrip_preserves_points_and_extensions(tmp_path: Path) -> None:
    track = Track(name="survey-walk")
    track.add(TrackPoint(datetime(2026, 1, 1, 12, 0, 0), 52.52, 13.405, 0.125, 5.25))
    track.add(TrackPoint(datetime(2026, 1, 1, 12, 0, 2), 52.5205, 13.4055, 0.25, 10.5))

    path = tmp_path / "track.gpx"
    write_gpx(track, path)

    loaded = read_gpx(path)
    assert loaded.name == "survey-walk"
    assert len(loaded.points) == 2
    assert loaded.points[0].timestamp == datetime(2026, 1, 1, 12, 0, 0)
    assert loaded.points[0].latitude == 52.52
    assert loaded.points[0].longitude == 13.405
    assert loaded.points[0].dose_rate == 0.125
    assert loaded.points[0].cps == 5.25
    assert loaded.points[1].dose_rate == 0.25
    assert loaded.points[1].cps == 10.5


def test_read_gpx_handles_plain_gpx_without_extensions(tmp_path: Path) -> None:
    plain_xml = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
  <trk>
    <trkseg>
      <trkpt lat="48.8566" lon="2.3522">
        <time>2026-01-01T08:30:00Z</time>
      </trkpt>
    </trkseg>
  </trk>
</gpx>
"""
    path = tmp_path / "external.gpx"
    path.write_text(plain_xml)

    loaded = read_gpx(path)
    assert loaded.name == "external"
    assert len(loaded.points) == 1
    assert loaded.points[0].latitude == 48.8566
    assert loaded.points[0].longitude == 2.3522
    assert loaded.points[0].dose_rate == 0.0
    assert loaded.points[0].cps == 0.0


def test_gpx_empty_track_has_no_points(tmp_path: Path) -> None:
    track = Track(name="empty-track")
    path = tmp_path / "track.gpx"
    write_gpx(track, path)

    tree = ElementTree.parse(path)
    assert tree.findall(".//gpx:trkpt", NS) == []

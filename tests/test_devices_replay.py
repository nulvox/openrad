from __future__ import annotations

from pathlib import Path

import pytest

from openrad.devices.replay import ReplayDevice

CSV_CONTENT = """timestamp,cps,dose_rate,latitude,longitude
2026-01-01T00:00:00,5.0,0.12,52.5200,13.4050
2026-01-01T00:00:01,6.0,0.13,52.5201,13.4051
2026-01-01T00:00:02,4.0,0.11,,
"""


def test_replay_streams_all_rows(tmp_path: Path) -> None:
    csv_path = tmp_path / "session.csv"
    csv_path.write_text(CSV_CONTENT)

    device = ReplayDevice(csv_path, speed=0)
    info = device.connect()
    assert info.driver == "replay"

    readings = list(device.stream())
    assert len(readings) == 3
    assert readings[0].cps == 5.0
    assert readings[0].latitude == 52.5200
    assert readings[2].latitude is None
    assert readings[2].longitude is None


def test_replay_missing_file_raises(tmp_path: Path) -> None:
    device = ReplayDevice(tmp_path / "missing.csv")
    with pytest.raises(FileNotFoundError):
        device.connect()

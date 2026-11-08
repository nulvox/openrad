from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from openrad.core.models import Spectrum, Track, TrackPoint
from openrad.storage.library import Library


def test_save_session_writes_track_and_metadata(tmp_path: Path) -> None:
    library = Library(root=tmp_path)

    track = Track(name="session-1")
    track.add(TrackPoint(datetime(2026, 1, 1, 0, 0, 0), 52.52, 13.405, 0.12, 5.0))

    session_dir = library.save_session("session-1", track=track, device_info={"driver": "replay"})

    assert (session_dir / "track.gpx").exists()
    assert not (session_dir / "spectrum.spe").exists()

    metadata = json.loads((session_dir / "metadata.json").read_text())
    assert metadata["has_track"] is True
    assert metadata["has_spectrum"] is False
    assert metadata["device_info"] == {"driver": "replay"}

    assert library.list_sessions() == ["session-1"]

    loaded_track = library.load_track("session-1")
    assert loaded_track is not None
    assert len(loaded_track.points) == 1
    assert loaded_track.points[0].dose_rate == 0.12
    assert library.load_spectrum("session-1") is None


def test_save_and_load_session_spectrum(tmp_path: Path) -> None:
    library = Library(root=tmp_path)
    spectrum = Spectrum(
        counts=[1, 5, 10],
        live_time_s=60.0,
        real_time_s=60.0,
        start_time=datetime(2026, 1, 1, 12, 0, 0),
        calibration=(0.0, 3.0, 0.0),
        name="rc-spec",
    )

    library.save_session("session-2", spectrum=spectrum, device_info={"driver": "radiacode"})

    loaded_spectrum = library.load_spectrum("session-2")
    assert loaded_spectrum is not None
    assert loaded_spectrum.counts == [1, 5, 10]
    assert loaded_spectrum.name == "rc-spec"
    assert library.load_track("session-2") is None

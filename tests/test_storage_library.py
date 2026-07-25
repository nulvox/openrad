from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from openrad.core.models import Track, TrackPoint
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

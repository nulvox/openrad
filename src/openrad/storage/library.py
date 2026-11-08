"""Local on-disk storage for saved survey sessions (tracks + spectra).

Each session gets its own directory: <library>/<session_id>/ containing
track.gpx, spectrum.spe (whichever are present), and metadata.json.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from openrad.core.models import Spectrum, Track
from openrad.storage.gpx import read_gpx, write_gpx
from openrad.storage.spe import read_spe, write_spe

DEFAULT_LIBRARY_DIR = Path.home() / ".openrad" / "library"


class Library:
    """A directory of saved sessions on the local filesystem."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root else DEFAULT_LIBRARY_DIR
        self.root.mkdir(parents=True, exist_ok=True)

    def save_session(
        self,
        session_id: str,
        *,
        track: Track | None = None,
        spectrum: Spectrum | None = None,
        device_info: dict[str, object] | None = None,
    ) -> Path:
        session_dir = self.root / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        if track is not None and track.points:
            write_gpx(track, session_dir / "track.gpx")
        if spectrum is not None:
            write_spe(spectrum, session_dir / "spectrum.spe")

        metadata = {
            "session_id": session_id,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "device_info": device_info or {},
            "has_track": track is not None and len(track.points) > 0,
            "has_spectrum": spectrum is not None,
        }
        (session_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
        return session_dir

    def list_sessions(self) -> list[str]:
        return sorted(p.name for p in self.root.iterdir() if p.is_dir())

    def load_track(self, session_id: str) -> Track | None:
        """Load `track.gpx` for `session_id` if present."""
        track_path = self.root / session_id / "track.gpx"
        if not track_path.exists():
            return None
        return read_gpx(track_path)

    def load_spectrum(self, session_id: str) -> Spectrum | None:
        """Load `spectrum.spe` for `session_id` if present."""
        spectrum_path = self.root / session_id / "spectrum.spe"
        if not spectrum_path.exists():
            return None
        return read_spe(spectrum_path)

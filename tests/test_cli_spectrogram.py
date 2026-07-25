from __future__ import annotations

from datetime import datetime
from pathlib import Path

from typer.testing import CliRunner

from openrad.cli.main import app
from openrad.core.models import Spectrum
from openrad.storage.spe import write_spe

runner = CliRunner()


def _write_frames(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for i in range(3):
        spectrum = Spectrum(
            counts=[i + c for c in range(16)],
            live_time_s=10.0,
            real_time_s=10.0,
            start_time=datetime(2026, 1, 1, 0, 0, i),
            calibration=(0.0, 3.0, 0.0),
        )
        write_spe(spectrum, directory / f"frame_{i:02d}.spe")


def test_cli_spectrogram_writes_png(tmp_path: Path) -> None:
    frame_dir = tmp_path / "frames"
    _write_frames(frame_dir)
    out_path = tmp_path / "out.png"

    result = runner.invoke(app, ["spectrogram", str(frame_dir), "--out", str(out_path)])

    assert result.exit_code == 0, result.output
    assert out_path.exists()
    assert out_path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_cli_spectrogram_channel_axis_flag(tmp_path: Path) -> None:
    frame_dir = tmp_path / "frames"
    _write_frames(frame_dir)
    out_path = tmp_path / "out.png"

    result = runner.invoke(
        app, ["spectrogram", str(frame_dir), "--out", str(out_path), "--channel-axis"]
    )

    assert result.exit_code == 0, result.output
    assert out_path.exists()

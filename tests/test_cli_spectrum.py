from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from openrad.cli.main import app

runner = CliRunner()

FIXTURES = Path(__file__).parent / "fixtures" / "theremino"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_cli_spectrum_writes_png_from_theremino_file(tmp_path: Path) -> None:
    out_path = tmp_path / "out.png"

    result = runner.invoke(
        app, ["spectrum", str(FIXTURES / "tc99mfinal.txt"), "--out", str(out_path)]
    )

    assert result.exit_code == 0, result.output
    assert out_path.exists()
    assert out_path.read_bytes()[:8] == PNG_MAGIC


def test_cli_spectrum_channel_axis_flag(tmp_path: Path) -> None:
    out_path = tmp_path / "out.png"

    result = runner.invoke(
        app,
        [
            "spectrum",
            str(FIXTURES / "tc99mfinal.txt"),
            "--out",
            str(out_path),
            "--channel-axis",
        ],
    )

    assert result.exit_code == 0, result.output
    assert out_path.read_bytes()[:8] == PNG_MAGIC

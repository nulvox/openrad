from __future__ import annotations

from datetime import datetime
from pathlib import Path

from typer.testing import CliRunner

from openrad.cli.main import app
from openrad.core.models import Spectrum
from openrad.storage.spe import write_spe

runner = CliRunner()

DATABASE = Path(__file__).parent / "fixtures" / "mini_sandia_decay.xml"


def _write_cs137_like_spectrum(path: Path) -> None:
    # 3 keV/channel; a peak at channel 220 lands at 660 keV, close to Cs-137's
    # real 661.657 keV line (well within the CLI's default 10 keV tolerance).
    counts = [5] * 400
    counts[220] = 2000
    spectrum = Spectrum(
        counts=counts,
        live_time_s=100.0,
        real_time_s=100.0,
        start_time=datetime(2026, 1, 1, 0, 0, 0),
        calibration=(0.0, 3.0, 0.0),
        name="test",
    )
    write_spe(spectrum, path)


def test_cli_identify_finds_matching_isotope(tmp_path: Path) -> None:
    spectrum_path = tmp_path / "spectrum.spe"
    _write_cs137_like_spectrum(spectrum_path)

    result = runner.invoke(
        app, ["identify", str(spectrum_path), "--database", str(DATABASE)]
    )

    assert result.exit_code == 0, result.output
    assert "Cs137" in result.output


def test_cli_identify_missing_database_errors(tmp_path: Path) -> None:
    spectrum_path = tmp_path / "spectrum.spe"
    _write_cs137_like_spectrum(spectrum_path)

    result = runner.invoke(
        app,
        ["identify", str(spectrum_path), "--database", str(tmp_path / "missing.xml")],
    )

    assert result.exit_code == 1
    assert "fetch_isotope_database" in result.output

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from openrad.cli.main import app
from openrad.core.models import Spectrum
from openrad.storage.n42 import _parse_duration_seconds, read_n42, write_n42
from openrad.storage.spe import write_spe

runner = CliRunner()
DATABASE = Path(__file__).parent / "fixtures" / "mini_sandia_decay.xml"


def test_n42_roundtrip(tmp_path: Path) -> None:
    spectrum = Spectrum(
        counts=[0, 4, 19, 8, 2],
        live_time_s=119.5,
        real_time_s=120.0,
        start_time=datetime(2026, 1, 1, 12, 30, 0),
        calibration=(-2.5, 2.95, 0.0001),
        name="n42-sample",
    )
    path = tmp_path / "sample.n42"
    write_n42(spectrum, path)

    loaded = read_n42(path)
    assert loaded.name == "n42-sample"
    assert loaded.counts == [0, 4, 19, 8, 2]
    assert loaded.live_time_s == pytest.approx(119.5)
    assert loaded.real_time_s == pytest.approx(120.0)
    assert loaded.start_time == datetime(2026, 1, 1, 12, 30, 0)
    assert loaded.calibration == pytest.approx((-2.5, 2.95, 0.0001))


def test_parse_iso_duration_variants() -> None:
    assert _parse_duration_seconds("PT300S") == pytest.approx(300.0)
    assert _parse_duration_seconds("PT1H2M3.5S") == pytest.approx(3723.5)
    assert _parse_duration_seconds("") == 0.0


def test_cli_export_n42_and_identify(tmp_path: Path) -> None:
    counts = [5] * 400
    counts[220] = 2000  # 660 keV at 3 keV/channel -> matches Cs-137
    spectrum = Spectrum(
        counts=counts,
        live_time_s=100.0,
        real_time_s=100.0,
        start_time=datetime(2026, 1, 1, 0, 0, 0),
        calibration=(0.0, 3.0, 0.0),
        name="cs137-test",
    )
    spe_path = tmp_path / "input.spe"
    n42_path = tmp_path / "output.n42"
    write_spe(spectrum, spe_path)

    export_res = runner.invoke(app, ["export-n42", str(spe_path), "--out", str(n42_path)])
    assert export_res.exit_code == 0, export_res.output
    assert n42_path.exists()

    id_res = runner.invoke(app, ["identify", str(n42_path), "--database", str(DATABASE)])
    assert id_res.exit_code == 0, id_res.output
    assert "Cs137" in id_res.output

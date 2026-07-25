from __future__ import annotations

from datetime import datetime
from pathlib import Path

from openrad.storage.theremino import read_theremino

FIXTURES = Path(__file__).parent / "fixtures" / "theremino"

SAMPLE = """\
-------------------------------------------
 Theremino_MCA - Pulse Height Histogram
-------------------------------------------
       Started at: 2020/01/07 23:23:19
       Total time: 60463 sec.
     Total pulses: 7098724
  Pulses per sec.: 117.4
         Sampling: 192000 Hz
   Minimum energy: 11 KeV
   Bin multiplier: 1
-------------------------------------------
 Energy(KeV)    Counts
-------------------------------------------
 0.0,           0
 2.4,           24736
 4.8,           8799
 7.2,           7947
"""


def test_theremino_parses_header_and_counts(tmp_path: Path) -> None:
    path = tmp_path / "sample.txt"
    path.write_text(SAMPLE)

    spectrum = read_theremino(path)

    assert spectrum.name == "sample"
    assert spectrum.start_time == datetime(2020, 1, 7, 23, 23, 19)
    assert spectrum.live_time_s == 60463.0
    assert spectrum.real_time_s == 60463.0
    assert spectrum.counts == [0, 24736, 8799, 7947]


def test_theremino_recovers_linear_calibration(tmp_path: Path) -> None:
    path = tmp_path / "sample.txt"
    path.write_text(SAMPLE)

    spectrum = read_theremino(path)

    # Exported energies step by 2.4 keV/channel in this sample, so the
    # least-squares fit should land close to a0=0, a1=2.4.
    a0, a1, a2 = spectrum.calibration
    assert round(a0, 6) == 0.0
    assert round(a1, 1) == 2.4
    assert a2 == 0.0


def test_theremino_parses_real_fixture() -> None:
    spectrum = read_theremino(FIXTURES / "tc99mfinal.txt")

    assert spectrum.name == "tc99mfinal"
    assert spectrum.start_time == datetime(2020, 1, 7, 23, 23, 19)
    assert spectrum.live_time_s == 60463.0
    assert len(spectrum.counts) > 1000
    assert spectrum.counts[0] == 0
    assert sum(spectrum.counts) == 7098724

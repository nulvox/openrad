from __future__ import annotations

from pathlib import Path

import pytest

from openrad.analysis.isotopes import load_isotope_library

FIXTURE = Path(__file__).parent / "fixtures" / "mini_sandia_decay.xml"


def test_load_isotope_library_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="fetch_isotope_database"):
        load_isotope_library(tmp_path / "does-not-exist.xml")


def test_cs137_gamma_line_comes_from_ba137m_daughter() -> None:
    (cs137,) = load_isotope_library(FIXTURE, nuclides=["Cs137"])

    assert cs137.name == "Cs137"
    assert len(cs137.lines) == 1
    line = cs137.lines[0]
    assert line.energy_kev == pytest.approx(661.657, abs=0.05)
    # 0.947 (branch to Ba137m) * 0.9011 (Ba137m's gamma intensity)
    assert line.intensity == pytest.approx(0.947 * 0.9011, abs=1e-3)


def test_co60_has_both_cascade_gammas() -> None:
    (co60,) = load_isotope_library(FIXTURE, nuclides=["Co60"])

    energies = sorted(line.energy_kev for line in co60.lines)
    assert energies == pytest.approx([1173.2, 1332.5])


def test_k40_gamma_intensity_matches_known_value() -> None:
    (k40,) = load_isotope_library(FIXTURE, nuclides=["K40"])

    assert len(k40.lines) == 1
    assert k40.lines[0].energy_kev == pytest.approx(1460.8)
    assert k40.lines[0].intensity == pytest.approx(0.1066, abs=1e-3)


def test_default_cutoff_excludes_short_lived_root() -> None:
    # Ba137m's half-life (153 s) is well under the default 30-day
    # equilibrium cutoff, so it shouldn't appear as its own library entry
    # when no explicit `nuclides` filter is given.
    library = load_isotope_library(FIXTURE)
    names = {isotope.name for isotope in library}

    assert "Ba137m" not in names
    assert {"Cs137", "Co60", "K40"} <= names

"""Isotope gamma-line reference data, parsed from a locally fetched database.

openrad doesn't vendor a copy of the database: it's LGPL-2.1-licensed
nuclear data from Sandia National Labs (see
scripts/fetch_isotope_database.py for how to get your own copy), and
sits awkwardly under this project's MIT license besides being large.
`load_isotope_library` parses whatever XML file the user fetched.

SandiaDecay's XML format lists nuclides (<n>) and their decay
transitions (<t>), each carrying the gamma lines (<g>) emitted during
that specific transition. A radionuclide's *practically observed*
spectrum often includes lines from its short-lived daughters too — e.g.
Cs-137's iconic 661.7 keV line is actually emitted by its 2.55-minute
daughter Ba-137m, not Cs-137 itself. `load_isotope_library` accounts for
this by walking each long-lived nuclide's decay chain and folding in
gammas from daughters short-lived enough to reach secular equilibrium
with it (default cutoff: 30 days — reasonable for a sample that isn't
freshly separated, but not exact physics for every source's history).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

DEFAULT_DATABASE_PATH = Path.home() / ".openrad" / "isotopes" / "sandia.decay.xml"

_NS = "{sandia.decay.xsd}"
_DAY_S = 86400.0
_DEFAULT_EQUILIBRIUM_HALFLIFE_S = 30 * _DAY_S
_MAX_CHAIN_DEPTH = 20


@dataclass(frozen=True)
class GammaLine:
    energy_kev: float
    intensity: float  # photons per decay of the root nuclide, roughly 0-1


@dataclass(frozen=True)
class Isotope:
    name: str
    lines: list[GammaLine]


@dataclass
class _Transition:
    child: str
    branching_ratio: float
    gammas: list[tuple[float, float]]


@dataclass
class _Nuclide:
    symbol: str
    half_life_s: float | None
    transitions: list[_Transition] = field(default_factory=list)


def load_isotope_library(
    path: str | Path = DEFAULT_DATABASE_PATH,
    *,
    nuclides: list[str] | None = None,
    equilibrium_halflife_s: float = _DEFAULT_EQUILIBRIUM_HALFLIFE_S,
    min_intensity: float = 1e-4,
) -> list[Isotope]:
    """Parse a SandiaDecay XML file into a gamma-line library.

    `nuclides` restricts output to those symbols (e.g. ["Cs137", "Co60"]);
    by default every nuclide with a half-life of at least
    `equilibrium_halflife_s` is included (long-lived enough to be a
    sensible standalone identification target).

    `min_intensity` drops lines emitted less often than that fraction of
    decays (default: 1 in 10,000). The database includes a long tail of
    extremely faint transitions that a hobbyist detector will never
    produce a visible peak for, but that would otherwise trivially
    "match" any nearby peak and drown out real candidates.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run scripts/fetch_isotope_database.py first, "
            "or pass --database with an existing SandiaDecay XML file."
        )

    all_nuclides = _parse_nuclides(path)

    if nuclides is not None:
        roots = [all_nuclides[s] for s in nuclides if s in all_nuclides]
    else:
        roots = [
            n
            for n in all_nuclides.values()
            if n.half_life_s is not None and n.half_life_s >= equilibrium_halflife_s
        ]

    library = []
    for root in roots:
        lines = _accumulate_gammas(
            root.symbol, 1.0, 0, all_nuclides, equilibrium_halflife_s, frozenset()
        )
        merged = [line for line in _merge_lines(lines) if line.intensity >= min_intensity]
        if merged:
            library.append(Isotope(name=root.symbol, lines=merged))
    return library


def _parse_nuclides(path: Path) -> dict[str, _Nuclide]:
    root = ElementTree.parse(path).getroot()
    nuclides: dict[str, _Nuclide] = {}

    for elem in root:
        tag = elem.tag.removeprefix(_NS)
        if tag == "n":
            symbol = elem.get("s")
            if symbol is not None:
                nuclides[symbol] = _Nuclide(
                    symbol=symbol, half_life_s=_parse_half_life(elem.get("hl"))
                )

    for elem in root:
        tag = elem.tag.removeprefix(_NS)
        if tag != "t":
            continue
        parent = elem.get("p")
        if parent not in nuclides:
            continue
        gammas = [
            (float(g.get("e", "0")), float(g.get("i", "0")))
            for g in elem
            if g.tag.removeprefix(_NS) == "g"
        ]
        nuclides[parent].transitions.append(
            _Transition(
                child=elem.get("c", ""),
                branching_ratio=float(elem.get("br", "0")),
                gammas=gammas,
            )
        )

    return nuclides


def _parse_half_life(raw: str | None) -> float | None:
    if raw is None:
        return None
    if raw == "INF":
        return float("inf")
    try:
        return float(raw)
    except ValueError:
        return None


def _accumulate_gammas(
    symbol: str,
    probability: float,
    depth: int,
    nuclides: dict[str, _Nuclide],
    equilibrium_halflife_s: float,
    visited: frozenset[str],
) -> list[tuple[float, float]]:
    if depth > _MAX_CHAIN_DEPTH or symbol in visited:
        return []
    visited = visited | {symbol}

    lines: list[tuple[float, float]] = []
    for transition in nuclides.get(symbol, _Nuclide(symbol, None)).transitions:
        step_probability = probability * transition.branching_ratio
        for energy_kev, intensity in transition.gammas:
            lines.append((energy_kev, step_probability * intensity))

        child = nuclides.get(transition.child)
        is_short_lived = (
            child is not None
            and child.half_life_s is not None
            and child.half_life_s < equilibrium_halflife_s
        )
        if child is not None and is_short_lived:
            lines.extend(
                _accumulate_gammas(
                    child.symbol,
                    step_probability,
                    depth + 1,
                    nuclides,
                    equilibrium_halflife_s,
                    visited,
                )
            )
    return lines


def _merge_lines(
    lines: list[tuple[float, float]], *, energy_tolerance_kev: float = 0.05
) -> list[GammaLine]:
    """Combine near-duplicate energies (same line reached via multiple decay paths)."""
    merged: dict[float, float] = {}
    for energy_kev, intensity in lines:
        key = round(energy_kev / energy_tolerance_kev) * energy_tolerance_kev
        merged[key] = merged.get(key, 0.0) + intensity
    return sorted(
        (GammaLine(energy_kev=e, intensity=i) for e, i in merged.items() if i > 0),
        key=lambda line: -line.intensity,
    )

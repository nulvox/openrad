# openrad

An open-source toolkit for radiation detectors — a pluggable device driver
layer, spectrum/track capture, and a local library — built as an open
alternative to closed vendor software such as [RadiaCode's
apps](https://www.radiacode.com/software).

Unlike RadiaCode's software, openrad isn't tied to one vendor's hardware:
device support is a driver interface (`openrad.devices.base.Device`), so
adding a new detector doesn't require rewriting the app. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how that's structured, and
[docs/ROADMAP.md](docs/ROADMAP.md) for what's built vs. planned.

## Status vs. RadiaCode's software

| Feature                          | RadiaCode | openrad                        |
| --------------------------------- | :-------: | :------------------------------ |
| Live dashboard                   |    ✅     | ✅ (CLI)                        |
| Data logging / library           |    ✅     | ✅                               |
| GPS radiation mapping (track)    |    ✅     | ⚠️ track capture + `.gpx` export; map rendering planned |
| Gamma spectroscopy (capture)     |    ✅     | ✅ `.spe` capture/export         |
| Spectrogram view                 |    ✅     | ✅ static PNG heatmap (no GUI needed) |
| Isotope identification           |    ✅     | ✅ peak matching against a fetched reference database |
| Gamma camera (photo + spectrum)  |    ✅     | ⏳ planned                      |
| Cs-137 food-activity mode        |    ✅     | ⏳ planned                      |
| Search mode (audio)              |    ✅     | ⏳ planned                      |
| Supported hardware               | RadiaCode only | Pluggable — replay driver today, real drivers in progress |
| Platforms                        | iOS/Android/Windows | CLI/library today (Linux/macOS/Windows via Python) |
| License                          | Proprietary | MIT |

## Quickstart

Requires [uv](https://docs.astral.sh/uv/). On NixOS (where manylinux wheels
like numpy/matplotlib/ruff won't run against the system's libs out of the
box), run `nix develop` first — it drops you into a shell with the right
`LD_LIBRARY_PATH` and a nixpkgs-native `ruff`, then `uv` works normally.

```bash
uv sync --extra dev

# List registered device drivers
uv run openrad devices

# Stream a sample survey as if from a live device
uv run openrad replay examples/sample_session.csv --speed 0
```

Each `replay` run saves a session (GPS track as `.gpx`) to
`~/.openrad/library/<session_id>/` unless run with `--no-save`.

```bash
uv sync --extra viz  # matplotlib + numpy, only needed for rendering

# Render a directory of .spe frames (one spectrum per time slice) as a
# spectrogram: time on x, energy on y, color = counts (log-scaled)
uv run openrad spectrogram examples/spectrogram --out spectrogram.png

# Render a single spectrum (.spe or a Theremino MCA export) as a PNG histogram
uv run openrad spectrum tests/fixtures/theremino/tc99mfinal.txt --out spectrum.png
```

```bash
# Isotope ID needs a reference database, which isn't vendored in this repo
# (it's ~6 MB of LGPL-2.1-licensed nuclear data — see the script for why).
# Fetch your own copy once:
uv run python scripts/fetch_isotope_database.py

# Then match spectrum peaks against it:
uv run openrad identify tests/fixtures/theremino/tc99mfinal.txt
```

Identification is a simple local-maxima peak finder plus energy matching
against known gamma lines (including short-lived daughters folded into
their parent via a secular-equilibrium assumption — see
`openrad/analysis/isotopes.py`) — a starting point for further
investigation, not a lab-grade result.

There's no dedicated spectrogram file format — a spectrogram is just an
ordered sequence of spectra, so a directory of `frame_00.spe`, `frame_01.spe`,
... (see `examples/spectrogram/`, or regenerate it with
`scripts/generate_example_spectrogram.py`) is what `openrad spectrogram`
expects.

## Development

```bash
uv sync --extra dev
uv run ruff check .
uv run mypy
uv run pytest
```

## Project layout

```
src/openrad/
  core/      Data model: Reading, Spectrum, Spectrogram, Track, DeviceInfo
  devices/   Device interface, registry, and drivers (replay driver included)
  storage/   .spe / .gpx / Theremino MCA read-write + local library + spectrogram loading
  analysis/  Peak finding + isotope identification (needs a fetched reference database)
  viz/       PNG rendering (spectrum + spectrogram heatmap), needs the "viz" extra
  cli/       `openrad` command-line entrypoint
tests/       pytest suite
examples/    sample CSV + a demo spectrogram for the replay/spectrogram commands
scripts/     one-off dev scripts (e.g. regenerating example data, fetching isotope data)
docs/        architecture and roadmap
```

## Contributing

The most useful next contribution is a real hardware driver — see
[docs/ROADMAP.md](docs/ROADMAP.md) and
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#adding-a-new-driver) for what
that involves. Issues and PRs welcome.

## License

MIT — see [LICENSE](LICENSE).

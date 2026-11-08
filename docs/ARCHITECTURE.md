# Architecture

## Layers

```
devices/    Device interface + registry + drivers (real hardware or replay)
core/       Data model shared by every layer (Reading, Spectrum, Track, ...)
storage/    Local library + file format readers/writers (.spe, .gpx)
viz/        Headless rendering (PNG output), e.g. the spectrogram heatmap
cli/        Thin CLI wiring devices -> a live dashboard -> storage/viz
```

Nothing above `core/` depends on a specific device, and nothing in `devices/`
depends on `storage/` or `cli/`. That separation is what makes "generic
radiation detectors" (the whole point of this project) tractable: a new
detector is a new file in `devices/`, not a rewrite of the app.

## The `Device` interface

Every driver — real or synthetic — implements `openrad.devices.base.Device`:

```python
class Device(ABC):
    def connect(self) -> DeviceInfo: ...
    def disconnect(self) -> None: ...
    def stream(self) -> Iterator[Reading]: ...
    def read_spectrum(self) -> Spectrum | None: ...  # optional
```

`stream()` is the only required data path: a generator of `Reading`
(timestamp, cps, dose_rate, optional lat/lon). `read_spectrum()` is optional
because not every detector (or the replay driver) does gamma spectroscopy.

## Adding a new driver

1. Create `devices/<name>.py`, subclass `Device`.
2. Decorate the class with `@registry.register("<name>")`.
3. Import the module somewhere it'll run at startup (the CLI does this
   explicitly today — see `cli/main.py`; a plugin/entry-points mechanism can
   replace that once there's more than a couple of built-in drivers).

`devices/replay.py` is the reference implementation: it reads a CSV and
replays it as a live-feeling stream, which is what makes the rest of the
system testable without hardware. Real hardware drivers include
`devices/ct007n.py` (GammaGuard CT007-N over BLE) and `devices/radiacode.py`
(RadiaCode RC-10x over BLE and USB, implementing the wire protocol documented
by [cdump/radiacode](https://github.com/cdump/radiacode)).

## Data model (`core/models.py`)

- `Reading` — one instantaneous sample (cps, dose_rate, optional GPS).
- `Spectrum` — one accumulated gamma spectrum (channel counts + calibration).
- `Spectrogram` / `SpectrogramFrame` — an ordered sequence of spectra (a
  Spectrum per time slice), the data behind a spectrogram plot.
- `Track` / `TrackPoint` — an ordered sequence of geotagged samples.
- `DeviceInfo` — static identity returned by `connect()` (driver, model,
  serial, firmware).

These are plain dataclasses on purpose: no ORM, no device-specific fields
leaking in. Device-specific quirks get normalized into this model inside the
driver, not exposed outward.

## Storage formats

- **Spectra → `.spe` and `.n42`**. ORTEC/IAEA ASCII `.spe` (`storage/spe.py`)
  is the default on-disk spectrum format because it is what hobbyist
  gamma-spectroscopy tools (Theremino MCA, Gamma Spectacular, Becquerel)
  read day to day. ANSI N42.42 XML (`storage/n42.py`, `openrad export-n42`)
  is also supported for interoperability with institutional tools such as
  [InterSpec](https://github.com/sandialabs/InterSpec).
- **Tracks → `.gpx`** (`storage/gpx.py`, GPX 1.1 read/write). The standard
  GPS track format; dose_rate and cps ride along as namespaced `<extensions>`
  so the file still opens in any ordinary GPX-consuming tool and round-trips
  cleanly back into `Track`.
- **Library** (`storage/library.py`) is just a directory per session
  (`track.gpx`, `spectrum.spe`, `metadata.json`) — no database. Simple to
  inspect, sync, or back up; a session-indexed SQLite layer can be added
  later without changing the on-disk file formats.

## Spectrogram storage and rendering

A spectrogram doesn't get its own file format: it's just a time-ordered
sequence of spectra, and `.spe` is already openrad's spectrum format, so a
directory of `frame_00.spe`, `frame_01.spe`, ... *is* the spectrogram —
`storage/spectrogram.load_spectrogram_dir()` reads the whole directory back
into a `Spectrogram`. `viz/spectrogram.render_spectrogram_png()` then renders
that as a static PNG heatmap (time × energy, color = log-scaled counts) using
matplotlib's headless `Agg` backend — no display or GUI required, which fits
a CLI/library-first tool. Color uses a single-hue sequential ramp (light to
dark blue), never a rainbow/jet colormap, since counts are a magnitude, not a
category.

`matplotlib`/`numpy` are an optional `viz` extra (`pip install
"openrad[viz]"`), not a base dependency, so headless/embedded uses of
`openrad` that never render anything stay lightweight. The CLI's
`spectrogram` command imports `viz.spectrogram` lazily and prints an install
hint if the extra isn't present, rather than making the whole CLI fail to
import.

## CLI

`cli/main.py` is intentionally thin: it wires a `Device` to a `rich`-based
live table and, at the end, to `Library.save_session()` (or, for
`spectrogram`, a loader to a renderer). It should stay thin — feature logic
(isotope ID, mapping, etc.) belongs in new modules under `core/`, `storage/`,
or `viz/`, not in the CLI file itself.

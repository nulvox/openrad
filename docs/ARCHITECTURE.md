# Architecture

## Layers

```
devices/    Device interface + registry + drivers (real hardware or replay)
core/       Data model shared by every layer (Reading, Spectrum, Track, ...)
storage/    Local library + file format readers/writers (.spe, .gpx)
cli/        Thin CLI wiring devices -> a live dashboard -> storage
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
system testable without hardware. The next real driver to add is almost
certainly a RadiaCode RC-10x BLE/USB driver — the wire protocol has already
been reverse-engineered by the community
([cdump/radiacode](https://github.com/cdump/radiacode)), so that work is
mostly porting/wrapping, not protocol archaeology.

## Data model (`core/models.py`)

- `Reading` — one instantaneous sample (cps, dose_rate, optional GPS).
- `Spectrum` — one accumulated gamma spectrum (channel counts + calibration).
- `Track` / `TrackPoint` — an ordered sequence of geotagged samples.
- `DeviceInfo` — static identity returned by `connect()` (driver, model,
  serial, firmware).

These are plain dataclasses on purpose: no ORM, no device-specific fields
leaking in. Device-specific quirks get normalized into this model inside the
driver, not exposed outward.

## Storage formats

- **Spectra → `.spe`** (ORTEC/IAEA ASCII). Chosen over ANSI N42.42 XML
  because it's what most hobbyist gamma-spectroscopy tools (Theremino MCA,
  Gamma Spectacular, Becquerel) actually read day to day. An N42 exporter
  (for interop with [InterSpec](https://github.com/sandialabs/InterSpec)) is
  a natural, self-contained follow-up in `storage/n42.py`.
- **Tracks → `.gpx`** (GPX 1.1). The standard GPS track format; dose_rate and
  cps ride along as namespaced `<extensions>` so the file still opens
  correctly in any ordinary GPX-consuming tool.
- **Library** (`storage/library.py`) is just a directory per session
  (`track.gpx`, `spectrum.spe`, `metadata.json`) — no database. Simple to
  inspect, sync, or back up; a session-indexed SQLite layer can be added
  later without changing the on-disk file formats.

## CLI

`cli/main.py` is intentionally thin: it wires a `Device` to a `rich`-based
live table and, at the end, to `Library.save_session()`. It should stay thin
— feature logic (isotope ID, mapping, etc.) belongs in new modules under
`core/` or a new top-level package, not in the CLI file itself.

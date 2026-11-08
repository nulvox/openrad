# Roadmap

This roadmap reflects the code on `main`. Checked items are implemented and covered by the current test suite; unchecked items are proposals or incomplete work.

## 0.1 foundation — implemented

### Device and telemetry pipeline

- [x] Typed `Device` interface (`connect`, `disconnect`, `stream`, optional `read_spectrum`)
- [x] Driver registry for named, pluggable device implementations
- [x] CSV replay driver for hardware-free development and deterministic tests
- [x] GammaGuard CT007-N BLE driver for live pulse-count telemetry
- [x] CT007-N advertised-name scanning and direct BLE-address connection
- [x] RadiaCode RC-10x BLE and USB driver (`VS.DATA_BUF` telemetry + `VS.SPECTRUM` v0/v1 decoding, based on the [cdump/radiacode](https://github.com/cdump/radiacode) wire protocol)
- [x] Live spectrum acquisition through `Device.read_spectrum()` (RadiaCode)
- [x] Async Bleak-to-sync `Device.stream()` bridge using a background event loop and queue
- [x] Live CLI dashboard plus low-contention plain-text mode
- [x] Core models: `DeviceInfo`, `Reading`, `Spectrum`, `Spectrogram`, `Track`
- [x] Optional GPS capture from readings into a saved track

The CT007-N protocol implementation intentionally does **not** claim calibrated dose readings by default. Its counts-to-dose factor was not found in the observed BLE characteristics, so `dose_rate` remains `0.0` unless a user supplies `counts_per_usv` for their unit.

### Storage and interchange

- [x] ORTEC/IAEA ASCII `.spe` spectrum read/write with energy calibration
- [x] ANSI N42.42 XML spectrum read/write (`storage/n42.py`, `openrad export-n42`) for InterSpec and institutional interoperability
- [x] Theremino MCA pulse-height histogram import with fitted linear calibration
- [x] GPX 1.1 track read/write with namespaced dose-rate and CPS extensions
- [x] Local per-session library (`track.gpx`, `spectrum.spe`, `metadata.json` save + load round-trips)
- [x] Spectrogram loading from a time-ordered directory of `.spe` frames
- [ ] Session index/search layer (likely SQLite) without replacing open on-disk formats
- [ ] HDF5 or Parquet export for large time-series and spectrum collections

### Analysis and visualization

- [x] Static spectrum PNG rendering with calibrated energy or channel axis
- [x] Static spectrogram PNG heatmap with log-scaled counts
- [x] Local-maxima spectrum peak detection
- [x] SandiaDecay XML reference-library loader
- [x] Candidate isotope matching against gamma-line energies
- [x] Short-lived daughter lines folded into parent candidates under a secular-equilibrium assumption
- [ ] Quantified measurement uncertainty and uncertainty propagation through calibration/analysis
- [ ] More robust peak fitting, background subtraction, confidence metrics, and detector-resolution models
- [ ] Cs-137 food-activity screening workflow

### Quality and portability

- [x] Strict `mypy` checking
- [x] Ruff linting
- [x] Pytest coverage across models, drivers, storage, analysis, visualization, and CLI commands
- [x] CI on Python 3.10–3.12 across Linux, macOS, and Windows
- [x] Reproducible Nix development shell for NixOS contributors

## Next — hardware and live acquisition

- [ ] Hardware-in-the-loop verification of the RadiaCode RC-10x driver against a physical unit
- [ ] GQ GMC-series USB-serial driver
- [ ] Spectrum accumulation during a `stream()` session
- [ ] Live spectrogram capture directly from a device session
- [ ] Driver discovery via Python entry points for out-of-tree plugins
- [ ] Fully async live CLI path to remove the remaining BLE/background-thread starvation risk

## Later — mapping and user interfaces

- [ ] Render saved or live tracks as dose-rate-colored paths on an OpenStreetMap/Leaflet basemap
- [ ] Desktop or web frontend reusing the existing device/core/storage layers
- [ ] Attach a photo and contextual metadata to a spectrum or log entry ("gamma camera")
- [ ] Search-mode audio after suitable live hardware is available for testing

## Explicitly out of scope for now

- Multi-user or cloud synchronization: openrad is local-first by design
- Claims of safety-grade dosimetry without traceable device calibration and uncertainty handling

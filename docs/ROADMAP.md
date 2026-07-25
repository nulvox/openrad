# Roadmap

## MVP (this scaffold)

- [x] `Device` interface + registry
- [x] Replay driver (CSV) for hardware-free development/testing
- [x] Core data model (Reading, Spectrum, Track)
- [x] `.spe` spectrum read/write
- [x] `.gpx` track write
- [x] Local library (per-session directory storage)
- [x] CLI: `openrad devices`, `openrad replay <file>`
- [x] Test suite + CI (ruff, mypy, pytest)

## Phase 2 — real hardware

- [ ] RadiaCode RC-10x driver (BLE + USB), building on the reverse-engineered
      protocol from [cdump/radiacode](https://github.com/cdump/radiacode)
- [ ] GQ GMC-series driver (USB-serial)
- [ ] `.spe` → live spectrum accumulation during a `stream()` session (not
      just import/export)
- [ ] `.gpx` reader (round-trip, for re-importing saved tracks)

## Phase 3 — analysis features

- [ ] Isotope identification: peak-finding + matching against a nuclide
      energy-line library (start with Cs-137, Co-60, K-40, Am-241, Na-22)
- [ ] Spectrogram view (time series of spectra, as RadiaCode's software does)
- [ ] N42.42 XML export, for interop with InterSpec and other institutional
      tools
- [ ] Cs-137 food-activity screening mode

## Phase 4 — UI

- [ ] Mapping UI: render a saved/live Track as a color-coded dose-rate track
      on an OpenStreetMap/Leaflet basemap (avoids a Google Maps API
      dependency/cost)
- [ ] Desktop or web frontend on top of the `openrad` library (the CLI/core
      split exists specifically so a GUI can reuse `devices`/`core`/`storage`
      without duplicating logic)
- [ ] "Gamma camera" — attach a photo to a spectrum/log entry

## Explicitly out of scope for now

- Search-mode audio playback (device-side feature, low priority without
  live hardware to test against)
- Multi-user/cloud sync — this project is local-first by design

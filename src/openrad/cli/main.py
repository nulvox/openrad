"""The `openrad` command-line interface."""

from __future__ import annotations

import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.live import Live
from rich.table import Table

from openrad.analysis.isotopes import DEFAULT_DATABASE_PATH
from openrad.core.models import DeviceInfo, Reading, Spectrum, Track, TrackPoint
from openrad.devices import registry
from openrad.devices.base import Device
from openrad.devices.ct007n import CT007NDevice  # noqa: F401  (registers "ct007n" driver)
from openrad.devices.radiacode import RadiacodeDevice  # noqa: F401  (registers "radiacode" driver)
from openrad.devices.replay import ReplayDevice  # noqa: F401  (registers "replay" driver)
from openrad.storage.library import Library
from openrad.storage.spectrogram import load_spectrogram_dir

app = typer.Typer(help="openrad: an open-source toolkit for radiation detectors.")
console = Console()


_DASHBOARD_MAX_ROWS = 20
_DASHBOARD_MIN_REFRESH_S = 0.25


def _read_spectrum_file(file: Path) -> Spectrum:
    """Load a Spectrum, detecting the format (.spe, .n42/.xml, or Theremino) from extension."""
    suffix = file.suffix.lower()
    if suffix == ".spe":
        from openrad.storage.spe import read_spe

        return read_spe(file)

    if suffix in {".n42", ".xml"}:
        from openrad.storage.n42 import read_n42

        return read_n42(file)

    from openrad.storage.theremino import read_theremino

    return read_theremino(file)


def _build_dashboard_table(title: str, rows: deque[tuple[str, str, str, str, str]]) -> Table:
    table = Table(title=title)
    table.add_column("time")
    table.add_column("cps", justify="right")
    table.add_column("dose (µSv/h)", justify="right")
    table.add_column("lat")
    table.add_column("lon")
    for row in rows:
        table.add_row(*row)
    return table


def _run_live_dashboard(
    device: Device, info: DeviceInfo, *, save: bool, library_dir: Path | None, plain: bool = False
) -> None:
    """Show readings for `device` until its stream ends, then save the track.

    `plain` prints one scrolling line per reading instead of a redrawing
    Rich table — easier to copy/select in a terminal, and avoids any
    chance that continuous live-redraw work on the main thread competes
    for the GIL with a driver's background I/O thread (relevant for BLE
    drivers like ct007n, where that contention is under investigation).
    """
    session_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    track = Track(name=session_id)

    def _handle_reading(reading: Reading) -> None:
        if reading.latitude is not None and reading.longitude is not None:
            track.add(
                TrackPoint(
                    timestamp=reading.timestamp,
                    latitude=reading.latitude,
                    longitude=reading.longitude,
                    dose_rate=reading.dose_rate,
                    cps=reading.cps,
                )
            )

    spectrum_data: Spectrum | None = None
    try:
        if plain:
            console.print(f"openrad live — {info.model}")
            for reading in device.stream():
                lat = f"{reading.latitude:.5f}" if reading.latitude is not None else "-"
                lon = f"{reading.longitude:.5f}" if reading.longitude is not None else "-"
                console.print(
                    f"{reading.timestamp.strftime('%H:%M:%S')}  "
                    f"cps={reading.cps:6.2f}  dose={reading.dose_rate:7.3f} uSv/h  "
                    f"lat={lat}  lon={lon}"
                )
                _handle_reading(reading)
        else:
            title = f"openrad live — {info.model}"
            recent_rows: deque[tuple[str, str, str, str, str]] = deque(
                maxlen=_DASHBOARD_MAX_ROWS
            )
            last_refresh = 0.0

            with Live(
                _build_dashboard_table(title, recent_rows),
                console=console,
                auto_refresh=False,
            ) as live:
                for reading in device.stream():
                    recent_rows.append(
                        (
                            reading.timestamp.strftime("%H:%M:%S"),
                            f"{reading.cps:.2f}",
                            f"{reading.dose_rate:.3f}",
                            f"{reading.latitude:.5f}" if reading.latitude is not None else "-",
                            f"{reading.longitude:.5f}" if reading.longitude is not None else "-",
                        )
                    )
                    _handle_reading(reading)
                    now = time.monotonic()
                    if now - last_refresh >= _DASHBOARD_MIN_REFRESH_S:
                        live.update(_build_dashboard_table(title, recent_rows), refresh=True)
                        last_refresh = now
                live.update(_build_dashboard_table(title, recent_rows), refresh=True)
    finally:
        if save:
            try:
                spectrum_data = device.read_spectrum()
            except Exception:  # noqa: BLE001 - best-effort snapshot before disconnect
                spectrum_data = None
        device.disconnect()

    if save and (track.points or spectrum_data is not None):
        library = Library(library_dir)
        session_dir = library.save_session(
            session_id,
            track=track if track.points else None,
            spectrum=spectrum_data,
            device_info=vars(info),
        )
        console.print(f"Saved session to {session_dir}")


@app.command("devices")
def list_devices() -> None:
    """List registered device drivers."""
    for name in registry.available():
        console.print(f"- {name}")


@app.command()
def replay(
    file: Path = typer.Argument(
        ..., help="CSV file to replay: timestamp,cps,dose_rate,latitude,longitude"
    ),
    speed: float = typer.Option(1.0, help="Playback speed multiplier; 0 = as fast as possible"),
    save: bool = typer.Option(True, help="Save the resulting track to the local library"),
    library_dir: Path | None = typer.Option(None, help="Override the library directory"),
    plain: bool = typer.Option(
        False, help="Print scrolling lines instead of a redrawing table (easier to copy)"
    ),
) -> None:
    """Stream a CSV file as if from a live device, showing a live dashboard."""
    device = ReplayDevice(file, speed=speed)
    info = device.connect()
    _run_live_dashboard(device, info, save=save, library_dir=library_dir, plain=plain)


@app.command()
def ct007n(
    address_or_name: str = typer.Argument(
        ..., help='BLE MAC address, or a name substring to scan for, e.g. "CT-N-13"'
    ),
    counts_per_usv: float | None = typer.Option(
        None,
        help=(
            "Counts-per-uSv conversion factor for dose_rate. Not transmitted by the "
            "device (see devices/ct007n.py) — without it, dose_rate is always 0.0."
        ),
    ),
    save: bool = typer.Option(True, help="Save the resulting track to the local library"),
    library_dir: Path | None = typer.Option(None, help="Override the library directory"),
    read_device_info: bool = typer.Option(
        False,
        help=(
            "Read Model/Firmware before subscribing. Off by default; see "
            "devices/ct007n.py for the disconnect investigation this relates to."
        ),
    ),
    plain: bool = typer.Option(
        True,
        help=(
            "Print scrolling lines instead of a redrawing table. On by default: the "
            "table's 4Hz redraw competing with the BLE background thread for the GIL "
            "is confirmed to cause the device to drop the connection (see "
            "devices/ct007n.py) — only disable this for a nicer dashboard once that's "
            "fixed some other way."
        ),
    ),
) -> None:
    """Connect to a CT007-N over Bluetooth LE, showing a live dashboard."""
    try:
        device = CT007NDevice(
            address_or_name, counts_per_usv=counts_per_usv, read_device_info=read_device_info
        )
        info = device.connect()
    except ImportError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1) from None

    _run_live_dashboard(device, info, save=save, library_dir=library_dir, plain=plain)


@app.command()
def radiacode(
    bluetooth: str | None = typer.Option(
        None,
        "--bluetooth",
        "-b",
        help='BLE MAC/UUID, or advertised name substring (e.g. "RadiaCode"). Omit for USB.',
    ),
    serial: str | None = typer.Option(
        None, help="USB serial number when connecting over USB with multiple devices."
    ),
    poll_interval: float = typer.Option(1.0, help="Seconds between DATA_BUF polls"),
    accumulated_spectrum: bool = typer.Option(
        False, help="Read long-term accumulated spectrum (VS.SPEC_ACCUM) instead of current"
    ),
    reset_spectrum: bool = typer.Option(
        False, help="Reset the device's current spectrum before streaming"
    ),
    spectrum_out: Path | None = typer.Option(
        None, help="Fetch a single spectrum snapshot to this .spe file and exit"
    ),
    save: bool = typer.Option(True, help="Save the session (track + spectrum) to the library"),
    library_dir: Path | None = typer.Option(None, help="Override the library directory"),
    plain: bool = typer.Option(
        True,
        help="Print scrolling lines instead of a redrawing table (recommended over BLE)",
    ),
) -> None:
    """Connect to a RadiaCode RC-10x over BLE or USB for live telemetry or spectrum export."""
    try:
        device = RadiacodeDevice(
            bluetooth_mac=bluetooth,
            serial_number=serial,
            poll_interval_s=poll_interval,
            accumulated_spectrum=accumulated_spectrum,
        )
        info = device.connect()
    except ImportError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1) from None

    if spectrum_out is not None:
        from openrad.storage.spe import write_spe

        try:
            if reset_spectrum:
                device.reset_spectrum()
            spec = device.read_spectrum()
            if spec is None:
                console.print("No spectrum returned by device.")
                raise typer.Exit(code=1)
            write_spe(spec, spectrum_out)
            console.print(f"Wrote {spectrum_out}")
        finally:
            device.disconnect()
        return

    if reset_spectrum:
        device.reset_spectrum()

    _run_live_dashboard(device, info, save=save, library_dir=library_dir, plain=plain)


@app.command()
def spectrogram(
    directory: Path = typer.Argument(
        ..., help="Directory of *.spe frame files, one per time slice"
    ),
    out: Path = typer.Option(Path("spectrogram.png"), help="Output PNG path"),
    channel_axis: bool = typer.Option(
        False, help="Plot raw channel number instead of calibrated energy (keV)"
    ),
) -> None:
    """Render a time series of spectra (a directory of .spe files) as a PNG heatmap."""
    try:
        from openrad.viz.spectrogram import render_spectrogram_png
    except ImportError:
        console.print('Rendering needs the "viz" extra: pip install "openrad[viz]"')
        raise typer.Exit(code=1) from None

    spectrogram_data = load_spectrogram_dir(directory)
    render_spectrogram_png(spectrogram_data, out, energy_axis=not channel_axis)
    console.print(f"Wrote {out}")


@app.command()
def spectrum(
    file: Path = typer.Argument(
        ..., help="Spectrum file: .spe, or a Theremino MCA histogram export"
    ),
    out: Path = typer.Option(Path("spectrum.png"), help="Output PNG path"),
    channel_axis: bool = typer.Option(
        False, help="Plot raw channel number instead of calibrated energy (keV)"
    ),
) -> None:
    """Render a single spectrum (.spe or Theremino export) as a PNG histogram."""
    try:
        from openrad.viz.spectrum import render_spectrum_png
    except ImportError:
        console.print('Rendering needs the "viz" extra: pip install "openrad[viz]"')
        raise typer.Exit(code=1) from None

    spectrum_data = _read_spectrum_file(file)
    render_spectrum_png(spectrum_data, out, energy_axis=not channel_axis)
    console.print(f"Wrote {out}")


@app.command("export-n42")
def export_n42(
    file: Path = typer.Argument(
        ..., help="Input spectrum file (.spe, Theremino export, or .n42)"
    ),
    out: Path = typer.Option(Path("spectrum.n42"), help="Output ANSI N42.42 XML path"),
) -> None:
    """Convert a spectrum (.spe or Theremino) into ANSI N42.42 XML for InterSpec."""
    from openrad.storage.n42 import write_n42

    spectrum_data = _read_spectrum_file(file)
    write_n42(spectrum_data, out)
    console.print(f"Wrote {out}")


@app.command()
def identify(
    file: Path = typer.Argument(
        ..., help="Spectrum file: .spe, or a Theremino MCA histogram export"
    ),
    database: Path = typer.Option(
        DEFAULT_DATABASE_PATH,
        help="SandiaDecay XML database path (see scripts/fetch_isotope_database.py)",
    ),
    tolerance: float = typer.Option(10.0, help="Peak-to-reference-line match tolerance, in keV"),
    top: int = typer.Option(5, help="Number of candidate isotopes to show"),
) -> None:
    """Suggest candidate isotopes by matching spectrum peaks against known gamma lines.

    This is a rough starting point (local-maxima peak finding + energy
    matching), not a lab-grade identification — treat results as leads to
    investigate, not conclusions.
    """
    from openrad.analysis.identify import find_peaks
    from openrad.analysis.identify import identify as identify_isotopes
    from openrad.analysis.isotopes import load_isotope_library

    try:
        library = load_isotope_library(database)
    except FileNotFoundError as exc:
        console.print(str(exc))
        raise typer.Exit(code=1) from None

    spectrum_data = _read_spectrum_file(file)
    peaks = find_peaks(spectrum_data)
    if not peaks:
        console.print("No significant peaks found.")
        raise typer.Exit(code=0)

    energies = ", ".join(f"{p.energy_kev:.1f} keV" for p in peaks)
    console.print(f"Found {len(peaks)} peak(s): {energies}")

    candidates = identify_isotopes(spectrum_data, library, tolerance_kev=tolerance, top_n=top)
    if not candidates:
        console.print("No matching isotopes in the database.")
        raise typer.Exit(code=0)

    table = Table(title="Candidate isotopes")
    table.add_column("isotope")
    table.add_column("score", justify="right")
    table.add_column("matched lines (keV)")
    for candidate in candidates:
        table.add_row(
            candidate.isotope,
            f"{candidate.score:.2f}",
            ", ".join(f"{e:.1f}" for e in candidate.matched_lines_kev),
        )
    console.print(table)


def main() -> None:
    app()


if __name__ == "__main__":
    main()

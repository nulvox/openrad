"""The `openrad` command-line interface."""

from __future__ import annotations

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
from openrad.devices.replay import ReplayDevice  # noqa: F401  (registers "replay" driver)
from openrad.storage.library import Library
from openrad.storage.spectrogram import load_spectrogram_dir

app = typer.Typer(help="openrad: an open-source toolkit for radiation detectors.")
console = Console()


def _read_spectrum_file(file: Path) -> Spectrum:
    """Load a Spectrum, detecting the format (.spe vs. Theremino) from the extension."""
    if file.suffix.lower() == ".spe":
        from openrad.storage.spe import read_spe

        return read_spe(file)

    from openrad.storage.theremino import read_theremino

    return read_theremino(file)


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
            table = Table(title=f"openrad live — {info.model}")
            table.add_column("time")
            table.add_column("cps", justify="right")
            table.add_column("dose (µSv/h)", justify="right")
            table.add_column("lat")
            table.add_column("lon")

            with Live(table, console=console, refresh_per_second=4):
                for reading in device.stream():
                    table.add_row(
                        reading.timestamp.strftime("%H:%M:%S"),
                        f"{reading.cps:.2f}",
                        f"{reading.dose_rate:.3f}",
                        f"{reading.latitude:.5f}" if reading.latitude is not None else "-",
                        f"{reading.longitude:.5f}" if reading.longitude is not None else "-",
                    )
                    _handle_reading(reading)
    finally:
        device.disconnect()

    if save and track.points:
        library = Library(library_dir)
        session_dir = library.save_session(session_id, track=track, device_info=vars(info))
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

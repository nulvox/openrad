"""The `openrad` command-line interface."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.live import Live
from rich.table import Table

from openrad.core.models import Track, TrackPoint
from openrad.devices import registry
from openrad.devices.replay import ReplayDevice  # noqa: F401  (registers "replay" driver)
from openrad.storage.library import Library
from openrad.storage.spectrogram import load_spectrogram_dir

app = typer.Typer(help="openrad: an open-source toolkit for radiation detectors.")
console = Console()


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
) -> None:
    """Stream a CSV file as if from a live device, showing a live dashboard."""
    device = ReplayDevice(file, speed=speed)
    info = device.connect()

    session_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    track = Track(name=session_id)

    table = Table(title=f"openrad live — {info.model}")
    table.add_column("time")
    table.add_column("cps", justify="right")
    table.add_column("dose (µSv/h)", justify="right")
    table.add_column("lat")
    table.add_column("lon")

    try:
        with Live(table, console=console, refresh_per_second=4):
            for reading in device.stream():
                table.add_row(
                    reading.timestamp.strftime("%H:%M:%S"),
                    f"{reading.cps:.2f}",
                    f"{reading.dose_rate:.3f}",
                    f"{reading.latitude:.5f}" if reading.latitude is not None else "-",
                    f"{reading.longitude:.5f}" if reading.longitude is not None else "-",
                )
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
    finally:
        device.disconnect()

    if save and track.points:
        library = Library(library_dir)
        session_dir = library.save_session(session_id, track=track, device_info=vars(info))
        console.print(f"Saved session to {session_dir}")


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


def main() -> None:
    app()


if __name__ == "__main__":
    main()

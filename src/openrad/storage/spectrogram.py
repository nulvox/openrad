"""Build a Spectrogram from a time-ordered directory of .spe frame files.

There's no dedicated spectrogram file format: a spectrogram is just an
ordered sequence of spectra, and .spe is already openrad's spectrum format
(see storage/spe.py), so a directory of *.spe files is the natural container
— one file per time slice.
"""

from __future__ import annotations

from pathlib import Path

from openrad.core.models import Spectrogram, SpectrogramFrame
from openrad.storage.spe import read_spe


def load_spectrogram_dir(path: str | Path, name: str | None = None) -> Spectrogram:
    """Load every *.spe file in `path`, ordered by filename, as one Spectrogram.

    All frames must share the same channel count. The first frame's energy
    calibration is used for the whole Spectrogram.
    """
    directory = Path(path)
    frame_paths = sorted(directory.glob("*.spe"))
    if not frame_paths:
        raise ValueError(f"no .spe files found in {directory}")

    first = read_spe(frame_paths[0])
    spectrogram = Spectrogram(name=name or directory.name, calibration=first.calibration)
    channel_count = len(first.counts)

    for index, frame_path in enumerate(frame_paths):
        spectrum = first if index == 0 else read_spe(frame_path)
        if len(spectrum.counts) != channel_count:
            raise ValueError(
                f"{frame_path.name} has {len(spectrum.counts)} channels, "
                f"expected {channel_count} (from {frame_paths[0].name})"
            )
        spectrogram.add(SpectrogramFrame(timestamp=spectrum.start_time, counts=spectrum.counts))

    return spectrogram

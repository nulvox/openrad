"""Data model shared by every device driver, storage backend, and the CLI."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class DeviceInfo:
    """Static identity of a connected device, returned by Device.connect()."""

    driver: str
    model: str
    serial: str | None = None
    firmware: str | None = None


@dataclass
class Reading:
    """A single point-in-time measurement from a device."""

    timestamp: datetime
    cps: float
    dose_rate: float  # microsieverts per hour
    latitude: float | None = None
    longitude: float | None = None


@dataclass
class Spectrum:
    """An accumulated gamma spectrum (channel counts + energy calibration)."""

    counts: list[int]
    live_time_s: float
    real_time_s: float
    start_time: datetime
    calibration: tuple[float, float, float] = (0.0, 3.0, 0.0)
    name: str = "spectrum"

    def energy_of_channel(self, channel: int) -> float:
        """Convert a channel number to keV using the quadratic calibration."""
        a0, a1, a2 = self.calibration
        return a0 + a1 * channel + a2 * channel * channel


@dataclass
class SpectrogramFrame:
    """One time-sliced spectrum within a Spectrogram."""

    timestamp: datetime
    counts: list[int]


@dataclass
class Spectrogram:
    """A time series of spectra: the raw data behind a spectrogram plot.

    Unlike Spectrum (one accumulated measurement), a Spectrogram is many
    short spectra recorded back to back, so intensity changes over time are
    visible per energy channel — e.g. a source passing by.
    """

    name: str
    calibration: tuple[float, float, float] = (0.0, 3.0, 0.0)
    frames: list[SpectrogramFrame] = field(default_factory=list)

    def add(self, frame: SpectrogramFrame) -> None:
        self.frames.append(frame)

    def energy_of_channel(self, channel: int) -> float:
        """Convert a channel number to keV using the quadratic calibration."""
        a0, a1, a2 = self.calibration
        return a0 + a1 * channel + a2 * channel * channel


@dataclass
class TrackPoint:
    """A single geotagged dose-rate sample along a Track."""

    timestamp: datetime
    latitude: float
    longitude: float
    dose_rate: float
    cps: float


@dataclass
class Track:
    """An ordered sequence of TrackPoints, e.g. one survey walk or drive."""

    name: str
    points: list[TrackPoint] = field(default_factory=list)

    def add(self, point: TrackPoint) -> None:
        self.points.append(point)

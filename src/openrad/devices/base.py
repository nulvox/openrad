"""The interface every device driver (real hardware or synthetic) must implement.

Adding support for a new detector means subclassing Device and registering it
with @registry.register("name") — see devices/replay.py for a working example,
and docs/ARCHITECTURE.md for the full guide.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from openrad.core.models import DeviceInfo, Reading, Spectrum


class Device(ABC):
    """A source of Readings, and optionally a Spectrum, from a detector."""

    @abstractmethod
    def connect(self) -> DeviceInfo:
        """Open the connection and return the device's static identity."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close the connection, releasing any resources."""

    @abstractmethod
    def stream(self) -> Iterator[Reading]:
        """Yield Readings as they arrive (or, for replay sources, are replayed)."""

    def read_spectrum(self) -> Spectrum | None:
        """Return the current accumulated spectrum, if this device supports it.

        Optional: not every device (or replay source) does gamma spectroscopy.
        """
        return None

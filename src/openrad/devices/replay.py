"""A Device driver that replays readings from a CSV file.

This exists so the rest of openrad (dashboard, storage, exports) can be built
and tested without real hardware. It's also the reference driver for what a
real driver (e.g. RadiaCode over BLE, GQ GMC over USB-serial) needs to
implement.
"""

from __future__ import annotations

import csv
import time
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from openrad.core.models import DeviceInfo, Reading
from openrad.devices.base import Device
from openrad.devices.registry import register


@register("replay")
class ReplayDevice(Device):
    """Replays readings from a CSV file with columns:

    timestamp,cps,dose_rate,latitude,longitude

    `timestamp` must be ISO 8601. `latitude`/`longitude` may be left blank
    for rows with no GPS fix.
    """

    def __init__(self, path: str | Path, speed: float = 1.0) -> None:
        self.path = Path(path)
        self.speed = speed  # 0 = replay as fast as possible

    def connect(self) -> DeviceInfo:
        if not self.path.exists():
            raise FileNotFoundError(f"replay file not found: {self.path}")
        return DeviceInfo(driver="replay", model="CSV Replay", serial=str(self.path))

    def disconnect(self) -> None:
        pass

    def stream(self) -> Iterator[Reading]:
        previous_timestamp: datetime | None = None
        with self.path.open(newline="") as fh:
            for row in csv.DictReader(fh):
                timestamp = datetime.fromisoformat(row["timestamp"])
                if self.speed > 0 and previous_timestamp is not None:
                    delay = (timestamp - previous_timestamp).total_seconds() / self.speed
                    if delay > 0:
                        time.sleep(delay)
                previous_timestamp = timestamp

                latitude = float(row["latitude"]) if row.get("latitude") else None
                longitude = float(row["longitude"]) if row.get("longitude") else None

                yield Reading(
                    timestamp=timestamp,
                    cps=float(row["cps"]),
                    dose_rate=float(row["dose_rate"]),
                    latitude=latitude,
                    longitude=longitude,
                )

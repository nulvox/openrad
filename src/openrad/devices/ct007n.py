"""BLE driver for the CT007-N (NanoNuke) radiation detector.

GammaGuard's BLE protocol is undocumented — no public spec, and unlike
RadiaCode (see docs/ARCHITECTURE.md), no known community reverse-engineering
effort. Everything below was determined by direct observation against a
real unit with scripts/ble_explore.py, not vendor docs:

- Custom service f100ffd0-0451-4100-b100-000000000000, characteristic
  f100ffd1-... (read, notify): a 4-byte little-endian uint32 pulse count
  *since the previous notification*, sent roughly every 100-220ms (the
  interval isn't fixed). CPS is derived by dividing by the actual elapsed
  wall-clock time between notifications, not an assumed interval.
- Standard Battery Service (0x180F / 0x2A19) and Device Information
  Service (0x180A) characteristics behave as documented in the Bluetooth
  SIG spec, except Battery Level is also 4 bytes little-endian here (the
  spec says 1 byte) — the first byte is still the 0-100 percentage.
- A second custom service (25fb9e91-.../c3fbc9e2-...) streams a one-shot
  ASCII boot banner on connect ("BotSpine.../OAD v0.11...") — a firmware
  debug console, not sensor data. Its paired write characteristic
  (d6af9b3c-...) is presumably a command channel for that console, but the
  command syntax is unknown, so it's unused here.

What's NOT known: the device's counts -> dose-rate conversion factor. The
GammaGuard app clearly applies one (it displays uSv/h with a device-specific
"Range to N.NN uSv/hr"), but it isn't transmitted on any characteristic we
found. Guessing a number for a radiation-safety reading would be actively
misleading, so `dose_rate` is 0.0 unless a `counts_per_usv` factor is
supplied explicitly (see CT007NDevice).

If GammaGuard's admin settings (password 1234 by default) expose the
conversion factor on your unit, pass it in; otherwise treat `cps` as the
trustworthy signal and dose_rate as unset.
"""

from __future__ import annotations

import asyncio
import queue
import re
import threading
import time
from collections.abc import Iterator
from datetime import datetime, timezone

from openrad.core.models import DeviceInfo, Reading
from openrad.devices.base import Device
from openrad.devices.registry import register

_COUNT_CHARACTERISTIC = "f100ffd1-0451-4100-b100-000000000000"
_MODEL_CHARACTERISTIC = "00002a24-0000-1000-8000-00805f9b34fb"
_FIRMWARE_CHARACTERISTIC = "00002a26-0000-1000-8000-00805f9b34fb"

_MAC_ADDRESS_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


def _decode_count(data: bytes | bytearray) -> int:
    """Decode a count-characteristic notification: a little-endian uint32."""
    return int.from_bytes(data[:4], "little")


def _decode_ascii(data: bytes | bytearray) -> str:
    return bytes(data).decode("ascii", errors="replace").strip()


def _compute_reading(
    counts: int,
    elapsed_s: float,
    *,
    counts_per_usv: float | None,
    timestamp: datetime,
) -> Reading:
    """Turn a raw pulse count over `elapsed_s` seconds into a Reading.

    `counts_per_usv` converts counts to a dose rate; without it (the usual
    case — see module docstring), dose_rate is 0.0 rather than a
    fabricated number.
    """
    cps = counts / elapsed_s if elapsed_s > 0 else 0.0
    dose_rate = (cps * 3600.0 / counts_per_usv) if counts_per_usv else 0.0
    return Reading(timestamp=timestamp, cps=cps, dose_rate=dose_rate)


@register("ct007n")
class CT007NDevice(Device):
    """Streams live Readings from a CT007-N over Bluetooth LE.

    `address_or_name` is either the BLE MAC address (fast, skips scanning)
    or a substring to match against the advertised name, e.g. "CT-N-13"
    (scans first, like scripts/ble_explore.py).

    `read_device_info` reads the Model/Firmware Device Information
    characteristics before subscribing to the count stream. Default False
    (kept off after isolation testing implicated something else below —
    see git history if you want the detour).

    CONFIRMED root cause of an earlier reliability issue: the CLI's Rich
    `Live` dashboard redraws at 4Hz on the main thread, while this driver's
    BLE I/O runs on a background thread's asyncio event loop (bridged into
    stream()'s sync generator via _BleRunner, since bleak is async-only and
    every Device.stream() must be a plain sync generator). That redraw work
    was starving the background loop of GIL time badly enough that BLE
    notification/ACK handling fell behind and the device dropped the
    connection — consistently within seconds to tens of seconds. Switching
    the CLI to plain scrolling output (cli/main.py's `ct007n --plain`,
    default True) removed the contention and the connection has held for
    minutes. The underlying fragility (a slow/blocked main thread can still
    starve the BLE thread) remains — a fully async CLI event loop would
    remove it structurally, but that's a larger change than this fix
    warranted.
    """

    def __init__(
        self,
        address_or_name: str,
        *,
        counts_per_usv: float | None = None,
        read_device_info: bool = False,
    ) -> None:
        self.address_or_name = address_or_name
        self.counts_per_usv = counts_per_usv
        self.read_device_info = read_device_info
        self._runner: _BleRunner | None = None

    def connect(self) -> DeviceInfo:
        self._runner = _BleRunner(
            self.address_or_name, self.counts_per_usv, read_device_info=self.read_device_info
        )
        model, firmware, address = self._runner.start()
        return DeviceInfo(driver="ct007n", model=model, serial=address, firmware=firmware)

    def disconnect(self) -> None:
        if self._runner is not None:
            self._runner.stop()
            self._runner = None

    def stream(self) -> Iterator[Reading]:
        if self._runner is None:
            raise RuntimeError("stream() called before connect()")
        while True:
            reading = self._runner.queue.get()
            if reading is None:
                if self._runner.error is not None:
                    raise self._runner.error
                return
            yield reading


class _BleRunner:
    """Runs a BleakClient connection on its own event loop in a background thread.

    bleak is async-only; Device.stream() is a plain sync generator (so
    every driver, real or replay, looks the same to the CLI). This bridges
    the two: notifications land in a thread-safe queue that stream() drains.
    """

    def __init__(
        self, address_or_name: str, counts_per_usv: float | None, *, read_device_info: bool
    ) -> None:
        self.address_or_name = address_or_name
        self.counts_per_usv = counts_per_usv
        self.read_device_info = read_device_info
        self.queue: queue.Queue[Reading | None] = queue.Queue()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._ready = threading.Event()
        self._stop_event: asyncio.Event | None = None
        self.error: BaseException | None = None
        self._device_info: tuple[str, str, str] = ("CT007-N", "", "")

    def start(self, timeout: float = 30.0) -> tuple[str, str, str]:
        self._thread.start()
        if not self._ready.wait(timeout=timeout):
            raise TimeoutError(f"timed out connecting to {self.address_or_name}")
        if self.error is not None:
            raise self.error
        return self._device_info

    def stop(self) -> None:
        if self._stop_event is not None:
            self._loop.call_soon_threadsafe(self._stop_event.set)
        self._thread.join(timeout=10.0)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main())
        finally:
            self.queue.put(None)

    async def _main(self) -> None:
        try:
            from bleak import BleakClient
        except ImportError as exc:
            raise ImportError(
                'CT007NDevice needs the "ble" extra: uv sync --extra ble '
                '(or pip install "openrad[ble]")'
            ) from exc

        self._stop_event = asyncio.Event()
        stop_event = self._stop_event

        def _on_disconnect(_client: object) -> None:
            # bleak never raises on an unexpected disconnect (device powered
            # off, dropped out of range, ...) unless you register this
            # callback — without it, `await stop_event.wait()` below blocks
            # forever. Only treat it as an error if *we* didn't request the
            # disconnect via stop() (which sets stop_event itself first).
            if not stop_event.is_set():
                self.error = ConnectionError(
                    f"{self.address_or_name} disconnected unexpectedly "
                    "(it may have powered off, or dropped the BLE link)"
                )
            self._loop.call_soon_threadsafe(stop_event.set)

        try:
            address = await _resolve_address(self.address_or_name)

            async with BleakClient(address, disconnected_callback=_on_disconnect) as client:
                if self.read_device_info:
                    model = _decode_ascii(await client.read_gatt_char(_MODEL_CHARACTERISTIC))
                    firmware = _decode_ascii(
                        await client.read_gatt_char(_FIRMWARE_CHARACTERISTIC)
                    )
                    model_label = f"CT007-N ({model})" if model else "CT007-N"
                    self._device_info = (model_label, firmware, address)
                else:
                    self._device_info = ("CT007-N", "", address)

                last_notification = time.monotonic()

                def _on_notify(_sender: object, data: bytearray) -> None:
                    nonlocal last_notification
                    now = time.monotonic()
                    elapsed = now - last_notification
                    last_notification = now
                    self.queue.put(
                        _compute_reading(
                            _decode_count(data),
                            elapsed,
                            counts_per_usv=self.counts_per_usv,
                            timestamp=datetime.now(timezone.utc),
                        )
                    )

                await client.start_notify(_COUNT_CHARACTERISTIC, _on_notify)
                self._ready.set()
                await stop_event.wait()
                if client.is_connected:
                    await client.stop_notify(_COUNT_CHARACTERISTIC)
        except Exception as exc:  # noqa: BLE001 - surfaced to the calling thread via start()
            self.error = exc
            self._ready.set()


async def _resolve_address(address_or_name: str) -> str:
    if _MAC_ADDRESS_RE.match(address_or_name):
        return address_or_name

    from bleak import BleakScanner

    devices = await BleakScanner.discover(timeout=10.0)
    matches = [d for d in devices if d.name and address_or_name.lower() in d.name.lower()]
    if not matches:
        raise ConnectionError(f"no BLE device found matching {address_or_name!r}")
    return matches[0].address

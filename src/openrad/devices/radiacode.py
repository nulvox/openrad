"""BLE and USB driver for RadiaCode RC-10x (101/102/103/103G) detectors.

Credits:
The RadiaCode wire protocol, register map, `VS.DATA_BUF` record layout, and
`VS.SPECTRUM` compression formats implemented here were reverse-engineered
and documented by Maxim Andreev (@cdump) and contributors in
https://github.com/cdump/radiacode.

This module implements that protocol directly against `openrad`'s domain
models (`DeviceInfo`, `Reading`, `Spectrum`) without requiring an external
SDK dependency:

- BLE transport uses `bleak` (already part of `openrad[ble]`), writing
  18-byte chunks to characteristic `e63215e6-7003-49d8-96b0-b024798fb901`
  and reassembling length-prefixed responses from notifications on
  `e63215e7-7003-49d8-96b0-b024798fb901`.
- USB transport uses `pyusb` (`openrad[usb]`) against VID `0x0483`,
  PID `0xF123` (bulk endpoints `0x01` out / `0x81` in).
- Custom or mock transports implementing `RadiacodeTransport` can be
  injected directly into `RadiacodeDevice` for deterministic offline testing.

Units note:
In `VS.DATA_BUF`'s `RealTimeData` records (`eid=0, gid=0`), `count_rate` is
reported directly in counts per second (`cps`), while `dose_rate` is in the
device protocol's internal Roentgen-derived scale where `10_000 * dose_rate`
equals microsieverts per hour (`uSv/h`).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import importlib
import re
import struct
import threading
import time
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from enum import IntEnum
from typing import Any, Protocol

from openrad.core.models import DeviceInfo, Reading, Spectrum
from openrad.devices.base import Device
from openrad.devices.registry import register

_WRITE_CHARACTERISTIC = "e63215e6-7003-49d8-96b0-b024798fb901"
_NOTIFY_CHARACTERISTIC = "e63215e7-7003-49d8-96b0-b024798fb901"
_BLE_WRITE_CHUNK_BYTES = 18

_USB_VID = 0x0483
_USB_PID = 0xF123
_USB_EP_OUT = 0x01
_USB_EP_IN = 0x81

_MAC_OR_UUID_RE = re.compile(
    r"^(([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}|"
    r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12})$"
)

# RadiaCode RealTimeData.dose_rate to uSv/h conversion factor (1e4).
DOSE_RATE_TO_USV_H = 10_000.0


class _Command(IntEnum):
    GET_STATUS = 0x0005
    SET_EXCHANGE = 0x0007
    GET_VERSION = 0x000A
    GET_SERIAL = 0x000B
    WR_VIRT_SFR = 0x0825
    RD_VIRT_STRING = 0x0826
    WR_VIRT_STRING = 0x0827
    SET_TIME = 0x0A04


class _VS(IntEnum):
    CONFIGURATION = 0x0002
    SERIAL_NUMBER = 0x0008
    DATA_BUF = 0x0100
    SPECTRUM = 0x0200
    ENERGY_CALIB = 0x0202
    SPEC_ACCUM = 0x0205


class _VSFR(IntEnum):
    DEVICE_TIME = 0x0504
    DOSE_RESET = 0x8007


class RadiacodeTransport(Protocol):
    """Low-level request/response transport for framed RadiaCode commands."""

    def execute(self, request: bytes) -> bytes:
        """Send a length-prefixed request and return the unprefixed response payload."""

    def close(self) -> None:
        """Release underlying transport resources."""


class _ByteReader:
    """Sequential binary reader over a byte buffer."""

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._pos = 0

    def remaining(self) -> int:
        return len(self._data) - self._pos

    def data(self) -> bytes:
        return self._data[self._pos :]

    def unpack(self, fmt: str) -> tuple[object, ...]:
        size = struct.calcsize(fmt)
        if self._pos + size > len(self._data):
            raise ValueError(
                f"need {size} bytes for {fmt!r}, only {self.remaining()} remaining"
            )
        values = struct.unpack_from(fmt, self._data, self._pos)
        self._pos += size
        return values

    def unpack_string(self) -> str:
        (length,) = self.unpack("<B")
        assert isinstance(length, int)
        (raw,) = self.unpack(f"<{length}s")
        assert isinstance(raw, bytes)
        return raw.decode("ascii", errors="replace")


def _parse_spec_format_version(config_text: str) -> int:
    """Extract SpecFormatVersion from the device's configuration text."""
    for line in config_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("SpecFormatVersion"):
            _, _, value = stripped.partition("=")
            try:
                return int(value.strip())
            except ValueError:
                return 0
    return 0


def _infer_model_from_serial(serial: str) -> str:
    """Derive a human-readable model label from a RadiaCode serial string."""
    parts = serial.strip().split("-")
    if len(parts) >= 2 and parts[0].upper() == "RC" and parts[1]:
        return f"RadiaCode-{parts[1]}"
    return "RadiaCode"


def decode_data_buf(
    data: bytes, base_time: datetime, *, ignore_errors: bool = True
) -> list[Reading]:
    """Decode a `VS.DATA_BUF` payload into chronological `Reading` objects.

    Walks all known record groups so the byte cursor stays aligned across
    mixed telemetry buffers, converting `GRP_RealTimeData` (`eid=0, gid=0`)
    records into `Reading` instances.
    """
    reader = _ByteReader(data)
    readings: list[Reading] = []
    next_seq: int | None = None

    while reader.remaining() >= 7:
        seq, eid, gid, ts_offset = reader.unpack("<BBBi")
        assert isinstance(seq, int)
        assert isinstance(eid, int)
        assert isinstance(gid, int)
        assert isinstance(ts_offset, int)

        if next_seq is not None and next_seq != seq:
            if not ignore_errors:
                raise ValueError(f"sequence jump in DATA_BUF: expected {next_seq}, got {seq}")
            break
        next_seq = (seq + 1) % 256

        timestamp = base_time + timedelta(milliseconds=ts_offset * 10)

        try:
            if eid == 0 and gid == 0:  # GRP_RealTimeData
                count_rate, dose_rate, _cr_err, _dr_err, _flags, _rt_flags = reader.unpack(
                    "<ffHHHB"
                )
                assert isinstance(count_rate, float)
                assert isinstance(dose_rate, float)
                readings.append(
                    Reading(
                        timestamp=timestamp,
                        cps=float(count_rate),
                        dose_rate=float(dose_rate) * DOSE_RATE_TO_USV_H,
                    )
                )
            elif eid == 0 and gid == 1:  # GRP_RawData
                reader.unpack("<ff")
            elif eid == 0 and gid == 2:  # GRP_DoseRateDB
                reader.unpack("<IffHH")
            elif eid == 0 and gid == 3:  # GRP_RareData
                reader.unpack("<IfHHH")
            elif eid == 0 and gid in {4, 5}:  # GRP_UserData / GRP_ScheduleData
                reader.unpack("<IffHH")
            elif eid == 0 and gid == 6:  # GRP_AccelData
                reader.unpack("<HHH")
            elif eid == 0 and gid == 7:  # GRP_Event
                reader.unpack("<BBH")
            elif eid == 0 and gid in {8, 9}:  # GRP_RawCountRate / GRP_RawDoseRate
                reader.unpack("<fH")
            elif eid == 1 and gid == 1:
                samples_num, _smpl_time_ms = reader.unpack("<HI")
                assert isinstance(samples_num, int)
                reader.unpack(f"<{8 * samples_num}x")
            elif eid == 1 and gid == 2:
                samples_num, _smpl_time_ms = reader.unpack("<HI")
                assert isinstance(samples_num, int)
                reader.unpack(f"<{16 * samples_num}x")
            elif eid == 1 and gid == 3:
                samples_num, _smpl_time_ms = reader.unpack("<HI")
                assert isinstance(samples_num, int)
                reader.unpack(f"<{14 * samples_num}x")
            else:
                if not ignore_errors:
                    raise ValueError(f"unknown DATA_BUF record type eid={eid} gid={gid}")
                break
        except ValueError:
            if not ignore_errors:
                raise
            break

    readings.sort(key=lambda r: r.timestamp)
    return readings


def _decode_counts_v0(reader: _ByteReader) -> list[int]:
    counts: list[int] = []
    while reader.remaining() > 0:
        (value,) = reader.unpack("<I")
        assert isinstance(value, int)
        counts.append(value)
    return counts


def _decode_counts_v1(reader: _ByteReader) -> list[int]:
    counts: list[int] = []
    last = 0
    while reader.remaining() > 0:
        (header,) = reader.unpack("<H")
        assert isinstance(header, int)
        run_length = (header >> 4) & 0x0FFF
        vlen = header & 0x0F
        for _ in range(run_length):
            if vlen == 0:
                value = 0
            elif vlen == 1:
                (byte_val,) = reader.unpack("<B")
                assert isinstance(byte_val, int)
                value = byte_val
            elif vlen == 2:
                (delta8,) = reader.unpack("<b")
                assert isinstance(delta8, int)
                value = last + delta8
            elif vlen == 3:
                (delta16,) = reader.unpack("<h")
                assert isinstance(delta16, int)
                value = last + delta16
            elif vlen == 4:
                b0, b1, b2_signed = reader.unpack("<BBb")
                assert isinstance(b0, int)
                assert isinstance(b1, int)
                assert isinstance(b2_signed, int)
                value = last + ((b2_signed << 16) | (b1 << 8) | b0)
            elif vlen == 5:
                (delta32,) = reader.unpack("<i")
                assert isinstance(delta32, int)
                value = last + delta32
            else:
                raise ValueError(f"unsupported vlen={vlen} in version 1 spectrum")
            last = value
            counts.append(value)
    return counts


def decode_spectrum(
    data: bytes,
    format_version: int = 1,
    *,
    start_time: datetime | None = None,
    name: str = "radiacode",
) -> Spectrum:
    """Decode a `VS.SPECTRUM` or `VS.SPEC_ACCUM` payload into a `Spectrum`."""
    if format_version not in {0, 1}:
        raise ValueError(f"unsupported spectrum format_version={format_version}")

    reader = _ByteReader(data)
    duration_s, a0, a1, a2 = reader.unpack("<Ifff")
    assert isinstance(duration_s, int)
    assert isinstance(a0, float)
    assert isinstance(a1, float)
    assert isinstance(a2, float)

    counts = _decode_counts_v0(reader) if format_version == 0 else _decode_counts_v1(reader)
    measured_at = start_time or datetime.now(timezone.utc)
    return Spectrum(
        counts=counts,
        live_time_s=float(duration_s),
        real_time_s=float(duration_s),
        start_time=measured_at,
        calibration=(float(a0), float(a1), float(a2)),
        name=name,
    )


async def _resolve_ble_address(address_or_name: str, timeout: float = 10.0) -> str:
    """Return a BLE MAC/UUID directly or scan for a matching advertised name."""
    if _MAC_OR_UUID_RE.match(address_or_name):
        return address_or_name

    from bleak import BleakScanner

    devices = await BleakScanner.discover(timeout=timeout)
    matches = [d for d in devices if d.name and address_or_name.lower() in d.name.lower()]
    if not matches:
        raise ConnectionError(f"no BLE device found matching {address_or_name!r}")
    return matches[0].address


def reassemble_ble_notifications(chunks: list[bytes]) -> bytes:
    """Reassemble a length-prefixed RadiaCode BLE response from GATT chunks."""
    if not chunks:
        raise ValueError("cannot reassemble empty notification list")

    first = chunks[0]
    if len(first) < 4:
        raise ValueError("first BLE notification chunk is shorter than 4-byte length header")

    (expected_len,) = struct.unpack_from("<i", first, 0)
    if expected_len < 0:
        raise ValueError(f"invalid negative BLE response length: {expected_len}")

    payload = bytearray(first[4:])
    for chunk in chunks[1:]:
        payload.extend(chunk)

    if len(payload) != expected_len:
        raise ValueError(
            f"reassembled BLE payload length {len(payload)} != expected {expected_len}"
        )
    return bytes(payload)


class _BleTransport:
    """Bleak-backed synchronous request/response transport for RadiaCode over BLE."""

    def __init__(self, address_or_name: str, *, connect_timeout: float = 30.0) -> None:
        try:
            import bleak  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                'RadiacodeDevice over BLE needs the "ble" extra: uv sync --extra ble '
                '(or pip install "openrad[ble]")'
            ) from exc

        self.address_or_name = address_or_name
        self.resolved_address: str = address_or_name
        self._resp_buffer = bytearray()
        self._resp_remaining = 0
        self._response: bytes | None = None
        self._closing = False
        self._connection_lost = False
        self._cond = threading.Condition()
        self._exec_lock = threading.Lock()
        self._loop = asyncio.new_event_loop()
        self._loop_ready = threading.Event()
        self._thread = threading.Thread(
            target=self._run_event_loop, name="openrad-radiacode-ble", daemon=True
        )
        self._thread.start()
        self._loop_ready.wait()
        self._client: object | None = None

        try:
            self._run(self._connect(), timeout=connect_timeout)
        except BaseException:
            self.close()
            raise

    def _run_event_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop_ready.set()
        try:
            self._loop.run_forever()
        finally:
            pending = asyncio.all_tasks(self._loop)
            for task in pending:
                task.cancel()
            if pending:
                self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            self._loop.run_until_complete(self._loop.shutdown_asyncgens())
            self._loop.close()

    def _run(self, coro: object, timeout: float) -> object:
        assert asyncio.iscoroutine(coro)
        future: concurrent.futures.Future[object] = asyncio.run_coroutine_threadsafe(
            coro, self._loop
        )
        try:
            return future.result(timeout)
        except BaseException:
            future.cancel()
            raise

    async def _connect(self) -> None:
        from bleak import BleakClient

        self.resolved_address = await _resolve_ble_address(self.address_or_name)
        client = BleakClient(self.resolved_address, disconnected_callback=self._on_disconnect)
        await client.connect()
        await client.start_notify(_NOTIFY_CHARACTERISTIC, self._on_notify)
        self._client = client

    def _on_disconnect(self, _client: object) -> None:
        with self._cond:
            self._connection_lost = True
            self._cond.notify_all()

    def _on_notify(self, _sender: object, data: bytearray) -> None:
        raw = bytes(data)
        with self._cond:
            if self._resp_remaining == 0:
                if len(raw) < 4:
                    return
                (payload_len,) = struct.unpack_from("<i", raw, 0)
                self._resp_remaining = 4 + payload_len
                self._resp_buffer = bytearray(raw[4:])
            else:
                self._resp_buffer.extend(raw)

            self._resp_remaining -= len(raw)
            if self._resp_remaining <= 0:
                self._response = bytes(self._resp_buffer)
                self._resp_buffer.clear()
                self._resp_remaining = 0
                self._cond.notify_all()

    async def _write(self, request: bytes) -> None:
        from bleak import BleakClient

        assert isinstance(self._client, BleakClient)
        for pos in range(0, len(request), _BLE_WRITE_CHUNK_BYTES):
            chunk = request[pos : pos + _BLE_WRITE_CHUNK_BYTES]
            await self._client.write_gatt_char(_WRITE_CHARACTERISTIC, chunk, response=False)

    def execute(self, request: bytes, timeout: float = 10.0) -> bytes:
        with self._exec_lock:
            if self._closing or self._connection_lost:
                raise ConnectionError("RadiaCode BLE connection is closed")

            with self._cond:
                self._resp_buffer.clear()
                self._resp_remaining = 0
                self._response = None

            deadline = time.monotonic() + timeout
            self._run(self._write(request), timeout=timeout)

            with self._cond:
                while self._response is None and not self._closing and not self._connection_lost:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("timed out waiting for RadiaCode BLE response")
                    self._cond.wait(remaining)

                if self._closing or self._connection_lost or self._response is None:
                    raise ConnectionError("RadiaCode BLE connection lost while awaiting response")

                result = self._response
                self._response = None
                return result

    def close(self) -> None:
        if self._closing:
            return
        self._closing = True

        with self._cond:
            self._cond.notify_all()

        if self._client is not None and self._loop.is_running():
            from bleak import BleakClient

            if isinstance(self._client, BleakClient):
                try:
                    self._run(self._client.disconnect(), timeout=5.0)
                except Exception:  # noqa: BLE001
                    pass
            self._client = None

        if self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(timeout=5.0)


class _UsbTransport:
    """pyusb-backed synchronous request/response transport for RadiaCode over USB."""

    def __init__(self, serial_number: str | None = None, *, timeout_ms: int = 3000) -> None:
        try:
            usb_core: Any = importlib.import_module("usb.core")
            usb_util: Any = importlib.import_module("usb.util")
        except ImportError as exc:
            raise ImportError(
                'RadiacodeDevice over USB needs pyusb: pip install "pyusb>=1.2"'
            ) from exc

        self._usb_core = usb_core
        self._usb_util = usb_util
        self._timeout_ms = timeout_ms

        if serial_number is not None:
            device = usb_core.find(
                idVendor=_USB_VID, idProduct=_USB_PID, serial_number=serial_number
            )
        else:
            device = usb_core.find(idVendor=_USB_VID, idProduct=_USB_PID)

        if device is None:
            target = f" (serial={serial_number!r})" if serial_number else ""
            raise ConnectionError(f"no RadiaCode USB device found{target}")

        self._device: Any = device
        # Drain any stale bulk-IN packets left in the endpoint buffer.
        while True:
            try:
                self._device.read(_USB_EP_IN, 256, timeout=100)
            except usb_core.USBTimeoutError:
                break

    def execute(self, request: bytes) -> bytes:
        if self._device is None:
            raise ConnectionError("RadiaCode USB connection is closed")

        self._device.write(_USB_EP_OUT, request)

        data = b""
        for _ in range(3):
            raw = self._device.read(_USB_EP_IN, 256, timeout=self._timeout_ms).tobytes()
            if raw:
                data = bytes(raw)
                break
        if not data:
            raise TimeoutError("no data received from RadiaCode USB endpoint")

        (response_length,) = struct.unpack_from("<I", data, 0)
        payload = bytearray(data[4:])
        while len(payload) < response_length:
            more = self._device.read(
                _USB_EP_IN, response_length - len(payload), timeout=self._timeout_ms
            ).tobytes()
            payload.extend(more)
        return bytes(payload[:response_length])

    def close(self) -> None:
        if self._device is not None:
            self._usb_util.dispose_resources(self._device)
            self._device = None


@register("radiacode")
class RadiacodeDevice(Device):
    """Streams live `Reading`s and reads gamma `Spectrum`s from a RadiaCode RC-10x."""

    def __init__(
        self,
        bluetooth_mac: str | None = None,
        *,
        serial_number: str | None = None,
        poll_interval_s: float = 1.0,
        accumulated_spectrum: bool = False,
        ignore_firmware_check: bool = False,
        transport: RadiacodeTransport | None = None,
    ) -> None:
        self.bluetooth_mac = bluetooth_mac
        self.serial_number = serial_number
        self.poll_interval_s = poll_interval_s
        self.accumulated_spectrum = accumulated_spectrum
        self.ignore_firmware_check = ignore_firmware_check
        self._transport: RadiacodeTransport | None = transport
        self._owns_transport = transport is None
        self._seq = 0
        self._base_time: datetime = datetime.now(timezone.utc)
        self._spectrum_format_version = 1
        self._last_reading_ts: datetime | None = None
        self._connected = False

    def connect(self) -> DeviceInfo:
        if self._transport is None:
            if self.bluetooth_mac is not None:
                self._transport = _BleTransport(self.bluetooth_mac)
            else:
                self._transport = _UsbTransport(serial_number=self.serial_number)
            self._owns_transport = True

        try:
            self._execute(_Command.SET_EXCHANGE, b"\x01\xff\x12\xff")
            now_local = datetime.now()
            self._set_local_time(now_local)
            self._write_vsfr(_VSFR.DEVICE_TIME, struct.pack("<I", 0))
            self._base_time = datetime.now(timezone.utc) + timedelta(seconds=128)

            _boot_ver, (target_major, target_minor, _target_date) = self._fw_version()
            if not self.ignore_firmware_check and (
                target_major < 4 or (target_major == 4 and target_minor < 8)
            ):
                raise RuntimeError(
                    f"RadiaCode firmware {target_major}.{target_minor} is older than 4.8; "
                    "upgrade firmware or pass ignore_firmware_check=True"
                )

            config_bytes = self._read_vs(_VS.CONFIGURATION).data()
            config_text = config_bytes.decode("cp1251", errors="replace")
            self._spectrum_format_version = _parse_spec_format_version(config_text)

            serial_bytes = self._read_vs(_VS.SERIAL_NUMBER).data()
            serial = serial_bytes.decode("ascii", errors="replace").strip("\x00").strip()
            if not serial:
                serial = self._hw_serial_number()

            model = _infer_model_from_serial(serial)
            self._connected = True
            return DeviceInfo(
                driver="radiacode",
                model=model,
                serial=serial or None,
                firmware=f"{target_major}.{target_minor}",
            )
        except BaseException:
            self.disconnect()
            raise

    def disconnect(self) -> None:
        self._connected = False
        if self._transport is not None and self._owns_transport:
            self._transport.close()
            self._transport = None

    def stream(self) -> Iterator[Reading]:
        if not self._connected or self._transport is None:
            raise RuntimeError("stream() called before connect()")

        while self._connected and self._transport is not None:
            raw_buf = self._read_vs(_VS.DATA_BUF).data()
            readings = decode_data_buf(raw_buf, self._base_time)
            for reading in readings:
                if self._last_reading_ts is None or reading.timestamp > self._last_reading_ts:
                    self._last_reading_ts = reading.timestamp
                    yield reading
            if self.poll_interval_s > 0:
                time.sleep(self.poll_interval_s)

    def read_spectrum(self) -> Spectrum | None:
        if not self._connected or self._transport is None:
            raise RuntimeError("read_spectrum() called before connect()")

        vs_id = _VS.SPEC_ACCUM if self.accumulated_spectrum else _VS.SPECTRUM
        raw_spec = self._read_vs(vs_id).data()
        return decode_spectrum(
            raw_spec,
            self._spectrum_format_version,
            start_time=datetime.now(timezone.utc),
            name="radiacode-accum" if self.accumulated_spectrum else "radiacode",
        )

    def reset_spectrum(self) -> None:
        """Clear the device's current on-board spectrum buffer."""
        if not self._connected or self._transport is None:
            raise RuntimeError("reset_spectrum() called before connect()")
        resp = self._execute(_Command.WR_VIRT_STRING, struct.pack("<II", int(_VS.SPECTRUM), 0))
        (retcode,) = resp.unpack("<I")
        if retcode != 1:
            raise RuntimeError(f"WR_VIRT_STRING(SPECTRUM) failed with retcode={retcode}")

    def reset_dose(self) -> None:
        """Reset the device's accumulated dose counter."""
        if not self._connected or self._transport is None:
            raise RuntimeError("reset_dose() called before connect()")
        self._write_vsfr(_VSFR.DOSE_RESET)

    def _execute(self, command: _Command, args: bytes = b"") -> _ByteReader:
        if self._transport is None:
            raise RuntimeError("transport is not connected")

        req_seq_no = 0x80 + self._seq
        self._seq = (self._seq + 1) % 32

        req_header = struct.pack("<HBB", int(command), 0, req_seq_no)
        body = req_header + args
        framed = struct.pack("<I", len(body)) + body

        response_bytes = self._transport.execute(framed)
        reader = _ByteReader(response_bytes)
        (resp_header,) = reader.unpack("<4s")
        if resp_header != req_header:
            assert isinstance(resp_header, bytes)
            raise RuntimeError(
                f"command header mismatch: sent {req_header.hex()}, got {resp_header.hex()}"
            )
        return reader

    def _read_vs(self, vs_id: _VS) -> _ByteReader:
        reader = self._execute(_Command.RD_VIRT_STRING, struct.pack("<I", int(vs_id)))
        retcode, flen = reader.unpack("<II")
        assert isinstance(retcode, int)
        assert isinstance(flen, int)
        if retcode != 1:
            raise RuntimeError(f"RD_VIRT_STRING({vs_id.name}) failed with retcode={retcode}")

        payload = reader.data()
        # Firmware quirk: some versions append an extra trailing NUL byte not counted in flen.
        if len(payload) == flen + 1 and payload[-1] == 0x00:
            payload = payload[:-1]
        if len(payload) != flen:
            raise RuntimeError(
                f"RD_VIRT_STRING({vs_id.name}) length mismatch: got {len(payload)}, expected {flen}"
            )
        return _ByteReader(payload)

    def _write_vsfr(self, vsfr_id: _VSFR, data: bytes = b"") -> None:
        reader = self._execute(_Command.WR_VIRT_SFR, struct.pack("<I", int(vsfr_id)) + data)
        (retcode,) = reader.unpack("<I")
        if retcode != 1:
            raise RuntimeError(f"WR_VIRT_SFR({vsfr_id.name}) failed with retcode={retcode}")

    def _set_local_time(self, dt: datetime) -> None:
        payload = struct.pack(
            "<BBBBBBBB",
            dt.day,
            dt.month,
            max(0, dt.year - 2000),
            0,
            dt.second,
            dt.minute,
            dt.hour,
            0,
        )
        self._execute(_Command.SET_TIME, payload)

    def _fw_version(self) -> tuple[tuple[int, int, str], tuple[int, int, str]]:
        reader = self._execute(_Command.GET_VERSION)
        boot_minor, boot_major = reader.unpack("<HH")
        boot_date = reader.unpack_string()
        target_minor, target_major = reader.unpack("<HH")
        target_date = reader.unpack_string().strip("\x00")
        assert isinstance(boot_major, int)
        assert isinstance(boot_minor, int)
        assert isinstance(target_major, int)
        assert isinstance(target_minor, int)
        return (
            (boot_major, boot_minor, boot_date),
            (target_major, target_minor, target_date),
        )

    def _hw_serial_number(self) -> str:
        reader = self._execute(_Command.GET_SERIAL)
        (serial_len,) = reader.unpack("<I")
        assert isinstance(serial_len, int)
        groups = []
        for _ in range(serial_len // 4):
            (word,) = reader.unpack("<I")
            assert isinstance(word, int)
            groups.append(f"{word:08X}")
        return "-".join(groups)

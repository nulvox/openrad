from __future__ import annotations

import asyncio
import struct
from datetime import datetime, timedelta, timezone

import pytest
from typer.testing import CliRunner

from openrad.cli.main import app
from openrad.devices.radiacode import (
    _VS,
    _VSFR,
    DOSE_RATE_TO_USV_H,
    RadiacodeDevice,
    _Command,
    _infer_model_from_serial,
    _parse_spec_format_version,
    _resolve_ble_address,
    decode_data_buf,
    decode_spectrum,
    reassemble_ble_notifications,
)


def _pack_realtime_record(
    seq: int, ts_offset_10ms: int, count_rate: float, dose_rate_raw: float
) -> bytes:
    header = struct.pack("<BBBi", seq, 0, 0, ts_offset_10ms)
    body = struct.pack("<ffHHHB", count_rate, dose_rate_raw, 50, 40, 0, 0)
    return header + body


def test_decode_data_buf_realtime_and_mixed_records() -> None:
    base_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Record 0: RealTimeData at +1.0s
    rec0 = _pack_realtime_record(seq=10, ts_offset_10ms=100, count_rate=8.5, dose_rate_raw=0.000015)
    # Record 1: RawData (eid=0, gid=1) at +1.5s — should be skipped cleanly without losing alignment
    rec1 = struct.pack("<BBBi", 11, 0, 1, 150) + struct.pack("<ff", 9.0, 0.000016)
    # Record 2: RareData (eid=0, gid=3) at +1.8s
    rec2 = struct.pack("<BBBi", 12, 0, 3, 180) + struct.pack("<IfHHH", 3600, 0.001, 4500, 8500, 0)
    # Record 3: Event (eid=0, gid=7) at +1.9s
    rec3 = struct.pack("<BBBi", 13, 0, 7, 190) + struct.pack("<BBH", 19, 0, 0)
    # Record 4: RealTimeData at +2.0s
    rec4 = _pack_realtime_record(
        seq=14, ts_offset_10ms=200, count_rate=12.25, dose_rate_raw=0.000024
    )

    readings = decode_data_buf(rec0 + rec1 + rec2 + rec3 + rec4, base_time)

    assert len(readings) == 2
    assert readings[0].timestamp == base_time + timedelta(seconds=1)
    assert readings[0].cps == pytest.approx(8.5)
    assert readings[0].dose_rate == pytest.approx(0.000015 * DOSE_RATE_TO_USV_H)

    assert readings[1].timestamp == base_time + timedelta(seconds=2)
    assert readings[1].cps == pytest.approx(12.25)
    assert readings[1].dose_rate == pytest.approx(0.000024 * DOSE_RATE_TO_USV_H)


def test_decode_data_buf_sequence_jump_stops_or_raises() -> None:
    base_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    rec0 = _pack_realtime_record(seq=1, ts_offset_10ms=100, count_rate=5.0, dose_rate_raw=0.00001)
    rec_gap = _pack_realtime_record(
        seq=3, ts_offset_10ms=200, count_rate=6.0, dose_rate_raw=0.00001
    )

    readings = decode_data_buf(rec0 + rec_gap, base_time, ignore_errors=True)
    assert len(readings) == 1

    with pytest.raises(ValueError, match="sequence jump"):
        decode_data_buf(rec0 + rec_gap, base_time, ignore_errors=False)


def test_decode_spectrum_v0_uncompressed() -> None:
    header = struct.pack("<Ifff", 300, -5.0, 2.5, 0.0001)
    counts_bytes = struct.pack("<4I", 0, 12, 45, 7)

    spectrum = decode_spectrum(header + counts_bytes, format_version=0, name="rc-v0")

    assert spectrum.name == "rc-v0"
    assert spectrum.live_time_s == 300.0
    assert spectrum.real_time_s == 300.0
    assert spectrum.calibration == pytest.approx((-5.0, 2.5, 0.0001))
    assert spectrum.counts == [0, 12, 45, 7]


def test_decode_spectrum_v1_compressed_all_vlens() -> None:
    header = struct.pack("<Ifff", 120, 0.0, 3.0, 0.0)

    # Pack one run of each vlen (0..5):
    # 1) vlen=0, count=2 -> [0, 0]
    op_v0 = struct.pack("<H", (2 << 4) | 0)
    # 2) vlen=1 (uint8), count=2 -> [10, 250]
    op_v1 = struct.pack("<HBB", (2 << 4) | 1, 10, 250)
    # 3) vlen=2 (int8 delta from 250), count=2 -> [245, 255]
    op_v2 = struct.pack("<Hbb", (2 << 4) | 2, -5, 10)
    # 4) vlen=3 (int16 delta from 255), count=1 -> [1255]
    op_v3 = struct.pack("<Hh", (1 << 4) | 3, 1000)
    # 5) vlen=4 (int24 delta from 1255: +70000 = 0x011170), count=1 -> [71255]
    op_v4 = struct.pack("<HBBb", (1 << 4) | 4, 0x70, 0x11, 0x01)
    # 6) vlen=5 (int32 delta from 71255: -70000), count=1 -> [1255]
    op_v5 = struct.pack("<Hi", (1 << 4) | 5, -70000)

    payload = header + op_v0 + op_v1 + op_v2 + op_v3 + op_v4 + op_v5
    spectrum = decode_spectrum(payload, format_version=1)

    assert spectrum.counts == [0, 0, 10, 250, 245, 255, 1255, 71255, 1255]
    assert spectrum.live_time_s == 120.0


def test_reassemble_ble_notifications_across_chunks() -> None:
    body = b"0123456789abcdefABCDEF"
    framed = struct.pack("<i", len(body)) + body
    chunks = [framed[:10], framed[10:18], framed[18:]]

    assert reassemble_ble_notifications(chunks) == body


def test_resolve_ble_address_passes_through_mac_and_uuid() -> None:
    mac = "52:43:01:02:03:04"
    uuid = "12345678-1234-1234-1234-123456789abc"
    assert asyncio.run(_resolve_ble_address(mac)) == mac
    assert asyncio.run(_resolve_ble_address(uuid)) == uuid


def test_helpers_parse_config_and_serial_model() -> None:
    config = "SomeKey=1\r\nSpecFormatVersion=1\r\nOther=2\r\n"
    assert _parse_spec_format_version(config) == 1
    assert _parse_spec_format_version("NoVersionHere=1") == 0
    assert _infer_model_from_serial("RC-102-001234") == "RadiaCode-102"
    assert _infer_model_from_serial("RC-103G-009876") == "RadiaCode-103G"
    assert _infer_model_from_serial("UNKNOWN") == "RadiaCode"


class _FakeRadiacodeTransport:
    """In-memory fake implementing `RadiacodeTransport` for end-to-end driver tests."""

    def __init__(self, *, fw_major: int = 4, fw_minor: int = 9) -> None:
        self.fw_major = fw_major
        self.fw_minor = fw_minor
        self.closed = False
        self.commands_seen: list[int] = []
        self.vs_writes: list[tuple[int, bytes]] = []
        self.vsfr_writes: list[tuple[int, bytes]] = []
        self._poll_count = 0
        self.device: RadiacodeDevice | None = None

    def close(self) -> None:
        self.closed = True

    def execute(self, request: bytes) -> bytes:
        (body_len,) = struct.unpack_from("<I", request, 0)
        body = request[4:]
        assert len(body) == body_len

        cmd, _zero, _seq = struct.unpack_from("<HBB", body, 0)
        req_header = body[:4]
        args = body[4:]
        self.commands_seen.append(cmd)

        if cmd in {_Command.SET_EXCHANGE, _Command.SET_TIME}:
            return req_header

        if cmd == _Command.WR_VIRT_SFR:
            (vsfr_id,) = struct.unpack_from("<I", args, 0)
            self.vsfr_writes.append((vsfr_id, args[4:]))
            return req_header + struct.pack("<I", 1)

        if cmd == _Command.WR_VIRT_STRING:
            vs_id, data_len = struct.unpack_from("<II", args, 0)
            self.vs_writes.append((vs_id, args[8 : 8 + data_len]))
            return req_header + struct.pack("<I", 1)

        if cmd == _Command.GET_VERSION:
            boot_date = b"Jan 01 2024"
            target_date = b"Feb 15 2025\x00"
            payload = (
                struct.pack("<HHB", 1, 3, len(boot_date))
                + boot_date
                + struct.pack("<HHB", self.fw_minor, self.fw_major, len(target_date))
                + target_date
            )
            return req_header + payload

        if cmd == _Command.RD_VIRT_STRING:
            (vs_id,) = struct.unpack_from("<I", args, 0)
            if vs_id == _VS.CONFIGURATION:
                cfg = b"SpecFormatVersion=0\r\n"
                # Include the extra trailing NUL byte quirk to verify workaround
                return req_header + struct.pack("<II", 1, len(cfg)) + cfg + b"\x00"
            if vs_id == _VS.SERIAL_NUMBER:
                serial = b"RC-103-004242"
                return req_header + struct.pack("<II", 1, len(serial)) + serial
            if vs_id == _VS.DATA_BUF:
                self._poll_count += 1
                rec1 = _pack_realtime_record(
                    seq=1, ts_offset_10ms=100, count_rate=6.0, dose_rate_raw=0.000012
                )
                rec2 = _pack_realtime_record(
                    seq=2, ts_offset_10ms=200, count_rate=7.5, dose_rate_raw=0.000015
                )
                buf = rec1 + rec2
                # Stop the device after the first poll so stream() terminates in the test
                if self.device is not None:
                    self.device._connected = False
                return req_header + struct.pack("<II", 1, len(buf)) + buf
            if vs_id in {_VS.SPECTRUM, _VS.SPEC_ACCUM}:
                spec = struct.pack("<Ifff3I", 60, 0.0, 3.0, 0.0, 5, 15, 2)
                return req_header + struct.pack("<II", 1, len(spec)) + spec

        raise AssertionError(f"unexpected command {cmd:#x}")


def test_radiacode_device_connect_stream_and_spectrum() -> None:
    transport = _FakeRadiacodeTransport()
    device = RadiacodeDevice(poll_interval_s=0.0, transport=transport)
    transport.device = device

    info = device.connect()
    assert info.driver == "radiacode"
    assert info.model == "RadiaCode-103"
    assert info.serial == "RC-103-004242"
    assert info.firmware == "4.9"

    spectrum = device.read_spectrum()
    assert spectrum is not None
    assert spectrum.counts == [5, 15, 2]
    assert spectrum.calibration == (0.0, 3.0, 0.0)

    device.reset_spectrum()
    assert (int(_VS.SPECTRUM), b"") in transport.vs_writes

    device.reset_dose()
    assert any(vsfr_id == int(_VSFR.DOSE_RESET) for vsfr_id, _ in transport.vsfr_writes)

    readings = list(device.stream())
    assert len(readings) == 2
    assert readings[0].cps == pytest.approx(6.0)
    assert readings[0].dose_rate == pytest.approx(0.12)
    assert readings[1].cps == pytest.approx(7.5)
    assert readings[1].dose_rate == pytest.approx(0.15)


def test_radiacode_device_rejects_old_firmware_by_default() -> None:
    transport = _FakeRadiacodeTransport(fw_major=4, fw_minor=7)
    device = RadiacodeDevice(transport=transport)

    with pytest.raises(RuntimeError, match="older than 4.8"):
        device.connect()


def test_cli_devices_lists_radiacode() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["devices"])
    assert result.exit_code == 0
    assert "- radiacode" in result.output

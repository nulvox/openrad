from __future__ import annotations

import asyncio
from datetime import datetime

from openrad.devices.ct007n import _compute_reading, _decode_ascii, _decode_count, _resolve_address


def test_decode_count_little_endian() -> None:
    assert _decode_count(bytes([0x01, 0x00, 0x00, 0x00])) == 1
    assert _decode_count(bytes([0x04, 0x00, 0x00, 0x00])) == 4
    assert _decode_count(bytearray([0x00, 0x01, 0x00, 0x00])) == 256


def test_decode_count_ignores_trailing_bytes() -> None:
    assert _decode_count(bytes([0x02, 0x00, 0x00, 0x00, 0xff, 0xff])) == 2


def test_decode_ascii_strips_whitespace() -> None:
    assert _decode_ascii(b"  BLE-1.4.2.2  ") == "BLE-1.4.2.2"


def test_compute_reading_derives_cps_from_elapsed_time() -> None:
    timestamp = datetime(2026, 1, 1, 0, 0, 0)
    reading = _compute_reading(3, 0.5, counts_per_usv=None, timestamp=timestamp)

    assert reading.cps == 6.0
    assert reading.timestamp == timestamp


def test_compute_reading_dose_rate_zero_without_conversion_factor() -> None:
    reading = _compute_reading(10, 1.0, counts_per_usv=None, timestamp=datetime.now())

    assert reading.dose_rate == 0.0


def test_compute_reading_applies_conversion_factor() -> None:
    # 10 cps, 3600 counts_per_usv -> 10 * 3600 / 3600 = 10 uSv/h
    reading = _compute_reading(10, 1.0, counts_per_usv=3600.0, timestamp=datetime.now())

    assert reading.dose_rate == 10.0


def test_compute_reading_zero_elapsed_does_not_divide_by_zero() -> None:
    reading = _compute_reading(5, 0.0, counts_per_usv=None, timestamp=datetime.now())

    assert reading.cps == 0.0


def test_resolve_address_passes_through_mac_without_scanning() -> None:
    address = asyncio.run(_resolve_address("34:15:13:E4:78:29"))

    assert address == "34:15:13:E4:78:29"

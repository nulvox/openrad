"""Discover a nearby BLE device and dump its GATT services + live notifications.

This is a reverse-engineering aid, not a finished driver. openrad doesn't
have public protocol documentation for the CT007-N (NanoNuke): GammaGuard's
BLE protocol is proprietary, its user's manual and datasheet contain no
technical/wire-format details, and — unlike RadiaCode, whose protocol the
community already reverse-engineered (see docs/ARCHITECTURE.md) — no public
CT007-N reverse-engineering effort turned up in a search either. So instead
of guessing, this script connects to the real device and reports exactly
what it exposes, which is the input a real devices/ct007n.py parser needs.

Usage:
    uv run python scripts/ble_explore.py "CT-N-13"
    uv run python scripts/ble_explore.py "CT-N-13" --seconds 120

Let the device count for a while after it connects (or press its button,
per the manual: short press toggles its local screen) so the notification
dump captures real reading updates, not just idle traffic.

Requires the "ble" extra: uv sync --extra ble (or pip install "openrad[ble]").
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime

from bleak import BleakClient, BleakScanner


async def _scan(name_match: str, timeout: float) -> str:
    print(f"Scanning for BLE devices matching {name_match!r} ({timeout:.0f}s)...")
    devices = await BleakScanner.discover(timeout=timeout)
    matches = [d for d in devices if d.name and name_match.lower() in d.name.lower()]

    if not matches:
        print("No matching devices found. Nearby devices seen:")
        for device in devices:
            print(f"  {device.address}  {device.name!r}")
        raise SystemExit(1)

    for device in matches:
        print(f"  found: {device.name}  {device.address}")
    return matches[0].address


def _on_notify(char_uuid: str, char_description: str):
    def _handler(_sender: object, data: bytearray) -> None:
        now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{now}] {char_uuid} ({char_description}): {data.hex(' ')}  ({len(data)} bytes)")

    return _handler


async def _dump(address: str, seconds: float) -> None:
    async with BleakClient(address) as client:
        print(f"\nConnected to {address}\n")
        print("Services and characteristics:")

        notifiable: list[tuple[str, str]] = []
        for service in client.services:
            print(f"  service {service.uuid}  ({service.description})")
            for char in service.characteristics:
                props = ",".join(char.properties)
                print(f"    char {char.uuid}  [{props}]  ({char.description})")

                if "read" in char.properties:
                    try:
                        value = await client.read_gatt_char(char.uuid)
                        print(f"      current value: {value.hex(' ')}  (ascii: {value!r})")
                    except Exception as exc:  # noqa: BLE001 - reporting, not handling
                        print(f"      read failed: {exc}")

                if "notify" in char.properties or "indicate" in char.properties:
                    notifiable.append((char.uuid, char.description))

        if not notifiable:
            print("\nNo notify/indicate characteristics found — nothing to subscribe to.")
            return

        print(f"\nSubscribing to {len(notifiable)} characteristic(s) for {seconds:.0f}s...")
        print("(let the device count, or press its button, to generate traffic)\n")
        for uuid, description in notifiable:
            await client.start_notify(uuid, _on_notify(uuid, description))

        await asyncio.sleep(seconds)

        for uuid, _description in notifiable:
            await client.stop_notify(uuid)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="Substring to match against the device's advertised name")
    parser.add_argument("--scan-timeout", type=float, default=10.0, help="Scan duration, seconds")
    parser.add_argument(
        "--seconds", type=float, default=60.0, help="How long to watch notifications"
    )
    args = parser.parse_args()

    address = asyncio.run(_scan(args.name, args.scan_timeout))
    asyncio.run(_dump(address, args.seconds))


if __name__ == "__main__":
    main()

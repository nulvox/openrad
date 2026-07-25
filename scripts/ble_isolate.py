"""Subscribe to exactly one BLE characteristic and time how long it survives.

Isolation tool for the CT007-N shutoff investigation: the full driver
(devices/ct007n.py) reads two Device Information characteristics and then
subscribes to the count-notify characteristic, and the device powers off
around ~30s in. A console-only session (ble_console.py) that never touches
the count characteristic ran 90+s without dying. This script subscribes to
just one named characteristic — no other reads, no other subscriptions —
so we can test each suspect in isolation and find out which one (if any)
is actually responsible.

Usage:
    uv run python scripts/ble_isolate.py "CT-N-13" f100ffd1-0451-4100-b100-000000000000

Runs until the device disconnects or Ctrl-C, printing a timestamp and
elapsed time for every notification plus the final elapsed time on exit.

Requires the "ble" extra: uv sync --extra ble.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from datetime import datetime


async def _scan(name_match: str, timeout: float) -> str:
    from bleak import BleakScanner

    print(f"Scanning for BLE devices matching {name_match!r} ({timeout:.0f}s)...")
    devices = await BleakScanner.discover(timeout=timeout)
    matches = [d for d in devices if d.name and name_match.lower() in d.name.lower()]
    if not matches:
        raise SystemExit(f"no device found matching {name_match!r}")
    print(f"  found: {matches[0].name}  {matches[0].address}")
    return matches[0].address


async def _run(address: str, characteristic: str) -> None:
    from bleak import BleakClient

    start = time.monotonic()
    disconnected = asyncio.Event()

    def _on_disconnect(_client: object) -> None:
        elapsed = time.monotonic() - start
        print(f"\n!!! device disconnected after {elapsed:.1f}s !!!")
        disconnected.set()

    def _on_notify(_sender: object, data: bytearray) -> None:
        now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        elapsed = time.monotonic() - start
        print(f"[{now}] (+{elapsed:5.1f}s) {data.hex(' ')}  ({len(data)} bytes)")

    async with BleakClient(address, disconnected_callback=_on_disconnect) as client:
        print(f"Connected to {address}. Subscribing to only {characteristic}.\n")
        await client.start_notify(characteristic, _on_notify)
        print("Watching. Ctrl-C to stop early.\n")

        try:
            await disconnected.wait()
        except KeyboardInterrupt:
            elapsed = time.monotonic() - start
            print(f"\nStopped by user after {elapsed:.1f}s (still connected).")
            if client.is_connected:
                await client.stop_notify(characteristic)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="Substring to match against the device's advertised name")
    parser.add_argument("characteristic", help="UUID of the single characteristic to subscribe to")
    parser.add_argument("--scan-timeout", type=float, default=10.0, help="Scan duration, seconds")
    args = parser.parse_args()

    address = asyncio.run(_scan(args.name, args.scan_timeout))
    asyncio.run(_run(address, args.characteristic))


if __name__ == "__main__":
    main()

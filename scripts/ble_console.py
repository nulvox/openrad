"""Interactively probe the CT007-N's debug console over BLE — carefully.

Reverse-engineering aid, not a firmware tool. The CT007-N exposes a custom
service (25fb9e91-.../.../...) that streams a boot banner on connect
("BotSpine.../OAD v0.11.../1816 bytes free.\\nOK\\n") — it reads like an
interactive text console (a ready-prompt, not a binary transfer), reachable
in normal connected mode. This script lets you type one line of ASCII text
at a time to its write characteristic and watch whatever comes back on its
paired notify characteristic, so you can probe what commands (if any) it
expects — the way you'd poke an unfamiliar serial console on a dev board.

It deliberately does NOT implement any binary/OAD block-transfer protocol,
and never sends anything you didn't type yourself. Go slowly:
  1. Send a blank line first — the most harmless possible probe.
  2. Try short, obviously-text commands one at a time: "help", "?", "status".
  3. Read every response before sending the next line.
  4. If anything mentions erase/flash/update/confirm or looks like it wants
     you to proceed with an operation, STOP and don't confirm anything —
     that's the boundary between "poking a console" and "starting a
     firmware operation," which this tool is not meant to cross.

Usage:
    uv run python scripts/ble_console.py "CT-N-13"

Requires the "ble" extra: uv sync --extra ble (or pip install "openrad[ble]").
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime

_CONSOLE_WRITE_CHARACTERISTIC = "d6af9b3c-fe92-1cb2-f74b-7afb7de57e6d"
_CONSOLE_NOTIFY_CHARACTERISTIC = "c3fbc9e2-676b-9fb5-3749-2f471dcf07b2"


async def _scan(name_match: str, timeout: float) -> str:
    from bleak import BleakScanner

    print(f"Scanning for BLE devices matching {name_match!r} ({timeout:.0f}s)...")
    devices = await BleakScanner.discover(timeout=timeout)
    matches = [d for d in devices if d.name and name_match.lower() in d.name.lower()]
    if not matches:
        raise SystemExit(f"no device found matching {name_match!r}")
    print(f"  found: {matches[0].name}  {matches[0].address}")
    return matches[0].address


def _timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def _on_console_notify(_sender: object, data: bytearray) -> None:
    text = bytes(data).decode("ascii", errors="replace")
    print(f"[{_timestamp()}] <<< {text!r}  (hex: {data.hex(' ')})")


async def _run(address: str) -> None:
    from bleak import BleakClient

    disconnected = asyncio.Event()

    def _on_disconnect(_client: object) -> None:
        print("\n!!! device disconnected !!!")
        disconnected.set()

    async with BleakClient(address, disconnected_callback=_on_disconnect) as client:
        print(f"Connected to {address}\n")
        await client.start_notify(_CONSOLE_NOTIFY_CHARACTERISTIC, _on_console_notify)

        print(
            "Console ready. Type a line and press enter to send it to the "
            "device; blank line is the most harmless first probe. "
            'Type "exit" or Ctrl-D to quit.\n'
        )

        loop = asyncio.get_event_loop()
        while not disconnected.is_set():
            try:
                line = await loop.run_in_executor(None, input, "> ")
            except EOFError:
                break
            if line.strip().lower() == "exit":
                break
            if disconnected.is_set():
                print("(device already disconnected, not sending)")
                break

            payload = (line + "\n").encode("ascii", errors="replace")
            print(f"[{_timestamp()}] >>> {payload!r}")
            try:
                await client.write_gatt_char(
                    _CONSOLE_WRITE_CHARACTERISTIC, payload, response=True
                )
            except Exception as exc:  # noqa: BLE001 - reporting, not handling
                print(f"write failed: {exc}")
                break

            await asyncio.sleep(0.5)  # let a response land before re-prompting

        if client.is_connected:
            await client.stop_notify(_CONSOLE_NOTIFY_CHARACTERISTIC)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="Substring to match against the device's advertised name")
    parser.add_argument("--scan-timeout", type=float, default=10.0, help="Scan duration, seconds")
    args = parser.parse_args()

    address = asyncio.run(_scan(args.name, args.scan_timeout))
    asyncio.run(_run(address))


if __name__ == "__main__":
    main()

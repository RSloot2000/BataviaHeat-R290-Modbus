#!/usr/bin/env python3
"""
BataviaHeat R290 Modbus Real-Time Monitor

Continuously reads specified registers and displays their values in real-time.
Useful for observing how values change during heat pump operation.

Can use discovered registers from a previous scan, or monitor specific addresses.

Usage:
    python modbus_monitor.py --port COM3 --slave-id 1
    python modbus_monitor.py --port COM3 --slave-id 1 --scan-file scan_results.json
    python modbus_monitor.py --port COM3 --addresses 0-10,20,30-35 --type holding
"""

import argparse
import json
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException
from rich.console import Console
from rich.live import Live
from rich.table import Table

console = Console()
running = True


def signal_handler(sig, frame):
    global running
    running = False


signal.signal(signal.SIGINT, signal_handler)


def parse_address_ranges(addr_str: str) -> list[int]:
    """Parse address specification like '0-10,20,30-35' into a list of addresses."""
    addresses = []
    for part in addr_str.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            addresses.extend(range(int(start), int(end) + 1))
        else:
            addresses.append(int(part))
    return sorted(set(addresses))


def load_scan_results(scan_file: str) -> dict[str, list[int]]:
    """Load previously discovered register addresses from a scan JSON file."""
    data = json.loads(Path(scan_file).read_text())
    result = {}
    for reg_type, registers in data.get("results", {}).items():
        if registers:
            result[reg_type] = sorted(int(addr) for addr in registers.keys())
    return result


def read_registers(
    client: ModbusSerialClient,
    slave_id: int,
    reg_type: str,
    addresses: list[int],
) -> dict[int, int | bool | None]:
    """Read specific register addresses. Returns address -> value mapping."""
    read_func = {
        "holding": client.read_holding_registers,
        "input": client.read_input_registers,
        "coil": client.read_coils,
        "discrete": client.read_discrete_inputs,
    }[reg_type]

    results = {}
    # Group into contiguous blocks for efficient reading
    blocks = []
    if addresses:
        block_start = addresses[0]
        block_end = addresses[0]
        for addr in addresses[1:]:
            if addr <= block_end + 5:  # Allow small gaps
                block_end = addr
            else:
                blocks.append((block_start, block_end - block_start + 1))
                block_start = addr
                block_end = addr
        blocks.append((block_start, block_end - block_start + 1))

    for start, count in blocks:
        try:
            response = read_func(start, count=count, device_id=slave_id)
            if not response.isError():
                if reg_type in ("holding", "input"):
                    for i, val in enumerate(response.registers):
                        if start + i in addresses:
                            results[start + i] = val
                else:
                    for i in range(count):
                        if start + i in addresses:
                            results[start + i] = bool(response.bits[i])
        except (ModbusException, Exception):
            for addr in range(start, start + count):
                if addr in addresses:
                    results[addr] = None

    return results


def make_table(
    reg_type: str,
    current: dict[int, int | bool | None],
    previous: dict[int, int | bool | None],
    baseline: dict[int, int | bool | None],
    read_count: int,
) -> Table:
    """Build a rich table showing current register values with change detection."""
    from register_map import HOLDING_REGISTERS, INPUT_REGISTERS, COILS, DISCRETE_INPUTS

    reg_maps = {
        "holding": HOLDING_REGISTERS,
        "input": INPUT_REGISTERS,
        "coil": COILS,
        "discrete": DISCRETE_INPUTS,
    }
    reg_map = reg_maps.get(reg_type, {})

    table = Table(
        title=f"BataviaHeat R290 - {reg_type.capitalize()} Registers "
              f"(Read #{read_count}, Press Ctrl+C to stop)"
    )
    table.add_column("Addr", style="cyan", justify="right", width=6)
    table.add_column("Name", style="white", width=28)
    table.add_column("Raw", style="green", justify="right", width=8)
    table.add_column("Hex", style="yellow", justify="right", width=8)

    if reg_type in ("holding", "input"):
        table.add_column("Signed", style="magenta", justify="right", width=8)
        table.add_column("×0.1", style="blue", justify="right", width=8)
    table.add_column("Changed", style="red", justify="center", width=8)
    table.add_column("Δ Base", style="dim", justify="right", width=8)

    for addr in sorted(current.keys()):
        val = current[addr]
        prev = previous.get(addr)
        base = baseline.get(addr)
        info = reg_map.get(addr, {})
        name = info.get("name", "")

        if val is None:
            row = [str(addr), name, "ERR", "", ""]
            if reg_type in ("holding", "input"):
                row.extend(["", ""])
            row.extend(["", ""])
            table.add_row(*row)
            continue

        changed = "●" if prev is not None and val != prev else ""
        delta = ""
        if base is not None and reg_type in ("holding", "input"):
            d = val - base
            if d != 0:
                delta = f"{d:+d}"

        if reg_type in ("holding", "input"):
            signed = val - 65536 if val > 32767 else val
            scale = info.get("scale", 0.1)
            unit = info.get("unit", "")
            scaled_str = f"{signed * scale:.1f}{unit}"
            table.add_row(
                str(addr), name, str(val), f"0x{val:04X}",
                str(signed), scaled_str, changed, delta,
            )
        else:
            table.add_row(str(addr), name, str(val), "", changed, delta)

    return table


def main():
    parser = argparse.ArgumentParser(
        description="BataviaHeat R290 Modbus Real-Time Monitor"
    )
    parser.add_argument(
        "--port", required=True, help="Serial port (e.g., COM3)"
    )
    parser.add_argument("--baudrate", type=int, default=9600, help="Baudrate (default: 9600)")
    parser.add_argument("--parity", default="N", choices=["N", "E", "O"])
    parser.add_argument("--stopbits", type=int, default=1, choices=[1, 2])
    parser.add_argument("--slave-id", type=int, default=1, help="Modbus slave ID")
    parser.add_argument(
        "--scan-file", default=None,
        help="Load addresses from a previous scan result JSON file",
    )
    parser.add_argument(
        "--addresses", default=None,
        help="Register addresses to monitor (e.g., '0-10,20,30-35')",
    )
    parser.add_argument(
        "--type", default="holding",
        choices=["holding", "input", "coil", "discrete"],
        help="Register type to monitor (default: holding)",
    )
    parser.add_argument(
        "--interval", type=float, default=2.0,
        help="Poll interval in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--log", default=None,
        help="Log changes to a CSV file",
    )
    args = parser.parse_args()

    # Determine which registers to monitor
    monitor_map: dict[str, list[int]] = {}

    if args.scan_file:
        monitor_map = load_scan_results(args.scan_file)
        if not monitor_map:
            console.print("[red]No registers found in scan file[/red]")
            sys.exit(1)
        console.print(f"[green]Loaded {sum(len(v) for v in monitor_map.values())} "
                      f"registers from {args.scan_file}[/green]")
    elif args.addresses:
        monitor_map[args.type] = parse_address_ranges(args.addresses)
    else:
        # Default: monitor first 50 holding registers
        monitor_map = {"holding": list(range(0, 50))}

    # Connect
    client = ModbusSerialClient(
        port=args.port, baudrate=args.baudrate, parity=args.parity,
        stopbits=args.stopbits, bytesize=8, timeout=1,
    )
    if not client.connect():
        console.print(f"[red]Failed to connect to {args.port}[/red]")
        sys.exit(1)
    console.print(f"[green]Connected to {args.port} @ {args.baudrate} baud[/green]")

    # CSV log file
    log_file = None
    if args.log:
        log_file = open(args.log, "a", encoding="utf-8")
        log_file.write("timestamp,reg_type,address,old_value,new_value\n")

    previous: dict[str, dict[int, int | bool | None]] = {}
    baseline: dict[str, dict[int, int | bool | None]] = {}
    read_count = 0

    try:
        # Only monitor one type at a time in live view for clarity
        reg_type = args.type if not args.scan_file else list(monitor_map.keys())[0]
        addresses = monitor_map.get(reg_type, [])

        with Live(console=console, refresh_per_second=1) as live:
            while running:
                read_count += 1
                current = read_registers(client, args.slave_id, reg_type, addresses)

                if not baseline.get(reg_type):
                    baseline[reg_type] = dict(current)

                # Log changes
                if log_file and reg_type in previous:
                    now = datetime.now().isoformat()
                    for addr, val in current.items():
                        old = previous.get(reg_type, {}).get(addr)
                        if old is not None and val != old:
                            log_file.write(f"{now},{reg_type},{addr},{old},{val}\n")
                            log_file.flush()

                table = make_table(
                    reg_type, current,
                    previous.get(reg_type, {}),
                    baseline.get(reg_type, {}),
                    read_count,
                )
                live.update(table)

                previous[reg_type] = current
                time.sleep(args.interval)
    finally:
        client.close()
        if log_file:
            log_file.close()
        console.print("\n[yellow]Monitor stopped.[/yellow]")


if __name__ == "__main__":
    main()

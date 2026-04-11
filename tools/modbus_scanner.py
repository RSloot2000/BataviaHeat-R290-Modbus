#!/usr/bin/env python3
"""
BataviaHeat R290 Modbus Register Scanner

Scans all Modbus register types across a configurable address range
to discover which registers are active on the heat pump.
Results are saved to a JSON file for analysis.

Usage:
    python modbus_scanner.py --port COM3 --slave-id 1 --output scan_results.json
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table

# Suppress noisy pymodbus buffer cleanup messages
logging.getLogger("pymodbus.transport.transport").setLevel(logging.ERROR)
logging.getLogger("pymodbus.logging").setLevel(logging.ERROR)

console = Console()

# Register scan ranges (start, count)
DEFAULT_SCAN_RANGES = {
    "holding": (0, 500),
    "input": (0, 500),
    "coil": (0, 200),
    "discrete": (0, 200),
}

BATCH_SIZE = 10  # Read registers in batches for efficiency


def create_client(port: str, baudrate: int, parity: str, stopbits: int) -> ModbusSerialClient:
    """Create and connect a Modbus RTU serial client."""
    client = ModbusSerialClient(
        port=port,
        baudrate=baudrate,
        parity=parity,
        stopbits=stopbits,
        bytesize=8,
        timeout=1,
    )
    if not client.connect():
        console.print(f"[red]Failed to connect to {port}[/red]")
        sys.exit(1)
    console.print(f"[green]Connected to {port} @ {baudrate} baud[/green]")
    return client


def _flush_and_retry(client: ModbusSerialClient) -> None:
    """Flush the serial buffer to recover from CRC/frame errors."""
    if client.socket:
        client.socket.reset_input_buffer()
    time.sleep(0.1)


def scan_registers(
    client: ModbusSerialClient,
    slave_id: int,
    reg_type: str,
    start: int,
    count: int,
) -> dict[int, int | bool]:
    """Scan a range of registers and return those that respond."""
    results = {}
    read_func = {
        "holding": client.read_holding_registers,
        "input": client.read_input_registers,
        "coil": client.read_coils,
        "discrete": client.read_discrete_inputs,
    }[reg_type]

    end = start + count
    errors = 0
    interrupted = False
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn(f"[cyan]Scanning {reg_type} registers..."),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("[dim]{task.fields[errors]} errors[/dim]"),
            console=console,
        ) as progress:
            task = progress.add_task(reg_type, total=count, errors=0)

            addr = start
            while addr < end:
                batch = min(BATCH_SIZE, end - addr)
                try:
                    response = read_func(addr, count=batch, device_id=slave_id)
                    if not response.isError():
                        if reg_type in ("holding", "input"):
                            for i, val in enumerate(response.registers):
                                results[addr + i] = val
                        else:
                            for i, val in enumerate(response.bits[:batch]):
                                results[addr + i] = bool(val)
                except KeyboardInterrupt:
                    raise
                except Exception:
                    errors += 1
                    progress.update(task, errors=errors)
                    _flush_and_retry(client)
                    for single_addr in range(addr, addr + batch):
                        try:
                            resp = read_func(single_addr, count=1, device_id=slave_id)
                            if not resp.isError():
                                if reg_type in ("holding", "input"):
                                    results[single_addr] = resp.registers[0]
                                else:
                                    results[single_addr] = bool(resp.bits[0])
                        except KeyboardInterrupt:
                            raise
                        except Exception:
                            _flush_and_retry(client)
                        time.sleep(0.05)

                addr += batch
                progress.advance(task, batch)
                time.sleep(0.05)
    except KeyboardInterrupt:
        interrupted = True
        console.print(f"\n[yellow]{reg_type} scan interrupted at address {addr}[/yellow]")

    return results


def display_results(reg_type: str, results: dict[int, int | bool]) -> None:
    """Display scan results in a formatted table."""
    if not results:
        console.print(f"  [dim]No {reg_type} registers responded[/dim]")
        return

    table = Table(title=f"{reg_type.capitalize()} Registers ({len(results)} found)")
    table.add_column("Address", style="cyan", justify="right")
    table.add_column("Dec Address", style="dim", justify="right")
    table.add_column("Raw Value", style="green", justify="right")
    table.add_column("Hex Value", style="yellow", justify="right")

    if reg_type in ("holding", "input"):
        table.add_column("Signed", style="magenta", justify="right")
        table.add_column("×0.1", style="blue", justify="right")
        for addr in sorted(results):
            val = results[addr]
            signed = val - 65536 if val > 32767 else val
            table.add_row(
                str(addr),
                str(addr),
                str(val),
                f"0x{val:04X}",
                str(signed),
                f"{signed * 0.1:.1f}",
            )
    else:
        for addr in sorted(results):
            table.add_row(str(addr), str(addr), str(results[addr]), "")

    console.print(table)


def main():
    parser = argparse.ArgumentParser(
        description="BataviaHeat R290 Modbus Register Scanner"
    )
    parser.add_argument(
        "--port", required=True, help="Serial port (e.g., COM3 on Windows, /dev/ttyUSB0 on Linux)"
    )
    parser.add_argument("--baudrate", type=int, default=9600, help="Baudrate (default: 9600)")
    parser.add_argument("--parity", default="N", choices=["N", "E", "O"], help="Parity (default: N)")
    parser.add_argument("--stopbits", type=int, default=1, choices=[1, 2], help="Stop bits (default: 1)")
    parser.add_argument("--slave-id", type=int, default=1, help="Modbus slave ID (default: 1)")
    parser.add_argument(
        "--range-start", type=int, default=0, help="Start address for scan (default: 0)"
    )
    parser.add_argument(
        "--range-count", type=int, default=500, help="Number of registers to scan (default: 500)"
    )
    parser.add_argument(
        "--types",
        nargs="+",
        default=["holding", "input", "coil", "discrete"],
        choices=["holding", "input", "coil", "discrete"],
        help="Register types to scan (default: all)",
    )
    parser.add_argument(
        "--output", default=None, help="Output JSON file (default: scan_YYYYMMDD_HHMMSS.json)"
    )
    parser.add_argument(
        "--baudrate-scan",
        action="store_true",
        help="Try common baudrates to find the correct one",
    )
    args = parser.parse_args()

    # Baudrate scan mode
    if args.baudrate_scan:
        console.print("[bold]Scanning common baudrates...[/bold]")
        common_baudrates = [9600, 19200, 38400, 57600, 115200, 4800, 2400, 1200]
        for br in common_baudrates:
            console.print(f"\n[yellow]Trying {br} baud...[/yellow]")
            try:
                client = ModbusSerialClient(
                    port=args.port, baudrate=br, parity=args.parity,
                    stopbits=args.stopbits, bytesize=8, timeout=1,
                )
                if client.connect():
                    response = client.read_holding_registers(0, count=1, device_id=args.slave_id)
                    if not response.isError():
                        console.print(f"[green bold]SUCCESS at {br} baud! Got response.[/green bold]")
                        client.close()
                        return
                    client.close()
            except Exception:
                pass
            console.print(f"  [dim]No response at {br} baud[/dim]")
        console.print("\n[red]No baudrate produced a valid response.[/red]")
        return

    # Normal scan mode
    client = create_client(args.port, args.baudrate, args.parity, args.stopbits)

    all_results = {}
    timestamp = datetime.now().isoformat()

    console.print(f"\n[bold]Scanning slave ID {args.slave_id}, "
                  f"range {args.range_start}-{args.range_start + args.range_count - 1}[/bold]\n")

    try:
        for reg_type in args.types:
            results = scan_registers(
                client, args.slave_id, reg_type, args.range_start, args.range_count
            )
            all_results[reg_type] = {str(k): v for k, v in results.items()}
            display_results(reg_type, results)
            console.print()
    finally:
        client.close()

    # Save results (always, even partial)
    if all_results:
        output_data = {
            "device": "BataviaHeat R290 3-8kW",
            "timestamp": timestamp,
            "connection": {
                "port": args.port,
                "baudrate": args.baudrate,
                "parity": args.parity,
                "stopbits": args.stopbits,
                "slave_id": args.slave_id,
            },
            "scan_range": {
                "start": args.range_start,
                "count": args.range_count,
            },
            "results": all_results,
        }

        if args.output is None:
            args.output = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        output_path = Path(args.output)
        output_path.write_text(json.dumps(output_data, indent=2))
        console.print(f"[green]Results saved to {output_path}[/green]")

        # Summary
        total = sum(len(v) for v in all_results.values())
        console.print(f"\n[bold]Total registers found: {total}[/bold]")


if __name__ == "__main__":
    main()

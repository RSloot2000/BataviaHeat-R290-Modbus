#!/usr/bin/env python3
"""
Extended scan: addresses 600-2000, then merge with scan_initial.json.

Strategy: scan register-by-register with a very short timeout (0.3s).
The device has address gaps where some addresses return errors.
After 200 consecutive no-response addresses, we assume the end is reached.
"""

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from pymodbus.client import ModbusSerialClient
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.live import Live
from rich.text import Text

logging.getLogger("pymodbus.transport.transport").setLevel(logging.ERROR)
logging.getLogger("pymodbus.logging").setLevel(logging.ERROR)

console = Console()

PORT = "COM5"
BAUDRATE = 9600
SLAVE_ID = 1
SCAN_START = 600
SCAN_COUNT = 1400  # 600-1999
TIMEOUT = 0.3  # Short timeout per register read
MAX_CONSECUTIVE_NOREPLY = 200  # Stop after this many no-reply in a row

INITIAL_FILE = Path(__file__).parent / "scan_initial.json"
MERGED_FILE = Path(__file__).parent / "scan_merged.json"
EXTENDED_FILE = Path(__file__).parent / "scan_extended_600_2000.json"


def create_client() -> ModbusSerialClient:
    client = ModbusSerialClient(
        port=PORT, baudrate=BAUDRATE, parity="N", stopbits=1, bytesize=8,
        timeout=TIMEOUT, retries=0,
    )
    client.connect()
    return client


def scan_registers(reg_type: str, start: int, count: int) -> dict[int, int]:
    read_name = {
        "holding": "read_holding_registers",
        "input": "read_input_registers",
    }[reg_type]

    results = {}
    end = start + count
    errors = 0
    no_reply_streak = 0

    client = create_client()
    if not client.connected:
        console.print("[red]Cannot connect![/red]")
        return results

    with Progress(
        SpinnerColumn(),
        TextColumn(f"[cyan]{reg_type} {start}-{end-1}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("[dim]{task.fields[found]} found, {task.fields[errors]} err, streak={task.fields[streak]}[/dim]"),
        console=console,
        refresh_per_second=4,
    ) as progress:
        task = progress.add_task(reg_type, total=count, found=0, errors=0, streak=0)

        for addr in range(start, end):
            try:
                read_func = getattr(client, read_name)
                response = read_func(addr, count=1, device_id=SLAVE_ID)
                if not response.isError():
                    results[addr] = response.registers[0]
                    no_reply_streak = 0
                else:
                    errors += 1
                    no_reply_streak += 1
            except KeyboardInterrupt:
                console.print("\n[yellow]Interrupted![/yellow]")
                break
            except Exception:
                errors += 1
                no_reply_streak += 1
                # Reconnect after transport error
                try:
                    client.close()
                except Exception:
                    pass
                time.sleep(0.2)
                client = create_client()

            progress.update(task, advance=1, found=len(results), errors=errors, streak=no_reply_streak)

            if no_reply_streak >= MAX_CONSECUTIVE_NOREPLY:
                console.print(f"\n[yellow]{MAX_CONSECUTIVE_NOREPLY} consecutive no-reply at addr {addr}, "
                              f"stopping {reg_type}.[/yellow]")
                break

            time.sleep(0.01)

    try:
        client.close()
    except Exception:
        pass
    return results


def main():
    # Quick connectivity test
    test = create_client()
    if not test.connected:
        console.print(f"[red]Failed to connect to {PORT}[/red]")
        sys.exit(1)
    console.print(f"[green]Connected to {PORT} @ {BAUDRATE} baud (timeout={TIMEOUT}s)[/green]")
    test.close()

    extended = {}
    for reg_type in ["holding", "input"]:
        results = scan_registers(reg_type, SCAN_START, SCAN_COUNT)
        extended[reg_type] = {str(k): v for k, v in sorted(results.items())}
        non_zero = sum(1 for v in results.values() if v != 0)
        console.print(f"  [green]{reg_type}: {len(results)} registers found "
                      f"({non_zero} non-zero)[/green]\n")

    # Save extended scan
    ext_data = {
        "device": "BataviaHeat R290 3-8kW",
        "timestamp": datetime.now().isoformat(),
        "scan_range": {"start": SCAN_START, "count": SCAN_COUNT},
        "results": extended,
    }
    EXTENDED_FILE.write_text(json.dumps(ext_data, indent=2))
    console.print(f"[green]Extended scan saved to {EXTENDED_FILE.name}[/green]")

    # Merge with initial scan
    if INITIAL_FILE.exists():
        initial = json.loads(INITIAL_FILE.read_text())
        merged = dict(initial)  # copy metadata
        merged["scan_range"] = {"start": 0, "count": SCAN_START + SCAN_COUNT}
        merged["timestamp_merged"] = datetime.now().isoformat()

        for reg_type in ["holding", "input"]:
            base = initial.get("results", {}).get(reg_type, {})
            ext = extended.get(reg_type, {})
            combined = {**base, **ext}
            merged.setdefault("results", {})[reg_type] = dict(
                sorted(combined.items(), key=lambda x: int(x[0]))
            )
            console.print(f"  [cyan]{reg_type}: {len(base)} initial + {len(ext)} extended "
                          f"= {len(combined)} total[/cyan]")

        MERGED_FILE.write_text(json.dumps(merged, indent=2))
        console.print(f"\n[bold green]Merged scan saved to {MERGED_FILE.name}[/bold green]")
    else:
        console.print(f"[yellow]{INITIAL_FILE.name} not found, skipping merge.[/yellow]")


if __name__ == "__main__":
    main()

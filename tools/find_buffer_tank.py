#!/usr/bin/env python3
"""
BataviaHeat Buffer Tank Temperature Finder

Scans all holding and input registers looking for values that match a known
buffer tank temperature (read from the tablet display). Once candidates are
found, monitor mode tracks them over time to confirm which register is the
real sensor.

Strategy:
  1. User reads the buffer tank temperature from the tablet (e.g. 45.3°C)
  2. Script scans HR[0-1400] and IR[0-300] for values matching that temp
     with common scales (×1, ×0.1, ×0.01)
  3. Candidates are shown sorted by match quality
  4. Monitor mode polls candidates every N seconds, highlighting changes
  5. User can observe on the tablet and correlate with register changes

Connection: Modbus TCP via DR164 RS485-to-WiFi converter.
The tablet can remain connected to the RS-485 bus during scanning.

Usage:
    python find_buffer_tank.py 45.3                  # Scan for 45.3°C
    python find_buffer_tank.py 45.3 --tolerance 1.0  # Wider search (±1°C)
    python find_buffer_tank.py 45.3 --monitor         # Scan + monitor candidates
    python find_buffer_tank.py --monitor --addresses HR5,HR74,IR135  # Monitor specific regs
    python find_buffer_tank.py --host 192.168.1.100   # Custom gateway IP

Press Ctrl+C to stop monitoring.
"""

import argparse
import signal
import sys
import time
from datetime import datetime

from pymodbus.client import ModbusTcpClient
from rich.console import Console
from rich.live import Live
from rich.table import Table

# ─── Connection defaults ─────────────────────────────────────────────────────
DEFAULT_HOST = "192.168.4.1"
DEFAULT_PORT = 502
DEFAULT_SLAVE = 1

# ─── Scan ranges ─────────────────────────────────────────────────────────────
# We scan these ranges for candidate registers
SCAN_RANGES = {
    "HR": [
        (0, 275),       # Midea/control range (HR[5] was a candidate)
        (275, 768),     # Unexplored gap
        (768, 850),     # Operational range
        (850, 1400),    # Extended range
    ],
    "IR": [
        (0, 300),       # Full input register range
    ],
}

# Known registers to exclude (already identified, not buffer tank)
KNOWN_REGS = {
    "HR": {
        4: "heating_target",
        22: "ambient_temp (IR alias)",
        768: "operational_status",
        773: "comp_discharge_temp",
        776: "water_outlet_temp",
        1283: "compressor_running",
        6402: "max_heating_temp",
        6426: "heating_curve_mode",
        6433: "curve_outdoor_high",
        6434: "curve_outdoor_low",
        6435: "curve_water_mild",
        6436: "curve_water_cold",
    },
    "IR": {
        22: "ambient_temp",
        23: "fin_coil_temp",
        24: "suction_temp",
        25: "discharge_temp",
        32: "low_pressure",
        33: "high_pressure",
        53: "pump_target_speed",
        54: "pump_flow_rate",
        66: "pump_control_signal",
        135: "plate_hx_inlet",
        136: "plate_hx_outlet",
        137: "module_water_outlet",
        138: "module_ambient",
        142: "pump_feedback",
    },
}

# Values that indicate disconnected sensors
DISCONNECTED = {0x8042, 0x8044, 0xFFFF, 0x7FFF}

console = Console()
running = True


def signal_handler(sig, frame):
    global running
    running = False


signal.signal(signal.SIGINT, signal_handler)


def connect(host: str, port: int) -> ModbusTcpClient:
    client = ModbusTcpClient(host=host, port=port, timeout=3)
    if not client.connect():
        console.print(f"[red]Cannot connect to {host}:{port}[/red]")
        sys.exit(1)
    return client


def read_register(client: ModbusTcpClient, reg_type: str, addr: int, slave: int) -> int | None:
    """Read a single register. Returns raw value or None on error."""
    try:
        if reg_type == "HR":
            resp = client.read_holding_registers(addr, count=1, slave=slave)
        else:
            resp = client.read_input_registers(addr, count=1, slave=slave)
        if not resp.isError() and hasattr(resp, "registers"):
            return resp.registers[0]
    except Exception:
        pass
    return None


def read_batch(client: ModbusTcpClient, reg_type: str, start: int, count: int, slave: int) -> dict[int, int]:
    """Read a batch of registers. Returns {addr: value} dict."""
    results = {}
    batch_size = 50  # TCP can handle larger batches than RTU
    for offset in range(0, count, batch_size):
        addr = start + offset
        n = min(batch_size, start + count - addr)
        try:
            if reg_type == "HR":
                resp = client.read_holding_registers(addr, count=n, slave=slave)
            else:
                resp = client.read_input_registers(addr, count=n, slave=slave)
            if not resp.isError() and hasattr(resp, "registers"):
                for i, val in enumerate(resp.registers):
                    results[addr + i] = val
        except Exception:
            # Fall back to smaller batches on error
            for single_addr in range(addr, addr + n):
                val = read_register(client, reg_type, single_addr, slave)
                if val is not None:
                    results[single_addr] = val
        time.sleep(0.05)
    return results


def to_signed(raw: int) -> int:
    return raw - 65536 if raw > 32767 else raw


def matches_temperature(raw: int, target: float, tolerance: float) -> list[dict]:
    """Check if a raw value could represent the target temperature.

    Returns list of possible interpretations that match.
    """
    if raw in DISCONNECTED or raw == 0:
        return []

    signed = to_signed(raw)
    matches = []

    scales = [
        (1,    "×1 (whole °C)"),
        (0.1,  "×0.1 (e.g. 453 = 45.3°C)"),
        (0.01, "×0.01 (e.g. 4530 = 45.30°C)"),
        (0.5,  "×0.5 (e.g. 91 = 45.5°C)"),
    ]

    for scale, label in scales:
        temp = signed * scale
        if abs(temp - target) <= tolerance:
            matches.append({
                "scale": scale,
                "label": label,
                "temp": temp,
                "diff": abs(temp - target),
            })

    return matches


def scan_for_temperature(
    client: ModbusTcpClient,
    target: float,
    tolerance: float,
    slave: int,
) -> list[dict]:
    """Scan all register ranges for values matching the target temperature."""
    candidates = []

    for reg_type, ranges in SCAN_RANGES.items():
        for start, end in ranges:
            count = end - start
            console.print(f"  Scanning {reg_type}[{start}-{end - 1}]...", end=" ")
            data = read_batch(client, reg_type, start, count, slave)
            console.print(f"[green]{len(data)} registers[/green]")

            for addr, raw in data.items():
                matches = matches_temperature(raw, target, tolerance)
                if matches:
                    known = KNOWN_REGS.get(reg_type, {}).get(addr)
                    for m in matches:
                        candidates.append({
                            "reg_type": reg_type,
                            "addr": addr,
                            "raw": raw,
                            "signed": to_signed(raw),
                            "scale": m["scale"],
                            "scale_label": m["label"],
                            "temp": m["temp"],
                            "diff": m["diff"],
                            "known_as": known,
                        })

    # Sort by match quality (closest first)
    candidates.sort(key=lambda c: (c["diff"], c["reg_type"], c["addr"]))
    return candidates


def show_candidates(candidates: list[dict], target: float) -> None:
    """Display scan results in a table."""
    table = Table(title=f"Candidates matching {target}°C", show_lines=True)
    table.add_column("Register", style="cyan", width=8)
    table.add_column("Raw", justify="right", width=7)
    table.add_column("Interpreted", justify="right", width=10)
    table.add_column("Diff", justify="right", width=6)
    table.add_column("Scale", width=28)
    table.add_column("Known as", style="yellow", width=22)
    table.add_column("Note", width=20)

    for c in candidates:
        reg = f"{c['reg_type']}[{c['addr']}]"
        known = c["known_as"] or ""
        note = ""
        if known:
            note = "[dim]already identified[/dim]"
        elif c["diff"] == 0:
            note = "[bold green]EXACT MATCH[/bold green]"
        elif c["diff"] <= 0.2:
            note = "[green]very close[/green]"
        elif c["diff"] <= 0.5:
            note = "[yellow]close[/yellow]"

        table.add_row(
            reg,
            str(c["raw"]),
            f"{c['temp']:.1f}°C",
            f"{c['diff']:.1f}",
            c["scale_label"],
            known,
            note,
        )

    console.print(table)
    console.print(f"\n[bold]{len(candidates)} candidates found[/bold]")

    # Give a summary of the best unknown candidates
    unknown = [c for c in candidates if not c["known_as"]]
    if unknown:
        console.print(f"[green]{len(unknown)} unknown registers[/green] (potential buffer tank sensors)")
        best = unknown[:10]
        console.print("\nTop candidates to monitor:")
        for c in best:
            console.print(f"  {c['reg_type']}[{c['addr']}] = {c['temp']:.1f}°C (raw {c['raw']}, {c['scale_label']})")


def parse_addresses(addr_str: str) -> list[tuple[str, int]]:
    """Parse comma-separated addresses like 'HR5,HR74,IR135'."""
    addresses = []
    for part in addr_str.split(","):
        part = part.strip().upper()
        if part.startswith("HR"):
            addresses.append(("HR", int(part[2:])))
        elif part.startswith("IR"):
            addresses.append(("IR", int(part[2:])))
        else:
            # Assume HR if no prefix
            addresses.append(("HR", int(part)))
    return addresses


def monitor_registers(
    client: ModbusTcpClient,
    addresses: list[tuple[str, int]],
    slave: int,
    interval: float,
) -> None:
    """Continuously monitor specific registers, highlighting changes."""
    prev_values: dict[tuple[str, int], int] = {}
    history: dict[tuple[str, int], list[tuple[float, int]]] = {addr: [] for addr in addresses}
    read_num = 0

    with Live(console=console, refresh_per_second=1) as live:
        while running:
            read_num += 1
            now = time.time()

            # Read all monitored registers
            current = {}
            for reg_type, addr in addresses:
                val = read_register(client, reg_type, addr, slave)
                if val is not None:
                    current[(reg_type, addr)] = val
                    history[(reg_type, addr)].append((now, val))

            # Build display table
            table = Table(
                title=f"Buffer Tank Monitor - Reading #{read_num} ({datetime.now():%H:%M:%S})",
                show_lines=True,
                width=110,
            )
            table.add_column("Register", style="cyan", width=8)
            table.add_column("Raw", justify="right", width=7)
            table.add_column("×0.1", justify="right", width=8)
            table.add_column("×1", justify="right", width=6)
            table.add_column("×0.01", justify="right", width=8)
            table.add_column("Change", width=8)
            table.add_column("Min", justify="right", width=8)
            table.add_column("Max", justify="right", width=8)
            table.add_column("Known as", style="yellow", width=20)

            for reg_type, addr in addresses:
                key = (reg_type, addr)
                if key not in current:
                    table.add_row(f"{reg_type}[{addr}]", "[red]ERR[/red]", "", "", "", "", "", "", "")
                    continue

                raw = current[key]
                signed = to_signed(raw)

                # Change detection
                change = ""
                if key in prev_values:
                    diff = raw - prev_values[key]
                    if diff > 0:
                        change = f"[green]+{diff}[/green]"
                    elif diff < 0:
                        change = f"[red]{diff}[/red]"

                # Min/max from history (×0.1 scale)
                vals = [to_signed(v) for _, v in history[key]]
                min_val = min(vals) * 0.1
                max_val = max(vals) * 0.1

                known = KNOWN_REGS.get(reg_type, {}).get(addr, "")

                table.add_row(
                    f"{reg_type}[{addr}]",
                    str(raw),
                    f"{signed * 0.1:.1f}°C",
                    f"{signed}°C",
                    f"{signed * 0.01:.2f}°C",
                    change,
                    f"{min_val:.1f}°C",
                    f"{max_val:.1f}°C",
                    known,
                )

            table.add_row("", "", "", "", "", "", "", "", "")
            table.add_row(
                "", "", "", "", "",
                f"[dim]{len(history[addresses[0]])} readings[/dim]",
                "", "",
                f"[dim]interval: {interval}s[/dim]",
            )

            live.update(table)
            prev_values = current.copy()

            # Wait for next poll
            wait_until = time.time() + interval
            while running and time.time() < wait_until:
                time.sleep(0.1)


def main():
    parser = argparse.ArgumentParser(
        description="Find buffer tank temperature registers by matching tablet readings",
    )
    parser.add_argument(
        "temperature", nargs="?", type=float, default=None,
        help="Target temperature shown on the tablet (e.g. 45.3)",
    )
    parser.add_argument(
        "--tolerance", "-t", type=float, default=0.5,
        help="Match tolerance in °C (default: 0.5)",
    )
    parser.add_argument(
        "--monitor", "-m", action="store_true",
        help="Monitor candidate registers continuously",
    )
    parser.add_argument(
        "--addresses", "-a", type=str, default=None,
        help="Comma-separated registers to monitor (e.g. HR5,HR74,IR135)",
    )
    parser.add_argument(
        "--interval", "-i", type=float, default=5.0,
        help="Monitor poll interval in seconds (default: 5)",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Modbus TCP host (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"TCP port (default: {DEFAULT_PORT})")
    parser.add_argument("--slave", type=int, default=DEFAULT_SLAVE, help=f"Slave ID (default: {DEFAULT_SLAVE})")

    args = parser.parse_args()

    if not args.temperature and not args.addresses:
        console.print("[red]Provide a target temperature or --addresses to monitor[/red]")
        console.print("Example: python find_buffer_tank.py 45.3")
        console.print("Example: python find_buffer_tank.py --monitor --addresses HR5,HR74,IR135")
        sys.exit(1)

    console.print("[bold]BataviaHeat Buffer Tank Temperature Finder[/bold]")
    console.print(f"Connecting to {args.host}:{args.port}, slave {args.slave}...\n")

    client = connect(args.host, args.port)
    console.print("[green]Connected![/green]\n")

    try:
        if args.addresses:
            # Monitor specific registers
            addresses = parse_addresses(args.addresses)
            console.print(f"Monitoring {len(addresses)} registers: {args.addresses}\n")
            monitor_registers(client, addresses, args.slave, args.interval)
        elif args.temperature is not None:
            # Scan for matching temperature
            console.print(f"Scanning for registers matching [bold]{args.temperature}°C[/bold] (±{args.tolerance}°C)...\n")
            candidates = scan_for_temperature(client, args.temperature, args.tolerance, args.slave)

            if not candidates:
                console.print("[yellow]No matching registers found.[/yellow]")
                console.print("Try increasing --tolerance or check the tablet temperature again.")
            else:
                show_candidates(candidates, args.temperature)

                if args.monitor:
                    # Auto-select top unknown candidates for monitoring
                    unknown = [c for c in candidates if not c["known_as"]]
                    if unknown:
                        # Deduplicate by register (keep best scale match)
                        seen = set()
                        monitor_addrs = []
                        for c in unknown[:15]:
                            key = (c["reg_type"], c["addr"])
                            if key not in seen:
                                seen.add(key)
                                monitor_addrs.append(key)

                        # Always include HR[5] if not already there
                        if ("HR", 5) not in seen:
                            monitor_addrs.insert(0, ("HR", 5))

                        console.print(f"\n[bold]Starting monitor on {len(monitor_addrs)} candidates...[/bold]")
                        console.print("[dim]Watch the tablet and note when the temperature changes. "
                                      "Registers that follow the same pattern are your buffer tank sensors.[/dim]\n")
                        monitor_registers(client, monitor_addrs, args.slave, args.interval)
                    else:
                        console.print("\n[yellow]All matches are known registers. "
                                      "Try a wider tolerance or different temperature.[/yellow]")
    except KeyboardInterrupt:
        pass
    finally:
        client.close()
        console.print("\n[yellow]Connection closed.[/yellow]")


if __name__ == "__main__":
    main()

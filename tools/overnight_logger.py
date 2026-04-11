#!/usr/bin/env python3
"""
BataviaHeat R290 Overnight Logger

Continuously polls all known holding and input registers, logs every change
to CSV, and logs full snapshots at regular intervals. Designed to run
unattended for hours. Press Ctrl+C to stop gracefully.

Output:
  - overnight_changes.csv: Every register value change with timestamps
  - overnight_snapshots.csv: Full register dumps at snapshot intervals
  - Console: Live status display

Usage:
    python overnight_logger.py
    python overnight_logger.py --interval 5 --snapshot-interval 300
"""

import csv
import logging
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
from rich.text import Text

logging.getLogger("pymodbus").setLevel(logging.CRITICAL)

console = Console()
running = True


def signal_handler(sig, frame):
    global running
    running = False


signal.signal(signal.SIGINT, signal_handler)

# ─── Connection Settings ───
PORT = "COM5"
BAUDRATE = 9600
SLAVE_ID = 1
POLL_INTERVAL = 5       # seconds between polls
SNAPSHOT_INTERVAL = 300  # seconds between full snapshots (5 min)
RECONNECT_DELAY = 5      # seconds to wait before reconnecting

# ─── Output files ───
SCRIPT_DIR = Path(__file__).parent
CHANGES_FILE = SCRIPT_DIR / "overnight_changes.csv"
SNAPSHOTS_FILE = SCRIPT_DIR / "overnight_snapshots.csv"

# ─── Registers to monitor ───
# All meaningful registers from our scans (confirmed + likely + key tentative).
# Grouped by function for readability. Excludes disconnected/noise addresses.

HOLDING_ADDRS = sorted([
    # Config / mode
    0, 1,
    # Temperature setpoints
    4, 94, 95, 103,
    # Sensor mirrors (primary block)
    5, 8, 9, 11, 12,
    32, 33,
    43,
    71, 72, 73, 74, 75, 76,
    # Room/DHW/ambient
    187, 188, 189,
    # Zone B block (repeat of main config)
    410, 411, 414, 415, 418, 419,
    # System config (extended range)
    600, 601, 616, 626, 641,
    773, 811, 812, 813, 814, 816,
    # Live compressor data (extended range)
    1301, 1304, 1319, 1348, 1350, 1352, 1355,
])

INPUT_ADDRS = sorted([
    # Refrigerant circuit temps
    22, 23, 24, 25,
    # Pressures
    32, 33,
    # Pump
    53, 54, 66,
    # System mirrors
    84, 85, 95,
    # High-precision pressures
    16, 17, 18, 19,
    # Module 0 temps/pump
    134, 135, 136, 137, 138, 139, 142,
])

# Register name lookup (from register_map.py — subset for display)
HR_NAMES = {
    0: "operating_mode", 1: "silent_mode",
    4: "heating_target", 94: "cooling_target", 95: "zone_b_target", 103: "dhw_max_temp",
    5: "buffer_lower", 8: "water_temp_1", 9: "water_temp_2",
    11: "high_press_kpa", 12: "low_press_kpa",
    32: "low_pressure", 33: "high_pressure",
    43: "comp_max_freq",
    71: "floor_inlet", 72: "water_outlet", 73: "solar_boiler",
    74: "buffer_upper", 75: "buffer_lower2", 76: "total_outlet",
    187: "room_temp", 188: "dhw_tank", 189: "ambient_temp",
    410: "zB_mode", 411: "zB_silent", 414: "zB_target", 415: "zB_buf_lower",
    418: "zB_temp1", 419: "zB_temp2",
    600: "sys_param_600", 601: "sys_param_601",
    616: "defrost_target", 626: "dhw_setpoint", 641: "outdoor_config",
    773: "max_outlet_limit", 811: "pump_max_rpm", 812: "pump_min_rpm",
    813: "defrost_interval", 814: "temp_limit", 816: "heat_target_mirror",
    1301: "comp_water_temp", 1304: "condenser_temp", 1319: "evap_target",
    1348: "plate_hx_in", 1350: "plate_hx_out",
    1352: "pump_speed_live", 1355: "pump_fb_live",
}

IR_NAMES = {
    22: "ambient", 23: "fin_coil", 24: "suction", 25: "discharge",
    32: "low_pressure", 33: "high_pressure",
    53: "pump_speed", 54: "flow_rate", 66: "pump_control",
    84: "heat_target_m", 85: "buf_upper_m", 95: "zB_target_m",
    16: "high_press_kpa", 17: "high_press_kpa2", 18: "high_press_kpa3", 19: "low_press_kpa",
    134: "mod0_discon", 135: "plate_hx_in", 136: "plate_hx_out",
    137: "mod_water_out", 138: "mod_ambient", 139: "mod_pump_speed", 142: "pump_feedback",
}

# Disconnected sensor markers
DISCONNECTED = {32834, 32836}  # 0x8042, 0x8044
NOISE_VALUES = {0x8E00, 0xE800, 0x9000, 0x0820}


def create_client() -> ModbusSerialClient:
    return ModbusSerialClient(
        port=PORT, baudrate=BAUDRATE, parity="N", stopbits=1, bytesize=8,
        timeout=1, retries=1,
    )


def read_block(client, func_name, addresses, slave_id):
    """Read a list of addresses using batch reads where possible."""
    results = {}
    read_func = getattr(client, func_name)

    # Group into contiguous blocks (allow gaps ≤ 10)
    blocks = []
    if not addresses:
        return results
    block_start = addresses[0]
    block_end = addresses[0]
    for addr in addresses[1:]:
        if addr <= block_end + 10:
            block_end = addr
        else:
            blocks.append((block_start, block_end - block_start + 1))
            block_start = addr
            block_end = addr
    blocks.append((block_start, block_end - block_start + 1))

    for start, count in blocks:
        try:
            resp = read_func(start, count=count, device_id=slave_id)
            if not resp.isError() and hasattr(resp, "registers"):
                for i, val in enumerate(resp.registers):
                    addr = start + i
                    if addr in addresses:
                        results[addr] = val
        except Exception:
            pass
        time.sleep(0.05)  # Small gap between blocks

    return results


def format_value(addr, val, names):
    """Format a register value for display."""
    if val is None:
        return "ERR"
    if val in DISCONNECTED:
        return "DISCON"
    if val in NOISE_VALUES:
        return f"noise(0x{val:04X})"
    name = names.get(addr, "")
    # Temperature registers (most are ×0.1°C)
    if any(t in name for t in ["temp", "ambient", "suction", "discharge", "fin",
                                 "buffer", "inlet", "outlet", "target", "room",
                                 "condenser", "evap", "defrost", "plate", "dhw",
                                 "floor", "solar", "water", "cooling"]):
        signed = val - 65536 if val > 32767 else val
        return f"{signed * 0.1:.1f}°C"
    if "pressure" in name or "press" in name:
        if "kpa" in name:
            return f"{val * 0.1:.1f}kPa"
        return f"{val * 0.1:.1f}bar"
    if "speed" in name or "rpm" in name or "freq" in name:
        return f"{val}rpm"
    if "flow" in name:
        return f"{val}L/h"
    if "control" in name or "feedback" in name or "fb" in name:
        return f"{val * 0.1:.1f}%"
    return str(val)


def build_status_table(hr_current, ir_current, hr_prev, ir_prev,
                       poll_count, change_count, start_time, errors):
    """Build a rich table showing current state."""
    elapsed = time.time() - start_time
    hours = int(elapsed // 3600)
    mins = int((elapsed % 3600) // 60)
    secs = int(elapsed % 60)

    table = Table(
        title=f"BataviaHeat Overnight Logger | Poll #{poll_count} | "
              f"Changes: {change_count} | Errors: {errors} | "
              f"Runtime: {hours:02d}:{mins:02d}:{secs:02d} | Ctrl+C to stop",
        expand=True,
    )
    table.add_column("HR Addr", style="cyan", justify="right", width=7)
    table.add_column("Name", width=18)
    table.add_column("Value", style="green", width=14)
    table.add_column("Chg", style="red", width=3)
    table.add_column("│", width=1, style="dim")
    table.add_column("IR Addr", style="cyan", justify="right", width=7)
    table.add_column("Name", width=18)
    table.add_column("Value", style="green", width=14)
    table.add_column("Chg", style="red", width=3)

    hr_addrs = sorted(hr_current.keys())
    ir_addrs = sorted(ir_current.keys())
    max_rows = max(len(hr_addrs), len(ir_addrs))

    for i in range(max_rows):
        row = []
        if i < len(hr_addrs):
            addr = hr_addrs[i]
            val = hr_current[addr]
            chg = "●" if hr_prev.get(addr) is not None and hr_prev[addr] != val else ""
            row.extend([str(addr), HR_NAMES.get(addr, ""), format_value(addr, val, HR_NAMES), chg])
        else:
            row.extend(["", "", "", ""])
        row.append("│")
        if i < len(ir_addrs):
            addr = ir_addrs[i]
            val = ir_current[addr]
            chg = "●" if ir_prev.get(addr) is not None and ir_prev[addr] != val else ""
            row.extend([str(addr), IR_NAMES.get(addr, ""), format_value(addr, val, IR_NAMES), chg])
        else:
            row.extend(["", "", "", ""])
        table.add_row(*row)

    return table


def main():
    console.print("[bold cyan]BataviaHeat R290 Overnight Logger[/bold cyan]")
    console.print(f"Port: {PORT}, Baud: {BAUDRATE}, Slave: {SLAVE_ID}")
    console.print(f"Poll interval: {POLL_INTERVAL}s, Snapshot interval: {SNAPSHOT_INTERVAL}s")
    console.print(f"Monitoring: {len(HOLDING_ADDRS)} holding + {len(INPUT_ADDRS)} input registers")
    console.print(f"Changes log: {CHANGES_FILE.name}")
    console.print(f"Snapshots log: {SNAPSHOTS_FILE.name}\n")

    # Open CSV files
    changes_existed = CHANGES_FILE.exists()
    changes_fp = open(CHANGES_FILE, "a", newline="", encoding="utf-8")
    changes_writer = csv.writer(changes_fp)
    if not changes_existed:
        changes_writer.writerow(["timestamp", "reg_type", "address", "name", "old_value", "new_value",
                                  "old_formatted", "new_formatted"])

    snapshots_existed = SNAPSHOTS_FILE.exists()
    snapshots_fp = open(SNAPSHOTS_FILE, "a", newline="", encoding="utf-8")
    snapshots_writer = csv.writer(snapshots_fp)
    if not snapshots_existed:
        header = ["timestamp"]
        for a in HOLDING_ADDRS:
            header.append(f"HR[{a}]_{HR_NAMES.get(a, '')}")
        for a in INPUT_ADDRS:
            header.append(f"IR[{a}]_{IR_NAMES.get(a, '')}")
        snapshots_writer.writerow(header)

    client = create_client()
    if not client.connect():
        console.print("[red]Cannot connect![/red]")
        return

    console.print("[green]Connected. Starting logging...[/green]\n")

    hr_prev: dict[int, int] = {}
    ir_prev: dict[int, int] = {}
    poll_count = 0
    change_count = 0
    error_count = 0
    start_time = time.time()
    last_snapshot = 0

    try:
        with Live(console=console, refresh_per_second=0.5) as live:
            while running:
                poll_count += 1
                now = datetime.now()
                timestamp = now.isoformat(timespec="seconds")

                # Read registers
                try:
                    hr_current = read_block(client, "read_holding_registers",
                                            HOLDING_ADDRS, SLAVE_ID)
                    ir_current = read_block(client, "read_input_registers",
                                            INPUT_ADDRS, SLAVE_ID)
                except Exception:
                    error_count += 1
                    # Try reconnecting
                    try:
                        client.close()
                    except Exception:
                        pass
                    time.sleep(RECONNECT_DELAY)
                    client = create_client()
                    if not client.connect():
                        console.print(f"[red]Reconnect failed at {timestamp}[/red]")
                    continue

                # Detect and log changes
                for addr, val in hr_current.items():
                    old = hr_prev.get(addr)
                    if old is not None and val != old:
                        change_count += 1
                        name = HR_NAMES.get(addr, "")
                        changes_writer.writerow([
                            timestamp, "holding", addr, name, old, val,
                            format_value(addr, old, HR_NAMES),
                            format_value(addr, val, HR_NAMES),
                        ])

                for addr, val in ir_current.items():
                    old = ir_prev.get(addr)
                    if old is not None and val != old:
                        change_count += 1
                        name = IR_NAMES.get(addr, "")
                        changes_writer.writerow([
                            timestamp, "input", addr, name, old, val,
                            format_value(addr, old, IR_NAMES),
                            format_value(addr, val, IR_NAMES),
                        ])

                changes_fp.flush()

                # Periodic snapshot
                elapsed = time.time() - start_time
                if elapsed - last_snapshot >= SNAPSHOT_INTERVAL:
                    last_snapshot = elapsed
                    row = [timestamp]
                    for a in HOLDING_ADDRS:
                        row.append(hr_current.get(a, ""))
                    for a in INPUT_ADDRS:
                        row.append(ir_current.get(a, ""))
                    snapshots_writer.writerow(row)
                    snapshots_fp.flush()

                # Update display
                table = build_status_table(
                    hr_current, ir_current, hr_prev, ir_prev,
                    poll_count, change_count, start_time, error_count,
                )
                live.update(table)

                hr_prev = hr_current
                ir_prev = ir_current

                # Wait for next poll
                time.sleep(POLL_INTERVAL)

    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
    finally:
        client.close()
        changes_fp.close()
        snapshots_fp.close()
        elapsed = time.time() - start_time
        hours = int(elapsed // 3600)
        mins = int((elapsed % 3600) // 60)
        console.print(f"\n[yellow]Logger stopped after {hours}h {mins}m.[/yellow]")
        console.print(f"[yellow]Total polls: {poll_count}, Changes logged: {change_count}, "
                      f"Errors: {error_count}[/yellow]")
        console.print(f"[yellow]Files: {CHANGES_FILE.name}, {SNAPSHOTS_FILE.name}[/yellow]")


if __name__ == "__main__":
    main()

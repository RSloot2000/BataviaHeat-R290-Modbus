#!/usr/bin/env python3
"""
BataviaHeat ↔ Midea Register Probe

Reads the Midea/Newntide register range (HR[0-274]) from the BataviaHeat heat pump
and interprets values using BOTH the BataviaHeat register map AND the Midea online
register map. This helps identify which Midea registers have valid data.

Strategy:
  1. Read HR[0-274] in batch blocks
  2. Show side-by-side: Midea interpretation vs BataviaHeat interpretation
  3. Highlight registers that changed between reads (= live/dynamic data)
  4. Save results to JSON for later analysis

Usage:
    python midea_probe.py                   # Single snapshot
    python midea_probe.py --monitor         # Continuous monitoring (5s interval)
    python midea_probe.py --monitor -i 2    # Monitor with 2s interval

Press Ctrl+C to stop monitoring.
"""

import argparse
import json
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

from pymodbus.client import ModbusSerialClient
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.text import Text

# ─── Connection ──────────────────────────────────────────────────────────────
PORT = "COM5"
BAUDRATE = 9600
SLAVE_ID = 1

console = Console()
running = True


def signal_handler(sig, frame):
    global running
    running = False


signal.signal(signal.SIGINT, signal_handler)

# ─── Midea register definitions (from online_registers.py) ──────────────────

MIDEA_REGS: dict[int, dict] = {
    # Control (0-10)
    0:   {"name": "control_switches", "unit": None, "scale": 1, "type": "bitfield",
          "desc": "bit0=room temp ctrl, bit1=water Z1, bit2=DHW, bit3=water Z2"},
    1:   {"name": "operational_mode", "unit": None, "scale": 1,
          "desc": "1=Auto, 2=Cool, 3=Heat"},
    2:   {"name": "set_water_temp_t1s", "unit": "°C", "scale": 1, "type": "packed",
          "desc": "low byte=Z1, high byte=Z2"},
    3:   {"name": "air_temp_ts", "unit": "°C", "scale": 0.5,
          "desc": "raw ÷ 2.0"},
    4:   {"name": "set_dhw_temp_t5s", "unit": "°C", "scale": 1,
          "desc": "DHW setpoint"},
    5:   {"name": "function_settings", "unit": None, "scale": 1, "type": "bitfield",
          "desc": "bit4=disinfect, bit6=silent, bit10=ECO, bit12/13=weather comp"},
    6:   {"name": "weather_curve", "unit": None, "scale": 1,
          "desc": "low byte=Z1, high byte=Z2"},
    7:   {"name": "quiet_mode_hp", "unit": None, "scale": 1, "desc": "0/1"},
    8:   {"name": "holiday_away", "unit": None, "scale": 1, "desc": "0/1"},
    9:   {"name": "forced_rear_heater", "unit": None, "scale": 1, "desc": ""},
    10:  {"name": "t_sg_max", "unit": "hr", "scale": 1, "desc": ""},
    # Operational (100-141)
    100: {"name": "compressor_freq", "unit": "Hz", "scale": 1,
          "desc": "Compressor frequency. 0=off."},
    101: {"name": "op_mode_status", "unit": None, "scale": 1,
          "desc": "2=Cooling, 3=Heating, 5=DHW, else=OFF"},
    102: {"name": "fan_speed", "unit": "r/min", "scale": 1, "desc": ""},
    103: {"name": "pmv_openness", "unit": "%", "scale": 1,
          "desc": "EEV opening. Raw 0-480 → 0-100%"},
    104: {"name": "water_inlet_temp", "unit": "°C", "scale": 1,
          "desc": "signed int16, whole degrees"},
    105: {"name": "water_outlet_temp", "unit": "°C", "scale": 1,
          "desc": "signed int16, whole degrees"},
    106: {"name": "condenser_temp_t3", "unit": "°C", "scale": 1,
          "desc": "signed int16"},
    107: {"name": "outdoor_ambient", "unit": "°C", "scale": 1,
          "desc": "signed int16"},
    108: {"name": "discharge_temp", "unit": "°C", "scale": 1,
          "desc": "signed int16"},
    109: {"name": "return_air_temp", "unit": "°C", "scale": 1,
          "desc": "suction / return air"},
    110: {"name": "water_outlet_t1", "unit": "°C", "scale": 1, "desc": "total"},
    111: {"name": "sys_water_out_t1b", "unit": "°C", "scale": 1, "desc": "system"},
    112: {"name": "refrig_liquid_t2", "unit": "°C", "scale": 1, "desc": "liquid side"},
    113: {"name": "refrig_gas_t2b", "unit": "°C", "scale": 1, "desc": "gas side"},
    114: {"name": "room_temp_ta", "unit": "°C", "scale": 1, "desc": ""},
    115: {"name": "water_tank_t5", "unit": "°C", "scale": 1, "desc": "DHW tank"},
    116: {"name": "high_pressure", "unit": "kPa", "scale": 1, "desc": "unsigned"},
    117: {"name": "low_pressure", "unit": "kPa", "scale": 1, "desc": "unsigned"},
    118: {"name": "outdoor_current", "unit": "A", "scale": 0.1,
          "desc": "raw ÷ 10"},
    119: {"name": "outdoor_voltage", "unit": "V", "scale": 1, "desc": ""},
    120: {"name": "tbt1", "unit": "°C", "scale": 1, "desc": ""},
    121: {"name": "tbt2", "unit": "°C", "scale": 1, "desc": ""},
    122: {"name": "compressor_hours", "unit": "hr", "scale": 1, "desc": "cumulative"},
    123: {"name": "unit_capacity", "unit": "kWh", "scale": 1, "desc": ""},
    124: {"name": "current_fault", "unit": None, "scale": 1, "desc": "0=no fault"},
    125: {"name": "fault_1", "unit": None, "scale": 1, "desc": "history"},
    126: {"name": "fault_2", "unit": None, "scale": 1, "desc": "history"},
    127: {"name": "fault_3", "unit": None, "scale": 1, "desc": "history"},
    128: {"name": "status_bits", "unit": None, "scale": 1,
          "desc": "bit1=defrosting"},
    129: {"name": "load_outputs", "unit": None, "scale": 1,
          "desc": "bit3=pump_I, bit4=SV1, bit6=pump_O, bit13=RUN"},
    130: {"name": "sw_version", "unit": None, "scale": 1, "desc": ""},
    131: {"name": "controller_version", "unit": None, "scale": 1, "desc": ""},
    132: {"name": "comp_target_freq", "unit": "Hz", "scale": 1, "desc": ""},
    133: {"name": "dc_bus_current", "unit": "A", "scale": 1, "desc": ""},
    134: {"name": "dc_bus_voltage", "unit": "V", "scale": 10,
          "desc": "raw × 10 = V"},
    135: {"name": "tf_module_temp", "unit": "°C", "scale": 1,
          "desc": "inverter module temp"},
    136: {"name": "climate_curve_1", "unit": "°C", "scale": 1, "desc": "Z1 calc"},
    137: {"name": "climate_curve_2", "unit": "°C", "scale": 1, "desc": "Z2 calc"},
    138: {"name": "water_flow", "unit": "m³/h", "scale": 0.01,
          "desc": "raw × 0.01"},
    139: {"name": "limit_current", "unit": "kW", "scale": 1, "desc": ""},
    140: {"name": "hydraulic_ability", "unit": "kW", "scale": 0.01,
          "desc": "raw × 0.01"},
    141: {"name": "tsolar", "unit": "°C", "scale": 1, "desc": ""},
    # Energy (143-186)
    143: {"name": "elec_consumed_hi", "unit": "kWh", "scale": 0.01,
          "desc": "DWORD hi with 144"},
    144: {"name": "elec_consumed_lo", "unit": "kWh", "scale": 1, "desc": "DWORD lo"},
    145: {"name": "power_output_hi", "unit": "kWh", "scale": 0.01,
          "desc": "DWORD hi with 146"},
    146: {"name": "power_output_lo", "unit": "kWh", "scale": 1, "desc": "DWORD lo"},
    148: {"name": "rt_heat_capacity", "unit": "kW", "scale": 0.01, "desc": "realtime"},
    149: {"name": "rt_renewable_heat", "unit": "kW", "scale": 0.01, "desc": ""},
    150: {"name": "rt_heat_power", "unit": "kW", "scale": 0.01, "desc": "consumption"},
    151: {"name": "rt_heat_cop", "unit": "COP", "scale": 0.01, "desc": ""},
    152: {"name": "tot_heat_prod_hi", "unit": "kWh", "scale": 0.01, "desc": "DWORD"},
    153: {"name": "tot_heat_prod_lo", "unit": "kWh", "scale": 1, "desc": ""},
    154: {"name": "tot_renew_heat_hi", "unit": "kWh", "scale": 0.01, "desc": ""},
    155: {"name": "tot_renew_heat_lo", "unit": "kWh", "scale": 1, "desc": ""},
    156: {"name": "tot_heat_cons_hi", "unit": "kWh", "scale": 0.01, "desc": ""},
    157: {"name": "tot_heat_cons_lo", "unit": "kWh", "scale": 1, "desc": ""},
    158: {"name": "tot_heat_mstr_hi", "unit": "kWh", "scale": 0.01, "desc": "master"},
    159: {"name": "tot_heat_mstr_lo", "unit": "kWh", "scale": 1, "desc": ""},
    160: {"name": "tot_rnw_mstr_hi", "unit": "kWh", "scale": 0.01, "desc": ""},
    161: {"name": "tot_rnw_mstr_lo", "unit": "kWh", "scale": 1, "desc": ""},
    162: {"name": "tot_cons_mstr_hi", "unit": "kWh", "scale": 0.01, "desc": ""},
    163: {"name": "tot_cons_mstr_lo", "unit": "kWh", "scale": 1, "desc": ""},
    164: {"name": "tot_cop_heating", "unit": "COP", "scale": 0.01, "desc": ""},
    165: {"name": "tot_cool_prod_hi", "unit": "kWh", "scale": 0.01, "desc": ""},
    166: {"name": "tot_cool_prod_lo", "unit": "kWh", "scale": 1, "desc": ""},
    167: {"name": "tot_cool_rnw_hi", "unit": "kWh", "scale": 0.01, "desc": ""},
    168: {"name": "tot_cool_rnw_lo", "unit": "kWh", "scale": 1, "desc": ""},
    169: {"name": "tot_cool_cons_hi", "unit": "kWh", "scale": 0.01, "desc": ""},
    170: {"name": "tot_cool_cons_lo", "unit": "kWh", "scale": 1, "desc": ""},
    171: {"name": "tot_cop_cooling", "unit": "COP", "scale": 0.01, "desc": ""},
    172: {"name": "tot_dhw_prod_hi", "unit": "kWh", "scale": 0.01, "desc": ""},
    173: {"name": "tot_dhw_prod_lo", "unit": "kWh", "scale": 1, "desc": ""},
    174: {"name": "tot_dhw_rnw_hi", "unit": "kWh", "scale": 0.01, "desc": ""},
    175: {"name": "tot_dhw_rnw_lo", "unit": "kWh", "scale": 1, "desc": ""},
    176: {"name": "tot_dhw_cons_hi", "unit": "kWh", "scale": 0.01, "desc": ""},
    177: {"name": "tot_dhw_cons_lo", "unit": "kWh", "scale": 1, "desc": ""},
    178: {"name": "tot_cop_dhw", "unit": "COP", "scale": 0.01, "desc": ""},
    179: {"name": "rt_rnw_cool_cap", "unit": "kW", "scale": 0.01, "desc": ""},
    180: {"name": "rt_cool_capacity", "unit": "kW", "scale": 0.01, "desc": ""},
    181: {"name": "rt_cool_power", "unit": "kW", "scale": 0.01, "desc": ""},
    182: {"name": "rt_cool_eer", "unit": "COP", "scale": 0.01, "desc": ""},
    183: {"name": "rt_dhw_capacity", "unit": "kW", "scale": 0.01, "desc": ""},
    185: {"name": "rt_dhw_power", "unit": "kW", "scale": 0.01, "desc": ""},
    186: {"name": "rt_dhw_cop", "unit": "COP", "scale": 0.01, "desc": ""},
}

# BataviaHeat known registers in the 0-274 range (subset)
BATAVIA_REGS: dict[int, dict] = {
    0:   {"name": "operating_mode", "desc": "4=heating"},
    1:   {"name": "silent_mode", "desc": "1=on"},
    4:   {"name": "heating_target", "unit": "°C", "scale": 0.1, "desc": "raw 500=50°C"},
    5:   {"name": "buffer_tank_lower", "unit": "°C", "scale": 0.1, "desc": "51.7°C"},
    8:   {"name": "water_temp_1", "unit": "°C", "scale": 0.1, "desc": ""},
    9:   {"name": "water_temp_2", "unit": "°C", "scale": 0.1, "desc": ""},
    11:  {"name": "high_press_raw", "unit": "kPa", "scale": 0.1, "desc": ""},
    12:  {"name": "low_press_raw", "unit": "kPa", "scale": 0.1, "desc": ""},
    32:  {"name": "low_pressure", "unit": "bar", "scale": 0.1, "desc": "CONFIRMED"},
    33:  {"name": "high_pressure", "unit": "bar", "scale": 0.1, "desc": "CONFIRMED"},
    43:  {"name": "comp_max_freq", "unit": "rpm", "scale": 1, "desc": "raw 7000"},
    71:  {"name": "floor_heat_inlet", "unit": "°C", "scale": 0.1, "desc": "disconnected?"},
    94:  {"name": "cooling_target", "unit": "°C", "scale": 0.1, "desc": ""},
    95:  {"name": "zone_b_target", "unit": "°C", "scale": 0.1, "desc": "CONFIRMED"},
    103: {"name": "dhw_max_temp", "unit": "°C", "scale": 0.1, "desc": "66.6°C"},
    260: {"name": "pcb_version_ascii", "desc": "firmware string"},
}

# Disconnected sensor markers
DISCONNECTED = {32834, 32836}  # 0x8042, 0x8044

# Registers NOT present in R290 (Mosibi)
R290_EXCLUDED = {200, 214, 223, 247, 248, 249, 250, 251, 252, 253, 254}


def create_client() -> ModbusSerialClient:
    client = ModbusSerialClient(
        port=PORT, baudrate=BAUDRATE, parity="N", stopbits=1, bytesize=8,
        timeout=0.5, retries=0,  # Short timeout, we handle retries ourselves
    )
    if not client.connect():
        console.print(f"[red]Kan niet verbinden met {PORT}[/red]")
        sys.exit(1)
    return client


def flush_bus(client: ModbusSerialClient) -> None:
    """Wait for bus silence and flush stale data from the receive buffer."""
    if hasattr(client, "socket") and client.socket:
        # Drain any pending bytes
        client.socket.timeout = 0.05
        try:
            while client.socket.read(256):
                pass
        except Exception:
            pass
        client.socket.timeout = 0.5


def read_with_retry(
    client: ModbusSerialClient,
    addr: int,
    count: int,
    retries: int = 3,
) -> list[int] | None:
    """Read holding registers with retry and bus-flush between attempts."""
    for attempt in range(retries):
        flush_bus(client)
        time.sleep(0.15)  # Wait for bus idle (~150ms > full RTU frame time)
        try:
            resp = client.read_holding_registers(addr, count=count, device_id=SLAVE_ID)
            if not resp.isError() and hasattr(resp, "registers"):
                return resp.registers
        except Exception:
            pass
        time.sleep(0.1 * (attempt + 1))  # Backoff
    return None


def read_range(client: ModbusSerialClient, start: int, count: int) -> dict[int, int]:
    """Read a range of holding registers with collision-resistant batches.

    Uses small batch size (10) to reduce collision window on shared bus.
    Each batch is verified: if it fails, falls back to single-register reads.
    """
    results = {}
    batch_size = 10  # Small batches to minimize collision window

    total_batches = (count + batch_size - 1) // batch_size
    for batch_idx in range(total_batches):
        addr = start + batch_idx * batch_size
        n = min(batch_size, start + count - addr)

        regs = read_with_retry(client, addr, n)
        if regs is not None:
            for i, val in enumerate(regs):
                results[addr + i] = val
        else:
            # Batch failed: fall back to single-register reads
            console.print(f"  [yellow]Batch {addr}-{addr+n-1} failed, trying singles...[/yellow]")
            for single in range(addr, addr + n):
                val = read_with_retry(client, single, 1, retries=2)
                if val is not None:
                    results[single] = val[0]
                time.sleep(0.05)
        time.sleep(0.1)  # Inter-batch gap

    return results


def read_ir_baseline(client: ModbusSerialClient) -> dict[int, int]:
    """Read known BataviaHeat input registers for cross-reference."""
    ir_addrs = [22, 23, 24, 25, 32, 33, 53, 54, 66, 84, 85, 95,
                134, 135, 136, 137, 138, 139, 142]
    results = {}
    # Read in small batches to avoid collisions
    batches = [(22, 12), (32, 2), (53, 2), (66, 1), (84, 2), (95, 1),
               (134, 9)]  # 134-142
    for start, count in batches:
        flush_bus(client)
        time.sleep(0.15)
        regs = None
        for attempt in range(3):
            try:
                resp = client.read_input_registers(start, count=count, device_id=SLAVE_ID)
                if not resp.isError() and hasattr(resp, "registers"):
                    regs = resp.registers
                    break
            except Exception:
                pass
            time.sleep(0.1 * (attempt + 1))
        if regs is not None:
            for i, val in enumerate(regs):
                addr = start + i
                if addr in ir_addrs:
                    results[addr] = val
        else:
            # Single reads fallback
            for addr in ir_addrs:
                if start <= addr < start + count and addr not in results:
                    flush_bus(client)
                    time.sleep(0.15)
                    try:
                        resp = client.read_input_registers(addr, count=1, device_id=SLAVE_ID)
                        if not resp.isError():
                            results[addr] = resp.registers[0]
                    except Exception:
                        pass
                    time.sleep(0.05)
    return results


def format_value(raw: int, reg_def: dict | None, as_midea: bool = True) -> str:
    """Format a raw register value according to the register definition."""
    if raw in DISCONNECTED:
        return "[dim]DISCON[/dim]"

    signed = raw - 65536 if raw > 32767 else raw

    if reg_def is None:
        return f"{raw}"

    scale = reg_def.get("scale", 1)
    unit = reg_def.get("unit", "")
    reg_type = reg_def.get("type", "")

    if reg_type == "bitfield":
        return f"0b{raw:016b}"
    if reg_type == "packed":
        lo = raw & 0xFF
        hi = (raw >> 8) & 0xFF
        return f"lo={lo} hi={hi}"

    if scale == 1:
        val_str = f"{signed}"
    elif scale == 0.1:
        val_str = f"{signed * 0.1:.1f}"
    elif scale == 0.5:
        val_str = f"{signed * 0.5:.1f}"
    elif scale == 0.01:
        val_str = f"{signed * 0.01:.2f}"
    elif scale == 10:
        val_str = f"{signed * 10}"
    else:
        val_str = f"{signed * scale:.2f}"

    if unit:
        val_str += f" {unit}"

    return val_str


def build_table(
    hr_data: dict[int, int],
    ir_data: dict[int, int],
    prev_hr: dict[int, int] | None = None,
    read_num: int = 1,
) -> Table:
    """Build a rich table with side-by-side Midea vs BataviaHeat interpretation."""
    table = Table(
        title=f"BataviaHeat ↔ Midea Register Probe — Lezing #{read_num}",
        show_lines=True,
        width=130,
    )
    table.add_column("Addr", style="cyan", justify="right", width=5)
    table.add_column("Raw", justify="right", width=7)
    table.add_column("Hex", style="dim", justify="right", width=6)
    table.add_column("Δ", width=2)
    table.add_column("Midea interpretatie", width=35)
    table.add_column("BataviaHeat interpretatie", width=30)
    table.add_column("Midea naam", style="blue", width=22)
    table.add_column("Cross-ref", style="yellow", width=18)

    # Show interesting register groups
    groups = [
        ("── CONTROL (0-10) ──", 0, 10),
        ("── OPERATIONAL (100-141) ──", 100, 141),
        ("── ENERGY (143-186) ──", 143, 186),
    ]

    for group_label, g_start, g_end in groups:
        table.add_row(
            "", "", "", "", f"[bold magenta]{group_label}[/bold magenta]",
            "", "", "",
        )

        for addr in range(g_start, g_end + 1):
            if addr not in hr_data:
                continue

            raw = hr_data[addr]
            signed = raw - 65536 if raw > 32767 else raw

            # Skip disconnected in energy range
            if raw in DISCONNECTED and g_start >= 143:
                continue

            midea_def = MIDEA_REGS.get(addr)
            bh_def = BATAVIA_REGS.get(addr)

            # Change indicator
            changed = ""
            if prev_hr and addr in prev_hr:
                if hr_data[addr] != prev_hr[addr]:
                    changed = "[bold red]▲[/bold red]"

            # Midea interpretation
            if midea_def:
                midea_val = format_value(raw, midea_def, as_midea=True)
                midea_name = midea_def["name"]
            else:
                midea_val = f"{raw}"
                midea_name = ""

            # BataviaHeat interpretation
            if bh_def:
                bh_val = format_value(raw, bh_def, as_midea=False)
            elif raw in DISCONNECTED:
                bh_val = "[dim]DISCON[/dim]"
            else:
                bh_val = f"×0.1={signed * 0.1:.1f}"

            # Cross-reference with IR
            xref = ""
            if addr == 116 and 33 in ir_data:
                ir_bar = ir_data[33] * 0.1
                ir_signed = ir_data[33] - 65536 if ir_data[33] > 32767 else ir_data[33]
                xref = f"IR[33]={ir_signed*0.1:.1f}bar"
            elif addr == 117 and 32 in ir_data:
                ir_signed = ir_data[32] - 65536 if ir_data[32] > 32767 else ir_data[32]
                xref = f"IR[32]={ir_signed*0.1:.1f}bar"
            elif addr == 107 and 22 in ir_data:
                ir_signed = ir_data[22] - 65536 if ir_data[22] > 32767 else ir_data[22]
                xref = f"IR[22]={ir_signed*0.1:.1f}°C"
            elif addr == 108 and 25 in ir_data:
                ir_signed = ir_data[25] - 65536 if ir_data[25] > 32767 else ir_data[25]
                xref = f"IR[25]={ir_signed*0.1:.1f}°C"
            elif addr == 109 and 24 in ir_data:
                ir_signed = ir_data[24] - 65536 if ir_data[24] > 32767 else ir_data[24]
                xref = f"IR[24]={ir_signed*0.1:.1f}°C"
            elif addr == 138 and 54 in ir_data:
                xref = f"IR[54]={ir_data[54]} L/h"
            elif addr == 100 and 53 in ir_data:
                xref = f"IR[53]={ir_data[53]} rpm"

            # R290 excluded marker
            if addr in R290_EXCLUDED:
                midea_name = f"[dim]×R290[/dim] {midea_name}"

            # Highlight non-zero non-disconnected values
            raw_style = ""
            if raw not in (0, *DISCONNECTED):
                raw_style = "[bold green]"

            raw_text = f"{raw_style}{raw}[/]" if raw_style else f"{raw}"
            hex_text = f"0x{raw:04X}"

            table.add_row(
                str(addr), raw_text, hex_text, changed,
                midea_val, bh_val, midea_name, xref,
            )

    # Cross-reference summary
    table.add_row("", "", "", "", "[bold magenta]── IR BASELINE ──[/bold magenta]", "", "", "")
    ir_names = {
        22: "ambient", 23: "fin_coil", 24: "suction", 25: "discharge",
        32: "low_press", 33: "high_press", 53: "pump_spd", 54: "flow_rate",
        66: "pump_ctrl", 135: "plate_in", 136: "plate_out", 138: "mod_ambient",
    }
    for addr in sorted(ir_data):
        val = ir_data[addr]
        signed = val - 65536 if val > 32767 else val
        name = ir_names.get(addr, f"ir_{addr}")
        table.add_row(
            f"IR{addr}", str(val), f"0x{val:04X}", "",
            f"{signed * 0.1:.1f} (×0.1)", "", name, "",
        )

    return table


def save_results(
    hr_data: dict[int, int],
    ir_data: dict[int, int],
    output_path: Path,
) -> None:
    """Save probe results to JSON."""
    data = {
        "device": "BataviaHeat R290 3-8kW (Midea/Newntide probe)",
        "timestamp": datetime.now().isoformat(),
        "connection": {"port": PORT, "baudrate": BAUDRATE, "slave_id": SLAVE_ID},
        "holding_registers": {str(k): v for k, v in sorted(hr_data.items())},
        "input_registers": {str(k): v for k, v in sorted(ir_data.items())},
        "analysis": {},
    }

    # Auto-analysis: check which Midea registers look valid
    for addr, reg in MIDEA_REGS.items():
        if addr not in hr_data:
            continue
        raw = hr_data[addr]
        signed = raw - 65536 if raw > 32767 else raw

        verdict = "unknown"
        if raw in DISCONNECTED:
            verdict = "disconnected"
        elif raw == 0:
            verdict = "zero (compressor off?)"
        elif addr in BATAVIA_REGS:
            verdict = f"CONFLICT: BataviaHeat uses as '{BATAVIA_REGS[addr]['name']}'"
        else:
            # Check if value is plausible for the Midea definition
            unit = reg.get("unit", "")
            scale = reg.get("scale", 1)
            if unit == "°C":
                if -40 <= signed <= 120:
                    verdict = "PLAUSIBLE temp (whole °C)"
                elif -400 <= signed <= 1200:
                    verdict = "PLAUSIBLE temp if ×0.1"
                else:
                    verdict = f"UNLIKELY temp: {signed}°C"
            elif unit == "kPa":
                if 0 < raw < 5000:
                    verdict = f"PLAUSIBLE pressure: {raw} kPa"
                else:
                    verdict = f"unlikely pressure: {raw} kPa"
            elif unit == "Hz":
                if 0 <= raw <= 200:
                    verdict = f"PLAUSIBLE freq: {raw} Hz"
                else:
                    verdict = f"unlikely freq: {raw} Hz"
            elif unit in ("kW", "kWh", "COP"):
                val = signed * scale
                if 0 <= val <= 100:
                    verdict = f"PLAUSIBLE: {val:.2f} {unit}"
                else:
                    verdict = f"value: {val:.2f} {unit}"
            else:
                verdict = f"raw={raw}"

        data["analysis"][str(addr)] = {
            "midea_name": reg["name"],
            "raw": raw,
            "verdict": verdict,
        }

    output_path.write_text(json.dumps(data, indent=2))
    console.print(f"[green]Resultaten opgeslagen: {output_path}[/green]")


def main():
    parser = argparse.ArgumentParser(description="BataviaHeat ↔ Midea Register Probe")
    parser.add_argument("--monitor", "-m", action="store_true",
                        help="Continue monitoring (i.p.v. single snapshot)")
    parser.add_argument("--interval", "-i", type=float, default=5.0,
                        help="Poll interval in seconden (default: 5)")
    parser.add_argument("--output", "-o", default=None,
                        help="Output JSON bestand")
    args = parser.parse_args()

    console.print("[bold]BataviaHeat ↔ Midea Register Probe[/bold]")
    console.print(f"Verbinden met {PORT} @ {BAUDRATE} baud, slave ID {SLAVE_ID}...\n")

    client = create_client()
    console.print("[green]Verbonden![/green]\n")

    output_path = Path(args.output) if args.output else (
        Path(__file__).parent / f"midea_probe_{datetime.now():%Y%m%d_%H%M%S}.json"
    )

    prev_hr = None
    read_num = 0

    try:
        if args.monitor:
            with Live(console=console, refresh_per_second=1) as live:
                while running:
                    read_num += 1
                    hr_data = read_range(client, 0, 275)
                    ir_data = read_ir_baseline(client)
                    table = build_table(hr_data, ir_data, prev_hr, read_num)
                    live.update(table)
                    prev_hr = hr_data.copy()

                    # Wait for next poll
                    wait_until = time.time() + args.interval
                    while running and time.time() < wait_until:
                        time.sleep(0.1)
        else:
            read_num = 1
            console.print("[cyan]Lezen van HR[0-274] + IR baseline...[/cyan]")
            console.print("[dim]Kleine batches (10 regs) met bus-idle detectie tegen collisies[/dim]\n")
            hr_data = read_range(client, 0, 275)
            console.print(f"  [green]HR: {len(hr_data)} registers gelezen[/green]")
            ir_data = read_ir_baseline(client)
            console.print(f"  [green]IR: {len(ir_data)} registers gelezen[/green]\n")
            table = build_table(hr_data, ir_data, None, read_num)
            console.print(table)
            prev_hr = hr_data

    except KeyboardInterrupt:
        pass
    finally:
        # Always save
        if prev_hr:
            save_results(prev_hr, ir_data if 'ir_data' in dir() else {}, output_path)
        client.close()
        console.print("\n[yellow]Verbinding gesloten.[/yellow]")


if __name__ == "__main__":
    main()

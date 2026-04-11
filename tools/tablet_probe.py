#!/usr/bin/env python3
"""
BataviaHeat Tablet Probe — Direct interrogation of the controller tablet.

When connected directly to the tablet (display unit) via RS-485, this script:
  1. Scans all Modbus slave IDs (1-247) to find which ones the tablet responds to
  2. Tries Modbus Device Identification (FC 0x2B/0x0E) for manufacturer/model strings
  3. Does a full register scan on every responding slave ID (HR + IR, 0-10000)
  4. Searches for ASCII strings in register values (firmware version extraction)
  5. Tries all function codes (FC 01-04) to discover coils/discrete inputs too
  6. Saves all results to JSON

The tablet is the device that normally reads from the heat pump and displays
sensor values + allows parameter changes. It should know all register names.

Hardware setup: USB-RS485 adapter → tablet Modbus port (H1/H2 or A/B)
The heat pump outdoor unit should NOT be connected during this test.

Usage:
    python tablet_probe.py                # Full probe
    python tablet_probe.py --slave 1      # Probe only slave ID 1
    python tablet_probe.py --quick        # Slave scan + first 1000 regs only

Press Ctrl+C to stop at any time — partial results will be saved.
"""

import argparse
import json
import signal
import struct
import sys
import time
from datetime import datetime
from pathlib import Path

import serial
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table

console = Console()

PORT = "COM5"
BAUDRATE = 9600
TIMEOUT = 0.20  # Tablet may be slower than the heat pump controller
OUT_DIR = Path(__file__).parent / "data"

running = True


def signal_handler(sig, frame):
    global running
    running = False
    console.print("\n[yellow]Ctrl+C — saving partial results...[/yellow]")


signal.signal(signal.SIGINT, signal_handler)


# ═══════════════════════════════════════════════════════════════════════════════
# LOW-LEVEL MODBUS RTU
# ═══════════════════════════════════════════════════════════════════════════════

def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def build_request(slave_id: int, fc: int, start: int, count: int) -> bytes:
    """Build FC01-04 read request."""
    pdu = struct.pack(">BBHH", slave_id, fc, start, count)
    return pdu + struct.pack("<H", crc16(pdu))


def build_mei_request(slave_id: int, mei_type: int = 0x0E,
                      read_device_id: int = 0x01, object_id: int = 0x00) -> bytes:
    """Build FC 0x2B (Read Device Identification) request.
    read_device_id: 0x01=basic, 0x02=regular, 0x03=extended, 0x04=individual
    object_id: 0x00=VendorName, 0x01=ProductCode, 0x02=MajorMinorRevision, etc."""
    pdu = struct.pack(">BBBBB", slave_id, 0x2B, mei_type, read_device_id, object_id)
    return pdu + struct.pack("<H", crc16(pdu))


def transact(ser: serial.Serial, request: bytes, expect_min: int = 5) -> bytes:
    """Send request, wait for response. Returns raw response bytes or empty."""
    ser.reset_input_buffer()
    time.sleep(0.005)
    ser.write(request)
    ser.flush()

    # Wait for response
    time.sleep(0.05)
    response = bytearray()
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        waiting = ser.in_waiting
        if waiting:
            response.extend(ser.read(waiting))
            if len(response) >= expect_min:
                # Wait a tiny bit more for trailing bytes
                time.sleep(0.02)
                extra = ser.in_waiting
                if extra:
                    response.extend(ser.read(extra))
                break
            time.sleep(0.01)
        else:
            time.sleep(0.02)

    return bytes(response)


def parse_read_response(data: bytes, expected_slave: int, fc: int
                        ) -> tuple[bool, list[int], int | None]:
    """Parse FC01-04 response. Returns (success, values, exception_code)."""
    if len(data) < 5:
        return False, [], None

    actual_slave = data[0]
    actual_fc = data[1]

    # Exception response
    if actual_fc == (fc | 0x80):
        exc_code = data[2] if len(data) > 2 else -1
        return False, [], exc_code

    if actual_slave != expected_slave or actual_fc != fc:
        return False, [], None

    byte_count = data[2]
    if len(data) < 3 + byte_count + 2:
        return False, [], None

    # Verify CRC
    payload = data[:3 + byte_count]
    expected_crc = crc16(payload)
    actual_crc = struct.unpack("<H", data[3 + byte_count:5 + byte_count])[0]
    if expected_crc != actual_crc:
        return False, [], None

    # Parse values
    if fc in (0x01, 0x02):
        # Coils / Discrete inputs — bit-packed
        bits = []
        for byte_val in data[3:3 + byte_count]:
            for bit in range(8):
                bits.append((byte_val >> bit) & 1)
        return True, bits, None
    else:
        # Registers — 16-bit words
        values = []
        for i in range(0, byte_count, 2):
            values.append(struct.unpack(">H", data[3 + i:5 + i])[0])
        return True, values, None


def parse_mei_response(data: bytes) -> dict | None:
    """Parse FC 0x2B (MEI / Device Identification) response."""
    if len(data) < 8:
        return None

    slave = data[0]
    fc = data[1]
    if fc != 0x2B:
        if fc == 0xAB:  # Exception
            return {"error": f"exception code {data[2]}" if len(data) > 2 else "exception"}
        return None

    mei_type = data[2]
    read_dev_id = data[3]
    conformity = data[4]
    more_follows = data[5]
    next_object_id = data[6]
    num_objects = data[7]

    objects = {}
    pos = 8
    for _ in range(num_objects):
        if pos + 2 > len(data):
            break
        obj_id = data[pos]
        obj_len = data[pos + 1]
        pos += 2
        if pos + obj_len > len(data):
            break
        obj_val = data[pos:pos + obj_len]
        # Try to decode as ASCII
        try:
            objects[obj_id] = obj_val.decode("ascii")
        except (UnicodeDecodeError, ValueError):
            objects[obj_id] = obj_val.hex()
        pos += obj_len

    return {
        "slave": slave,
        "conformity": conformity,
        "more_follows": more_follows,
        "objects": objects,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1: SLAVE ID SCAN
# ═══════════════════════════════════════════════════════════════════════════════

def scan_slave_ids(ser: serial.Serial, slave_range: range) -> dict[int, list]:
    """Scan all slave IDs, return dict of {slave_id: [(fc, addr, value), ...]}."""
    console.print("\n[bold cyan]═══ PHASE 1: Slave ID Scan ═══[/bold cyan]")
    console.print(f"Scanning slave IDs {slave_range.start}-{slave_range.stop - 1} "
                  f"with FC03 (HR[0]) and FC04 (IR[0])...\n")

    found: dict[int, list] = {}

    with Progress(
        SpinnerColumn(), TextColumn("[cyan]Scanning"), BarColumn(),
        TextColumn("{task.percentage:>3.0f}%"),
        TextColumn("[dim]ID {task.fields[current]}, found: {task.fields[found]}[/dim]"),
        TimeElapsedColumn(), console=console,
    ) as progress:
        task = progress.add_task("scan", total=len(slave_range), current=0, found=0)

        for slave_id in slave_range:
            if not running:
                break
            progress.update(task, current=slave_id)
            hits = []

            for fc, label in [(0x03, "HR"), (0x04, "IR")]:
                req = build_request(slave_id, fc, 0, 1)
                resp = transact(ser, req, 7)
                ok, values, exc = parse_read_response(resp, slave_id, fc)
                if ok and values:
                    hits.append((label, 0, values[0]))
                elif exc is not None:
                    hits.append((f"{label}:exc{exc}", 0, 0))

            if hits:
                found[slave_id] = hits
                progress.console.print(
                    f"  [green]Slave {slave_id} RESPONDED![/green] "
                    + ", ".join(f"{h[0]}[{h[1]}]={h[2]}" for h in hits)
                )

            progress.advance(task)
            progress.update(task, found=len(found))

    console.print(f"\n[bold]Found {len(found)} responding slave(s).[/bold]")
    return found


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 2: DEVICE IDENTIFICATION (FC 0x2B)
# ═══════════════════════════════════════════════════════════════════════════════

DEVICE_ID_OBJECTS = {
    0x00: "VendorName",
    0x01: "ProductCode",
    0x02: "MajorMinorRevision",
    0x03: "VendorUrl",
    0x04: "ProductName",
    0x05: "ModelName",
    0x06: "UserApplicationName",
}


def probe_device_identification(ser: serial.Serial, slave_ids: list[int]) -> dict:
    """Try FC 0x2B on each slave ID with all read levels."""
    console.print("\n[bold cyan]═══ PHASE 2: Device Identification (FC 0x2B) ═══[/bold cyan]")

    results = {}
    for slave_id in slave_ids:
        if not running:
            break
        console.print(f"\n  Slave {slave_id}:")
        slave_results = {}

        # Try basic (0x01), regular (0x02), extended (0x03)
        for level, level_name in [(0x01, "basic"), (0x02, "regular"), (0x03, "extended")]:
            req = build_mei_request(slave_id, 0x0E, level, 0x00)
            resp = transact(ser, req, 10)
            parsed = parse_mei_response(resp)

            if parsed and "objects" in parsed and parsed["objects"]:
                slave_results[level_name] = parsed
                for obj_id, obj_val in parsed["objects"].items():
                    name = DEVICE_ID_OBJECTS.get(obj_id, f"Object_{obj_id}")
                    console.print(f"    [green]{name}: {obj_val}[/green]")
            elif parsed and "error" in parsed:
                console.print(f"    [yellow]{level_name}: {parsed['error']}[/yellow]")
            else:
                console.print(f"    [dim]{level_name}: no response[/dim]")

        # Also try individual object reads (0x04), one by one
        for obj_id in range(7):
            req = build_mei_request(slave_id, 0x0E, 0x04, obj_id)
            resp = transact(ser, req, 10)
            parsed = parse_mei_response(resp)
            if parsed and "objects" in parsed and parsed["objects"]:
                for oid, oval in parsed["objects"].items():
                    name = DEVICE_ID_OBJECTS.get(oid, f"Object_{oid}")
                    if oid not in slave_results.get("basic", {}).get("objects", {}):
                        console.print(f"    [green]{name} (individual): {oval}[/green]")
                        slave_results.setdefault("individual", {})[oid] = oval

        results[slave_id] = slave_results

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 3: FULL REGISTER SCAN
# ═══════════════════════════════════════════════════════════════════════════════

# Known ranges from heat pump + extended ranges for tablet-specific data
SCAN_RANGES = [
    # Ranges known from the heat pump
    (0, 300),
    (500, 700),
    (750, 950),
    (1000, 1200),
    (1283, 1500),
    (2000, 2200),
    (3000, 3100),
    (3300, 3400),
    (4000, 4200),
    (5000, 5100),
    (6000, 6100),
    (6400, 6600),
    (7000, 7200),
    (8000, 8200),
    (9000, 9200),
    (9900, 10000),
    # Extended hunt: tablet might use ranges beyond heat pump
    (10000, 10200),
    (15000, 15200),
    (20000, 20200),
    (30000, 30200),
    (40000, 40200),
    (50000, 50200),
    (60000, 60200),
]

SCAN_RANGES_QUICK = [
    (0, 300),
    (750, 950),
    (1000, 1100),
    (1283, 1420),
    (3300, 3400),
    (5000, 5020),
    (6400, 6520),
]

BLOCK_SIZE = 50  # Read N registers at a time


def scan_registers(ser: serial.Serial, slave_id: int, fc: int, fc_label: str,
                   ranges: list[tuple[int, int]]) -> dict[int, int]:
    """Scan register ranges, return {addr: value} for all that responded."""
    all_regs: dict[int, int] = {}
    total_addrs = sum(end - start for start, end in ranges)

    with Progress(
        SpinnerColumn(),
        TextColumn(f"[cyan]Slave {slave_id} {fc_label}"),
        BarColumn(),
        TextColumn("{task.percentage:>3.0f}%"),
        TextColumn("[dim]{task.fields[status]}[/dim]"),
        TimeElapsedColumn(), console=console,
    ) as progress:
        task = progress.add_task("scan", total=total_addrs, status="starting...")

        for range_start, range_end in ranges:
            if not running:
                break
            addr = range_start
            consecutive_fails = 0

            while addr < range_end and running:
                count = min(BLOCK_SIZE, range_end - addr)
                progress.update(task, status=f"addr {addr}-{addr + count - 1}")

                req = build_request(slave_id, fc, addr, count)
                resp = transact(ser, req, 5 + count * 2)
                ok, values, exc = parse_read_response(resp, slave_id, fc)

                if ok and values:
                    for i, v in enumerate(values):
                        all_regs[addr + i] = v
                    consecutive_fails = 0
                else:
                    consecutive_fails += 1
                    # If too many consecutive failures, skip ahead in this range
                    if consecutive_fails > 3:
                        skip = min(200, range_end - addr)
                        progress.advance(task, skip)
                        addr += skip
                        consecutive_fails = 0
                        continue

                progress.advance(task, count)
                addr += count

    return all_regs


def scan_coils(ser: serial.Serial, slave_id: int, fc: int, fc_label: str,
               max_addr: int = 1000) -> dict[int, int]:
    """Scan coils/discrete inputs in blocks of 100."""
    all_bits: dict[int, int] = {}
    block = 100
    addr = 0

    console.print(f"  Scanning {fc_label} 0-{max_addr}...", end=" ")
    consecutive_fails = 0

    while addr < max_addr and running:
        count = min(block, max_addr - addr)
        req = build_request(slave_id, fc, addr, count)
        resp = transact(ser, req)
        ok, bits, exc = parse_read_response(resp, slave_id, fc)

        if ok and bits:
            for i, b in enumerate(bits[:count]):
                all_bits[addr + i] = b
            consecutive_fails = 0
        else:
            consecutive_fails += 1
            if consecutive_fails > 3:
                break

        addr += count

    num_set = sum(1 for v in all_bits.values() if v)
    console.print(f"found {len(all_bits)} addresses, {num_set} set to 1")
    return all_bits


def full_register_scan(ser: serial.Serial, slave_ids: list[int],
                       ranges: list[tuple[int, int]]) -> dict:
    """Phase 3: scan all register types on all slave IDs."""
    console.print("\n[bold cyan]═══ PHASE 3: Full Register Scan ═══[/bold cyan]")
    total = sum(r[1] - r[0] for r in ranges)
    console.print(f"Scanning {total} addresses per slave across {len(ranges)} ranges\n")

    results = {}
    for slave_id in slave_ids:
        if not running:
            break
        console.print(f"\n[bold]Slave {slave_id}:[/bold]")
        slave_data = {}

        # Holding registers (FC03)
        hr = scan_registers(ser, slave_id, 0x03, "HR", ranges)
        if hr:
            console.print(f"  HR: {len(hr)} registers found, "
                          f"non-zero: {sum(1 for v in hr.values() if v)}")
            slave_data["holding_registers"] = hr

        # Input registers (FC04)
        ir = scan_registers(ser, slave_id, 0x04, "IR", ranges)
        if ir:
            console.print(f"  IR: {len(ir)} registers found, "
                          f"non-zero: {sum(1 for v in ir.values() if v)}")
            slave_data["input_registers"] = ir

        # Coils (FC01) — quick scan
        coils = scan_coils(ser, slave_id, 0x01, "Coils", 200)
        if coils:
            slave_data["coils"] = coils

        # Discrete inputs (FC02) — quick scan
        di = scan_coils(ser, slave_id, 0x02, "Discrete Inputs", 200)
        if di:
            slave_data["discrete_inputs"] = di

        results[slave_id] = slave_data

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 4: ASCII STRING EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

# Known firmware strings to search for
KNOWN_STRINGS = [
    "HL087A",      # Internal PCB (already found on slave 1)
    "HL081B",      # External PCB
    "VF281A",      # Driver board
    "1GDNET",      # Hardware ID
    "NET-DK",      # Software version
    "EcoHome",     # App name
    "Newntide",    # OEM brand
    "Midea",       # Original manufacturer
    "BataviaHeat", # Brand name
    "V100",        # Version prefix common in Midea
]


def extract_ascii_strings(registers: dict[int, int], min_len: int = 4) -> list[dict]:
    """Extract ASCII strings from register data.

    Tries both byte orders (Midea uses swapped: lo byte first, hi byte second)."""
    found_strings = []

    sorted_addrs = sorted(registers.keys())
    if not sorted_addrs:
        return found_strings

    for byte_order_name, extract in [
        ("swapped (Midea)", lambda v: bytes([v & 0xFF, (v >> 8) & 0xFF])),
        ("normal",          lambda v: bytes([(v >> 8) & 0xFF, v & 0xFF])),
    ]:
        # Build consecutive runs of addresses
        runs = []
        current_run_start = sorted_addrs[0]
        current_run_end = sorted_addrs[0]

        for addr in sorted_addrs[1:]:
            if addr == current_run_end + 1:
                current_run_end = addr
            else:
                runs.append((current_run_start, current_run_end))
                current_run_start = addr
                current_run_end = addr
        runs.append((current_run_start, current_run_end))

        for run_start, run_end in runs:
            raw_bytes = bytearray()
            for addr in range(run_start, run_end + 1):
                raw_bytes.extend(extract(registers[addr]))

            # Scan for printable ASCII runs
            current_str = ""
            str_start_addr = run_start
            for i, b in enumerate(raw_bytes):
                if 0x20 <= b <= 0x7E:
                    if not current_str:
                        str_start_addr = run_start + i // 2
                    current_str += chr(b)
                else:
                    if len(current_str) >= min_len:
                        found_strings.append({
                            "string": current_str,
                            "start_addr": str_start_addr,
                            "byte_order": byte_order_name,
                            "length": len(current_str),
                        })
                    current_str = ""

            if len(current_str) >= min_len:
                found_strings.append({
                    "string": current_str,
                    "start_addr": str_start_addr,
                    "byte_order": byte_order_name,
                    "length": len(current_str),
                })

    return found_strings


def analyze_strings(scan_results: dict) -> dict:
    """Phase 4: extract and analyze ASCII strings from all scan data."""
    console.print("\n[bold cyan]═══ PHASE 4: ASCII String Extraction ═══[/bold cyan]")

    all_strings = {}
    for slave_id, slave_data in scan_results.items():
        slave_strings = []

        for reg_type in ["holding_registers", "input_registers"]:
            regs = slave_data.get(reg_type, {})
            if not regs:
                continue

            strings = extract_ascii_strings(regs)
            for s in strings:
                s["register_type"] = reg_type
                slave_strings.append(s)

        if slave_strings:
            console.print(f"\n  [bold]Slave {slave_id}:[/bold] {len(slave_strings)} strings found")

            # Sort by length (longest first = most interesting)
            slave_strings.sort(key=lambda s: s["length"], reverse=True)
            for s in slave_strings[:30]:  # Show top 30
                # Highlight known firmware strings
                highlight = ""
                for known in KNOWN_STRINGS:
                    if known.lower() in s["string"].lower():
                        highlight = f" [bold green]← MATCH: {known}[/bold green]"
                        break

                console.print(
                    f"    {s['register_type'][:2].upper()}[{s['start_addr']}]: "
                    f'"{s["string"]}" ({s["length"]} chars, {s["byte_order"]}){highlight}'
                )

            all_strings[slave_id] = slave_strings

    return all_strings


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 5: COMPARISON WITH HEAT PUMP DATA
# ═══════════════════════════════════════════════════════════════════════════════

def compare_with_heatpump(scan_results: dict) -> dict:
    """Compare tablet register values with known heat pump register values."""
    console.print("\n[bold cyan]═══ PHASE 5: Comparison with Heat Pump Register Map ═══[/bold cyan]")

    try:
        from register_map import HOLDING_REGISTERS as HEATPUMP_HR
    except ImportError:
        console.print("  [yellow]Cannot import register_map.py — skipping comparison[/yellow]")
        return {}

    comparison = {}
    for slave_id, slave_data in scan_results.items():
        tablet_hr = slave_data.get("holding_registers", {})
        if not tablet_hr:
            continue

        matches = []
        differences = []
        tablet_only = []

        for addr in sorted(set(tablet_hr.keys()) | set(HEATPUMP_HR.keys())):
            in_tablet = addr in tablet_hr
            in_hp = addr in HEATPUMP_HR

            if in_tablet and in_hp:
                hp_name = HEATPUMP_HR[addr]["name"]
                t_val = tablet_hr[addr]
                if t_val == 0:
                    # Tablet might store 0 for sensor values (no hardware connected)
                    differences.append({
                        "addr": addr, "name": hp_name,
                        "tablet_val": t_val, "note": "tablet=0 (no sensor hardware?)"
                    })
                else:
                    matches.append({
                        "addr": addr, "name": hp_name, "tablet_val": t_val,
                    })
            elif in_tablet and not in_hp and tablet_hr[addr] != 0:
                tablet_only.append({"addr": addr, "value": tablet_hr[addr]})

        console.print(f"\n  [bold]Slave {slave_id}:[/bold]")
        console.print(f"    Matching addresses: {len(matches)}")
        console.print(f"    Different (tablet=0): {len(differences)}")
        console.print(f"    Tablet-only (non-zero): {len(tablet_only)}")

        if tablet_only:
            console.print(f"\n    [green]NEW registers only on tablet:[/green]")
            for t in tablet_only[:50]:
                console.print(f"      HR[{t['addr']}] = {t['value']} (0x{t['value']:04X})")

        comparison[slave_id] = {
            "matches": matches,
            "differences": differences,
            "tablet_only": tablet_only,
        }

    return comparison


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def save_results(results: dict, path: Path) -> None:
    """Save all results to JSON (convert int keys to str for JSON compat)."""
    def convert(obj):
        if isinstance(obj, dict):
            return {str(k): convert(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [convert(v) for v in obj]
        return obj

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(convert(results), f, indent=2, ensure_ascii=False)
    console.print(f"\n[green]Results saved to: {path}[/green]")


def main():
    parser = argparse.ArgumentParser(description="BataviaHeat Tablet Probe")
    parser.add_argument("--slave", type=int, default=None,
                        help="Probe only this slave ID (skip slave scan)")
    parser.add_argument("--quick", action="store_true",
                        help="Quick mode — smaller register ranges")
    parser.add_argument("--port", default=PORT, help=f"Serial port (default: {PORT})")
    parser.add_argument("--output", "-o", default=None, help="Output JSON file")
    args = parser.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = Path(args.output) if args.output else OUT_DIR / f"tablet_probe_{ts}.json"

    console.print("[bold]╔═══════════════════════════════════════════════════╗[/bold]")
    console.print("[bold]║    BataviaHeat Controller Tablet Probe           ║[/bold]")
    console.print("[bold]╚═══════════════════════════════════════════════════╝[/bold]")
    console.print(f"Port: {args.port}, Baud: {BAUDRATE}, Quick: {args.quick}")
    console.print(f"Output: {output_path}\n")

    ser = serial.Serial(
        port=args.port, baudrate=BAUDRATE, parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE, bytesize=serial.EIGHTBITS,
        timeout=TIMEOUT,
    )

    all_results: dict = {
        "device": "BataviaHeat Controller Tablet",
        "timestamp": datetime.now().isoformat(),
        "connection": {"port": args.port, "baudrate": BAUDRATE},
    }

    try:
        # Phase 1: Find slave IDs
        if args.slave:
            slave_ids = [args.slave]
            console.print(f"\n[dim]Skipping slave scan — using slave ID {args.slave}[/dim]")
        else:
            found = scan_slave_ids(ser, range(1, 248))
            slave_ids = sorted(found.keys())
            all_results["slave_scan"] = {
                str(k): [{"type": h[0], "addr": h[1], "value": h[2]} for h in v]
                for k, v in found.items()
            }

            if not slave_ids:
                console.print("\n[red bold]No slaves found! Check wiring.[/red bold]")
                console.print("  - Is the tablet powered on?")
                console.print("  - Are A+/B- wires correct?")
                console.print("  - Try swapping A/B wires")
                save_results(all_results, output_path)
                return

        # Phase 2: Device Identification
        if running:
            dev_id = probe_device_identification(ser, slave_ids)
            all_results["device_identification"] = dev_id

        # Phase 3: Full register scan
        if running:
            ranges = SCAN_RANGES_QUICK if args.quick else SCAN_RANGES
            scan_data = full_register_scan(ser, slave_ids, ranges)
            all_results["registers"] = scan_data

        # Phase 4: ASCII strings
        if running and "registers" in all_results:
            strings = analyze_strings(all_results["registers"])
            all_results["ascii_strings"] = strings

        # Phase 5: Comparison
        if running and "registers" in all_results:
            comp = compare_with_heatpump(all_results["registers"])
            all_results["comparison"] = comp

    finally:
        ser.close()
        save_results(all_results, output_path)

    # Summary
    console.print("\n[bold]═══ SUMMARY ═══[/bold]")
    console.print(f"Slave IDs found: {slave_ids}")
    for sid in slave_ids:
        if "registers" in all_results and sid in all_results["registers"]:
            rd = all_results["registers"][sid]
            for rt, label in [("holding_registers", "HR"), ("input_registers", "IR"),
                              ("coils", "Coils"), ("discrete_inputs", "DI")]:
                if rt in rd:
                    console.print(f"  Slave {sid} {label}: {len(rd[rt])} addresses")

    console.print(f"\nResults saved to: [green]{output_path}[/green]")
    console.print("\n[dim]Tip: Open the JSON file and look for firmware strings")
    console.print("and register addresses that don't exist on the heat pump.[/dim]")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
    except serial.SerialException as e:
        console.print(f"\n[red]Serial error: {e}[/red]")
        console.print("Is the USB-RS485 adapter connected to COM5?")
        sys.exit(1)

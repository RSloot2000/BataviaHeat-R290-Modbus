#!/usr/bin/env python3
"""
BataviaHeat Tablet Sniffer — Passively capture what the tablet requests.

The tablet (display unit) is a Modbus MASTER that polls the heat pump (slave).
When connected to the tablet's A/B lines with no heat pump on the bus, the
tablet will keep sending requests that go unanswered. This script captures
those requests to learn:

  - Which slave ID(s) the tablet addresses
  - Which function codes it uses (FC03/FC04/FC06/FC16 etc.)
  - Which register addresses it reads/writes
  - The polling pattern and interval
  - Any register addresses we haven't discovered yet

This is pure passive listening — we never transmit anything.

Usage:
    python tablet_sniffer.py                    # Run for 60 seconds
    python tablet_sniffer.py --duration 300     # Run for 5 minutes
    python tablet_sniffer.py --duration 0       # Run until Ctrl+C

Press Ctrl+C to stop — results are always saved.
"""

import argparse
import json
import signal
import struct
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import serial
from rich.console import Console
from rich.live import Live
from rich.table import Table

console = Console()

PORT = "COM5"
BAUDRATE = 9600
TIMEOUT = 0.05  # Short timeout for passive reading
OUT_DIR = Path(__file__).parent / "data"

running = True


def signal_handler(sig, frame):
    global running
    running = False


signal.signal(signal.SIGINT, signal_handler)


# ═══════════════════════════════════════════════════════════════════════════════
# CRC & FRAME PARSING
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


def validate_crc(frame: bytes) -> bool:
    """Check if the last 2 bytes are a valid CRC16 for the preceding data."""
    if len(frame) < 4:
        return False
    payload = frame[:-2]
    expected = crc16(payload)
    actual = struct.unpack("<H", frame[-2:])[0]
    return expected == actual


# FC descriptions
FC_NAMES = {
    0x01: "Read Coils",
    0x02: "Read Discrete Inputs",
    0x03: "Read Holding Registers",
    0x04: "Read Input Registers",
    0x05: "Write Single Coil",
    0x06: "Write Single Register",
    0x0F: "Write Multiple Coils",
    0x10: "Write Multiple Registers",
    0x17: "Read/Write Multiple Registers",
    0x2B: "Read Device Identification",
}


def parse_request(frame: bytes) -> dict | None:
    """Parse a Modbus RTU master request frame.

    Returns dict with parsed fields, or None if not a valid request."""
    if not validate_crc(frame):
        return None

    if len(frame) < 4:
        return None

    slave_id = frame[0]
    fc = frame[1]

    result = {
        "slave_id": slave_id,
        "fc": fc,
        "fc_name": FC_NAMES.get(fc, f"Unknown(0x{fc:02X})"),
        "raw_hex": frame.hex(),
        "length": len(frame),
    }

    if fc in (0x01, 0x02, 0x03, 0x04):
        # Read request: [slave][fc][start_hi][start_lo][count_hi][count_lo][crc_lo][crc_hi]
        if len(frame) == 8:
            start = struct.unpack(">H", frame[2:4])[0]
            count = struct.unpack(">H", frame[4:6])[0]
            result["start_addr"] = start
            result["count"] = count
            result["end_addr"] = start + count - 1
            return result

    elif fc == 0x05:
        # Write single coil: [slave][fc][addr_hi][addr_lo][value_hi][value_lo][crc]
        if len(frame) == 8:
            addr = struct.unpack(">H", frame[2:4])[0]
            value = struct.unpack(">H", frame[4:6])[0]
            result["start_addr"] = addr
            result["count"] = 1
            result["value"] = value
            return result

    elif fc == 0x06:
        # Write single register: [slave][fc][addr_hi][addr_lo][value_hi][value_lo][crc]
        if len(frame) == 8:
            addr = struct.unpack(">H", frame[2:4])[0]
            value = struct.unpack(">H", frame[4:6])[0]
            result["start_addr"] = addr
            result["count"] = 1
            result["value"] = value
            return result

    elif fc == 0x10:
        # Write multiple registers: [slave][fc][start_hi][start_lo][count_hi][count_lo][byte_count][data...][crc]
        if len(frame) >= 11:
            start = struct.unpack(">H", frame[2:4])[0]
            count = struct.unpack(">H", frame[4:6])[0]
            byte_count = frame[6]
            values = []
            for i in range(count):
                offset = 7 + i * 2
                if offset + 2 <= len(frame) - 2:
                    values.append(struct.unpack(">H", frame[offset:offset + 2])[0])
            result["start_addr"] = start
            result["count"] = count
            result["end_addr"] = start + count - 1
            result["values"] = values
            return result

    elif fc == 0x0F:
        # Write multiple coils
        if len(frame) >= 10:
            start = struct.unpack(">H", frame[2:4])[0]
            count = struct.unpack(">H", frame[4:6])[0]
            result["start_addr"] = start
            result["count"] = count
            result["end_addr"] = start + count - 1
            return result

    elif fc == 0x2B:
        # MEI — Device Identification
        if len(frame) >= 7:
            result["mei_type"] = frame[2]
            result["read_device_id"] = frame[3]
            result["object_id"] = frame[4]
            return result

    # Unknown FC but valid CRC — still report it
    result["start_addr"] = None
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# FRAME COLLECTOR (inter-frame gap based)
# ═══════════════════════════════════════════════════════════════════════════════

def collect_frames(ser: serial.Serial, duration: float) -> list[tuple[float, bytes]]:
    """Collect raw Modbus RTU frames by detecting inter-frame gaps.

    At 9600 baud, 1 byte = ~1.04ms, so a 3.5 character gap = ~3.6ms.
    We use 4ms as the frame delimiter. Any bytes arriving with >4ms gap
    between them are considered separate frames.

    Returns list of (timestamp, frame_bytes)."""

    frames: list[tuple[float, bytes]] = []
    current_frame = bytearray()
    last_byte_time = 0.0
    frame_gap = 0.004  # 4ms inter-frame gap for 9600 baud

    start_time = time.monotonic()
    end_time = start_time + duration if duration > 0 else float("inf")

    # Stats for live display
    stats = {
        "frames_total": 0,
        "frames_valid": 0,
        "bytes_total": 0,
        "unique_requests": set(),
        "slaves_seen": set(),
        "fcs_seen": set(),
    }

    def make_status_table() -> Table:
        t = Table(title="Tablet Sniffer - Live", show_header=False, 
                  border_style="cyan", width=60)
        elapsed = time.monotonic() - start_time
        t.add_row("Elapsed", f"{elapsed:.1f}s")
        t.add_row("Raw frames", str(stats["frames_total"]))
        t.add_row("Valid Modbus requests", str(stats["frames_valid"]))
        t.add_row("Bytes captured", str(stats["bytes_total"]))
        t.add_row("Slave IDs seen", str(sorted(stats["slaves_seen"])) if stats["slaves_seen"] else "-")
        t.add_row("Function codes", str(sorted(stats["fcs_seen"])) if stats["fcs_seen"] else "-")
        t.add_row("Unique addr ranges", str(len(stats["unique_requests"])))
        remaining = end_time - time.monotonic() if duration > 0 else float("inf")
        t.add_row("Remaining", f"{remaining:.0f}s" if remaining < float("inf") else "Ctrl+C to stop")
        return t

    console.print("[bold cyan]═══ Passive Tablet Sniffer ═══[/bold cyan]")
    console.print(f"Listening on {PORT} at {BAUDRATE} baud...")
    console.print("The tablet should be sending requests to the heat pump.")
    console.print("We'll capture everything it sends.\n")

    with Live(make_status_table(), console=console, refresh_per_second=2) as live:
        while running and time.monotonic() < end_time:
            waiting = ser.in_waiting
            if waiting:
                data = ser.read(waiting)
                now = time.monotonic()

                for byte in data:
                    if current_frame and (now - last_byte_time) > frame_gap:
                        # Gap detected — previous frame is complete
                        frame = bytes(current_frame)
                        frames.append((now - start_time, frame))
                        stats["frames_total"] += 1
                        stats["bytes_total"] += len(frame)

                        # Quick parse for live display
                        parsed = parse_request(frame)
                        if parsed:
                            stats["frames_valid"] += 1
                            stats["slaves_seen"].add(parsed["slave_id"])
                            stats["fcs_seen"].add(parsed["fc"])
                            if parsed.get("start_addr") is not None:
                                key = (parsed["slave_id"], parsed["fc"],
                                       parsed["start_addr"], parsed.get("count", 0))
                                stats["unique_requests"].add(key)

                        current_frame = bytearray()

                    current_frame.append(byte)
                    last_byte_time = now

                live.update(make_status_table())
            else:
                # No data — check if we have a pending frame that's been idle
                now = time.monotonic()
                if current_frame and (now - last_byte_time) > frame_gap:
                    frame = bytes(current_frame)
                    frames.append((now - start_time, frame))
                    stats["frames_total"] += 1
                    stats["bytes_total"] += len(frame)

                    parsed = parse_request(frame)
                    if parsed:
                        stats["frames_valid"] += 1
                        stats["slaves_seen"].add(parsed["slave_id"])
                        stats["fcs_seen"].add(parsed["fc"])
                        if parsed.get("start_addr") is not None:
                            key = (parsed["slave_id"], parsed["fc"],
                                   parsed["start_addr"], parsed.get("count", 0))
                            stats["unique_requests"].add(key)

                    current_frame = bytearray()
                    live.update(make_status_table())

                time.sleep(0.001)

    # Flush any remaining bytes
    if current_frame:
        frames.append((time.monotonic() - start_time, bytes(current_frame)))

    return frames


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════

def analyze_frames(frames: list[tuple[float, bytes]]) -> dict:
    """Analyze captured frames and produce a comprehensive report."""
    console.print(f"\n[bold cyan]═══ Analysis of {len(frames)} captured frames ═══[/bold cyan]\n")

    requests: list[dict] = []
    invalid_frames: list[dict] = []

    for ts, frame in frames:
        parsed = parse_request(frame)
        if parsed:
            parsed["timestamp"] = round(ts, 4)
            requests.append(parsed)
        else:
            invalid_frames.append({
                "timestamp": round(ts, 4),
                "hex": frame.hex(),
                "length": len(frame),
            })

    console.print(f"Total frames: {len(frames)}")
    console.print(f"Valid Modbus requests: {len(requests)}")
    console.print(f"Invalid/corrupt frames: {len(invalid_frames)}")

    if not requests:
        console.print("\n[yellow]No valid Modbus requests captured![/yellow]")
        console.print("Possible reasons:")
        console.print("  - Tablet is not sending (powered off? different baud rate?)")
        console.print("  - A/B wires are swapped")
        console.print("  - Tablet doesn't poll when heat pump is absent")
        console.print("  - Different baud rate (try 19200, 4800)")
        return {"frames": len(frames), "requests": 0}

    # ---- Slave IDs ----
    slave_counts = defaultdict(int)
    for r in requests:
        slave_counts[r["slave_id"]] += 1

    console.print(f"\n[bold]Slave IDs addressed by tablet:[/bold]")
    for sid, count in sorted(slave_counts.items()):
        console.print(f"  Slave {sid}: {count} requests")

    # ---- Function Codes ----
    fc_counts = defaultdict(int)
    for r in requests:
        fc_counts[(r["fc"], r["fc_name"])] += 1

    console.print(f"\n[bold]Function codes used:[/bold]")
    for (fc, name), count in sorted(fc_counts.items()):
        console.print(f"  FC 0x{fc:02X} ({name}): {count} requests")

    # ---- Register map ----
    read_ranges: dict[int, list[dict]] = defaultdict(list)  # keyed by slave_id
    write_requests: list[dict] = []

    for r in requests:
        if r.get("start_addr") is None:
            continue
        if r["fc"] in (0x03, 0x04, 0x01, 0x02):
            read_ranges[r["slave_id"]].append(r)
        elif r["fc"] in (0x05, 0x06, 0x10):
            write_requests.append(r)

    # Deduplicate read ranges
    console.print(f"\n[bold]Register ranges the tablet reads:[/bold]")
    unique_ranges: dict[int, list] = {}
    for sid in sorted(read_ranges.keys()):
        seen = set()
        unique = []
        for r in read_ranges[sid]:
            key = (r["fc"], r["start_addr"], r.get("count", 0))
            if key not in seen:
                seen.add(key)
                unique.append(r)
        unique.sort(key=lambda x: (x["fc"], x["start_addr"]))
        unique_ranges[sid] = unique

        console.print(f"\n  [bold]Slave {sid}:[/bold]")
        table = Table(show_header=True, border_style="dim")
        table.add_column("FC", style="cyan", width=5)
        table.add_column("Type", width=12)
        table.add_column("Start", style="green", width=7)
        table.add_column("Count", width=7)
        table.add_column("End", style="green", width=7)
        table.add_column("Polls", width=7)

        for r in unique:
            fc_str = f"0x{r['fc']:02X}"
            count_for_range = sum(
                1 for rr in read_ranges[sid]
                if rr["fc"] == r["fc"] and rr["start_addr"] == r["start_addr"]
            )
            table.add_row(
                fc_str,
                r["fc_name"].replace("Read ", ""),
                str(r["start_addr"]),
                str(r.get("count", "?")),
                str(r.get("end_addr", "?")),
                str(count_for_range),
            )

        console.print(table)

    # Write requests
    if write_requests:
        console.print(f"\n[bold]Write requests from tablet:[/bold]")
        write_table = Table(show_header=True, border_style="dim")
        write_table.add_column("Time", width=8)
        write_table.add_column("Slave", width=6)
        write_table.add_column("FC", width=5)
        write_table.add_column("Addr", width=7)
        write_table.add_column("Value(s)", width=30)

        seen_writes = set()
        for w in write_requests:
            key = (w["slave_id"], w["fc"], w["start_addr"],
                   str(w.get("value", w.get("values", ""))))
            if key in seen_writes:
                continue
            seen_writes.add(key)

            vals = str(w.get("value", w.get("values", "?")))
            write_table.add_row(
                f"{w['timestamp']:.2f}",
                str(w["slave_id"]),
                f"0x{w['fc']:02X}",
                str(w["start_addr"]),
                vals,
            )

        console.print(write_table)

    # ---- Timing analysis ----
    if len(requests) > 1:
        intervals = []
        for i in range(1, len(requests)):
            if requests[i]["slave_id"] == requests[i-1]["slave_id"]:
                dt = requests[i]["timestamp"] - requests[i-1]["timestamp"]
                if dt > 0:
                    intervals.append(dt)

        if intervals:
            console.print(f"\n[bold]Timing:[/bold]")
            console.print(f"  Avg interval between requests: {sum(intervals)/len(intervals)*1000:.1f} ms")
            console.print(f"  Min: {min(intervals)*1000:.1f} ms, Max: {max(intervals)*1000:.1f} ms")

    # ---- Compare with our known register map ----
    console.print(f"\n[bold]Comparison with known register_map.py:[/bold]")
    try:
        from register_map import HOLDING_REGISTERS as HP_HR
        known_addrs = set(HP_HR.keys())
    except ImportError:
        known_addrs = set()
        console.print("  [yellow]Could not import register_map.py[/yellow]")

    if known_addrs:
        tablet_addrs = set()
        for sid, ranges_list in unique_ranges.items():
            for r in ranges_list:
                if r["fc"] in (0x03, 0x04):
                    for a in range(r["start_addr"], r.get("end_addr", r["start_addr"]) + 1):
                        tablet_addrs.add(a)

        both = tablet_addrs & known_addrs
        tablet_only = tablet_addrs - known_addrs
        heatpump_only = known_addrs - tablet_addrs

        console.print(f"  Registers in both: {len(both)}")
        console.print(f"  Tablet reads but NOT in our map: {len(tablet_only)}")
        if tablet_only:
            # Group into ranges for readability
            sorted_new = sorted(tablet_only)
            ranges_str = []
            start = sorted_new[0]
            end = start
            for a in sorted_new[1:]:
                if a == end + 1:
                    end = a
                else:
                    ranges_str.append(f"{start}-{end}" if start != end else str(start))
                    start = a
                    end = a
            ranges_str.append(f"{start}-{end}" if start != end else str(start))
            console.print(f"    NEW ranges: {', '.join(ranges_str[:30])}")

        console.print(f"  In our map but tablet doesn't read: {len(heatpump_only)}")

    # Build result
    result = {
        "capture_info": {
            "total_frames": len(frames),
            "valid_requests": len(requests),
            "invalid_frames": len(invalid_frames),
            "duration_s": round(frames[-1][0] if frames else 0, 2),
        },
        "slave_ids": dict(slave_counts),
        "function_codes": {f"0x{fc:02X}_{name}": cnt for (fc, name), cnt in fc_counts.items()},
        "unique_read_ranges": {
            str(sid): [
                {"fc": r["fc"], "start": r["start_addr"],
                 "count": r.get("count"), "end": r.get("end_addr")}
                for r in ranges_list
            ]
            for sid, ranges_list in unique_ranges.items()
        },
        "write_requests": [
            {"slave": w["slave_id"], "fc": w["fc"], "addr": w["start_addr"],
             "value": w.get("value"), "values": w.get("values"),
             "time": w["timestamp"]}
            for w in write_requests
        ],
        "all_requests": requests,
        "invalid_frames": invalid_frames[:100],  # Limit stored invalid frames
    }

    if known_addrs and tablet_addrs:
        result["comparison"] = {
            "both": sorted(both),
            "tablet_only": sorted(tablet_only),
            "heatpump_only": sorted(heatpump_only),
        }

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="BataviaHeat Tablet Sniffer")
    parser.add_argument("--duration", "-d", type=float, default=60,
                        help="Capture duration in seconds (0 = until Ctrl+C, default: 60)")
    parser.add_argument("--port", default=PORT, help=f"Serial port (default: {PORT})")
    parser.add_argument("--baud", type=int, default=BAUDRATE,
                        help=f"Baud rate (default: {BAUDRATE})")
    parser.add_argument("--output", "-o", default=None, help="Output JSON file")
    args = parser.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = Path(args.output) if args.output else OUT_DIR / f"tablet_sniff_{ts}.json"

    console.print("[bold]╔═══════════════════════════════════════════════════╗[/bold]")
    console.print("[bold]║    BataviaHeat Tablet Sniffer (Passive)          ║[/bold]")
    console.print("[bold]╚═══════════════════════════════════════════════════╝[/bold]")
    console.print(f"Port: {args.port}, Baud: {args.baud}")
    console.print(f"Duration: {'until Ctrl+C' if args.duration == 0 else f'{args.duration}s'}")
    console.print(f"Output: {output_path}")

    ser = serial.Serial(
        port=args.port, baudrate=args.baud, parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE, bytesize=serial.EIGHTBITS,
        timeout=TIMEOUT,
    )

    try:
        frames = collect_frames(ser, args.duration)
    finally:
        ser.close()

    if frames:
        results = analyze_frames(frames)
        results["connection"] = {"port": args.port, "baudrate": args.baud}
        results["timestamp"] = datetime.now().isoformat()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        console.print(f"\n[green]Results saved to: {output_path}[/green]")
    else:
        console.print("\n[yellow]No frames captured.[/yellow]")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
    except serial.SerialException as e:
        console.print(f"\n[red]Serial error: {e}[/red]")
        sys.exit(1)

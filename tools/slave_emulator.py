#!/usr/bin/env python3
"""
BataviaHeat Slave Emulator — Pretend to be the heat pump so the tablet talks.

The tablet (display unit) is a Modbus master that polls slave ID 1.
When the heat pump doesn't answer, the tablet retries the same first request
forever. By emulating the heat pump (responding to the tablet's reads with
dummy data), the tablet will proceed through its full poll cycle, revealing
ALL register ranges it knows about.

This script:
  1. Listens for Modbus requests on the bus
  2. Responds to FC03 (Read Holding Registers) and FC04 (Read Input Registers)
     as slave ID 1, returning zero-filled register data
  3. Responds to FC06/FC10 (Write) with proper acknowledgements
  4. Logs every unique request the tablet makes
  5. After running for a while, saves a complete map of what the tablet polls

The emulator answers ALL register ranges — it doesn't need to know in advance
which addresses the tablet will ask for.

Usage:
    python slave_emulator.py                    # Run for 120 seconds
    python slave_emulator.py --duration 300     # Run for 5 minutes
    python slave_emulator.py --duration 0       # Run until Ctrl+C
    python slave_emulator.py --slave 1 --slave 2  # Respond as multiple slaves

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
TIMEOUT = 0.003  # Very short — we need to respond fast
OUT_DIR = Path(__file__).parent / "data"

running = True


def signal_handler(sig, frame):
    global running
    running = False


signal.signal(signal.SIGINT, signal_handler)


# ═══════════════════════════════════════════════════════════════════════════════
# CRC
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


def add_crc(data: bytes) -> bytes:
    return data + struct.pack("<H", crc16(data))


def check_crc(frame: bytes) -> bool:
    if len(frame) < 4:
        return False
    payload = frame[:-2]
    expected = crc16(payload)
    actual = struct.unpack("<H", frame[-2:])[0]
    return expected == actual


# ═══════════════════════════════════════════════════════════════════════════════
# REQUEST PARSING
# ═══════════════════════════════════════════════════════════════════════════════

FC_NAMES = {
    0x01: "Read Coils",
    0x02: "Read Discrete Inputs",
    0x03: "Read Holding Registers",
    0x04: "Read Input Registers",
    0x05: "Write Single Coil",
    0x06: "Write Single Register",
    0x0F: "Write Multiple Coils",
    0x10: "Write Multiple Registers",
    0x2B: "Device Identification",
}


def parse_request(frame: bytes) -> dict | None:
    """Parse a Modbus RTU request frame."""
    if not check_crc(frame):
        return None
    if len(frame) < 4:
        return None

    slave_id = frame[0]
    fc = frame[1]

    result = {
        "slave_id": slave_id,
        "fc": fc,
        "fc_name": FC_NAMES.get(fc, f"FC_0x{fc:02X}"),
        "raw": frame,
    }

    if fc in (0x01, 0x02, 0x03, 0x04) and len(frame) == 8:
        result["start"] = struct.unpack(">H", frame[2:4])[0]
        result["count"] = struct.unpack(">H", frame[4:6])[0]
        return result

    elif fc == 0x05 and len(frame) == 8:
        result["addr"] = struct.unpack(">H", frame[2:4])[0]
        result["value"] = struct.unpack(">H", frame[4:6])[0]
        result["start"] = result["addr"]
        result["count"] = 1
        return result

    elif fc == 0x06 and len(frame) == 8:
        result["addr"] = struct.unpack(">H", frame[2:4])[0]
        result["value"] = struct.unpack(">H", frame[4:6])[0]
        result["start"] = result["addr"]
        result["count"] = 1
        return result

    elif fc == 0x10 and len(frame) >= 11:
        result["start"] = struct.unpack(">H", frame[2:4])[0]
        result["count"] = struct.unpack(">H", frame[4:6])[0]
        byte_count = frame[6]
        values = []
        for i in range(result["count"]):
            off = 7 + i * 2
            if off + 2 <= len(frame) - 2:
                values.append(struct.unpack(">H", frame[off:off + 2])[0])
        result["values"] = values
        return result

    elif fc == 0x0F and len(frame) >= 10:
        result["start"] = struct.unpack(">H", frame[2:4])[0]
        result["count"] = struct.unpack(">H", frame[4:6])[0]
        return result

    # Unknown FC but valid CRC
    result["start"] = None
    result["count"] = None
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# RESPONSE BUILDING
# ═══════════════════════════════════════════════════════════════════════════════

def build_read_registers_response(slave_id: int, fc: int, count: int,
                                  values: list[int] | None = None) -> bytes:
    """Build FC03/FC04 read response with register data."""
    byte_count = count * 2
    if values is None:
        values = [0] * count  # Default: return zeros

    pdu = struct.pack(">BBB", slave_id, fc, byte_count)
    for v in values[:count]:
        pdu += struct.pack(">H", v & 0xFFFF)
    return add_crc(pdu)


def build_read_bits_response(slave_id: int, fc: int, count: int) -> bytes:
    """Build FC01/FC02 response with coil/discrete input data (all zeros)."""
    byte_count = (count + 7) // 8
    pdu = struct.pack(">BBB", slave_id, fc, byte_count)
    pdu += b"\x00" * byte_count
    return add_crc(pdu)


def build_write_single_response(slave_id: int, fc: int,
                                addr: int, value: int) -> bytes:
    """Build FC05/FC06 write response (echo back the request)."""
    pdu = struct.pack(">BBHH", slave_id, fc, addr, value)
    return add_crc(pdu)


def build_write_multiple_response(slave_id: int, fc: int,
                                  start: int, count: int) -> bytes:
    """Build FC0F/FC10 write multiple response."""
    pdu = struct.pack(">BBHH", slave_id, fc, start, count)
    return add_crc(pdu)


def build_exception_response(slave_id: int, fc: int, exc_code: int = 0x01) -> bytes:
    """Build Modbus exception response."""
    pdu = struct.pack(">BBB", slave_id, fc | 0x80, exc_code)
    return add_crc(pdu)


# ═══════════════════════════════════════════════════════════════════════════════
# FRAME COLLECTOR (fast, for real-time response)
# ═══════════════════════════════════════════════════════════════════════════════

def collect_frame(ser: serial.Serial, max_wait: float = 0.5) -> bytes | None:
    """Wait for and collect one complete Modbus RTU frame.

    Uses inter-character gap detection (3.5 char times = ~3.6ms at 9600 baud).
    Returns the frame bytes, or None if timeout."""
    frame_gap = 0.004  # 4ms gap = frame delimiter at 9600 baud

    # Wait for first byte
    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        if ser.in_waiting:
            break
        time.sleep(0.0005)
    else:
        return None

    # Collect bytes until gap
    buf = bytearray()
    last_byte_time = time.monotonic()

    while True:
        waiting = ser.in_waiting
        if waiting:
            buf.extend(ser.read(waiting))
            last_byte_time = time.monotonic()
        else:
            now = time.monotonic()
            if buf and (now - last_byte_time) > frame_gap:
                break  # Frame complete
            if now - last_byte_time > max_wait:
                break  # Timeout
            time.sleep(0.0003)

    return bytes(buf) if buf else None


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN EMULATOR LOOP
# ═══════════════════════════════════════════════════════════════════════════════

def run_emulator(ser: serial.Serial, slave_ids: set[int], duration: float) -> dict:
    """Run the slave emulator, respond to tablet requests, log everything."""

    start_time = time.monotonic()
    end_time = start_time + duration if duration > 0 else float("inf")

    # Statistics
    stats = {
        "requests_total": 0,
        "responses_sent": 0,
        "unique_ranges": set(),
        "writes_seen": [],
        "all_requests": [],
        "invalid_frames": 0,
        "ignored_slaves": set(),
    }

    # Log of unique ranges per (slave, fc)
    range_log: dict[tuple, list] = defaultdict(list)

    def make_table() -> Table:
        t = Table(title="Slave Emulator - Live", show_header=False,
                  border_style="cyan", width=64)
        elapsed = time.monotonic() - start_time
        t.add_row("Elapsed", f"{elapsed:.1f}s")
        t.add_row("Requests received", str(stats["requests_total"]))
        t.add_row("Responses sent", str(stats["responses_sent"]))
        t.add_row("Unique poll ranges", str(len(stats["unique_ranges"])))
        t.add_row("Write requests", str(len(stats["writes_seen"])))
        t.add_row("Invalid frames", str(stats["invalid_frames"]))
        t.add_row("Emulating slave IDs", str(sorted(slave_ids)))

        # Show last few unique ranges
        recent = sorted(stats["unique_ranges"])[-8:]
        for key in recent:
            t.add_row("", f"  FC{key[1]:02X} [{key[2]}-{key[2]+key[3]-1}]")

        remaining = end_time - time.monotonic() if duration > 0 else float("inf")
        t.add_row("Remaining", f"{remaining:.0f}s" if remaining < float("inf") else "Ctrl+C")
        return t

    console.print("[bold cyan]═══ Slave Emulator Running ═══[/bold cyan]")
    console.print(f"Emulating slave ID(s): {sorted(slave_ids)}")
    console.print("Responding to all FC03/FC04 reads with zeros...")
    console.print("Waiting for tablet requests...\n")

    with Live(make_table(), console=console, refresh_per_second=2) as live:
        while running and time.monotonic() < end_time:
            # Wait for a frame from the tablet
            frame = collect_frame(ser, max_wait=0.2)
            if frame is None:
                live.update(make_table())
                continue

            # Parse the request
            req = parse_request(frame)
            if req is None:
                stats["invalid_frames"] += 1
                live.update(make_table())
                continue

            stats["requests_total"] += 1

            # Only respond if addressed to one of our emulated slave IDs
            if req["slave_id"] not in slave_ids:
                stats["ignored_slaves"].add(req["slave_id"])
                live.update(make_table())
                continue

            fc = req["fc"]
            sid = req["slave_id"]

            # Build and send response
            response = None

            if fc in (0x03, 0x04):
                # Read registers — respond with zeros
                count = req["count"]
                response = build_read_registers_response(sid, fc, count)

                # Log this range
                key = (sid, fc, req["start"], count)
                if key not in stats["unique_ranges"]:
                    stats["unique_ranges"].add(key)
                    ts = round(time.monotonic() - start_time, 3)
                    range_log[(sid, fc)].append({
                        "start": req["start"],
                        "count": count,
                        "end": req["start"] + count - 1,
                        "first_seen": ts,
                    })
                    live.console.print(
                        f"  [green]NEW[/green] FC{fc:02X} "
                        f"HR[{req['start']}-{req['start']+count-1}] "
                        f"({count} regs) @ {ts:.1f}s"
                    )

            elif fc in (0x01, 0x02):
                # Read coils/discrete — respond with zeros
                response = build_read_bits_response(sid, fc, req["count"])
                key = (sid, fc, req["start"], req["count"])
                if key not in stats["unique_ranges"]:
                    stats["unique_ranges"].add(key)
                    live.console.print(
                        f"  [green]NEW[/green] FC{fc:02X} "
                        f"[{req['start']}-{req['start']+req['count']-1}]"
                    )

            elif fc == 0x06:
                # Write single register — echo back
                response = build_write_single_response(
                    sid, fc, req["addr"], req["value"]
                )
                stats["writes_seen"].append({
                    "time": round(time.monotonic() - start_time, 3),
                    "fc": fc,
                    "addr": req["addr"],
                    "value": req["value"],
                })
                live.console.print(
                    f"  [yellow]WRITE[/yellow] FC06 "
                    f"HR[{req['addr']}] = {req['value']} (0x{req['value']:04X})"
                )

            elif fc == 0x05:
                # Write single coil — echo back
                response = build_write_single_response(
                    sid, fc, req["addr"], req["value"]
                )
                stats["writes_seen"].append({
                    "time": round(time.monotonic() - start_time, 3),
                    "fc": fc,
                    "addr": req["addr"],
                    "value": req["value"],
                })
                live.console.print(
                    f"  [yellow]WRITE[/yellow] FC05 "
                    f"Coil[{req['addr']}] = {req['value']}"
                )

            elif fc == 0x10:
                # Write multiple registers — acknowledge
                response = build_write_multiple_response(
                    sid, fc, req["start"], req["count"]
                )
                stats["writes_seen"].append({
                    "time": round(time.monotonic() - start_time, 3),
                    "fc": fc,
                    "start": req["start"],
                    "count": req["count"],
                    "values": req.get("values", []),
                })
                live.console.print(
                    f"  [yellow]WRITE[/yellow] FC10 "
                    f"HR[{req['start']}-{req['start']+req['count']-1}] "
                    f"= {req.get('values', [])}"
                )

            elif fc == 0x0F:
                # Write multiple coils — acknowledge
                response = build_write_multiple_response(
                    sid, fc, req["start"], req["count"]
                )

            else:
                # Unsupported FC — return exception (illegal function)
                response = build_exception_response(sid, fc, 0x01)
                live.console.print(
                    f"  [red]UNSUPPORTED FC 0x{fc:02X}[/red] — sent exception"
                )

            if response:
                # Important: small delay before responding
                # Modbus RTU requires 3.5 char silence before response
                time.sleep(0.004)
                ser.write(response)
                ser.flush()
                stats["responses_sent"] += 1

            # Record for full log
            stats["all_requests"].append({
                "time": round(time.monotonic() - start_time, 3),
                "slave": sid,
                "fc": fc,
                "start": req.get("start"),
                "count": req.get("count"),
            })

            live.update(make_table())

    return stats, range_log


def print_summary(stats: dict, range_log: dict):
    """Print a comprehensive summary of what the tablet polled."""
    console.print("\n[bold]═══════════════════════════════════════════════════[/bold]")
    console.print("[bold]              EMULATOR RESULTS                     [/bold]")
    console.print("[bold]═══════════════════════════════════════════════════[/bold]")

    console.print(f"\nTotal requests: {stats['requests_total']}")
    console.print(f"Responses sent: {stats['responses_sent']}")
    console.print(f"Unique poll ranges: {len(stats['unique_ranges'])}")
    console.print(f"Write requests: {len(stats['writes_seen'])}")

    if stats["ignored_slaves"]:
        console.print(f"Ignored slave IDs: {sorted(stats['ignored_slaves'])}")

    # Register ranges sorted by address
    console.print("\n[bold cyan]All register ranges the tablet reads:[/bold cyan]")
    table = Table(show_header=True, border_style="dim")
    table.add_column("FC", width=5)
    table.add_column("Type", width=15)
    table.add_column("Start", width=7)
    table.add_column("End", width=7)
    table.add_column("Count", width=7)
    table.add_column("First seen", width=10)

    all_ranges = []
    for (sid, fc), ranges in range_log.items():
        for r in ranges:
            all_ranges.append((sid, fc, r))

    all_ranges.sort(key=lambda x: (x[1], x[2]["start"]))

    total_regs = 0
    for sid, fc, r in all_ranges:
        fc_name = FC_NAMES.get(fc, f"FC_{fc:02X}")
        table.add_row(
            f"0x{fc:02X}",
            fc_name.replace("Read ", ""),
            str(r["start"]),
            str(r["end"]),
            str(r["count"]),
            f"{r['first_seen']:.1f}s",
        )
        total_regs += r["count"]

    console.print(table)
    console.print(f"\n[bold]Total registers polled: {total_regs}[/bold]")

    # Compare with our known register map
    try:
        from register_map import HOLDING_REGISTERS as HP_HR
        known = set(HP_HR.keys())
        tablet = set()
        for sid, fc, r in all_ranges:
            if fc in (0x03, 0x04):
                for a in range(r["start"], r["end"] + 1):
                    tablet.add(a)

        new_regs = tablet - known
        if new_regs:
            console.print(f"\n[green bold]NEW registers the tablet reads "
                          f"that we don't have in register_map.py: {len(new_regs)}[/green bold]")
            # Group into ranges
            sorted_new = sorted(new_regs)
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
            for rs in ranges_str:
                console.print(f"    {rs}")
        else:
            console.print("\n[dim]No new registers beyond register_map.py[/dim]")

    except ImportError:
        pass

    # Write requests
    if stats["writes_seen"]:
        console.print(f"\n[yellow bold]WRITES from tablet:[/yellow bold]")
        for w in stats["writes_seen"]:
            console.print(f"  t={w['time']:.1f}s  FC{w['fc']:02X}  "
                          f"addr={w.get('addr', w.get('start'))}  "
                          f"value={w.get('value', w.get('values'))}")

    # Poll cycle timing
    if len(stats["all_requests"]) > 1:
        # Find complete cycles (when the same range appears again)
        first_range = stats["all_requests"][0]
        cycle_starts = [
            r["time"] for r in stats["all_requests"]
            if r["start"] == first_range["start"] and r["fc"] == first_range["fc"]
        ]
        if len(cycle_starts) > 1:
            cycles = [cycle_starts[i+1] - cycle_starts[i]
                      for i in range(len(cycle_starts) - 1)]
            if cycles:
                console.print(f"\n[bold]Poll cycle timing:[/bold]")
                console.print(f"  Estimated cycle period: {sum(cycles)/len(cycles):.2f}s")
                console.print(f"  Cycles observed: {len(cycle_starts)}")


def save_emulator_results(stats: dict, range_log: dict, path: Path):
    """Save all emulator results to JSON."""
    result = {
        "timestamp": datetime.now().isoformat(),
        "requests_total": stats["requests_total"],
        "responses_sent": stats["responses_sent"],
        "unique_ranges_count": len(stats["unique_ranges"]),
        "writes_count": len(stats["writes_seen"]),
        "register_ranges": {},
        "writes": stats["writes_seen"],
        "all_requests": stats["all_requests"][:5000],  # Limit size
    }

    for (sid, fc), ranges in range_log.items():
        key = f"slave{sid}_FC{fc:02X}"
        result["register_ranges"][key] = ranges

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)
    console.print(f"\n[green]Results saved to: {path}[/green]")


# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="BataviaHeat Slave Emulator")
    parser.add_argument("--duration", "-d", type=float, default=120,
                        help="Run duration in seconds (0=until Ctrl+C, default: 120)")
    parser.add_argument("--slave", type=int, action="append", default=None,
                        help="Slave ID(s) to emulate (default: 1). Can specify multiple.")
    parser.add_argument("--port", default=PORT, help=f"Serial port (default: {PORT})")
    parser.add_argument("--output", "-o", default=None, help="Output JSON file")
    args = parser.parse_args()

    slave_ids = set(args.slave) if args.slave else {1}
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = Path(args.output) if args.output else OUT_DIR / f"emulator_{ts}.json"

    console.print("[bold]╔═══════════════════════════════════════════════════╗[/bold]")
    console.print("[bold]║    BataviaHeat Slave Emulator                    ║[/bold]")
    console.print("[bold]╚═══════════════════════════════════════════════════╝[/bold]")
    console.print(f"Port: {args.port}, Baud: {BAUDRATE}")
    console.print(f"Emulating slave ID(s): {sorted(slave_ids)}")
    console.print(f"Duration: {'until Ctrl+C' if args.duration == 0 else f'{args.duration}s'}")
    console.print(f"Output: {output_path}\n")

    ser = serial.Serial(
        port=args.port, baudrate=BAUDRATE, parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE, bytesize=serial.EIGHTBITS,
        timeout=TIMEOUT,
    )
    # Drain any pending data
    ser.reset_input_buffer()

    try:
        stats, range_log = run_emulator(ser, slave_ids, args.duration)
    finally:
        ser.close()

    print_summary(stats, range_log)
    save_emulator_results(stats, range_log, output_path)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
    except serial.SerialException as e:
        console.print(f"\n[red]Serial error: {e}[/red]")
        sys.exit(1)

#!/usr/bin/env python3
"""
BataviaHeat R290 Overnight Modbus Monitor — Combined Active + Passive

Active mode:  Polls known registers at regular intervals, logs every value.
Passive mode: Listens for tablet↔heat-pump traffic between active polls.
              Detects unknown register reads/writes the tablet performs.

Uses raw serial for full bus control (no pymodbus — avoids "wrong slave" issues).

Output files (in 'Modbus snooper/' directory):
  - overnight_<ts>.db      — SQLite database with tables: readings, frames, changes
  - overnight_raw_<ts>.bin — raw serial bytes with timestamps for post-processing
  - overnight_summary.txt  — written at shutdown: stats, min/max/unique per register

Database tables:
  - readings: all register values (source='active'|'passive', reg_type, address, raw_value)
  - frames:   decoded passive bus frames (direction, fc, slave, start_addr, data_hex)
  - changes:  register value changes (source, reg_type, address, old→new)

Usage:
    python overnight_monitor.py
    python overnight_monitor.py --interval 5      (poll every 5 seconds instead of 10)
    python overnight_monitor.py --passive-only     (only sniff, no active polling)

Press Ctrl+C to stop gracefully and write summary.
"""

import argparse
import sqlite3
import os
import struct
import sys
import time
from datetime import datetime
from pathlib import Path

import serial
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.text import Text

console = Console()

# ── Connection settings ──────────────────────────────────────────────────────
PORT = "COM5"
BAUDRATE = 9600
SLAVE_ID = 1

# ── Output directory ─────────────────────────────────────────────────────────
OUT_DIR = Path(__file__).parent / "data"

# ── Register blocks to actively poll ─────────────────────────────────────────
# Updated 2026-03-17 based on clean scan (display disconnected).
# HR and IR share the same register space on this controller, so we only
# need HR reads — IR would return identical data.
# (function_code, label, start_address, count)
ACTIVE_POLL_BLOCKS = [
    # ── Primary block HR[0-165]: control, sensors, config, energy ──
    (0x03, "holding", 0, 13),       # HR[0-12]: control switches, mode, setpoints, runtime counters
    (0x03, "holding", 16, 10),      # HR[16-25]: runtime counters (11-12,16-20) + temps (22-25)
    (0x03, "holding", 31, 16),      # HR[31-46]: signed vals, pressures, superheat, temps
    (0x03, "holding", 53, 28),      # HR[53-80]: pump RPM, flow, EEV, config params
    (0x03, "holding", 94, 10),      # HR[94-103]: cooling/heating targets, compressor freq, DHW
    (0x03, "holding", 118, 13),     # HR[118-130]: operational params, versions
    (0x03, "holding", 137, 1),      # HR[137]: unknown operational
    (0x03, "holding", 146, 10),     # HR[146-155]: energy/pump config
    (0x03, "holding", 156, 1),      # HR[156]: flag
    (0x03, "holding", 163, 3),      # HR[163-165]: energy accumulators (growing ~11/read)
    # ── Firmware string HR[256-269] (static, low priority) ──
    (0x03, "holding", 256, 14),     # HR[256-269]: "X1.HL087A.K05.503-1.V100B25"
    # ── Tablet poll ranges (beyond primary block) ──
    (0x03, "holding", 512, 16),     # HR[512-527]: tablet polls — unknown
    (0x03, "holding", 768, 54),     # HR[768-821]: system status, limits, pump config
    (0x03, "holding", 910, 1),      # HR[910]: operation flag
    (0x03, "holding", 912, 2),      # HR[912-913]: operation params
    # ── Secondary sensor block HR[1000-1099] ──
    (0x03, "holding", 1000, 8),     # HR[1000-1007]: tablet polls
    (0x03, "holding", 1024, 25),    # HR[1024-1048]: tablet polls
    # ── Secondary live data HR[1283-1410] ──
    (0x03, "holding", 1283, 87),    # HR[1283-1369]: compressor live mirror
    (0x03, "holding", 1370, 40),    # HR[1370-1409]: extended secondary block
    # ── Shadow ranges ──
    (0x03, "holding", 3331, 42),    # HR[3331-3372]: zone/module mirror
    (0x03, "holding", 4000, 16),    # HR[4000-4015]: tablet polls — unknown
    # ── Modbus interface area HR[6400-6511] ──
    (0x03, "holding", 6400, 45),    # HR[6400-6444]: M-serie params
    (0x03, "holding", 6464, 48),    # HR[6464-6511]: N-serie params
    # ── Extended config blocks HR[6528-6887] ──
    (0x03, "holding", 6528, 48),    # HR[6528-6575]: tablet polls
    (0x03, "holding", 6592, 47),    # HR[6592-6638]: tablet polls
    (0x03, "holding", 6656, 32),    # HR[6656-6687]: tablet polls
    (0x03, "holding", 6720, 80),    # HR[6720-6799]: tablet polls (split read)
    (0x03, "holding", 6800, 23),    # HR[6800-6822]: tablet polls (rest)
    (0x03, "holding", 6848, 40),    # HR[6848-6887]: tablet polls
    # ── Internal firmware config HR[6912-7471] ──
    (0x03, "holding", 6912, 48),    # HR[6912-6959]: tablet polls
    (0x03, "holding", 6976, 48),    # HR[6976-7023]: tablet polls
    (0x03, "holding", 7040, 48),    # HR[7040-7087]: tablet polls
    (0x03, "holding", 7104, 48),    # HR[7104-7151]: tablet polls
    (0x03, "holding", 7168, 48),    # HR[7168-7215]: tablet polls — F/P-serie hier?
    (0x03, "holding", 7216, 80),    # HR[7216-7295]: Zone A/B blocks + config (split read)
    (0x03, "holding", 7296, 48),    # HR[7296-7343]: tablet polls
    (0x03, "holding", 7360, 48),    # HR[7360-7407]: tablet polls — M14-M21 hier
    (0x03, "holding", 7424, 48),    # HR[7424-7471]: tablet polls
]

# ── Modbus RTU helpers ───────────────────────────────────────────────────────

def crc16(data: bytes) -> int:
    """Modbus CRC-16."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def build_read_request(slave_id: int, fc: int, start: int, count: int) -> bytes:
    pdu = struct.pack(">BBHH", slave_id, fc, start, count)
    return pdu + struct.pack("<H", crc16(pdu))


def verify_crc(frame: bytes) -> bool:
    if len(frame) < 4:
        return False
    payload = frame[:-2]
    expected = crc16(payload)
    actual = struct.unpack("<H", frame[-2:])[0]
    return expected == actual


def parse_read_response(frame: bytes) -> tuple[int, int, list[int]] | None:
    """Parse FC03/FC04 response → (slave_id, func_code, [values])."""
    if len(frame) < 5 or not verify_crc(frame):
        return None
    slave = frame[0]
    fc = frame[1]
    if fc & 0x80:  # Exception
        return None
    if fc not in (0x03, 0x04):
        return None
    byte_count = frame[2]
    if len(frame) < 3 + byte_count + 2:
        return None
    values = []
    for i in range(0, byte_count, 2):
        values.append(struct.unpack(">H", frame[3 + i:5 + i])[0])
    return slave, fc, values


def parse_request_frame(frame: bytes) -> dict | None:
    """Try to parse a Modbus RTU request frame.
    Returns dict with slave, fc, start_addr, count/value, frame_type."""
    if len(frame) < 4 or not verify_crc(frame):
        return None
    slave = frame[0]
    fc = frame[1]
    if fc in (0x03, 0x04) and len(frame) == 8:
        # Read holding/input request: slave + fc + addr(2) + count(2) + crc(2)
        start = struct.unpack(">H", frame[2:4])[0]
        count = struct.unpack(">H", frame[4:6])[0]
        return {"slave": slave, "fc": fc, "start": start, "count": count,
                "type": "read_request"}
    elif fc == 0x06 and len(frame) == 8:
        # Write single register: slave + fc + addr(2) + value(2) + crc(2)
        addr = struct.unpack(">H", frame[2:4])[0]
        value = struct.unpack(">H", frame[4:6])[0]
        return {"slave": slave, "fc": fc, "start": addr, "value": value,
                "type": "write_single"}
    elif fc == 0x10 and len(frame) >= 9:
        # Write multiple registers
        addr = struct.unpack(">H", frame[2:4])[0]
        count = struct.unpack(">H", frame[4:6])[0]
        byte_cnt = frame[6]
        values = []
        for i in range(0, byte_cnt, 2):
            values.append(struct.unpack(">H", frame[7 + i:9 + i])[0])
        return {"slave": slave, "fc": fc, "start": addr, "count": count,
                "values": values, "type": "write_multiple"}
    elif fc in (0x01, 0x02, 0x05, 0x0F):
        # Coil read/write requests
        if len(frame) >= 8:
            addr = struct.unpack(">H", frame[2:4])[0]
            val = struct.unpack(">H", frame[4:6])[0]
            return {"slave": slave, "fc": fc, "start": addr, "value": val,
                    "type": "coil_request"}
    return None


# ── Frame detector ───────────────────────────────────────────────────────────
# Modbus RTU frames are separated by silence of ≥3.5 character times.
# At 9600 baud: 1 char = ~1.04ms, so gap = ~3.6ms. Use 4ms to be safe.
FRAME_GAP_S = 0.004  # 4ms silence = new frame


class FrameDetector:
    """Accumulates bytes and splits into frames based on inter-character gaps."""

    def __init__(self):
        self.buffer = bytearray()
        self.last_byte_time = 0.0

    def feed(self, data: bytes, now: float) -> list[bytes]:
        """Feed new bytes, return list of completed frames."""
        frames = []
        if self.buffer and (now - self.last_byte_time) > FRAME_GAP_S:
            # Gap detected → previous buffer is a complete frame
            frames.append(bytes(self.buffer))
            self.buffer.clear()
        self.buffer.extend(data)
        self.last_byte_time = now
        return frames

    def flush(self) -> bytes | None:
        """Flush any remaining bytes as a frame."""
        if self.buffer:
            frame = bytes(self.buffer)
            self.buffer.clear()
            return frame
        return None

    def drain(self) -> bytes:
        """Drain buffer without treating it as a frame (for pre-poll cleanup)."""
        data = bytes(self.buffer)
        self.buffer.clear()
        return data


# ── Active poller ────────────────────────────────────────────────────────────

def active_poll_cycle(ser: serial.Serial,
                      ) -> dict[str, dict[int, int | None]]:
    """Execute one full poll cycle. Returns {reg_type: {addr: value}}."""
    results: dict[str, dict[int, int | None]] = {"holding": {}, "input": {}}

    for fc, label, start, count in ACTIVE_POLL_BLOCKS:
        # Flush stale data
        ser.reset_input_buffer()
        time.sleep(0.005)

        request = build_read_request(SLAVE_ID, fc, start, count)
        ser.write(request)
        ser.flush()

        # Wait for response
        time.sleep(0.05)
        response = bytearray()
        deadline = time.monotonic() + 0.3
        expected_len = 3 + count * 2 + 2  # slave+fc+bytecount + data + crc

        while time.monotonic() < deadline:
            waiting = ser.in_waiting
            if waiting:
                response.extend(ser.read(waiting))
                if len(response) >= expected_len:
                    break
                time.sleep(0.005)
            else:
                time.sleep(0.015)

        if response:
            parsed = parse_read_response(bytes(response))
            if parsed and parsed[0] == SLAVE_ID:
                _, _, values = parsed
                for i, val in enumerate(values):
                    results[label][start + i] = val
            else:
                for i in range(count):
                    results[label][start + i] = None
        else:
            for i in range(count):
                results[label][start + i] = None

        time.sleep(0.01)  # Small gap between blocks

    return results


# ── Passive listener ─────────────────────────────────────────────────────────

def decode_passive_frame(frame: bytes) -> dict | None:
    """Try to decode a passively captured Modbus RTU frame."""
    if len(frame) < 4:
        return None

    # Try as request
    req = parse_request_frame(frame)
    if req:
        return req

    # Try as read response (FC03/FC04)
    resp = parse_read_response(frame)
    if resp:
        slave, fc, values = resp
        return {"slave": slave, "fc": fc, "values": values, "type": "read_response"}

    return None


# ── Display ──────────────────────────────────────────────────────────────────

def make_status_table(
    cycle: int,
    current: dict[str, dict[int, int | None]],
    previous: dict[str, dict[int, int | None]],
    passive_count: int,
    passive_writes: int,
    start_time: datetime,
    changes_count: int,
) -> Table:
    """Build a compact status display."""
    from register_map import HOLDING_REGISTERS, INPUT_REGISTERS

    elapsed = datetime.now() - start_time
    hours = int(elapsed.total_seconds() // 3600)
    mins = int((elapsed.total_seconds() % 3600) // 60)

    table = Table(
        title=f"BataviaHeat Overnight Monitor — Cycle #{cycle} "
              f"| Running {hours}h{mins:02d}m | {changes_count} changes | "
              f"{passive_count} passive frames | {passive_writes} writes detected",
        expand=True,
    )
    table.add_column("Reg", style="cyan", justify="right", width=6)
    table.add_column("Type", style="dim", width=4)
    table.add_column("Name", style="white", width=32)
    table.add_column("Raw", style="green", justify="right", width=7)
    table.add_column("Scaled", style="blue", justify="right", width=9)
    table.add_column("Chg", style="red", justify="center", width=3)

    reg_maps = {"holding": HOLDING_REGISTERS, "input": INPUT_REGISTERS}

    for reg_type in ("holding", "input"):
        reg_map = reg_maps.get(reg_type, {})
        prefix = "HR" if reg_type == "holding" else "IR"
        cur = current.get(reg_type, {})
        prev = previous.get(reg_type, {})

        for addr in sorted(cur.keys()):
            val = cur[addr]
            info = reg_map.get(addr, {})
            name = info.get("name", "")
            if val is None:
                table.add_row(str(addr), prefix, name, "ERR", "", "")
                continue
            scale = info.get("scale", 0.1)
            unit = info.get("unit", "")
            signed = val - 65536 if val > 32767 else val
            scaled = f"{signed * scale:.1f}{unit}" if unit else str(val)
            changed = "●" if prev.get(reg_type, {}).get(addr) is not None and prev[reg_type][addr] != val else ""
            table.add_row(str(addr), prefix, name[:32], str(val), scaled, changed)

    return table


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="BataviaHeat R290 Overnight Monitor")
    parser.add_argument("--port", default=PORT, help=f"Serial port (default: {PORT})")
    parser.add_argument("--interval", type=float, default=10.0,
                        help="Active poll interval in seconds (default: 10)")
    parser.add_argument("--passive-only", action="store_true",
                        help="Only sniff bus traffic, no active polling")
    args = parser.parse_args()

    # Open output files
    OUT_DIR.mkdir(exist_ok=True)
    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    db_path = OUT_DIR / f"overnight_{ts_str}.db"
    summary_path = OUT_DIR / f"overnight_summary_{ts_str}.txt"
    raw_log_path = OUT_DIR / f"overnight_raw_{ts_str}.bin"

    raw_log = open(raw_log_path, "wb")

    db = sqlite3.connect(str(db_path))
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.executescript("""
        CREATE TABLE readings (
            id INTEGER PRIMARY KEY,
            timestamp TEXT NOT NULL,
            source TEXT NOT NULL,
            reg_type TEXT NOT NULL,
            address INTEGER NOT NULL,
            raw_value INTEGER,
            hex_value TEXT
        );
        CREATE TABLE frames (
            id INTEGER PRIMARY KEY,
            timestamp TEXT NOT NULL,
            direction TEXT NOT NULL,
            fc TEXT NOT NULL,
            slave INTEGER,
            start_addr INTEGER,
            count_or_value INTEGER,
            data_hex TEXT,
            raw_frame_hex TEXT
        );
        CREATE TABLE changes (
            id INTEGER PRIMARY KEY,
            timestamp TEXT NOT NULL,
            source TEXT NOT NULL,
            reg_type TEXT NOT NULL,
            address INTEGER NOT NULL,
            old_value INTEGER,
            new_value INTEGER,
            old_scaled TEXT,
            new_scaled TEXT
        );
        CREATE INDEX idx_readings_reg ON readings(reg_type, address);
        CREATE INDEX idx_readings_ts ON readings(timestamp);
        CREATE INDEX idx_readings_src ON readings(source);
        CREATE INDEX idx_frames_ts ON frames(timestamp);
        CREATE INDEX idx_frames_dir ON frames(direction);
        CREATE INDEX idx_frames_addr ON frames(start_addr);
        CREATE INDEX idx_changes_reg ON changes(reg_type, address);
        CREATE INDEX idx_changes_ts ON changes(timestamp);
    """)

    # Open serial port
    ser = serial.Serial(
        port=args.port, baudrate=BAUDRATE, parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE, bytesize=serial.EIGHTBITS,
        timeout=0,  # Non-blocking reads
    )
    ser.reset_input_buffer()

    console.print(f"[bold cyan]BataviaHeat R290 Overnight Monitor[/bold cyan]")
    console.print(f"Port: {args.port}, Baud: {BAUDRATE}, Slave: {SLAVE_ID}")
    console.print(f"Active poll interval: {args.interval}s, Passive-only: {args.passive_only}")
    console.print(f"[dim]Database:    {db_path.name}[/dim]")
    console.print(f"[dim]Raw bytes:   {raw_log_path.name}[/dim]")
    console.print(f"[dim]Summary:     {summary_path.name}[/dim]")
    console.print("[yellow]Press Ctrl+C to stop and write summary[/yellow]\n")

    # State tracking
    from register_map import HOLDING_REGISTERS, INPUT_REGISTERS
    reg_maps = {"holding": HOLDING_REGISTERS, "input": INPUT_REGISTERS}

    current: dict[str, dict[int, int | None]] = {"holding": {}, "input": {}}
    previous: dict[str, dict[int, int | None]] = {"holding": {}, "input": {}}
    last_values: dict[str, dict[int, int | None]] = {"holding": {}, "input": {}}
    passive_count = 0
    passive_writes = 0
    passive_unknown_addrs: set[tuple[str, int]] = set()  # (reg_type, addr) not in our map
    passive_response_data: dict[str, dict[int, int]] = {"holding": {}, "input": {}}  # From passive responses
    last_request: dict | None = None  # Track last request to pair with response
    changes_count = 0
    cycle = 0
    active_block_idx = 0  # Rotate through blocks one at a time to minimize bus time
    start_time = datetime.now()

    detector = FrameDetector()
    next_poll = time.monotonic() + 3.0  # Start first active poll after 3s

    try:
        with Live(console=console, refresh_per_second=0.5) as live:
            while True:
                now_mono = time.monotonic()

                # ── Passive: read any available bytes ──
                waiting = ser.in_waiting
                if waiting:
                    raw = ser.read(waiting)
                    # Log raw bytes with timestamp for post-processing
                    ts_bytes = struct.pack(">d", now_mono)  # 8-byte double timestamp
                    raw_log.write(ts_bytes + struct.pack(">H", len(raw)) + raw)

                    frames = detector.feed(raw, now_mono)
                    for frame in frames:
                        decoded = decode_passive_frame(frame)
                        if decoded:
                            now_str = datetime.now().isoformat(timespec="milliseconds")
                            passive_count += 1

                            if decoded["type"] == "read_request":
                                fc_name = {0x03: "holding", 0x04: "input"}.get(decoded["fc"], f"fc{decoded['fc']:02x}")
                                db.execute(
                                    "INSERT INTO frames (timestamp,direction,fc,slave,start_addr,count_or_value,data_hex,raw_frame_hex) VALUES (?,?,?,?,?,?,?,?)",
                                    (now_str, "REQUEST", f"FC{decoded['fc']:02X}",
                                     decoded["slave"], decoded["start"], decoded["count"],
                                     "", frame.hex()),
                                )
                                last_request = decoded
                                for a in range(decoded["start"], decoded["start"] + decoded["count"]):
                                    if a not in reg_maps.get(fc_name, {}):
                                        passive_unknown_addrs.add((fc_name, a))

                            elif decoded["type"] == "read_response":
                                vals = decoded.get("values", [])
                                vals_hex = " ".join(f"{v:04X}" for v in vals)
                                paired_start = None
                                if last_request and last_request.get("type") == "read_request":
                                    req_fc = last_request["fc"]
                                    resp_fc = decoded["fc"]
                                    if req_fc == resp_fc and decoded["slave"] == last_request["slave"]:
                                        paired_start = last_request["start"]
                                        fc_name = {0x03: "holding", 0x04: "input"}.get(req_fc, "")
                                        if fc_name:
                                            for i, v in enumerate(vals):
                                                addr = last_request["start"] + i
                                                passive_response_data.setdefault(fc_name, {})[addr] = v
                                                db.execute(
                                                    "INSERT INTO readings (timestamp,source,reg_type,address,raw_value,hex_value) VALUES (?,?,?,?,?,?)",
                                                    (now_str, "passive", fc_name, addr, v, f"0x{v:04X}"),
                                                )
                                                old_val = last_values[fc_name].get(addr)
                                                if old_val is not None and old_val != v:
                                                    changes_count += 1
                                                    info = reg_maps.get(fc_name, {}).get(addr, {})
                                                    scale = info.get("scale", 0.1)
                                                    unit = info.get("unit", "")
                                                    old_s = old_val - 65536 if old_val > 32767 else old_val
                                                    new_s = v - 65536 if v > 32767 else v
                                                    old_scaled = f"{old_s * scale:.1f}{unit}" if unit else str(old_val)
                                                    new_scaled = f"{new_s * scale:.1f}{unit}" if unit else str(v)
                                                    db.execute(
                                                        "INSERT INTO changes (timestamp,source,reg_type,address,old_value,new_value,old_scaled,new_scaled) VALUES (?,?,?,?,?,?,?,?)",
                                                        (now_str, "passive", fc_name, addr, old_val, v, old_scaled, new_scaled),
                                                    )
                                                last_values[fc_name][addr] = v
                                    last_request = None

                                db.execute(
                                    "INSERT INTO frames (timestamp,direction,fc,slave,start_addr,count_or_value,data_hex,raw_frame_hex) VALUES (?,?,?,?,?,?,?,?)",
                                    (now_str, "RESPONSE", f"FC{decoded['fc']:02X}",
                                     decoded["slave"], paired_start,
                                     len(vals), vals_hex, frame.hex()),
                                )

                            elif decoded["type"] == "write_single":
                                passive_writes += 1
                                db.execute(
                                    "INSERT INTO frames (timestamp,direction,fc,slave,start_addr,count_or_value,data_hex,raw_frame_hex) VALUES (?,?,?,?,?,?,?,?)",
                                    (now_str, "WRITE_SINGLE", "FC06",
                                     decoded["slave"], decoded["start"], decoded["value"],
                                     f"{decoded['value']:04X}", frame.hex()),
                                )
                                last_request = None

                            elif decoded["type"] == "write_multiple":
                                passive_writes += 1
                                vals_hex = " ".join(f"{v:04X}" for v in decoded.get("values", []))
                                db.execute(
                                    "INSERT INTO frames (timestamp,direction,fc,slave,start_addr,count_or_value,data_hex,raw_frame_hex) VALUES (?,?,?,?,?,?,?,?)",
                                    (now_str, "WRITE_MULTI", "FC10",
                                     decoded["slave"], decoded["start"], decoded["count"],
                                     vals_hex, frame.hex()),
                                )
                                last_request = None

                            elif decoded["type"] == "coil_request":
                                db.execute(
                                    "INSERT INTO frames (timestamp,direction,fc,slave,start_addr,count_or_value,data_hex,raw_frame_hex) VALUES (?,?,?,?,?,?,?,?)",
                                    (now_str, "COIL_REQ", f"FC{decoded['fc']:02X}",
                                     decoded["slave"], decoded["start"], decoded["value"],
                                     "", frame.hex()),
                                )
                                last_request = decoded

                            db.commit()

                # ── Active: time for a poll? ──
                if not args.passive_only and now_mono >= next_poll:
                    # Drain and flush to clear any stale bus data
                    detector.drain()
                    ser.reset_input_buffer()
                    time.sleep(0.05)  # 50ms silence before our poll

                    # Poll ONE block at a time to minimize bus occupation
                    fc, label, start, count = ACTIVE_POLL_BLOCKS[active_block_idx]
                    active_block_idx = (active_block_idx + 1) % len(ACTIVE_POLL_BLOCKS)

                    # Only increment cycle when we've gone through all blocks
                    if active_block_idx == 0:
                        cycle += 1

                    ser.reset_input_buffer()
                    request = build_read_request(SLAVE_ID, fc, start, count)
                    ser.write(request)
                    ser.flush()

                    # Wait for response
                    time.sleep(0.05)
                    response = bytearray()
                    deadline = time.monotonic() + 0.4
                    expected_len = 3 + count * 2 + 2

                    while time.monotonic() < deadline:
                        w = ser.in_waiting
                        if w:
                            response.extend(ser.read(w))
                            if len(response) >= expected_len:
                                break
                            time.sleep(0.005)
                        else:
                            time.sleep(0.015)

                    now_str = datetime.now().isoformat(timespec="milliseconds")

                    if response:
                        parsed = parse_read_response(bytes(response))
                        if parsed and parsed[0] == SLAVE_ID:
                            _, _, values = parsed
                            for i, val in enumerate(values):
                                addr = start + i
                                db.execute(
                                    "INSERT INTO readings (timestamp,source,reg_type,address,raw_value,hex_value) VALUES (?,?,?,?,?,?)",
                                    (now_str, "active", label, addr, val, f"0x{val:04X}"),
                                )

                                old_val = last_values[label].get(addr)
                                if old_val is not None and old_val != val:
                                    changes_count += 1
                                    info = reg_maps.get(label, {}).get(addr, {})
                                    scale = info.get("scale", 0.1)
                                    unit = info.get("unit", "")
                                    old_s = old_val - 65536 if old_val > 32767 else old_val
                                    new_s = val - 65536 if val > 32767 else val
                                    old_scaled = f"{old_s * scale:.1f}{unit}" if unit else str(old_val)
                                    new_scaled = f"{new_s * scale:.1f}{unit}" if unit else str(val)
                                    db.execute(
                                        "INSERT INTO changes (timestamp,source,reg_type,address,old_value,new_value,old_scaled,new_scaled) VALUES (?,?,?,?,?,?,?,?)",
                                        (now_str, "active", label, addr, old_val, val, old_scaled, new_scaled),
                                    )
                                last_values[label][addr] = val

                                current.setdefault(label, {})[addr] = val

                    db.commit()
                    raw_log.flush()

                    # Update display every full cycle
                    if active_block_idx == 0:
                        table = make_status_table(
                            cycle, current, previous,
                            passive_count, passive_writes,
                            start_time, changes_count,
                        )
                        live.update(table)
                        previous = {k: dict(v) for k, v in current.items()}

                    # Short interval between blocks, longer between full cycles
                    next_poll = now_mono + (0.5 if active_block_idx != 0 else args.interval)

                # Small sleep to avoid CPU spin
                time.sleep(0.002)

    except KeyboardInterrupt:
        console.print("\n[yellow]Stopping...[/yellow]")
    finally:
        # Flush any remaining passive frame
        remaining = detector.flush()
        if remaining:
            decoded = decode_passive_frame(remaining)
            if decoded:
                passive_count += 1

        ser.close()
        raw_log.close()
        db.commit()

        # ── Write summary (query from SQLite) ────────────────────────────
        elapsed = datetime.now() - start_time
        hours = int(elapsed.total_seconds() // 3600)
        mins = int((elapsed.total_seconds() % 3600) // 60)
        secs = int(elapsed.total_seconds() % 60)

        total_readings = db.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
        total_frames = db.execute("SELECT COUNT(*) FROM frames").fetchone()[0]
        total_changes = db.execute("SELECT COUNT(*) FROM changes").fetchone()[0]

        summary_lines = [
            f"BataviaHeat R290 Overnight Monitor Summary",
            f"==========================================",
            f"Started:  {start_time.isoformat()}",
            f"Stopped:  {datetime.now().isoformat()}",
            f"Duration: {hours}h {mins}m {secs}s",
            f"Database: {db_path.name}",
            f"",
            f"Active poll cycles: {cycle}",
            f"Total register readings: {total_readings:,}",
            f"Passive frames captured: {passive_count}",
            f"Passive write operations detected: {passive_writes}",
            f"Total register changes detected: {total_changes:,}",
            f"",
        ]

        if passive_unknown_addrs:
            summary_lines.append(f"Unknown registers read by tablet ({len(passive_unknown_addrs)}):")
            for reg_type, addr in sorted(passive_unknown_addrs):
                summary_lines.append(f"  {reg_type}[{addr}]")
            summary_lines.append("")

        # Per-register stats from database
        for reg_type in ("holding", "input"):
            prefix = "HR" if reg_type == "holding" else "IR"
            rows = db.execute("""
                SELECT address, MIN(raw_value), MAX(raw_value),
                       COUNT(DISTINCT raw_value), COUNT(*)
                FROM readings WHERE reg_type = ?
                GROUP BY address ORDER BY address
            """, (reg_type,)).fetchall()
            if not rows:
                continue
            summary_lines.append(f"── {prefix} Register Statistics ({len(rows)} registers) ──")
            summary_lines.append(f"{'Addr':>6} {'Name':<32} {'Min':>7} {'Max':>7} {'#Unique':>7} {'#Reads':>7}")

            for addr, min_v, max_v, n_unique, n_reads in rows:
                info = reg_maps.get(reg_type, {}).get(addr, {})
                name = info.get("name", "")[:32]
                changed_marker = " ***" if n_unique > 1 else ""
                summary_lines.append(
                    f"{addr:>6} {name:<32} {min_v:>7} {max_v:>7} "
                    f"{n_unique:>7} {n_reads:>7}{changed_marker}"
                )
            summary_lines.append("")

        # Registers that changed (from changes table)
        changed_rows = db.execute("""
            SELECT reg_type, address, COUNT(DISTINCT new_value) as n_vals
            FROM changes GROUP BY reg_type, address
            ORDER BY reg_type, address
        """).fetchall()

        if changed_rows:
            summary_lines.append(f"── Registers That Changed ({len(changed_rows)}) ──")
            for reg_type, addr, n_vals in changed_rows:
                prefix = "HR" if reg_type == "holding" else "IR"
                info = reg_maps.get(reg_type, {}).get(addr, {})
                name = info.get("name", "")
                scale = info.get("scale", 0.1)
                unit = info.get("unit", "")
                # Get distinct values from readings table
                distinct = db.execute(
                    "SELECT DISTINCT raw_value FROM readings WHERE reg_type=? AND address=? ORDER BY raw_value",
                    (reg_type, addr),
                ).fetchall()
                vals_raw = [r[0] for r in distinct]
                if unit:
                    vals_str = [f"{(v - 65536 if v > 32767 else v) * scale:.1f}{unit}" for v in vals_raw]
                else:
                    vals_str = [str(v) for v in vals_raw]
                n = len(vals_raw)
                if n <= 10:
                    summary_lines.append(f"  {prefix}[{addr}] {name}: {n} unique values: {', '.join(vals_str)}")
                else:
                    summary_lines.append(f"  {prefix}[{addr}] {name}: {n} unique values (range {vals_str[0]} → {vals_str[-1]})")
            summary_lines.append("")

        summary_text = "\n".join(summary_lines)
        summary_path.write_text(summary_text, encoding="utf-8")

        db.close()

        console.print(f"\n[bold green]Summary written to {summary_path.name}[/bold green]")
        console.print(f"[bold green]Database: {db_path.name}[/bold green]")
        console.print(summary_text)


if __name__ == "__main__":
    main()

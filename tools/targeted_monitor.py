#!/usr/bin/env python3
"""
BataviaHeat R290 Targeted Monitor — Second Pass

Focused monitoring to resolve open questions from overnight analysis:
  1. IR[16-20] + IR[23-25] identification (compressor speed/pressure?)
  2. HR[32] vs IR[32] comparison (is HR[32] pressure or outdoor temp?)
  3. Shadow ranges HR[3331-3372] and HR[6400-6511]
  4. HR[768] operational status tracking
  5. HR[5010] tablet room temperature
  6. All temperature-candidate registers

Adds computed columns for easier analysis:
  - Differences between suspected mirrors (HR[32] vs IR[32], etc.)
  - Rate-of-change for fast-changing registers
  - Compressor on/off state derived from HR[768]

Output: SQLite database with same schema as overnight_monitor.py

Usage:
    python targeted_monitor.py
    python targeted_monitor.py --interval 5
    python targeted_monitor.py --passive-only

Press Ctrl+C to stop gracefully.
"""

import argparse
import sqlite3
import struct
import sys
import time
from datetime import datetime
from pathlib import Path

import serial
from rich.console import Console
from rich.live import Live
from rich.table import Table

console = Console()

# ── Connection settings ──────────────────────────────────────────────────────
PORT = "COM5"
BAUDRATE = 9600
SLAVE_ID = 1
OUT_DIR = Path(__file__).parent

# ── Targeted poll blocks ─────────────────────────────────────────────────────
# Focused on open questions, with tags for analysis.
POLL_BLOCKS = [
    # === Question 1: What are IR[16-20]? (compressor data?) ===
    (0x04, "input", 16, 10),       # IR[16-25]: strongly correlated cluster
    # === Question 2: HR[32] — pressure or temperature? ===
    (0x03, "holding", 32, 2),      # HR[32-33]: labeled "pressure" but overnight looked like temp
    (0x04, "input", 32, 2),        # IR[32-33]: known pressures (CONFIRMED bar ×0.1)
    # === Question 3: Operational status ===
    (0x03, "holding", 768, 54),    # HR[768-821]: operational block (768=status, 773=compressor temp)
    (0x03, "holding", 910, 10),    # HR[910-919]: operation flags
    (0x03, "holding", 1000, 8),    # HR[1000-1007]: operational mode
    (0x03, "holding", 1024, 25),   # HR[1024-1048]: operation codes + temps
    # === Question 4: Live compressor data ===
    (0x03, "holding", 1283, 87),   # HR[1283-1369]: full compressor live block
    # === Question 5: Shadow ranges ===
    (0x03, "holding", 3331, 42),   # HR[3331-3372]: shadow range 1
    (0x03, "holding", 6400, 48),   # HR[6400-6447]: shadow range 2a
    (0x03, "holding", 6464, 48),   # HR[6464-6511]: shadow range 2b
    # === Question 6: Tablet communication ===
    (0x03, "holding", 5000, 7),    # HR[5000-5006]: clock sync
    (0x03, "holding", 5010, 1),    # HR[5010]: room temp from tablet
    # === Baseline sensors (known good, for correlation) ===
    (0x04, "input", 22, 4),        # IR[22-25]: ambient/fin/suction/discharge
    (0x04, "input", 53, 2),        # IR[53-54]: pump speed + flow
    (0x04, "input", 66, 1),        # IR[66]: pump control signal
    (0x04, "input", 134, 9),       # IR[134-142]: module temps + pump feedback
    # === Writable registers (check tablet influence) ===
    (0x03, "holding", 0, 13),      # HR[0-12]: mode, setpoints, system
    (0x03, "holding", 71, 6),      # HR[71-76]: DISPROVEN sensors — verify they stay 0
    (0x03, "holding", 94, 2),      # HR[94-95]: cooling target, zone B
    (0x03, "holding", 187, 3),     # HR[187-189]: DISPROVEN — verify stay 0
]


# ── Modbus RTU helpers ───────────────────────────────────────────────────────

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


def build_read_request(slave_id: int, fc: int, start: int, count: int) -> bytes:
    pdu = struct.pack(">BBHH", slave_id, fc, start, count)
    return pdu + struct.pack("<H", crc16(pdu))


def verify_crc(frame: bytes) -> bool:
    if len(frame) < 4:
        return False
    return crc16(frame[:-2]) == struct.unpack("<H", frame[-2:])[0]


def parse_read_response(frame: bytes) -> tuple[int, int, list[int]] | None:
    if len(frame) < 5 or not verify_crc(frame):
        return None
    slave, fc = frame[0], frame[1]
    if fc & 0x80 or fc not in (0x03, 0x04):
        return None
    byte_count = frame[2]
    if len(frame) < 3 + byte_count + 2:
        return None
    values = []
    for i in range(0, byte_count, 2):
        values.append(struct.unpack(">H", frame[3 + i:5 + i])[0])
    return slave, fc, values


def parse_request_frame(frame: bytes) -> dict | None:
    if len(frame) < 4 or not verify_crc(frame):
        return None
    slave, fc = frame[0], frame[1]
    if fc in (0x03, 0x04) and len(frame) == 8:
        start = struct.unpack(">H", frame[2:4])[0]
        count = struct.unpack(">H", frame[4:6])[0]
        return {"slave": slave, "fc": fc, "start": start, "count": count, "type": "read_request"}
    elif fc == 0x06 and len(frame) == 8:
        addr = struct.unpack(">H", frame[2:4])[0]
        value = struct.unpack(">H", frame[4:6])[0]
        return {"slave": slave, "fc": fc, "start": addr, "value": value, "type": "write_single"}
    elif fc == 0x10 and len(frame) >= 9:
        addr = struct.unpack(">H", frame[2:4])[0]
        count = struct.unpack(">H", frame[4:6])[0]
        byte_cnt = frame[6]
        values = [struct.unpack(">H", frame[7+i:9+i])[0] for i in range(0, byte_cnt, 2)]
        return {"slave": slave, "fc": fc, "start": addr, "count": count, "values": values, "type": "write_multiple"}
    elif fc in (0x01, 0x02, 0x05, 0x0F) and len(frame) >= 8:
        addr = struct.unpack(">H", frame[2:4])[0]
        val = struct.unpack(">H", frame[4:6])[0]
        return {"slave": slave, "fc": fc, "start": addr, "value": val, "type": "coil_request"}
    return None


# ── Frame detector ───────────────────────────────────────────────────────────
FRAME_GAP_S = 0.004


class FrameDetector:
    def __init__(self):
        self.buffer = bytearray()
        self.last_byte_time = 0.0

    def feed(self, data: bytes, now: float) -> list[bytes]:
        frames = []
        if self.buffer and (now - self.last_byte_time) > FRAME_GAP_S:
            frames.append(bytes(self.buffer))
            self.buffer.clear()
        self.buffer.extend(data)
        self.last_byte_time = now
        return frames

    def drain(self) -> bytes:
        data = bytes(self.buffer)
        self.buffer.clear()
        return data


# ── Active poller ────────────────────────────────────────────────────────────

def active_poll_cycle(ser: serial.Serial) -> dict[str, dict[int, int | None]]:
    results: dict[str, dict[int, int | None]] = {"holding": {}, "input": {}}
    for fc, label, start, count in POLL_BLOCKS:
        ser.reset_input_buffer()
        time.sleep(0.005)
        request = build_read_request(SLAVE_ID, fc, start, count)
        ser.write(request)
        ser.flush()
        time.sleep(0.05)

        response = bytearray()
        deadline = time.monotonic() + 0.3
        expected_len = 3 + count * 2 + 2
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
                for i, val in enumerate(parsed[2]):
                    results[label][start + i] = val
            else:
                for i in range(count):
                    results[label][start + i] = None
        else:
            for i in range(count):
                results[label][start + i] = None
        time.sleep(0.01)
    return results


# ── Display ──────────────────────────────────────────────────────────────────

# Key registers to highlight in the display
DISPLAY_KEYS = {
    "holding": {
        32: "HR32 low_press/temp?",
        33: "HR33 high_press?",
        187: "HR187 room(DISPROVEN)",
        189: "HR189 outdoor(DISPROVEN)",
        768: "HR768 oper_status",
        773: "HR773 compressor_temp",
        776: "HR776 water_outlet",
        910: "HR910 oper_flag",
        5010: "HR5010 tablet_room",
        3331: "HR3331 shadow_status",
        3340: "HR3340 shadow_temp",
        6400: "HR6400 shadow2_status",
    },
    "input": {
        16: "IR16 ???",
        17: "IR17 ???",
        18: "IR18 ???",
        19: "IR19 ???",
        20: "IR20 ???",
        22: "IR22 ambient",
        23: "IR23 fin_coil",
        24: "IR24 suction",
        25: "IR25 discharge",
        32: "IR32 low_press(bar)",
        33: "IR33 high_press(bar)",
    },
}


def make_table(cycle, current, previous, passive_count, passive_writes, start_time, changes_count):
    elapsed = datetime.now() - start_time
    h = int(elapsed.total_seconds() // 3600)
    m = int((elapsed.total_seconds() % 3600) // 60)

    table = Table(
        title=f"Targeted Monitor #{cycle} | {h}h{m:02d}m | {changes_count} chg | "
              f"{passive_count} passive | {passive_writes} writes",
        expand=True,
    )
    table.add_column("Reg", style="cyan", justify="right", width=8)
    table.add_column("Label", width=24)
    table.add_column("Raw", style="green", justify="right", width=7)
    table.add_column("x0.1", style="blue", justify="right", width=8)
    table.add_column("Chg", style="red", justify="center", width=3)

    # Show only key registers for compact display
    for reg_type in ("holding", "input"):
        prefix = "HR" if reg_type == "holding" else "IR"
        cur = current.get(reg_type, {})
        prev = previous.get(reg_type, {})
        keys = DISPLAY_KEYS.get(reg_type, {})
        for addr in sorted(keys):
            if addr not in cur:
                continue
            val = cur[addr]
            label = keys[addr]
            if val is None:
                table.add_row(f"{prefix}[{addr}]", label, "ERR", "", "")
                continue
            signed = val - 65536 if val > 32767 else val
            scaled = f"{signed * 0.1:.1f}"
            changed = "*" if addr in prev and prev[addr] is not None and prev[addr] != val else ""
            table.add_row(f"{prefix}[{addr}]", label, str(val), scaled, changed)

    # Add HR[32] vs IR[32] comparison row
    hr32 = current.get("holding", {}).get(32)
    ir32 = current.get("input", {}).get(32)
    if hr32 is not None and ir32 is not None:
        table.add_row("", "--- COMPARISON ---", "", "", "")
        table.add_row("", f"HR32/10={hr32*0.1:.1f} IR32/10={ir32*0.1:.1f}",
                       f"d={hr32-ir32}", "", "")

    return table


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="BataviaHeat R290 Targeted Monitor")
    parser.add_argument("--port", default=PORT)
    parser.add_argument("--interval", type=float, default=10.0)
    parser.add_argument("--passive-only", action="store_true")
    args = parser.parse_args()

    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    db_path = OUT_DIR / f"targeted_{ts_str}.db"

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
        CREATE INDEX idx_changes_reg ON changes(reg_type, address);
        CREATE INDEX idx_changes_ts ON changes(timestamp);
    """)

    ser = serial.Serial(
        port=args.port, baudrate=BAUDRATE, parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE, bytesize=serial.EIGHTBITS, timeout=0,
    )
    ser.reset_input_buffer()

    console.print(f"[bold cyan]BataviaHeat R290 Targeted Monitor[/bold cyan]")
    console.print(f"Port: {args.port} | Interval: {args.interval}s | DB: {db_path.name}")
    console.print("[yellow]Press Ctrl+C to stop[/yellow]\n")

    current: dict[str, dict[int, int | None]] = {"holding": {}, "input": {}}
    previous: dict[str, dict[int, int | None]] = {"holding": {}, "input": {}}
    last_values: dict[str, dict[int, int | None]] = {"holding": {}, "input": {}}
    passive_count = 0
    passive_writes = 0
    changes_count = 0
    cycle = 0
    last_request: dict | None = None
    start_time = datetime.now()
    detector = FrameDetector()
    next_poll = time.monotonic() + 3.0

    try:
        with Live(console=console, refresh_per_second=0.5) as live:
            while True:
                now_mono = time.monotonic()

                # ── Passive listening ──
                waiting = ser.in_waiting
                if waiting:
                    raw = ser.read(waiting)
                    for frame in detector.feed(raw, now_mono):
                        decoded = decode_passive_frame(frame)
                        if not decoded:
                            continue
                        now_str = datetime.now().isoformat(timespec="milliseconds")
                        passive_count += 1

                        if decoded["type"] == "read_request":
                            db.execute(
                                "INSERT INTO frames VALUES (NULL,?,?,?,?,?,?,?,?)",
                                (now_str, "REQUEST", f"FC{decoded['fc']:02X}",
                                 decoded["slave"], decoded["start"], decoded["count"],
                                 "", frame.hex()),
                            )
                            last_request = decoded

                        elif decoded["type"] == "read_response" and last_request and last_request.get("type") == "read_request":
                            if decoded["fc"] == last_request["fc"] and decoded["slave"] == last_request["slave"]:
                                fc_name = {0x03: "holding", 0x04: "input"}.get(last_request["fc"], "")
                                if fc_name:
                                    for i, v in enumerate(decoded["values"]):
                                        addr = last_request["start"] + i
                                        db.execute(
                                            "INSERT INTO readings VALUES (NULL,?,?,?,?,?,?)",
                                            (now_str, "passive", fc_name, addr, v, f"0x{v:04X}"),
                                        )
                                        old = last_values[fc_name].get(addr)
                                        if old is not None and old != v:
                                            changes_count += 1
                                            db.execute(
                                                "INSERT INTO changes VALUES (NULL,?,?,?,?,?,?,?,?)",
                                                (now_str, "passive", fc_name, addr, old, v, str(old), str(v)),
                                            )
                                        last_values[fc_name][addr] = v
                            last_request = None
                            db.execute(
                                "INSERT INTO frames VALUES (NULL,?,?,?,?,?,?,?,?)",
                                (now_str, "RESPONSE", f"FC{decoded['fc']:02X}",
                                 decoded["slave"], None, len(decoded["values"]),
                                 " ".join(f"{v:04X}" for v in decoded["values"]), frame.hex()),
                            )

                        elif decoded["type"] == "write_single":
                            passive_writes += 1
                            db.execute(
                                "INSERT INTO frames VALUES (NULL,?,?,?,?,?,?,?,?)",
                                (now_str, "WRITE_SINGLE", "FC06",
                                 decoded["slave"], decoded["start"], decoded["value"],
                                 f"{decoded['value']:04X}", frame.hex()),
                            )
                            last_request = None

                        elif decoded["type"] == "write_multiple":
                            passive_writes += 1
                            db.execute(
                                "INSERT INTO frames VALUES (NULL,?,?,?,?,?,?,?,?)",
                                (now_str, "WRITE_MULTI", "FC10",
                                 decoded["slave"], decoded["start"], decoded["count"],
                                 " ".join(f"{v:04X}" for v in decoded.get("values", [])), frame.hex()),
                            )
                            last_request = None

                        db.commit()

                # ── Active polling ──
                if not args.passive_only and now_mono >= next_poll:
                    detector.drain()
                    ser.reset_input_buffer()
                    time.sleep(0.01)

                    previous = {k: dict(v) for k, v in current.items()}
                    current = active_poll_cycle(ser)
                    cycle += 1

                    now_str = datetime.now().isoformat(timespec="milliseconds")
                    for reg_type in ("holding", "input"):
                        for addr, val in current[reg_type].items():
                            if val is not None:
                                db.execute(
                                    "INSERT INTO readings VALUES (NULL,?,?,?,?,?,?)",
                                    (now_str, "active", reg_type, addr, val, f"0x{val:04X}"),
                                )
                                old = last_values[reg_type].get(addr)
                                if old is not None and old != val:
                                    changes_count += 1
                                    db.execute(
                                        "INSERT INTO changes VALUES (NULL,?,?,?,?,?,?,?,?)",
                                        (now_str, "active", reg_type, addr, old, val, str(old), str(val)),
                                    )
                                last_values[reg_type][addr] = val
                    db.commit()

                    live.update(make_table(
                        cycle, current, previous, passive_count, passive_writes,
                        start_time, changes_count))
                    next_poll = now_mono + args.interval

                if not waiting:
                    time.sleep(0.002)

    except KeyboardInterrupt:
        console.print("\n[yellow]Stopping...[/yellow]")

    # Write summary
    total_readings = db.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
    total_frames = db.execute("SELECT COUNT(*) FROM frames").fetchone()[0]
    total_changes = db.execute("SELECT COUNT(*) FROM changes").fetchone()[0]

    console.print(f"\n[bold green]Done![/bold green]")
    console.print(f"  Database: {db_path.name}")
    console.print(f"  Readings: {total_readings:,}")
    console.print(f"  Frames:   {total_frames:,}")
    console.print(f"  Changes:  {total_changes:,}")

    db.close()
    ser.close()


def decode_passive_frame(frame: bytes) -> dict | None:
    if len(frame) < 4:
        return None
    req = parse_request_frame(frame)
    if req:
        return req
    resp = parse_read_response(frame)
    if resp:
        slave, fc, values = resp
        return {"slave": slave, "fc": fc, "values": values, "type": "read_response"}
    return None


if __name__ == "__main__":
    main()

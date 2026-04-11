#!/usr/bin/env python3
"""Scan the config register gap HR[6600-7500] that tablet_probe.py missed.

Reads holding registers in blocks, prints all non-zero values, and saves
JSON for merging with the main probe data.
"""

import json
import struct
import sys
import time
from datetime import datetime
from pathlib import Path

import serial

# ------------------------------------------------------------------
# Connection settings (same as tablet_probe.py)
# ------------------------------------------------------------------
PORT = "COM5"
BAUD = 9600
SLAVE_ID = 1
TIMEOUT = 0.5

# ------------------------------------------------------------------
# Ranges to scan — the gaps between tablet_probe SCAN_RANGES
# ------------------------------------------------------------------
SCAN_RANGES = [
    # Gap 1: between (6400,6600) and (7000,7200) in tablet_probe
    (6600, 7000),
    # Gap 2: after (7000,7200) — extend to cover P-serie candidate addresses
    (7200, 7500),
]

BLOCK_SIZE = 50


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def build_request(slave: int, fc: int, addr: int, count: int) -> bytes:
    pdu = struct.pack(">BBHH", slave, fc, addr, count)
    c = crc16(pdu)
    return pdu + struct.pack("<H", c)


def transact(ser: serial.Serial, req: bytes, expected_len: int = 256) -> bytes:
    ser.reset_input_buffer()
    ser.write(req)
    time.sleep(0.08)
    resp = ser.read(expected_len)
    return resp


def parse_response(resp: bytes, slave: int, fc: int) -> list[int] | None:
    if len(resp) < 5:
        return None
    if resp[0] != slave:
        return None
    if resp[1] == (fc | 0x80):
        return None  # exception
    if resp[1] != fc:
        return None
    byte_count = resp[2]
    if len(resp) < 3 + byte_count + 2:
        return None
    data = resp[3:3 + byte_count]
    # verify CRC
    payload = resp[:3 + byte_count]
    expected_crc = crc16(payload)
    actual_crc = struct.unpack("<H", resp[3 + byte_count:5 + byte_count])[0]
    if expected_crc != actual_crc:
        return None
    values = []
    for i in range(0, byte_count, 2):
        values.append(struct.unpack(">H", data[i:i + 2])[0])
    return values


def scan_gap(ser: serial.Serial) -> dict[int, int]:
    all_regs: dict[int, int] = {}
    total = sum(e - s for s, e in SCAN_RANGES)
    scanned = 0

    for rstart, rend in SCAN_RANGES:
        addr = rstart
        consecutive_fails = 0

        while addr < rend:
            count = min(BLOCK_SIZE, rend - addr)
            req = build_request(SLAVE_ID, 0x03, addr, count)
            resp = transact(ser, req, 5 + count * 2)
            values = parse_response(resp, SLAVE_ID, 0x03)

            if values:
                for i, v in enumerate(values):
                    all_regs[addr + i] = v
                consecutive_fails = 0
            else:
                consecutive_fails += 1
                if consecutive_fails > 3:
                    skip = min(200, rend - addr)
                    addr += skip
                    scanned += skip
                    consecutive_fails = 0
                    continue

            scanned += count
            addr += count

            pct = scanned * 100 // total
            sys.stdout.write(f"\r  Scanning HR[{rstart}-{rend}]  {pct:3d}%  ({len(all_regs)} found)")
            sys.stdout.flush()

    print()
    return all_regs


def main():
    print(f"Config Gap Scanner — HR[6600-7500]")
    print(f"Port: {PORT}, Slave: {SLAVE_ID}, Baud: {BAUD}")
    print()

    ser = serial.Serial(PORT, BAUD, timeout=TIMEOUT, bytesize=8, parity="N", stopbits=1)
    try:
        regs = scan_gap(ser)
    finally:
        ser.close()

    # Print all found registers
    print(f"\nGevonden: {len(regs)} registers met waarden\n")

    if regs:
        print(f"{'Adres':>6}  {'Waarde':>6}  {'Signed':>7}  {'Hex':>6}")
        print(f"{'─'*6}  {'─'*6}  {'─'*7}  {'─'*6}")
        for addr in sorted(regs):
            v = regs[addr]
            signed = v if v < 32768 else v - 65536
            print(f"{addr:>6}  {v:>6}  {signed:>7}  0x{v:04X}")

    # Also check: do any values match P-serie expected values?
    print("\n── P-serie kenmerkende waarden zoeken ──")
    targets = {"P03=6800": 6800, "P05=2100": 2100, "P09=999": 999}
    for label, val in targets.items():
        matches = [a for a, v in regs.items() if v == val]
        if matches:
            print(f"  {label}: gevonden op HR[{', '.join(str(a) for a in matches)}]")
        else:
            print(f"  {label}: NIET gevonden in gap")

    # Save to JSON
    out_dir = Path(__file__).parent / "data"
    out_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"config_gap_scan_{ts}.json"

    data = {
        "description": "Config gap scan HR[6600-7500]",
        "timestamp": datetime.now().isoformat(),
        "slave_id": SLAVE_ID,
        "scan_ranges": SCAN_RANGES,
        "holding_registers": {str(a): v for a, v in sorted(regs.items())},
        "count": len(regs),
    }
    out_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"\nOpgeslagen: {out_file}")


if __name__ == "__main__":
    main()

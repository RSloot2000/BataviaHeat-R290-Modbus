#!/usr/bin/env python3
"""
Probe all register ranges discovered from the tablet emulator session.
Reads 28 FC03 register blocks that the tablet polls, plus key write registers.
Saves results to JSON with non-zero analysis.
"""

import argparse
import json
import struct
import time
from datetime import datetime
from pathlib import Path

import serial

# ── Config ──────────────────────────────────────────────────────────────
PORT = "COM5"
BAUDRATE = 9600
SLAVE_ID = 1
TIMEOUT = 0.3  # seconds per request

# All 28 FC03 ranges the tablet polls (from emulator_20260317_150944.json)
TABLET_READ_RANGES = [
    (512, 16),     # HR[512-527]
    (768, 54),     # HR[768-821]
    (910, 1),      # HR[910]
    (912, 2),      # HR[912-913]
    (1000, 8),     # HR[1000-1007]
    (1024, 25),    # HR[1024-1048]
    (1283, 87),    # HR[1283-1369]
    (3331, 42),    # HR[3331-3372]
    (4000, 16),    # HR[4000-4015]
    (6400, 45),    # HR[6400-6444]
    (6464, 48),    # HR[6464-6511]
    (6528, 48),    # HR[6528-6575]
    (6592, 47),    # HR[6592-6638]
    (6656, 32),    # HR[6656-6687]
    (6720, 103),   # HR[6720-6822]
    (6848, 40),    # HR[6848-6887]
    (6912, 48),    # HR[6912-6959]
    (6976, 48),    # HR[6976-7023]
    (7040, 48),    # HR[7040-7087]
    (7104, 48),    # HR[7104-7151]
    (7168, 48),    # HR[7168-7215]
    (7296, 48),    # HR[7296-7343]
    (7360, 48),    # HR[7360-7407]
    (7424, 48),    # HR[7424-7471]
    (21501, 5),    # HR[21501-21505]
    (21506, 102),  # HR[21506-21607]
    (21608, 102),  # HR[21608-21709]
    (21812, 102),  # HR[21812-21913]
]

# Key write registers to also read
WRITE_REGISTERS = [5010, 6400, 21500]

# Extra: Coil[8] - tablet heartbeat
COIL_PROBES = [8]


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


def build_fc03(slave: int, start: int, count: int) -> bytes:
    pdu = struct.pack(">BBhH", slave, 3, start, count)
    c = crc16(pdu)
    return pdu + struct.pack("<H", c)


def build_fc01(slave: int, start: int, count: int) -> bytes:
    pdu = struct.pack(">BBhH", slave, 1, start, count)
    c = crc16(pdu)
    return pdu + struct.pack("<H", c)


def parse_fc03_response(resp: bytes, expected_count: int):
    """Parse FC03 response, return list of register values or None on error."""
    if len(resp) < 5:
        return None
    slave, fc, byte_count = resp[0], resp[1], resp[2]
    if fc & 0x80:  # exception
        return None
    expected_len = 3 + byte_count + 2
    if len(resp) < expected_len:
        return None
    # verify CRC
    payload = resp[:3 + byte_count]
    crc_recv = struct.unpack("<H", resp[3 + byte_count:5 + byte_count])[0]
    if crc16(payload) != crc_recv:
        return None
    # unpack registers
    values = []
    for i in range(expected_count):
        offset = 3 + i * 2
        if offset + 2 > len(payload):
            break
        values.append(struct.unpack(">H", payload[offset:offset + 2])[0])
    return values


def parse_fc01_response(resp: bytes):
    """Parse FC01 response, return list of coil bits or None."""
    if len(resp) < 5:
        return None
    slave, fc, byte_count = resp[0], resp[1], resp[2]
    if fc & 0x80:
        return None
    expected_len = 3 + byte_count + 2
    if len(resp) < expected_len:
        return None
    payload = resp[:3 + byte_count]
    crc_recv = struct.unpack("<H", resp[3 + byte_count:5 + byte_count])[0]
    if crc16(payload) != crc_recv:
        return None
    coil_bytes = payload[3:]
    bits = []
    for b in coil_bytes:
        for bit in range(8):
            bits.append((b >> bit) & 1)
    return bits


def read_registers(ser, start, count, retries=2):
    """Read holding registers, return list of values or None."""
    for attempt in range(retries + 1):
        ser.reset_input_buffer()
        req = build_fc03(SLAVE_ID, start, count)
        ser.write(req)
        time.sleep(0.05 + count * 0.002)  # scale wait for larger reads
        resp = ser.read(5 + count * 2)
        values = parse_fc03_response(resp, count)
        if values is not None:
            return values
        time.sleep(0.1)
    return None


def read_coils(ser, start, count, retries=2):
    """Read coils, return list of bit values or None."""
    for attempt in range(retries + 1):
        ser.reset_input_buffer()
        req = build_fc01(SLAVE_ID, start, count)
        ser.write(req)
        time.sleep(0.1)
        byte_count = (count + 7) // 8
        resp = ser.read(5 + byte_count)
        bits = parse_fc01_response(resp)
        if bits is not None:
            return bits[:count]
        time.sleep(0.1)
    return None


def signed16(v):
    """Convert unsigned 16-bit to signed."""
    return v - 65536 if v > 32767 else v


def main():
    parser = argparse.ArgumentParser(description="Probe tablet register ranges on heat pump")
    parser.add_argument("--port", default=PORT)
    parser.add_argument("--passes", type=int, default=2,
                        help="Number of read passes (to detect dynamic registers)")
    parser.add_argument("--delay", type=float, default=0.15,
                        help="Delay between requests (seconds)")
    args = parser.parse_args()

    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = data_dir / f"tablet_probe_{ts}.json"

    results = {
        "timestamp": datetime.now().isoformat(),
        "passes": args.passes,
        "ranges": {},
        "write_registers": {},
        "coils": {},
        "summary": {},
    }

    ser = serial.Serial(args.port, BAUDRATE, timeout=TIMEOUT,
                        bytesize=8, parity="N", stopbits=1)
    print(f"Verbonden met {args.port} @ {BAUDRATE} baud")
    print(f"Probing {len(TABLET_READ_RANGES)} register bereiken, {args.passes} pass(es)...\n")

    total_regs = 0
    total_nonzero = 0
    total_errors = 0

    for pass_num in range(1, args.passes + 1):
        print(f"═══ Pass {pass_num}/{args.passes} ═══")

        for start, count in TABLET_READ_RANGES:
            end = start + count - 1
            key = f"HR[{start}-{end}]"

            values = read_registers(ser, start, count)
            time.sleep(args.delay)

            if values is None:
                print(f"  ✗ {key:25s}  FOUT (geen antwoord)")
                if pass_num == 1:
                    if key not in results["ranges"]:
                        results["ranges"][key] = {"start": start, "count": count, "error": True}
                    total_errors += 1
                continue

            nonzero = [(start + i, v) for i, v in enumerate(values) if v != 0]
            total_regs += count
            total_nonzero += len(nonzero)

            if pass_num == 1:
                results["ranges"][key] = {
                    "start": start,
                    "count": count,
                    "error": False,
                    "values": {str(start + i): v for i, v in enumerate(values)},
                    "nonzero_count": len(nonzero),
                    "passes": [values],
                }
            else:
                if key in results["ranges"] and not results["ranges"][key].get("error"):
                    results["ranges"][key]["passes"].append(values)

            nz_str = f"{len(nonzero):3d} non-zero" if nonzero else "all zero"
            status = "✓" if values is not None else "✗"
            print(f"  {status} {key:25s}  {count:3d} regs, {nz_str}")

            # Show interesting non-zero values (first pass only, max 10)
            if pass_num == 1 and nonzero:
                for addr, val in nonzero[:10]:
                    s = signed16(val)
                    extra = ""
                    if 100 < val < 1000:
                        extra = f"  (÷10={val/10:.1f})"
                    elif val == 0xFF00:
                        extra = "  (=0xFF00)"
                    elif val > 32767:
                        extra = f"  (signed={s})"
                    print(f"       HR[{addr}] = {val}{extra}")
                if len(nonzero) > 10:
                    print(f"       ... en nog {len(nonzero) - 10} meer")

        # Also read the write registers
        if pass_num == 1:
            print(f"\n  Schrijf-registers:")
            for addr in WRITE_REGISTERS:
                values = read_registers(ser, addr, 1)
                time.sleep(args.delay)
                if values:
                    v = values[0]
                    s = signed16(v)
                    extra = ""
                    if addr == 5010:
                        extra = f"  ({v/10:.1f}°C kamertemp)"
                    elif addr == 6400:
                        modes = {0: "off", 1: "cooling", 2: "heating", 3: "auto", 4: "DHW"}
                        extra = f"  ({modes.get(v, '?')})"
                    print(f"  ✓ HR[{addr}] = {v}{extra}")
                    results["write_registers"][str(addr)] = v
                else:
                    print(f"  ✗ HR[{addr}]  FOUT")

            # Read coils
            print(f"\n  Coils:")
            for coil_addr in COIL_PROBES:
                bits = read_coils(ser, coil_addr, 1)
                time.sleep(args.delay)
                if bits is not None:
                    print(f"  ✓ Coil[{coil_addr}] = {bits[0]}")
                    results["coils"][str(coil_addr)] = bits[0]
                else:
                    print(f"  ✗ Coil[{coil_addr}]  FOUT")

        print()

    ser.close()

    # Detect dynamic registers (changed between passes)
    if args.passes >= 2:
        dynamic = []
        for key, info in results["ranges"].items():
            if info.get("error") or len(info.get("passes", [])) < 2:
                continue
            p1, p2 = info["passes"][0], info["passes"][1]
            for i, (v1, v2) in enumerate(zip(p1, p2)):
                if v1 != v2:
                    addr = info["start"] + i
                    dynamic.append({"addr": addr, "pass1": v1, "pass2": v2,
                                    "delta": v2 - v1})
        results["summary"]["dynamic_registers"] = dynamic
        if dynamic:
            print(f"═══ Dynamische registers (veranderd tussen passes) ═══")
            for d in dynamic:
                print(f"  HR[{d['addr']}]: {d['pass1']} → {d['pass2']} (Δ{d['delta']:+d})")
            print()

    # Summary
    range_ok = sum(1 for r in results["ranges"].values() if not r.get("error"))
    range_err = sum(1 for r in results["ranges"].values() if r.get("error"))
    all_nonzero = []
    for key, info in results["ranges"].items():
        if not info.get("error") and "values" in info:
            for addr_str, val in info["values"].items():
                if val != 0:
                    all_nonzero.append((int(addr_str), val))

    results["summary"]["ranges_ok"] = range_ok
    results["summary"]["ranges_error"] = range_err
    results["summary"]["total_registers"] = total_regs
    results["summary"]["total_nonzero"] = len(all_nonzero)

    print(f"═══ Samenvatting ═══")
    print(f"  Bereiken gelezen:  {range_ok}/{len(TABLET_READ_RANGES)}")
    print(f"  Bereiken fout:     {range_err}")
    print(f"  Totaal registers:  {total_regs}")
    print(f"  Non-zero waarden:  {len(all_nonzero)}")
    if args.passes >= 2:
        print(f"  Dynamische regs:   {len(results['summary'].get('dynamic_registers', []))}")
    print(f"\n  Opgeslagen: {outfile}")

    # Remove passes from JSON to save space (keep only values from pass 1)
    for key in results["ranges"]:
        if "passes" in results["ranges"][key]:
            del results["ranges"][key]["passes"]

    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()

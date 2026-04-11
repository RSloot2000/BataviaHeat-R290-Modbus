#!/usr/bin/env python3
"""Decode the daily energy history records from HR[21500+]."""

import json

with open("data/tablet_probe_20260317_152351.json", encoding="utf-8") as f:
    data = json.load(f)

def decode_ascii_regs(vals, start, count):
    """Decode count registers starting at start as ASCII string."""
    s = ""
    for i in range(count):
        v = vals.get(str(start + i), 0)
        hi = (v >> 8) & 0xFF
        lo = v & 0xFF
        s += chr(hi) if 0x20 <= hi <= 0x7E else ""
        s += chr(lo) if 0x20 <= lo <= 0x7E else ""
    return s

# HR[21501-21505] = header
print("=== Header HR[21501-21505] ===")
info = data["ranges"]["HR[21501-21505]"]
vals = info["values"]
print(f"  HR[21501] = {vals['21501']}  (aantal dagen historie?)")
unit = decode_ascii_regs(vals, 21502, 3)
print(f"  HR[21502-21504] = \"{unit}\"  (eenheid: 0.1kWh)")
print(f"  HR[21505] = {vals['21505']}  (onbekend)")

# Each daily record is 17 registers:
# [0-4]: date as ASCII "DD/MM/YYYY" (5 regs = 10 bytes)
# [5]: status/flag byte (D=68, H=72, or small number)
# [6-16]: energy data fields
RECORD_SIZE = 17

print("\n=== Dagelijkse energierecords (17 registers per dag) ===")
print("  Formaat: datum + status + 11 data-registers")
print()

# Process all 3 blocks
blocks = [
    ("HR[21506-21607]", 21506, 102),
    ("HR[21608-21709]", 21608, 102),
    ("HR[21812-21913]", 21812, 102),
]

for block_name, block_start, block_count in blocks:
    info = data["ranges"].get(block_name, {})
    if "values" not in info:
        print(f"  {block_name}: GEEN DATA")
        continue

    vals = info["values"]
    num_records = block_count // RECORD_SIZE

    print(f"  --- {block_name} ({num_records} records) ---")

    for rec in range(num_records):
        base = block_start + rec * RECORD_SIZE

        # Decode date
        date_str = decode_ascii_regs(vals, base, 5)

        # Status/flag
        status = vals.get(str(base + 5), 0)
        status_hi = (status >> 8) & 0xFF
        status_lo = status & 0xFF
        status_ch = chr(status_lo) if 0x20 <= status_lo <= 0x7E else f"0x{status_lo:02X}"

        # Data fields (11 registers, base+6 to base+16)
        fields = []
        for i in range(6, RECORD_SIZE):
            v = vals.get(str(base + i), 0)
            fields.append(v)

        # Pretty print
        nz_fields = [(i, v) for i, v in enumerate(fields) if v != 0]
        print(f"\n  [{date_str}] status={status_ch}({status})")
        for i, v in enumerate(fields):
            label = ""
            # Guess at field meanings based on energy context
            if i == 0:
                label = "verbruik_elek?"
            elif i == 1:
                label = "opgewekt_warmte?"
            elif i == 2:
                label = "???"
            elif i == 3:
                label = "COP_x10?"

            extra = ""
            if v != 0:
                if 10 <= v <= 9999:
                    extra = f" (div10={v/10:.1f})"
                marker = " <--"
            else:
                marker = ""
                extra = ""

            if v != 0:
                print(f"    field[{i:2d}] HR[{base+6+i}] = {v:6d}{extra}  {label}{marker}")

    print()

# Also decode HR[4000-4015] = firmware string
print("\n=== HR[4000-4015] = Firmware string ===")
info = data["ranges"]["HR[4000-4015]"]
vals = info["values"]
fw = decode_ascii_regs(vals, 4000, 16)
print(f"  \"{fw}\"")
print("  Dit is de 'External PCB' firmware: X1.HL081B.K05.001-1.V100A03")

# HR[6595] = humidity
print(f"\n=== Luchtvochtigheid ===")
print(f"  HR[6595] = 520 (div10 = 52.0%) <- dit is de opgeslagen luchtvochtigheid!")
print(f"  HR[6594] = 700 (div10 = 70.0%) <- max grenswaarde?")

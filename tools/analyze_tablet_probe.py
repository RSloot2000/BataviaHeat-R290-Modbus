#!/usr/bin/env python3
"""Quick analysis of tablet probe data - check for ASCII strings and energy history."""

import json
import sys

with open("data/tablet_probe_20260317_152351.json", encoding="utf-8") as f:
    data = json.load(f)

# Check if large values might be ASCII strings
print("=== ASCII analyse van verdachte bereiken ===")
for key in ["HR[4000-4015]", "HR[21501-21505]", "HR[21506-21607]",
            "HR[21608-21709]", "HR[21812-21913]"]:
    info = data["ranges"].get(key, {})
    if "values" not in info:
        continue
    vals = info["values"]
    # Try to decode as ASCII (2 bytes per register, big-endian)
    ascii_str = ""
    raw_vals = []
    for addr in sorted(vals.keys(), key=int):
        v = vals[addr]
        raw_vals.append((int(addr), v))
        hi = (v >> 8) & 0xFF
        lo = v & 0xFF
        if 0x20 <= hi <= 0x7E:
            ascii_str += chr(hi)
        else:
            ascii_str += "."
        if 0x20 <= lo <= 0x7E:
            ascii_str += chr(lo)
        else:
            ascii_str += "."
    print(f"\n{key} als ASCII: \"{ascii_str}\"")
    # Also show raw values
    nz = [(a, v) for a, v in raw_vals if v != 0]
    print(f"  Non-zero: {len(nz)}/{len(raw_vals)}")
    for addr, v in nz[:25]:
        hi, lo = (v >> 8) & 0xFF, v & 0xFF
        ch = chr(hi) if 0x20 <= hi <= 0x7E else "."
        cl = chr(lo) if 0x20 <= lo <= 0x7E else "."
        print(f"  HR[{addr}] = {v:5d} (0x{v:04X}) [{ch}{cl}]")
    if len(nz) > 25:
        print(f"  ... en nog {len(nz)-25} meer")

# Analyse HR[6592-6638] for humidity and other config
print("\n\n=== HR[6592-6638] detail (humidity range?) ===")
info = data["ranges"].get("HR[6592-6638]", {})
if "values" in info:
    for addr in sorted(info["values"].keys(), key=int):
        v = info["values"][addr]
        if v != 0:
            s = v - 65536 if v > 32767 else v
            extra = ""
            if 100 < v < 1000:
                extra = f" (div10={v/10:.1f})"
            elif v > 32767:
                extra = f" (signed={s})"
            print(f"  HR[{int(addr)}] = {v}{extra}")

# Look for energy-like values across all ranges
print("\n\n=== Mogelijke energiedata (grote waarden die op kWh/MWh lijken) ===")
for key, info in data["ranges"].items():
    if "values" not in info:
        continue
    for addr_str, v in info["values"].items():
        addr = int(addr_str)
        # Energy counters: typically 100-99999, or pairs for 32-bit
        if 1000 <= v <= 65000 and addr not in range(4000, 4016):
            # Skip known ASCII ranges
            if addr in range(21506, 21608) or addr in range(21608, 21710) or addr in range(21812, 21914):
                continue
            if addr in range(7000, 7500):
                continue  # config
            if v > 10000:
                s = v - 65536 if v > 32767 else v
                print(f"  {key} HR[{addr}] = {v} (0x{v:04X}, signed={s})")

# Check 21500+ structure: look for repeating patterns suggesting monthly data
print("\n\n=== HR[21506-21607] structuur analyse (102 regs = 12 maanden * 8.5?) ===")
info = data["ranges"].get("HR[21506-21607]", {})
if "values" in info:
    vals = info["values"]
    # Group by 17 (102/6=17) or by other patterns
    all_vals = [vals.get(str(21506 + i), 0) for i in range(102)]
    # Try grouping by various sizes
    for group_size in [6, 8, 10, 12, 17, 34, 51]:
        if 102 % group_size == 0:
            groups = 102 // group_size
            print(f"\n  Gegroepeerd per {group_size} ({groups} groepen):")
            for g in range(min(groups, 4)):
                chunk = all_vals[g*group_size:(g+1)*group_size]
                # Show as hex for ASCII detection
                ascii_part = ""
                for v in chunk[:8]:
                    hi, lo = (v >> 8) & 0xFF, v & 0xFF
                    ascii_part += chr(hi) if 0x20 <= hi <= 0x7E else "."
                    ascii_part += chr(lo) if 0x20 <= lo <= 0x7E else "."
                print(f"    Groep {g}: {chunk[:8]}... ASCII=\"{ascii_part}\"")

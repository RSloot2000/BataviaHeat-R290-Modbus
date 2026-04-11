"""
Match T/O/S status monitor values against probe data to find register addresses.
Uses old probe data from 2026-03-17 (before parameter changes).
"""
import json
import sys
from pathlib import Path

# Load ALL data sources and merge
all_regs = {}

# Source 1: tablet_probe (nested: registers -> '1' -> holding_registers -> {'addr': val})
probe_file = Path('data/tablet_probe_20260317_180509.json')
if probe_file.exists():
    probe = json.loads(probe_file.read_text())
    for slave_id, slave_data in probe.get('registers', {}).items():
        for addr_str, val in slave_data.get('holding_registers', {}).items():
            all_regs[int(addr_str)] = val

# Source 2: clean scan (flat: {'addr': val})
for scan_name in ['scan_clean_full.json', 'midea_probe_clean1.json', 'midea_probe_clean2.json']:
    scan_file = Path('data') / scan_name
    if scan_file.exists():
        scan = json.loads(scan_file.read_text())
        if isinstance(scan, dict):
            # Try common structures
            if 'holding_registers' in scan:
                src = scan['holding_registers']
            elif 'registers' in scan:
                src = scan['registers']
                if isinstance(src, dict) and any(isinstance(v, dict) for v in src.values()):
                    # Nested like probe
                    for sid, sd in src.items():
                        if isinstance(sd, dict) and 'holding_registers' in sd:
                            src = sd['holding_registers']
                            break
            else:
                src = scan
            for k, v in src.items():
                try:
                    addr = int(k)
                    if isinstance(v, (int, float)):
                        all_regs.setdefault(addr, v)  # don't overwrite probe data
                except (ValueError, TypeError):
                    pass

print(f"Total registers loaded: {len(all_regs)}")
if all_regs:
    print(f"Range: {min(all_regs.keys())} - {max(all_regs.keys())}")
print()

# T-series target values (pre-change probe data had M02=50, M11=0, P01=0)
# Note: some values will differ in probe vs current tablet readings
# because parameters were changed. We mark those.
targets = {
    # Sensor values that shouldn't change between old/new:
    "T01 ambient 15.6C": [156],
    "T03 water outlet 48.5C": [485],
    "T04 system outlet 30.5C": [305],
    "T06 buffer upper 51.9C": [519],
    "T07 buffer lower 51.8C": [518],
    "T09 3way_v1 409": [409],
    "T10 3way_v2 410": [410],
    "T11 3way_v3 409": [409],  # same as T09
    "T12 unit_status 4": [4],
    "T13 inverter_status 35": [35],
    "T15 mode 2": [2],
    "T17 target_temp 28C": [28, 280],  # CHANGED by weather curve
    "T18 control_temp 51.8C": [518],
    "T28 system_runtime 127h": [127],
    "T30 module_temp 20.6C": [206],
    "T32 target_speed 20rps": [20, 200, 2000],
    "T36 bus_voltage 322.8V": [3228],
    "T38 inv_current 1.3A": [13],
    "T39 PFC_temp 21.4C": [214],
    "T41 freq_limit 7": [7],
    "T89 comp_runtime 34h": [34],
    "T90 DHW_max 75C": [75, 750],
    "T91 DHW_min 18C": [18, 180],
    "T92 cool_max 35C": [35, 350],
    "T93 cool_min 10C": [10, 100],
    "T94 heat_max 28C": [28, 280],
    "T95 heat_min 28C": [28, 280],
    "T101 room_temp 24.7C": [247],
}

# Search for matches
for t_name, target_vals in targets.items():
    matches = []
    for addr in sorted(all_regs.keys()):
        val = all_regs[addr]
        if val in target_vals:
            matches.append(f"HR[{addr}]={val}")
    if matches and len(matches) <= 20:
        print(f"{t_name}: {' | '.join(matches)}")
    elif matches:
        print(f"{t_name}: {len(matches)} matches (first 8: {' | '.join(matches[:8])})")
    else:
        print(f"{t_name}: NO MATCH")

print("\n" + "="*70)
print("SHADOW BLOCK HR[3331-3372] ANALYSIS")
print("="*70)
DC = 32836  # 0x8044 = sensor disconnected
for addr in range(3331, 3373):
    val = all_regs.get(addr, '?')
    if val == DC:
        status = "DISCONNECTED (0x8044)"
    elif val == 0:
        status = "zero"
    elif isinstance(val, int) and 100 <= val <= 800:
        status = f"temp? {val/10:.1f}°C"
    elif isinstance(val, int) and 1000 <= val <= 9999:
        status = f"raw {val}"
    else:
        status = f"raw {val}"
    print(f"  HR[{addr}] = {val:>6}  {status}" if isinstance(val, int) else f"  HR[{addr}] = {val}")

print("\n" + "="*70)
print("COMPRESSOR BLOCK HR[1283-1369] (non-zero, non-DC)")
print("="*70)
for addr in range(1283, 1370):
    val = all_regs.get(addr, None)
    if val is not None and val != 0 and val != DC:
        print(f"  HR[{addr}] = {val:>6}  ({val/10:.1f})" if val < 10000 else f"  HR[{addr}] = {val:>6}")

print("\n" + "="*70)
print("SYSTEM BLOCK HR[768-821] (non-zero)")
print("="*70)
for addr in range(768, 822):
    val = all_regs.get(addr, None)
    if val is not None and val != 0:
        print(f"  HR[{addr}] = {val:>6}")

print("\n" + "="*70)
print("STATUS BLOCK HR[1024-1048] (non-zero)")
print("="*70)
for addr in range(1024, 1049):
    val = all_regs.get(addr, None)
    if val is not None and val != 0:
        print(f"  HR[{addr}] = {val:>6}")

print("\n" + "="*70)
print("PRIMARY BLOCK HR[0-100] (non-zero)")
print("="*70)
for addr in range(0, 101):
    val = all_regs.get(addr, None)
    if val is not None and val != 0:
        print(f"  HR[{addr}] = {val:>6}  ({val/10:.1f})" if 50 < val < 5000 else f"  HR[{addr}] = {val:>6}")

print("\n" + "="*70)
print("FULL DUMP of tablet-polled ranges (non-zero values):")
print("="*70)

# Tablet poll ranges
tablet_ranges = [
    (512, 527), (768, 821), (910, 913),
    (1000, 1007), (1024, 1048), (1283, 1369),
    (3331, 3372), (4000, 4015),
]

for start, end in tablet_ranges:
    vals = []
    for addr in range(start, end + 1):
        if addr in all_regs and all_regs[addr] != 0:
            vals.append(f"  HR[{addr}] = {all_regs[addr]}")
    if vals:
        print(f"\n--- HR[{start}-{end}] ---")
        for v in vals:
            print(v)

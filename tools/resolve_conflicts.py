"""Resolve HR[1322] superheat-vs-current conflict and find T29 register.

Monitors key registers at 5s intervals. When compressor starts:
- Compares HR[42] (confirmed superheat) with HR[1322] (T33 candidate)
  If they diverge → HR[1322] is NOT superheat but compressor current
  If they match → HR[1322] IS superheat, T33 mapping needs revisiting
- Scans compressor block (HR[1283-1320]) for T29 (compressor speed, rps)
  T29 was 0 when comp OFF, HR[1289]=169.6 → HR[1289] is NOT T29

Usage: python resolve_conflicts.py
  Runs until compressor cycles ON, captures data, then exits.
"""

import time
import sys
from pymodbus.client import ModbusSerialClient

PORT = "COM5"
SLAVE = 1

# Registers to monitor every cycle
MONITOR_REGS = {
    42:   ("superheat_primary",    "°C", 0.1),
    1283: ("compressor_on_off",    "",    1),
    1322: ("T33_candidate",        "?",   0.1),
    1365: ("mirror_1322",          "?",   0.1),
    1325: ("inverter_current_T38", "A",   0.1),
    1327: ("torque_T34",           "%",   0.1),
    1335: ("comp_voltage_T35",     "V",   0.1),
    1338: ("mains_voltage",        "V",   0.1),
    1368: ("dc_bus_T36",           "V",   0.1),
    41:   ("compressor_power",     "W",   1),
}

# Full compressor block to scan for T29 when compressor turns ON
# T29 = compressor speed in rps, should be 0 when OFF and >0 when ON
T29_SCAN_START = 1283
T29_SCAN_COUNT = 87  # 1283-1369

def read_reg(client, addr):
    """Read a single holding register, return raw value or None."""
    resp = client.read_holding_registers(addr, count=1, device_id=SLAVE)
    if resp.isError():
        return None
    return resp.registers[0]

def read_block(client, start, count):
    """Read a block of holding registers, return list of (addr, raw) or None."""
    resp = client.read_holding_registers(start, count=count, device_id=SLAVE)
    if resp.isError():
        return None
    return [(start + i, v) for i, v in enumerate(resp.registers)]

def main():
    client = ModbusSerialClient(
        port=PORT, baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=1
    )
    if not client.connect():
        print("ERROR: Cannot connect to COM5")
        sys.exit(1)

    print("=== Conflict Resolver: HR[1322] superheat vs current, T29 search ===")
    print("Waiting for compressor to start... (Ctrl+C to stop)\n")

    comp_was_off = True
    comp_on_readings = []

    try:
        while True:
            # Read monitored registers
            values = {}
            for addr in sorted(MONITOR_REGS):
                raw = read_reg(client, addr)
                values[addr] = raw

            comp_on = values.get(1283, 0) == 1
            ts = time.strftime("%H:%M:%S")

            # Format status line
            hr42 = values.get(42)
            hr1322 = values.get(1322)
            comp_power = values.get(41, 0)

            if hr42 is not None and hr1322 is not None:
                s42 = hr42 * 0.1
                s1322 = hr1322 * 0.1
                match = "MATCH" if hr42 == hr1322 else f"DIFFER (42={s42:.1f}, 1322={s1322:.1f})"
            else:
                match = "READ_ERROR"

            status = "ON " if comp_on else "OFF"
            print(f"[{ts}] Comp={status} Power={comp_power:4d}W  "
                  f"HR[42]={s42:5.1f}  HR[1322]={s1322:5.1f}  {match}  "
                  f"T38={values.get(1325,0)*0.1:.1f}A  "
                  f"T34={values.get(1327,0)*0.1:.1f}%  "
                  f"T35={values.get(1335,0)*0.1:.1f}V")

            # When compressor transitions OFF→ON: scan full block for T29
            if comp_on and comp_was_off:
                print("\n*** COMPRESSOR STARTED! Scanning full block for T29... ***")
                time.sleep(2)  # Let values stabilize

                # Read baseline (what was 0 when OFF) vs now
                block = read_block(client, T29_SCAN_START, T29_SCAN_COUNT)
                if block:
                    print(f"\n{'Addr':>6}  {'Raw':>6}  {'×0.1':>8}  {'Name/Notes'}")
                    print("-" * 50)
                    for addr, raw in block:
                        name = MONITOR_REGS.get(addr, (None,))[0] or ""
                        scaled = raw * 0.1
                        # Highlight registers that are non-zero (potential T29)
                        marker = ""
                        if addr == 1289:
                            marker = " ← was 169.6 when OFF (NOT T29)"
                        elif raw > 0 and addr not in MONITOR_REGS:
                            marker = " ← CANDIDATE for T29?"
                        print(f"  {addr:4d}  {raw:6d}  {scaled:8.1f}  {name}{marker}")

                comp_on_readings.append(values.copy())

            # When we have 3+ ON readings, do final analysis
            if comp_on and len(comp_on_readings) >= 3:
                print("\n\n=== ANALYSIS (3 readings with compressor ON) ===")
                all_match = all(
                    r.get(42) == r.get(1322) for r in comp_on_readings
                )
                if all_match:
                    print("RESULT: HR[42] == HR[1322] in ALL ON readings")
                    print("→ HR[1322] IS superheat (not compressor current)")
                    print("→ T33 on tablet may display superheat, not current")
                    print("→ OR our T33 register mapping was wrong (both were 0)")
                else:
                    print("RESULT: HR[42] != HR[1322] — they DIVERGE!")
                    print("→ HR[1322] is NOT superheat but a different value")
                    for i, r in enumerate(comp_on_readings):
                        print(f"  Reading {i+1}: HR[42]={r[42]*0.1:.1f}  "
                              f"HR[1322]={r[1322]*0.1:.1f}")

                # Keep monitoring a bit more
                if len(comp_on_readings) >= 10:
                    print("\n10 ON readings captured. Done.")
                    break

            comp_was_off = not comp_on
            time.sleep(5)

    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        client.close()
        if comp_on_readings:
            print(f"\nCaptured {len(comp_on_readings)} readings with compressor ON.")

if __name__ == "__main__":
    main()

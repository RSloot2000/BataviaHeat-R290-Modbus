"""Probe Midea R290 energy registers HR[143-186] on BataviaHeat.

Reads the full energy register block in one pass and displays results
alongside the expected Midea R290 register definitions.

Usage: python probe_energy.py
  Requires: USB-RS485 on COM5, tablet DISCONNECTED, slave ID 1.
"""

from pymodbus.client import ModbusSerialClient
import time

PORT = "COM5"
SLAVE = 1

# Midea R290 energy register definitions (from online_registers.py / APK decompile)
MIDEA_ENERGY = {
    143: ("electricity_consumption_hi",         "kWh",  0.01, "DWORD hi met 144"),
    144: ("electricity_consumption_lo",         "kWh",  1,    "DWORD lo"),
    145: ("power_output_hi",                    "kWh",  0.01, "DWORD hi met 146 — thermisch"),
    146: ("power_output_lo",                    "kWh",  1,    "DWORD lo"),
    147: ("pump_feedback",                      "%",    0.1,  "Pompfeedback (bevestigd)"),
    148: ("realtime_heating_capacity",          "kW",   0.01, "Live thermisch vermogen"),
    149: ("realtime_renewable_heating_cap",     "kW",   0.01, "Live hernieuwbaar"),
    150: ("realtime_heating_power_consumption", "kW",   0.01, "★ LIVE STROOMVERBRUIK"),
    151: ("realtime_heating_cop",               "COP",  0.01, "★ LIVE COP"),
    152: ("total_heating_energy_produced_hi",   "kWh",  0.01, "DWORD hi met 153"),
    153: ("total_heating_energy_produced_lo",   "kWh",  1,    "DWORD lo"),
    154: ("total_renewable_heating_hi",         "kWh",  0.01, "DWORD hi met 155"),
    155: ("total_renewable_heating_lo",         "kWh",  1,    "DWORD lo"),
    156: ("total_heating_power_consumed_hi",    "kWh",  0.01, "DWORD hi met 157"),
    157: ("total_heating_power_consumed_lo",    "kWh",  1,    "DWORD lo"),
    158: ("total_heating_produced_master_hi",   "kWh",  0.01, "DWORD hi met 159"),
    159: ("total_heating_produced_master_lo",   "kWh",  1,    "DWORD lo"),
    160: ("total_renewable_heating_master_hi",  "kWh",  0.01, "DWORD hi met 161"),
    161: ("total_renewable_heating_master_lo",  "kWh",  1,    "DWORD lo"),
    162: ("total_heating_consumed_master_hi",   "kWh",  0.01, "DWORD hi met 163"),
    163: ("total_heating_consumed_master_lo",   "kWh",  1,    "DWORD lo — ook energieteller 1"),
    164: ("total_cop_heating_master",           "COP",  0.01, "Totaal COP verwarming"),
    165: ("total_cooling_energy_produced_hi",   "kWh",  0.01, "DWORD hi met 166"),
    166: ("total_cooling_energy_produced_lo",   "kWh",  1,    "DWORD lo"),
    167: ("total_cooling_renewable_hi",         "kWh",  0.01, "DWORD hi met 168"),
    168: ("total_cooling_renewable_lo",         "kWh",  1,    "DWORD lo"),
    169: ("total_cooling_consumed_hi",          "kWh",  0.01, "DWORD hi met 170"),
    170: ("total_cooling_consumed_lo",          "kWh",  1,    "DWORD lo"),
    171: ("total_cop_cooling_master",           "COP",  0.01, "Totaal COP koeling"),
    172: ("total_dhw_energy_produced_hi",       "kWh",  0.01, "DWORD hi met 173"),
    173: ("total_dhw_energy_produced_lo",       "kWh",  1,    "DWORD lo"),
    174: ("total_dhw_renewable_hi",             "kWh",  0.01, "DWORD hi met 175"),
    175: ("total_dhw_renewable_lo",             "kWh",  1,    "DWORD lo"),
    176: ("total_dhw_consumed_hi",              "kWh",  0.01, "DWORD hi met 177"),
    177: ("total_dhw_consumed_lo",              "kWh",  1,    "DWORD lo"),
    178: ("total_cop_dhw",                      "COP",  0.01, "Totaal COP warm water"),
    179: ("realtime_renewable_cooling_cap",     "kW",   0.01, "Live hernieuwbaar koeling"),
    180: ("realtime_cooling_capacity",          "kW",   0.01, "Live koelvermogen"),
    181: ("realtime_cooling_consumption",       "kW",   0.01, "Live koelverbruik"),
    182: ("realtime_cooling_eer",               "COP",  0.01, "Live koeling EER"),
    183: ("realtime_dhw_heating_capacity",      "kW",   0.01, "Live DHW vermogen"),
    184: ("realtime_dhw_renewable_capacity",    "kW",   0.01, "Live DHW hernieuwbaar"),
    185: ("realtime_dhw_consumption",           "kW",   0.01, "Live DHW verbruik"),
    186: ("realtime_dhw_cop",                   "COP",  0.01, "Live DHW COP"),
}

# Also read known compressor registers for context
CONTEXT_REGS = {
    41:   ("compressor_power",      "W",   1),
    1283: ("compressor_on_off",     "",    1),
    1325: ("inverter_current_T38",  "A",   0.1),
    1335: ("comp_voltage_T35",      "V",   0.1),
    1338: ("mains_voltage",         "V",   0.1),
}

DISCONNECTED = {32834, 32836}  # 0x8042, 0x8044


def main():
    client = ModbusSerialClient(
        port=PORT, baudrate=9600, bytesize=8,
        parity="N", stopbits=1, timeout=1,
    )
    if not client.connect():
        print(f"FOUT: Kan niet verbinden met {PORT}")
        return

    print("=" * 90)
    print("BataviaHeat R290 — Energie Register Probe")
    print(f"Poort: {PORT}, Slave: {SLAVE}")
    print("=" * 90)

    # --- Read context registers one by one ---
    print("\n── CONTEXT (compressor status) ──")
    for addr, (name, unit, scale) in sorted(CONTEXT_REGS.items()):
        result = client.read_holding_registers(addr, count=1, device_id=SLAVE)
        if result.isError():
            print(f"  HR[{addr:4d}]  ERROR  {name}")
            continue
        raw = result.registers[0]
        if raw in DISCONNECTED:
            print(f"  HR[{addr:4d}]  DISCONNECTED  {name}")
        else:
            signed = raw - 65536 if raw > 32767 else raw
            val = signed * scale
            print(f"  HR[{addr:4d}]  raw={raw:6d}  → {val:8.2f} {unit:4s}  {name}")
        time.sleep(0.05)

    # --- Read energy block HR[143-186] in chunks ---
    print("\n── MIDEA ENERGIE BLOK HR[143-186] ──")
    print(f"{'HR':>6s}  {'Raw':>7s}  {'Signed':>7s}  {'Scaled':>12s}  {'Naam':<45s}  Opmerking")
    print("-" * 90)

    energy_data = {}
    # Read in two chunks to stay within Modbus max register count
    for chunk_start, chunk_count in [(143, 44)]:  # 143-186 = 44 registers
        result = client.read_holding_registers(chunk_start, count=chunk_count, device_id=SLAVE)
        if result.isError():
            print(f"  FOUT bij lezen HR[{chunk_start}-{chunk_start+chunk_count-1}]: {result}")
            # Try individual reads
            for addr in range(chunk_start, chunk_start + chunk_count):
                r = client.read_holding_registers(addr, count=1, device_id=SLAVE)
                if not r.isError():
                    energy_data[addr] = r.registers[0]
                time.sleep(0.05)
        else:
            for i, val in enumerate(result.registers):
                energy_data[chunk_start + i] = val

    # Display results
    non_zero = 0
    for addr in range(143, 187):
        if addr not in energy_data:
            defn = MIDEA_ENERGY.get(addr)
            name = defn[0] if defn else "?"
            print(f"  [{addr:4d}]  {'---':>7s}  {'---':>7s}  {'---':>12s}  {name}")
            continue

        raw = energy_data[addr]
        defn = MIDEA_ENERGY.get(addr)
        if defn:
            name, unit, scale, note = defn
        else:
            name, unit, scale, note = f"unknown_{addr}", "?", 1, ""

        signed = raw - 65536 if raw > 32767 else raw

        if raw in DISCONNECTED:
            scaled_str = "DISCONNECTED"
        else:
            val = signed * scale
            if scale < 1:
                scaled_str = f"{val:.2f} {unit}"
            else:
                scaled_str = f"{val:.0f} {unit}"

        marker = ""
        if raw not in DISCONNECTED and raw != 0:
            non_zero += 1
            marker = " ◄"

        print(f"  [{addr:4d}]  {raw:7d}  {signed:7d}  {scaled_str:>12s}  {name:<45s}  {note}{marker}")

    # --- DWORD combinations ---
    print(f"\n── DWORD PAREN (hi×65536 + lo, ×0.01 kWh) ──")
    dword_pairs = [
        (143, 144, "Totaal elektriciteitsverbruik"),
        (145, 146, "Totaal thermisch vermogen geleverd"),
        (152, 153, "Totaal verwarming geproduceerd"),
        (154, 155, "Totaal hernieuwbare verwarming"),
        (156, 157, "Totaal verwarming verbruikt"),
        (158, 159, "Totaal verwarming (master)"),
        (160, 161, "Totaal hernieuwbaar (master)"),
        (162, 163, "Totaal verbruikt (master)"),
        (165, 166, "Totaal koeling geproduceerd"),
        (167, 168, "Totaal koeling hernieuwbaar"),
        (169, 170, "Totaal koeling verbruikt"),
        (172, 173, "Totaal DHW geproduceerd"),
        (174, 175, "Totaal DHW hernieuwbaar"),
        (176, 177, "Totaal DHW verbruikt"),
    ]
    for hi_addr, lo_addr, label in dword_pairs:
        hi = energy_data.get(hi_addr, 0)
        lo = energy_data.get(lo_addr, 0)
        if hi in DISCONNECTED or lo in DISCONNECTED:
            print(f"  HR[{hi_addr}+{lo_addr}]  DISCONNECTED  {label}")
            continue
        total_raw = hi * 65536 + lo
        total_kwh = total_raw * 0.01
        if total_raw > 0:
            print(f"  HR[{hi_addr}+{lo_addr}]  {hi}×65536 + {lo} = {total_raw}  → {total_kwh:.2f} kWh  {label}  ◄")
        else:
            print(f"  HR[{hi_addr}+{lo_addr}]  {total_raw}  → {total_kwh:.2f} kWh  {label}")

    # --- COP registers ---
    print(f"\n── COP REGISTERS ──")
    cop_regs = [
        (151, "Realtime COP verwarming"),
        (164, "Totaal COP verwarming (master)"),
        (171, "Totaal COP koeling (master)"),
        (178, "Totaal COP DHW"),
        (182, "Realtime EER koeling"),
        (186, "Realtime COP DHW"),
    ]
    for addr, label in cop_regs:
        raw = energy_data.get(addr, 0)
        if raw in DISCONNECTED:
            print(f"  HR[{addr}]  DISCONNECTED  {label}")
        else:
            cop = raw * 0.01
            print(f"  HR[{addr}]  raw={raw}  → COP {cop:.2f}  {label}")

    # --- Realtime power ---
    print(f"\n── REALTIME VERMOGEN ──")
    rt_regs = [
        (148, "Verwarming capaciteit (thermisch)"),
        (149, "Hernieuwbare verwarming"),
        (150, "Verwarming stroomverbruik"),
        (180, "Koeling capaciteit"),
        (181, "Koeling stroomverbruik"),
        (183, "DHW capaciteit"),
        (185, "DHW stroomverbruik"),
    ]
    for addr, label in rt_regs:
        raw = energy_data.get(addr, 0)
        if raw in DISCONNECTED:
            print(f"  HR[{addr}]  DISCONNECTED  {label}")
        else:
            val = raw * 0.01
            print(f"  HR[{addr}]  raw={raw}  → {val:.2f} kW  {label}")

    # --- Summary ---
    print(f"\n{'='*90}")
    print(f"Resultaat: {non_zero} van {len(energy_data)} registers bevatten data (niet-nul, niet-disconnected)")

    # Quick calculated power check
    mains_v = energy_data.get(1338, 0)  # Not in this block
    # Read mains voltage
    r = client.read_holding_registers(1338, count=1, device_id=SLAVE)
    if not r.isError():
        mains_v = r.registers[0] * 0.1
    r = client.read_holding_registers(1325, count=1, device_id=SLAVE)
    inv_a = r.registers[0] * 0.1 if not r.isError() else 0

    if mains_v > 0 and inv_a > 0:
        calc_power = mains_v * inv_a
        print(f"\n  Berekend vermogen: HR[1338]×HR[1325] = {mains_v:.1f}V × {inv_a:.1f}A = {calc_power:.0f} W")
        # Compare with HR[150] if available
        rt_power = energy_data.get(150, 0) * 0.01
        if rt_power > 0:
            print(f"  Midea RT vermogen: HR[150] = {rt_power:.2f} kW = {rt_power*1000:.0f} W")
            print(f"  Verschil: {abs(calc_power - rt_power*1000):.0f} W")

    client.close()
    print(f"\nKlaar! Koppel het tablet weer aan indien nodig.")


if __name__ == "__main__":
    main()

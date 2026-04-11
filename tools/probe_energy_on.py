"""Wait for compressor ON, then read energy registers HR[143-186].

Polls HR[1283] every 10s. When compressor starts, reads the full
energy block plus compressor registers to verify realtime power/COP.

Usage: python probe_energy_on.py
  Requires: USB-RS485 on COM5, tablet DISCONNECTED.
  Let it run until the compressor starts (could be minutes to hours).
  Press Ctrl+C to stop early.
"""

from pymodbus.client import ModbusSerialClient
import time
from datetime import datetime

PORT = "COM5"
SLAVE = 1
POLL_INTERVAL = 10  # seconds

# Midea R290 energy register definitions
ENERGY_REGS = {
    148: ("realtime_heating_capacity",          "kW",   0.01),
    149: ("realtime_renewable_heating_cap",     "kW",   0.01),
    150: ("realtime_heating_power_consumption", "kW",   0.01),
    151: ("realtime_heating_cop",               "COP",  0.01),
}

CONTEXT_REGS = {
    41:   ("compressor_power",      "W",   1),
    1283: ("compressor_on_off",     "",    1),
    1325: ("inverter_current_T38",  "A",   0.1),
    1335: ("comp_voltage_T35",      "V",   0.1),
    1338: ("mains_voltage",         "V",   0.1),
    1368: ("dc_bus_T36",            "V",   0.1),
}


def read_reg(client, addr, count=1):
    r = client.read_holding_registers(addr, count=count, device_id=SLAVE)
    if r.isError():
        return None
    return r.registers


def main():
    client = ModbusSerialClient(
        port=PORT, baudrate=9600, bytesize=8,
        parity="N", stopbits=1, timeout=1,
    )
    if not client.connect():
        print(f"FOUT: Kan niet verbinden met {PORT}")
        return

    print("=" * 80)
    print("Wachten op compressor start... (poll elke 10s, Ctrl+C om te stoppen)")
    print("=" * 80)

    samples_on = []
    comp_was_on = False

    try:
        while True:
            now = datetime.now().strftime("%H:%M:%S")

            # Check compressor status
            vals = read_reg(client, 1283)
            if vals is None:
                print(f"  [{now}] Leesfout HR[1283]")
                time.sleep(POLL_INTERVAL)
                continue

            comp_on = vals[0] == 1

            if not comp_on:
                print(f"  [{now}] Compressor UIT — wachtend...", end="\r")
                comp_was_on = False
                time.sleep(POLL_INTERVAL)
                continue

            # Compressor is ON!
            if not comp_was_on:
                print(f"\n  [{now}] ★ COMPRESSOR GESTART! Lees energie-registers...")
                comp_was_on = True

            # Read context registers
            ctx = {}
            for addr, (name, unit, scale) in sorted(CONTEXT_REGS.items()):
                vals = read_reg(client, addr)
                if vals:
                    raw = vals[0]
                    signed = raw - 65536 if raw > 32767 else raw
                    ctx[addr] = signed * scale
                time.sleep(0.05)

            # Read energy block HR[143-186]
            energy_vals = read_reg(client, 143, count=44)
            if energy_vals is None:
                print(f"  [{now}] Leesfout HR[143-186]")
                time.sleep(POLL_INTERVAL)
                continue

            energy = {}
            for i, raw in enumerate(energy_vals):
                addr = 143 + i
                signed = raw - 65536 if raw > 32767 else raw
                energy[addr] = (raw, signed)

            # Display
            sample = {"time": now}
            print(f"\n  [{now}] COMPRESSOR AAN — Meetresultaten:")
            print(f"    Context:")
            for addr, (name, unit, scale) in sorted(CONTEXT_REGS.items()):
                val = ctx.get(addr, "?")
                print(f"      HR[{addr:4d}] = {val:8.1f} {unit:4s}  {name}")
                sample[name] = val

            print(f"    Energie (realtime):")
            for addr, (name, unit, scale) in sorted(ENERGY_REGS.items()):
                raw, signed = energy.get(addr, (0, 0))
                val = signed * scale
                marker = " ◄◄◄" if val > 0 else ""
                print(f"      HR[{addr}] = raw {raw:6d} → {val:8.3f} {unit}  {name}{marker}")
                sample[name] = val

            # Also show calculated power
            mains_v = ctx.get(1338, 0)
            inv_a = ctx.get(1325, 0)
            if mains_v > 0 and inv_a > 0:
                calc = mains_v * inv_a
                rt_power = energy.get(150, (0, 0))[1] * 0.01
                print(f"    Berekend: {mains_v:.1f}V × {inv_a:.1f}A = {calc:.0f} W")
                if rt_power > 0:
                    print(f"    HR[150] RT: {rt_power:.3f} kW = {rt_power*1000:.0f} W")
                    print(f"    Verschil: {abs(calc - rt_power*1000):.0f} W")

            # Show all non-zero energy registers
            print(f"    Alle niet-nul registers in HR[143-186]:")
            for addr in range(143, 187):
                raw, signed = energy.get(addr, (0, 0))
                if raw != 0 and raw not in (32834, 32836):
                    defn = ENERGY_REGS.get(addr)
                    name = defn[0] if defn else f"HR[{addr}]"
                    print(f"      [{addr}] raw={raw:6d} signed={signed:6d}")

            samples_on.append(sample)
            print(f"\n    ({len(samples_on)} samples verzameld met comp ON)")

            # After 5 samples, summarize and exit
            if len(samples_on) >= 5:
                print(f"\n{'='*80}")
                print("5 samples verzameld! Samenvatting realtime energie-registers:")
                for s in samples_on:
                    t = s["time"]
                    rt_cap = s.get("realtime_heating_capacity", 0)
                    rt_pow = s.get("realtime_heating_power_consumption", 0)
                    rt_cop = s.get("realtime_heating_cop", 0)
                    inv_a = s.get("inverter_current_T38", 0)
                    print(f"  {t}: cap={rt_cap:.3f}kW pow={rt_pow:.3f}kW COP={rt_cop:.2f} I={inv_a:.1f}A")
                print(f"{'='*80}")
                break

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print(f"\n\nGestopt door gebruiker. {len(samples_on)} samples verzameld.")

    client.close()


if __name__ == "__main__":
    main()

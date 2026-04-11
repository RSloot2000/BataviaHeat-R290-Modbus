"""
BataviaHeat R290 — Post-optimalisatie analyse script.

Vergelijkt de oude (pre-optimalisatie) en nieuwe (post-optimalisatie) overnight
scans en analyseert weercurve gedrag, compressorcycli, en energie.

Databases:
  - data/nachtmeting 16-17.db    (vóór optimalisatie: M02=50, M11=0, P01=0)
  - data/overnight_20260317_231919.db  (ná optimalisatie: M02=35, M11=17, P01=1)
"""

import sqlite3
import sys
import os
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DB_OLD = DATA_DIR / "nachtmeting 16-17.db"
DB_NEW = DATA_DIR / "overnight_20260317_231919.db"

# Register names for display
REG_NAMES = {
    1: "water_outlet_temp",
    4: "heating_target_temp",
    5: "buffer_tank_lower",
    22: "ambient_temp",
    23: "fin_coil_temp",
    24: "suction_temp",
    36: "discharge_temp",
    40: "plate_hx_inlet",
    41: "compressor_power",
    42: "superheat",
    54: "pump_flow_rate",
    163: "energy_counter_1",
    164: "energy_counter_2",
    165: "energy_counter_3",
    768: "operational_status",
    772: "weather_target_mirror",
    816: "weather_curve_target",
    1283: "compressor_on_off",
    1338: "mains_voltage",
    6400: "operating_mode",
    6402: "M02_heating_setpoint",
    6410: "M10_curve_mode_flag",
    6426: "M11_zone_A_heating_curve",
    6428: "M13_zone_B_heating_curve",
    6433: "M18_custom_heat_ambient_1",
    6434: "M19_custom_heat_ambient_2",
    6435: "M20_custom_heat_outlet_1",
    6436: "M21_custom_heat_outlet_2",
    6472: "P01_pump_mode",
}


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def reg_name(addr: int) -> str:
    return REG_NAMES.get(addr, f"HR[{addr}]")


def print_header(title: str):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def scan_metadata(conn: sqlite3.Connection, label: str):
    """Print basic scan metadata."""
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM readings")
    readings = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM changes")
    changes = c.fetchone()[0]
    c.execute("SELECT MIN(timestamp), MAX(timestamp) FROM readings")
    t = c.fetchone()
    c.execute("SELECT COUNT(DISTINCT timestamp) FROM readings")
    cycles = c.fetchone()[0]
    c.execute("SELECT COUNT(DISTINCT address) FROM readings")
    regs = c.fetchone()[0]

    print(f"  {label}:")
    print(f"    Periode:    {t[0][:19]} — {t[1][:19]}")
    print(f"    Cycli:      {cycles}")
    print(f"    Registers:  {regs}")
    print(f"    Metingen:   {readings:,}")
    print(f"    Wijzigingen: {changes:,}")


def compare_config(conn_old: sqlite3.Connection, conn_new: sqlite3.Connection):
    """Compare initial config values between old and new scan."""
    print_header("CONFIGURATIE VERGELIJKING (startwaarden)")

    # Get first reading of each config register
    query = """
        SELECT address, raw_value
        FROM readings
        WHERE address >= 6400 AND address <= 7500
        GROUP BY address
        HAVING rowid = MIN(rowid)
        ORDER BY address
    """
    old_vals = dict(conn_old.execute(query).fetchall())
    new_vals = dict(conn_new.execute(query).fetchall())

    all_addrs = sorted(set(old_vals.keys()) | set(new_vals.keys()))
    print(f"\n  {'Adres':>6}  {'Naam':<30}  {'Oud':>8}  {'Nieuw':>8}  {'Status'}")
    print(f"  {'─' * 6}  {'─' * 30}  {'─' * 8}  {'─' * 8}  {'─' * 10}")

    for addr in all_addrs:
        ov = old_vals.get(addr, "—")
        nv = new_vals.get(addr, "—")
        if ov != nv:
            name = reg_name(addr)
            status = "GEWIJZIGD" if ov != "—" and nv != "—" else "NIEUW" if ov == "—" else "VERWIJDERD"
            print(f"  {addr:>6}  {name:<30}  {str(ov):>8}  {str(nv):>8}  {status}")


def compressor_cycles(conn: sqlite3.Connection, label: str):
    """Detect and report compressor ON/OFF cycles."""
    print_header(f"COMPRESSOR CYCLI — {label}")

    c = conn.cursor()

    # Try HR[768] first (operational_status: 0=standby, 4=running),
    # then HR[1283] (compressor_on_off: 0=off, 1=on)
    for addr, on_val, off_val, name in [
        (768, 4, 0, "HR[768] operational_status"),
        (1283, 1, 0, "HR[1283] compressor_on_off"),
    ]:
        c.execute("""
            SELECT timestamp, old_value, new_value
            FROM changes WHERE address = ?
            ORDER BY timestamp
        """, (addr,))
        changes = c.fetchall()
        if changes:
            print(f"  Bron: {name} ({len(changes)} wisselingen)")
            break
    else:
        # No changes found; try to detect from readings directly
        c.execute("""
            SELECT timestamp, raw_value FROM readings
            WHERE address = 768 ORDER BY timestamp
        """)
        vals = c.fetchall()
        if not vals:
            print("  Geen compressor data gevonden.")
            return []
        # Build synthetic change list
        changes = []
        prev = vals[0]
        for row in vals[1:]:
            if row["raw_value"] != prev["raw_value"]:
                changes.append({"timestamp": row["timestamp"],
                                "old_value": prev["raw_value"],
                                "new_value": row["raw_value"]})
            prev = row
        on_val, off_val = 4, 0
        if not changes:
            # Check if it was running the whole time
            if vals[0]["raw_value"] == 4:
                t0 = datetime.fromisoformat(vals[0]["timestamp"])
                t1 = datetime.fromisoformat(vals[-1]["timestamp"])
                dur = (t1 - t0).total_seconds() / 3600
                print(f"  Compressor CONTINU AAN gedurende {dur:.1f} uur")
            else:
                print(f"  Compressor stond UIT gedurende hele scan (status={vals[0]['raw_value']})")
            return []
        print(f"  Bron: HR[768] readings ({len(changes)} wisselingen)")

    cycles = []
    on_time = None
    for row in changes:
        if isinstance(row, dict):
            ts, old_val_r, new_val_r = row["timestamp"], row["old_value"], row["new_value"]
        else:
            ts, old_val_r, new_val_r = row["timestamp"], row["old_value"], row["new_value"]
        if new_val_r == on_val and old_val_r != on_val:
            on_time = ts
        elif old_val_r == on_val and new_val_r != on_val and on_time:
            cycles.append((on_time, ts))
            on_time = None

    if not cycles:
        print("  Geen complete compressor cycli gevonden.")
        return []

    durations = []
    for start, end in cycles:
        dur = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
        durations.append(dur)

    avg_dur = sum(durations) / len(durations)
    total_on = sum(durations)

    # Total scan duration
    c.execute("SELECT MIN(timestamp), MAX(timestamp) FROM readings")
    t = c.fetchone()
    total_scan = (datetime.fromisoformat(t[1]) - datetime.fromisoformat(t[0])).total_seconds()
    duty_cycle = total_on / total_scan * 100 if total_scan > 0 else 0

    print(f"  Aantal cycli:          {len(cycles)}")
    print(f"  Gemiddelde draaitijd:  {avg_dur / 60:.1f} min")
    print(f"  Kortste:               {min(durations) / 60:.1f} min")
    print(f"  Langste:               {max(durations) / 60:.1f} min")
    print(f"  Totale draaitijd:      {total_on / 3600:.1f} uur ({duty_cycle:.0f}% duty cycle)")

    if len(cycles) > 1:
        off_times = []
        for i in range(1, len(cycles)):
            t_off = datetime.fromisoformat(cycles[i - 1][1])
            t_on = datetime.fromisoformat(cycles[i][0])
            off_times.append((t_on - t_off).total_seconds())
        print(f"  Gemiddelde pauze:      {sum(off_times) / len(off_times) / 60:.1f} min")

    print(f"\n  {'#':>3}  {'Start':>20}  {'Stop':>20}  {'Duur':>8}")
    print(f"  {'─' * 3}  {'─' * 20}  {'─' * 20}  {'─' * 8}")
    for i, (start, end) in enumerate(cycles[:25], 1):
        dur = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
        print(f"  {i:>3}  {start[:19]:>20}  {end[:19]:>20}  {dur / 60:>6.1f}m")
    if len(cycles) > 25:
        print(f"  ... en {len(cycles) - 25} meer")

    return cycles


def weather_curve_analysis(conn: sqlite3.Connection, label: str):
    """Analyze relationship between ambient temp and heating target."""
    print_header(f"WEERCURVE GEDRAG — {label}")

    c = conn.cursor()

    # Get readings for ambient (HR[22]) and weather target (HR[816]) separately
    # then correlate by matching timestamps or index order
    ambient_data = {}
    target_data = {}
    for addr, store in [(22, ambient_data), (816, target_data)]:
        c.execute("SELECT timestamp, raw_value FROM readings WHERE address = ? ORDER BY timestamp", (addr,))
        for row in c.fetchall():
            store[row["timestamp"]] = row["raw_value"]

    common_ts = sorted(set(ambient_data.keys()) & set(target_data.keys()))

    if common_ts:
        print(f"  Datapunten: {len(common_ts)}")
        paired = [(ambient_data[ts], target_data[ts]) for ts in common_ts]
    else:
        # Fallback: pair by index order
        amb_list = list(c.execute("SELECT raw_value FROM readings WHERE address = 22 ORDER BY timestamp").fetchall())
        tgt_list = list(c.execute("SELECT raw_value FROM readings WHERE address = 816 ORDER BY timestamp").fetchall())
        n = min(len(amb_list), len(tgt_list))
        if n == 0:
            print("  Geen ambient/target data gevonden.")
            return
        print(f"  Datapunten (index-gebaseerd): {n}")
        paired = [(amb_list[i][0], tgt_list[i][0]) for i in range(n)]

    # Group by rounded ambient temp
    buckets: dict[int, list[int]] = {}
    for amb_raw, tgt_raw in paired:
        amb = round(amb_raw * 0.1)
        if amb not in buckets:
            buckets[amb] = []
        buckets[amb].append(tgt_raw)

    # Check if target is static or dynamic
    all_targets = set()
    for tgts in buckets.values():
        all_targets.update(tgts)

    if len(all_targets) == 1:
        val = all_targets.pop()
        print(f"  Watertemp target is STATISCH: {val * 0.1:.1f}°C")
        print(f"  → Weercurve is INACTIEF (M11=0)")
        return

    print(f"  Watertemp target is DYNAMISCH: {len(all_targets)} unieke waarden")
    print(f"  → Weercurve is ACTIEF")
    print(f"\n  {'Buiten °C':>10}  {'Water target °C':>15}  {'Min':>6}  {'Max':>6}  {'Metingen':>8}")
    print(f"  {'─' * 10}  {'─' * 15}  {'─' * 6}  {'─' * 6}  {'─' * 8}")
    for amb in sorted(buckets.keys()):
        tgts = buckets[amb]
        avg_t = sum(tgts) / len(tgts) * 0.1
        mn = min(tgts) * 0.1
        mx = max(tgts) * 0.1
        print(f"  {amb:>9}°C  {avg_t:>14.1f}°C  {mn:>5.1f}  {mx:>5.1f}  {len(tgts):>8}")


def temperature_summary(conn: sqlite3.Connection, label: str):
    """Summary of key temperature registers."""
    print_header(f"TEMPERATUREN — {label}")

    addrs = [22, 1, 3, 36, 40, 5, 816, 772]
    c = conn.cursor()
    print(f"  {'Register':<30}  {'Min':>8}  {'Max':>8}  {'Gem':>8}  {'Uniek':>6}")
    print(f"  {'─' * 30}  {'─' * 8}  {'─' * 8}  {'─' * 8}  {'─' * 6}")
    for addr in addrs:
        c.execute("""
            SELECT MIN(raw_value), MAX(raw_value), AVG(raw_value),
                   COUNT(DISTINCT raw_value)
            FROM readings WHERE address = ? AND raw_value < 32000
        """, (addr,))
        row = c.fetchone()
        if row and row[0] is not None:
            name = reg_name(addr)
            print(f"  {name:<30}  {row[0] * 0.1:>7.1f}°  {row[1] * 0.1:>7.1f}°  "
                  f"{row[2] * 0.1:>7.1f}°  {row[3]:>6}")
        else:
            print(f"  {reg_name(addr):<30}  — geen data —")


def energy_comparison(conn_old: sqlite3.Connection, conn_new: sqlite3.Connection):
    """Compare energy consumption between old and new scan."""
    print_header("ENERGIE VERGELIJKING")

    for db, label in [(conn_old, "Vóór optimalisatie"), (conn_new, "Ná optimalisatie")]:
        c = db.cursor()
        c.execute("SELECT MIN(timestamp), MAX(timestamp) FROM readings")
        t = c.fetchone()
        hours = (datetime.fromisoformat(t[1]) - datetime.fromisoformat(t[0])).total_seconds() / 3600

        print(f"\n  {label} ({hours:.1f} uur):")
        for addr in [163, 164, 165]:
            c.execute("SELECT MIN(raw_value), MAX(raw_value) FROM readings WHERE address = ?", (addr,))
            row = c.fetchone()
            if row and row[0] is not None:
                delta = row[1] - row[0]
                rate = delta / hours if hours > 0 else 0
                print(f"    {reg_name(addr):<25}  Δ{delta:>6} Wh  ({rate:>5.0f} W gem)")


def pump_analysis(conn: sqlite3.Connection, label: str):
    """Analyze pump behavior (P01 effect)."""
    print_header(f"WATERPOMP GEDRAG — {label}")

    c = conn.cursor()
    c.execute("""
        SELECT MIN(raw_value), MAX(raw_value), AVG(raw_value),
               COUNT(DISTINCT raw_value), COUNT(*)
        FROM readings WHERE address = 54
    """)
    row = c.fetchone()
    if row and row[4] > 0:
        print(f"  Debiet:  min={row[0]} L/h  max={row[1]} L/h  "
              f"gem={row[2]:.0f} L/h  ({row[3]} unieke waarden)")

    # Check for zero flow (pump off)
    c.execute("SELECT COUNT(*) FROM readings WHERE address = 54 AND raw_value = 0")
    zero = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM readings WHERE address = 54")
    total = c.fetchone()[0]
    if total > 0:
        pct = zero / total * 100
        if zero > 0:
            print(f"  Pomp UIT: {zero}/{total} metingen ({pct:.1f}%) → P01=1 werkt!")
        else:
            print(f"  Pomp draait CONTINU (0 stops in {total} metingen)")

    # Check pump speed changes
    c.execute("""
        SELECT COUNT(*) FROM changes WHERE address = 54
    """)
    speed_changes = c.fetchone()[0]
    print(f"  Debiet wijzigingen: {speed_changes}")


def main():
    print("BataviaHeat R290 — Post-optimalisatie Analyse")
    print("=" * 70)

    if not DB_OLD.exists():
        print(f"WAARSCHUWING: Oude database niet gevonden: {DB_OLD}")
    if not DB_NEW.exists():
        print(f"FOUT: Nieuwe database niet gevonden: {DB_NEW}")
        sys.exit(1)

    conn_new = connect(DB_NEW)
    conn_old = connect(DB_OLD) if DB_OLD.exists() else None

    # 1. Metadata
    print_header("SCAN OVERZICHT")
    if conn_old:
        scan_metadata(conn_old, "Vóór optimalisatie (16-17 maart)")
    scan_metadata(conn_new, "Ná optimalisatie (17-18 maart)")

    # 2. Config changes
    if conn_old:
        compare_config(conn_old, conn_new)

    # 3. Compressor cycles
    if conn_old:
        compressor_cycles(conn_old, "Vóór optimalisatie")
    compressor_cycles(conn_new, "Ná optimalisatie")

    # 4. Weather curve
    if conn_old:
        weather_curve_analysis(conn_old, "Vóór optimalisatie (M11=0)")
    weather_curve_analysis(conn_new, "Ná optimalisatie (M11=17)")

    # 5. Temperatures
    if conn_old:
        temperature_summary(conn_old, "Vóór optimalisatie")
    temperature_summary(conn_new, "Ná optimalisatie")

    # 6. Energy
    if conn_old:
        energy_comparison(conn_old, conn_new)

    # 7. Pump behavior
    if conn_old:
        pump_analysis(conn_old, "Vóór optimalisatie (P01=0)")
    pump_analysis(conn_new, "Ná optimalisatie (P01=1)")

    # Cleanup
    conn_new.close()
    if conn_old:
        conn_old.close()

    print(f"\n{'=' * 70}")
    print("✓ Analyse voltooid.")


if __name__ == "__main__":
    main()

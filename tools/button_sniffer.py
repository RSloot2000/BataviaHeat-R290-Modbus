#!/usr/bin/env python3
"""
BataviaHeat R290 — Button Sniffer
Monitort registers terwijl je op de tablet op knoppen drukt (aan/uit, stille modus, etc.)
Logt alle wijzigingen naar een bestand + korte melding op console.

Gebruik:
  1. Start dit script
  2. Wacht tot "Baseline vastgelegd" verschijnt
  3. Druk op een knop op de tablet (bijv. aan/uit of stille modus)
  4. Wijzigingen worden gelogd naar data/button_sniffer_YYYYMMDD_HHMMSS.log
  5. Ctrl+C om te stoppen

Gescande bereiken:
  - HR[0-10]       Mosibi control registers (aan/uit, mode, silent, etc.)
  - HR[768-772]    Operational status
  - HR[1283-1290]  Compressor status
  - HR[6400-6510]  Tablet parameters (N/M/P/G/F-series)
"""

import logging, signal, sys, time
from datetime import datetime
from pathlib import Path

from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException

# Onderdruk alle pymodbus meldingen (incl. "Cleanup recv buffer")
logging.getLogger("pymodbus").setLevel(logging.CRITICAL)

# ─── Connection Settings ───
PORT = "COM5"
BAUDRATE = 9600
SLAVE_ID = 1
POLL_INTERVAL = 0.5  # seconden tussen polls
MODBUS_TIMEOUT = 1   # korte timeout zodat script niet hangt

# ─── Output ───
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
LOG_FILE = DATA_DIR / f"button_sniffer_{datetime.now():%Y%m%d_%H%M%S}.log"

# ─── Register bereiken om te monitoren ───
# (start_address, count, label)
SCAN_RANGES = [
    (0, 11, "Control (HR[0-10])"),
    (768, 5, "Op. status (HR[768-772])"),
    (1283, 8, "Comp. status (HR[1283-1290])"),
    (6400, 111, "Tablet params (HR[6400-6510])"),
]

# ─── Bekende register namen (voor leesbaarheid) ───
KNOWN_NAMES: dict[int, str] = {
    # Mosibi control block
    0: "control_switches (bitfield: b0=room, b1=waterZ1, b2=DHW, b3=waterZ2)",
    1: "water_outlet_temp (Mosibi: operational_mode 1=Auto/2=Cool/3=Heat)",
    2: "set_water_temp_t1s (packed: lo=Z1, hi=Z2)",
    3: "air_temp_ts (×0.5)",
    4: "heating_target_temp (×0.1)",
    5: "buffer_tank_lower (Mosibi: function_settings bitfield b4=disinfect b6=silent b10=ECO)",
    6: "weather_curve_selection (packed)",
    7: "quiet_mode_hp (Mosibi: 0/1)",
    8: "holiday_away (Mosibi: 0/1)",
    9: "forced_rear_heater",
    10: "t_sg_max",
    # Zone B
    410: "zB_mode",
    411: "zB_silent",
    414: "zB_target",
    415: "zB_buf_lower",
    # Operational
    768: "operational_status (0=standby, 1=starting, 4=running)",
    769: "operational_sub_status",
    770: "unknown_770",
    771: "unknown_771",
    772: "unknown_772",
    # Compressor
    1283: "compressor_on_off (0=off, 1=on)",
    1284: "unknown_1284",
    1289: "status_bitfield_1289",
    # Tablet N-serie
    6465: "N01 power_mode (0=Std/1=Kracht/2=Eco/3=Auto)",
    6466: "N02 verwarm_koel_type (0=Heat/1=Both/2=Cool)",
    6468: "N04 vierwegklep",
    6469: "N05 type_draadschakelaar",
    6470: "N06 start_stop_controle (0=Unie/1=Afstand/2=Lokaal/3=Draad/4=Net)",
    6471: "N07 geheugen_bewaren",
    6472: "N08/P01 inkomende_stroom_zelfstart / waterpomp_modus",
    6475: "N11 warmwater_functie",
    6484: "N20 tank_elektr_verwarming",
    6485: "N21 onderste_retourpomp",
    6486: "N22 zonne",
    6487: "N23 koppelingsschakelaar",
    6490: "N26 bediening_type (0=Single/2=Dubbel)",
    6496: "N32 slim_netwerk",
    6500: "N36 inlaattemp_sensor_vloerverw",
    6501: "N37 systeem_outlet_sensor",
    6502: "N38 EVU_PV_signaal",
    6503: "N39 SG_Grid_signaal",
    6505: "N41 zonne_temp_sensor",
    6512: "N48 zoneA_koeling_einde",
    6513: "N49 zoneA_verwarming_einde",
    # Tablet M-serie
    6401: "M01 koeling_instelling",
    6402: "M02 verwarming_instelling",
    6403: "M03 DHW_instelling",
    6404: "M04 koeling_doeltemp_kamer",
    6405: "M05 verwarming_doeltemp_kamer",
    6408: "M08 verwarming_B",
    6410: "M10_flag curve_mode_flag",
    6425: "M10 zoneA_koelcurve",
    6426: "M11 zoneA_verwarmcurve",
    6427: "M12 zoneB_koelcurve",
    6428: "M13 zoneB_verwarmcurve",
    6429: "M14 custom_koel_omgevingstemp_1",
    6430: "M15 custom_koel_omgevingstemp_2",
    6431: "M16 custom_koel_uitlaattemp_1",
    6432: "M17 custom_koel_uitlaattemp_2",
    6433: "M18 custom_verwarm_omgevingstemp_1",
    6434: "M19 custom_verwarm_omgevingstemp_2",
    6435: "M20 custom_verwarm_uitlaattemp_1",
    6436: "M21 custom_verwarm_uitlaattemp_2",
    6440: "M40 externe_warmtebron",
    6455: "M55 voorverwarming_temp",
    6456: "M56 voorverwarming_interval",
    6457: "M57 voorverwarming_tijd",
    6460: "M60 vloerverw_voor_droging",
    6461: "M61 vloerverw_tijdens_droging",
    6462: "M62 vloerverw_na_droging",
    6463: "M63 vloerverw_droogtemp",
    # G-serie
    6412: "G01 sterilisatie",
    6413: "G02 sterilisatie_temp",
    6414: "G03 sterilisatie_max_cyclus",
    6415: "G04 sterilisatie_hoge_temp_tijd",
}

running = True
logfile = None


def signal_handler(sig, frame):
    global running
    running = False


signal.signal(signal.SIGINT, signal_handler)


def log(msg: str, console: bool = True):
    """Schrijf naar logbestand en optioneel naar console."""
    if logfile:
        logfile.write(msg + "\n")
        logfile.flush()
    if console:
        print(msg)


def read_all_ranges(client: ModbusSerialClient) -> dict[int, int] | None:
    """Lees alle gescande bereiken. Skipt blokken bij fouten, reconnect bij nodig."""
    values = {}
    for start, count, label in SCAN_RANGES:
        try:
            result = client.read_holding_registers(start, count=count, device_id=SLAVE_ID)
            if result.isError():
                continue  # stil overslaan, bus-conflict met tablet
            for i, val in enumerate(result.registers):
                values[start + i] = val
        except (ModbusException, Exception):
            # Bij timeout of corrupt frame: reconnect en door
            try:
                client.close()
                time.sleep(0.2)
                client.connect()
            except Exception:
                pass
            continue
    return values if values else None


def format_value(addr: int, val: int) -> str:
    """Formatteer waarde met extra info voor bekende registers."""
    # Bitfield weergave voor verdachte control registers
    if addr in (0, 5, 1289):
        return f"{val} (0x{val:04X} = 0b{val:016b})"
    return str(val)


def get_name(addr: int) -> str:
    """Haal bekende naam op of geef 'unknown'."""
    return KNOWN_NAMES.get(addr, "?")


def main():
    global logfile

    print("=" * 70)
    print("  BataviaHeat R290 — Button Sniffer")
    print("  Drukt op een knop op de tablet en zie welke registers veranderen")
    print("=" * 70)
    print(f"\nVerbinding: {PORT} @ {BAUDRATE} baud, slave {SLAVE_ID}")
    print(f"Poll interval: {POLL_INTERVAL}s")
    print(f"Bereiken: {sum(c for _, c, _ in SCAN_RANGES)} registers over {len(SCAN_RANGES)} blokken")
    print(f"Logbestand: {LOG_FILE}\n")

    # Open logbestand
    logfile = open(LOG_FILE, "w", encoding="utf-8")
    log(f"BataviaHeat R290 — Button Sniffer")
    log(f"Gestart: {datetime.now():%Y-%m-%d %H:%M:%S}")
    log(f"Verbinding: {PORT} @ {BAUDRATE} baud, slave {SLAVE_ID}")
    log(f"Poll interval: {POLL_INTERVAL}s")
    log("")

    client = ModbusSerialClient(port=PORT, baudrate=BAUDRATE, timeout=MODBUS_TIMEOUT)
    if not client.connect():
        log("FOUT: Kan niet verbinden met Modbus!")
        sys.exit(1)

    log("Verbonden. Eerste lezing (baseline)...", console=True)

    # Baseline vastleggen — probeer max 5x
    baseline = None
    for attempt in range(5):
        baseline = read_all_ranges(client)
        if baseline:
            break
        time.sleep(0.5)

    if baseline is None:
        log("FOUT: Geen registers gelezen na 5 pogingen!")
        client.close()
        sys.exit(1)

    previous = dict(baseline)
    total_regs = len(baseline)
    log(f"Baseline vastgelegd: {total_regs} registers\n", console=True)

    # Toon + log huidige waardes van de meest interessante registers
    log("─── Baseline waarden ───")
    for addr in sorted(baseline.keys()):
        if addr <= 10 or addr in (768, 769, 1283):
            name = get_name(addr)
            val = format_value(addr, baseline[addr])
            log(f"  HR[{addr:>5}] = {val:>30}  │ {name}")

    log("")
    log("━" * 70)
    log("  ▶ Druk nu op een knop op de tablet...")
    log("  ▶ Ctrl+C om te stoppen")
    log("━" * 70)
    log("")

    change_count = 0
    poll_count = 0
    errors = 0

    while running:
        time.sleep(POLL_INTERVAL)
        poll_count += 1

        current = read_all_ranges(client)
        if current is None:
            errors += 1
            if errors % 10 == 0:
                print(f"  ({errors} lees-fouten, bus druk? Ga door...)")
            continue

        # Vergelijk met vorige lezing
        changes = []
        for addr in sorted(current.keys()):
            old = previous.get(addr)
            new = current[addr]
            if old is not None and old != new:
                changes.append((addr, old, new))

        if changes:
            change_count += len(changes)
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]

            header = f"┌── {ts} ── {len(changes)} wijziging(en) (poll #{poll_count}) ──"
            log(header)
            for addr, old_val, new_val in changes:
                name = get_name(addr)
                old_fmt = format_value(addr, old_val)
                new_fmt = format_value(addr, new_val)
                delta = new_val - old_val
                sign = "+" if delta > 0 else ""
                line = f"│  HR[{addr:>5}]  {old_fmt} → {new_fmt}  ({sign}{delta})  │ {name}"
                log(line)
            log(f"└── totaal {change_count} wijzigingen ──\n")

        previous = dict(current)

    summary = f"\nGestopt na {poll_count} polls, {change_count} wijzigingen, {errors} lees-fouten."
    log(summary)
    log(f"Logbestand: {LOG_FILE}")
    client.close()
    logfile.close()
    print(f"  Log opgeslagen: {LOG_FILE}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
BataviaHeat R290 — Passive Bus Sniffer
Luistert mee op de RS-485 bus ZONDER zelf te zenden.
De tablet blijft normaal werken — geen bus-conflicten.

Decodeert Modbus RTU frames:
  - FC03 (Read Holding Registers) request + response
  - FC06 (Write Single Register)   ← DEZE WILLE WE ZIEN (knoppen!)
  - FC16 (Write Multiple Registers) ← EN DEZE
  - FC01/02/04/05/15 (overige functies)

Wanneer je op de tablet op een knop drukt (aan/uit, stille modus, etc.)
stuurt de tablet een FC06 of FC16 — dit script toont het register en de waarde.

Gebruik:
  1. Start dit script (tablet mag aangesloten blijven)
  2. Wacht tot frames verschijnen (tablet pollt continu)
  3. Druk op een knop op de tablet
  4. WRITE-frames worden gemarkeerd met ████ en gelogd
  5. Ctrl+C om te stoppen

Output: console + data/bus_sniffer_YYYYMMDD_HHMMSS.log
"""

import signal, struct, sys, time
from datetime import datetime
from pathlib import Path

import serial

# ─── Connection Settings ───
PORT = "COM5"
BAUDRATE = 9600
SLAVE_ID = 1

# Modbus RTU inter-frame gap: 3.5 char times @ 9600 = ~4ms
# We gebruiken iets meer marge vanwege OS-buffering
FRAME_GAP_MS = 8

# ─── Output ───
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
LOG_FILE = DATA_DIR / f"bus_sniffer_{datetime.now():%Y%m%d_%H%M%S}.log"

# ─── Bekende register namen ───
KNOWN_NAMES: dict[int, str] = {
    # Mosibi control block
    0: "control_switches (bitfield)",
    1: "water_outlet_temp / operational_mode",
    2: "set_water_temp_t1s",
    3: "air_temp_ts",
    4: "heating_target_temp (×0.1)",
    5: "buffer_tank_lower / function_settings",
    6: "weather_curve_selection",
    7: "quiet_mode_hp",
    8: "holiday_away",
    9: "forced_rear_heater",
    10: "t_sg_max",
    # Operational
    768: "operational_status",
    769: "operational_sub_status",
    773: "discharge_temp",
    776: "water_outlet_temp_live",
    # Compressor
    1283: "compressor_on_off",
    1289: "status_bitfield",
    1325: "inverter_current",
    1338: "mains_voltage",
    1368: "dc_bus_voltage",
    # Tablet N-serie
    6465: "N01 power_mode",
    6466: "N02 verwarm_koel_type",
    6468: "N04 vierwegklep",
    6469: "N05 type_draadschakelaar",
    6470: "N06 start_stop_controle",
    6471: "N07 geheugen_bewaren",
    6472: "N08/P01 waterpomp_modus",
    6475: "N11 warmwater_functie",
    6484: "N20 tank_elektr_verwarming",
    6485: "N21 onderste_retourpomp",
    6486: "N22 zonne",
    6487: "N23 koppelingsschakelaar",
    6490: "N26 bediening_type",
    6496: "N32 slim_netwerk",
    # Tablet M-serie
    6400: "M00?",
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
    6433: "M18 custom_verwarm_omgevingstemp_1",
    6434: "M19 custom_verwarm_omgevingstemp_2",
    6435: "M20 custom_verwarm_uitlaattemp_1",
    6436: "M21 custom_verwarm_uitlaattemp_2",
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


def crc16(data: bytes) -> int:
    """Bereken Modbus RTU CRC-16."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def check_crc(frame: bytes) -> bool:
    """Controleer of CRC klopt."""
    if len(frame) < 4:
        return False
    payload = frame[:-2]
    expected = struct.unpack("<H", frame[-2:])[0]
    return crc16(payload) == expected


def get_name(addr: int) -> str:
    return KNOWN_NAMES.get(addr, "")


def format_value(addr: int, val: int) -> str:
    """Formatteer waarde met bitfield weergave voor control registers."""
    if addr in (0, 5, 1289):
        return f"{val} (0x{val:04X} = 0b{val:016b})"
    return str(val)


def decode_frame(frame: bytes, ts: str) -> str | None:
    """Decodeer een Modbus RTU frame en retourneer leesbare beschrijving."""
    if len(frame) < 4:
        return None

    if not check_crc(frame):
        return None  # corrupt frame, stil overslaan

    dev_id = frame[0]
    fc = frame[1]

    # ─── FC03: Read Holding Registers ───
    if fc == 0x03:
        if len(frame) == 8:
            # REQUEST: [dev_id, 0x03, addr_hi, addr_lo, count_hi, count_lo, crc, crc]
            addr = struct.unpack(">H", frame[2:4])[0]
            count = struct.unpack(">H", frame[4:6])[0]
            return f"  READ   FC03  dev={dev_id}  HR[{addr}..{addr+count-1}] ({count} regs)"
        elif len(frame) >= 5:
            # RESPONSE: [dev_id, 0x03, byte_count, data..., crc, crc]
            byte_count = frame[2]
            reg_count = byte_count // 2
            return f"  REPLY  FC03  dev={dev_id}  {reg_count} regs ({byte_count} bytes)"

    # ─── FC06: Write Single Register ───  ★★★ DIT WILLEN WE ZIEN ★★★
    elif fc == 0x06 and len(frame) == 8:
        addr = struct.unpack(">H", frame[2:4])[0]
        value = struct.unpack(">H", frame[4:6])[0]
        name = get_name(addr)
        val_fmt = format_value(addr, value)
        name_str = f"  ({name})" if name else ""
        return (
            f"████ WRITE FC06  dev={dev_id}  HR[{addr}] = {val_fmt}{name_str}"
        )

    # ─── FC16: Write Multiple Registers ───  ★★★ DIT OOK ★★★
    elif fc == 0x10:
        if len(frame) >= 9 and len(frame) > 7 + frame[6]:
            # REQUEST: [dev_id, 0x10, addr_hi, addr_lo, count_hi, count_lo, byte_count, data..., crc, crc]
            addr = struct.unpack(">H", frame[2:4])[0]
            count = struct.unpack(">H", frame[4:6])[0]
            byte_count = frame[6]
            values = []
            for i in range(count):
                offset = 7 + i * 2
                if offset + 2 <= len(frame) - 2:
                    val = struct.unpack(">H", frame[offset:offset+2])[0]
                    values.append(val)
            lines = [f"████ WRITE FC16  dev={dev_id}  HR[{addr}..{addr+count-1}] ({count} regs):"]
            for i, val in enumerate(values):
                a = addr + i
                name = get_name(a)
                val_fmt = format_value(a, val)
                name_str = f"  ({name})" if name else ""
                lines.append(f"████   HR[{a}] = {val_fmt}{name_str}")
            return "\n".join(lines)
        elif len(frame) == 8:
            # RESPONSE echo: [dev_id, 0x10, addr_hi, addr_lo, count_hi, count_lo, crc, crc]
            addr = struct.unpack(">H", frame[2:4])[0]
            count = struct.unpack(">H", frame[4:6])[0]
            return f"  REPLY  FC16  dev={dev_id}  HR[{addr}..{addr+count-1}] OK"

    # ─── FC01: Read Coils ───
    elif fc == 0x01:
        if len(frame) == 8:
            addr = struct.unpack(">H", frame[2:4])[0]
            count = struct.unpack(">H", frame[4:6])[0]
            return f"  READ   FC01  dev={dev_id}  Coil[{addr}..{addr+count-1}]"
        else:
            return f"  REPLY  FC01  dev={dev_id}  {len(frame)-5} bytes"

    # ─── FC04: Read Input Registers ───
    elif fc == 0x04:
        if len(frame) == 8:
            addr = struct.unpack(">H", frame[2:4])[0]
            count = struct.unpack(">H", frame[4:6])[0]
            return f"  READ   FC04  dev={dev_id}  IR[{addr}..{addr+count-1}]"
        else:
            byte_count = frame[2]
            reg_count = byte_count // 2
            return f"  REPLY  FC04  dev={dev_id}  {reg_count} regs"

    # ─── FC05: Write Single Coil ───  ★★★ MOGELIJK AAN/UIT KNOP ★★★
    elif fc == 0x05 and len(frame) == 8:
        addr = struct.unpack(">H", frame[2:4])[0]
        value = struct.unpack(">H", frame[4:6])[0]
        state = "ON" if value == 0xFF00 else "OFF" if value == 0x0000 else f"0x{value:04X}"
        return f"████ WRITE FC05  dev={dev_id}  Coil[{addr}] = {state}"

    # ─── FC15: Write Multiple Coils ───
    elif fc == 0x0F:
        if len(frame) >= 8:
            addr = struct.unpack(">H", frame[2:4])[0]
            count = struct.unpack(">H", frame[4:6])[0]
            return f"████ WRITE FC15  dev={dev_id}  Coil[{addr}..{addr+count-1}]"

    # ─── Exception response (FC | 0x80) ───
    elif fc & 0x80:
        orig_fc = fc & 0x7F
        exc_code = frame[2] if len(frame) > 2 else 0
        exc_names = {1: "IllegalFunction", 2: "IllegalDataAddr", 3: "IllegalDataVal", 4: "ServerFailure"}
        exc_name = exc_names.get(exc_code, f"code={exc_code}")
        return f"  ERROR  FC{orig_fc:02d}  dev={dev_id}  {exc_name}"

    # Onbekend
    return f"  ???    FC{fc:02X}  dev={dev_id}  len={len(frame)}  {frame.hex(' ')}"


def main():
    global logfile

    print("=" * 70)
    print("  BataviaHeat R290 — Passive Bus Sniffer")
    print("  Luistert mee op RS-485, stuurt NIETS — geen bus-conflicten!")
    print("=" * 70)
    print(f"\nPoort: {PORT} @ {BAUDRATE} baud")
    print(f"Frame gap: {FRAME_GAP_MS}ms")
    print(f"Logbestand: {LOG_FILE}")
    print()

    # Open logbestand
    logfile = open(LOG_FILE, "w", encoding="utf-8")
    log(f"BataviaHeat R290 — Passive Bus Sniffer")
    log(f"Gestart: {datetime.now():%Y-%m-%d %H:%M:%S}")
    log(f"Poort: {PORT} @ {BAUDRATE} baud")
    log("")

    # Open seriële poort — alleen lezen, geen schrijfbuffer
    ser = serial.Serial(
        port=PORT,
        baudrate=BAUDRATE,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=0.1,  # korte read timeout
    )
    ser.reset_input_buffer()

    log("Luistert... (WRITE-frames worden gemarkeerd met ████)")
    log("Ctrl+C om te stoppen\n")

    frame_buf = bytearray()
    last_byte_time = time.monotonic()
    frame_count = 0
    write_count = 0

    # Track welke read-requests er lopen voor context
    pending_read_addr: int | None = None
    pending_read_count: int | None = None
    pending_read_fc: int | None = None

    # Compact mode: alleen WRITE-frames en fouten tonen op console
    # Alles wordt naar het logbestand geschreven
    read_summary_interval = 50  # elke N read-frames een samenvatting op console

    while running:
        # Lees beschikbare bytes
        data = ser.read(ser.in_waiting or 1)
        now = time.monotonic()

        if data:
            # Als er een pauze was > frame_gap → vorig frame is compleet
            if frame_buf and (now - last_byte_time) * 1000 > FRAME_GAP_MS:
                # Decodeer het voltooide frame
                frame = bytes(frame_buf)
                frame_buf.clear()
                ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]

                decoded = decode_frame(frame, ts)
                if decoded:
                    frame_count += 1
                    is_write = "████" in decoded

                    if is_write:
                        write_count += 1
                        # WRITE-frames: altijd naar console + log
                        log(f"\n{'='*70}")
                        log(f"  {ts}  FRAME #{frame_count}")
                        log(decoded)
                        log(f"  raw: {frame.hex(' ')}")
                        log(f"{'='*70}\n")
                    else:
                        # READ/REPLY: alleen naar log, samenvatting op console
                        log(f"{ts}  {decoded}", console=False)
                        if frame_count % read_summary_interval == 0:
                            print(f"  [{ts}] {frame_count} frames ({write_count} writes) ...", end="\r")

            # Voeg nieuwe bytes toe aan buffer
            frame_buf.extend(data)
            last_byte_time = now

        elif frame_buf and (now - last_byte_time) * 1000 > FRAME_GAP_MS:
            # Timeout — verwerk laatste frame
            frame = bytes(frame_buf)
            frame_buf.clear()
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]

            decoded = decode_frame(frame, ts)
            if decoded:
                frame_count += 1
                is_write = "████" in decoded

                if is_write:
                    write_count += 1
                    log(f"\n{'='*70}")
                    log(f"  {ts}  FRAME #{frame_count}")
                    log(decoded)
                    log(f"  raw: {frame.hex(' ')}")
                    log(f"{'='*70}\n")
                else:
                    log(f"{ts}  {decoded}", console=False)
                    if frame_count % read_summary_interval == 0:
                        print(f"  [{ts}] {frame_count} frames ({write_count} writes) ...", end="\r")

    print()
    summary = f"\nGestopt. {frame_count} frames, {write_count} WRITE-frames."
    log(summary)
    log(f"Logbestand: {LOG_FILE}")
    ser.close()
    logfile.close()
    print(f"  Log opgeslagen: {LOG_FILE}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
BataviaHeat R290 — Interactieve Coil Tester
Loopt door coils en vraagt na elke schrijfactie of er iets veranderde.
Resultaten worden gelogd naar data/coil_test_YYYYMMDD_HHMMSS.log

⚠ DIT SCRIPT SCHRIJFT DAADWERKELIJK NAAR DE WARMTEPOMP!
   Elke actie vereist bevestiging met Y/N.
"""

import logging, signal, sys, time
from datetime import datetime
from pathlib import Path

from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException

logging.getLogger("pymodbus").setLevel(logging.CRITICAL)

# ─── Connection Settings ───
PORT = "COM5"
BAUDRATE = 9600
SLAVE_ID = 1

# ─── Output ───
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
LOG_FILE = DATA_DIR / f"coil_test_{datetime.now():%Y%m%d_%H%M%S}.log"

# ─── Te testen coils ───
# Bekende coils uit bus_sniffer sessie + gaten ertussen om te ontdekken
# Per test: (coil_heen, coil_terug, beschrijving)
#   coil_heen  = schakelt WEG van standaard (zodat je effect ziet)
#   coil_terug = schakelt TERUG naar standaard
#
# Standaard: unit=AAN, silent=AAN, level=2
COILS_TO_TEST = [
    # Bekende coils — eerst weg van standaard, dan terug
    (1025, 1024, "Unit UIT → daarna terug AAN"),
    (1074, 1073, "Stille modus UIT → daarna terug AAN"),
    (1075, 1076, "Stil niveau 1 → daarna terug naar 2"),
    # Gat 1026-1072: mogelijk meer functies
    (1026, None, "Onbekend — zone A verwarming?"),
    (1027, None, "Onbekend — zone A koeling?"),
    (1028, None, "Onbekend — zone B aan?"),
    (1029, None, "Onbekend — zone B uit?"),
    (1030, None, "Onbekend"),
    (1031, None, "Onbekend"),
    (1032, None, "Onbekend"),
    # DHW / warm water gebied
    (1040, None, "Onbekend — DHW?"),
    (1041, None, "Onbekend"),
    (1042, None, "Onbekend"),
    # Midden bereik
    (1048, None, "Onbekend"),
    (1049, None, "Onbekend"),
    (1050, None, "Onbekend"),
    # Vlak voor de stille modus coils
    (1064, None, "Onbekend"),
    (1065, None, "Onbekend"),
    (1066, None, "Onbekend"),
    (1067, None, "Onbekend"),
    (1068, None, "Onbekend"),
    (1069, None, "Onbekend"),
    (1070, None, "Onbekend"),
    (1071, None, "Onbekend"),
    (1072, None, "Onbekend"),
    # Na de stille modus: misschien meer niveaus of andere functies
    (1077, None, "Onbekend — stil niveau 3?"),
    (1078, None, "Onbekend"),
    (1079, None, "Onbekend"),
    (1080, None, "Onbekend"),
    # Eco / power mode
    (1088, None, "Onbekend — eco?"),
    (1089, None, "Onbekend"),
    (1090, None, "Onbekend"),
    (1091, None, "Onbekend"),
    (1092, None, "Onbekend"),
    # Verder zoeken
    (1096, None, "Onbekend"),
    (1100, None, "Onbekend"),
    (1104, None, "Onbekend"),
    (1108, None, "Onbekend"),
    (1112, None, "Onbekend"),
    (1116, None, "Onbekend"),
    (1120, None, "Onbekend"),
    (1124, None, "Onbekend"),
    (1128, None, "Onbekend"),
]

logfile = None


def log(msg: str):
    """Schrijf naar logbestand + console."""
    if logfile:
        logfile.write(msg + "\n")
        logfile.flush()
    print(msg)


def ask(prompt: str) -> str:
    """Vraag input en log het antwoord."""
    response = input(prompt).strip().lower()
    if logfile:
        logfile.write(f"{prompt}{response}\n")
        logfile.flush()
    return response


def main():
    global logfile

    print("=" * 70)
    print("  BataviaHeat R290 — Interactieve Coil Tester")
    print("  ⚠ Dit script SCHRIJFT naar de warmtepomp!")
    print("=" * 70)
    print(f"\nLogbestand: {LOG_FILE}")
    print(f"{len(COILS_TO_TEST)} coils te testen\n")

    logfile = open(LOG_FILE, "w", encoding="utf-8")
    log(f"BataviaHeat R290 — Coil Test")
    log(f"Gestart: {datetime.now():%Y-%m-%d %H:%M:%S}")
    log(f"Poort: {PORT} @ {BAUDRATE} baud\n")

    client = ModbusSerialClient(port=PORT, baudrate=BAUDRATE, timeout=2)
    if not client.connect():
        log("FOUT: Kan niet verbinden!")
        sys.exit(1)

    log("Verbonden.\n")
    log("Instructies:")
    log("  Y = er veranderde iets (beschrijf wat)")
    log("  N = geen zichtbare verandering")
    log("  S = overslaan (skip)")
    log("  Q = stoppen\n")
    log("─" * 70)

    results = []

    def write_coil(client, coil_addr, label):
        """Schrijf een coil. Retourneert True bij succes, False bij fout."""
        try:
            result = client.write_coil(coil_addr, True, device_id=SLAVE_ID)
            if result.isError():
                log(f"  ✗ Modbus fout bij Coil[{coil_addr}]: {result}")
                return False
            log(f"  ✓ Geschreven: Coil[{coil_addr}] = ON  ({label})")
            return True
        except (ModbusException, Exception) as e:
            log(f"  ✗ Exception bij Coil[{coil_addr}]: {e}")
            try:
                client.close()
                time.sleep(0.3)
                client.connect()
            except Exception:
                pass
            return False

    for i, (coil_heen, coil_terug, desc) in enumerate(COILS_TO_TEST, 1):
        log(f"\n[{i}/{len(COILS_TO_TEST)}] Coil[{coil_heen}]  — {desc}")
        if coil_terug:
            log(f"  (heen: Coil[{coil_heen}], terug: Coil[{coil_terug}])")

        # Eerst vragen of we deze willen testen
        choice = ask(f"  Schrijf Coil[{coil_heen}] = ON (0xFF00)? [Y/N/S/Q]: ")

        if choice == "q":
            log("Gestopt door gebruiker.")
            break
        elif choice == "s" or choice == "n":
            log(f"  → Overgeslagen")
            results.append((coil_heen, desc, "SKIP", ""))
            continue
        elif choice != "y":
            log(f"  → Overgeslagen (onbekende invoer)")
            results.append((coil_heen, desc, "SKIP", ""))
            continue

        # Schrijf de coil (heen-richting)
        if not write_coil(client, coil_heen, "heen"):
            results.append((coil_heen, desc, "ERROR", "schrijffout"))
            continue

        # Wacht even zodat gebruiker effect kan zien
        time.sleep(0.5)

        # Vraag wat er gebeurde
        changed = ask("  Veranderde er iets? [Y/N]: ")

        if changed == "y":
            note = ask("  Wat veranderde? (korte beschrijving): ")
            log(f"  ★ GEVONDEN: Coil[{coil_heen}] = {note}")
            results.append((coil_heen, desc, "GEVONDEN", note))
        else:
            log(f"  → Geen effect")
            results.append((coil_heen, desc, "GEEN EFFECT", ""))

        # Terugschakelen naar standaard als we een coil_terug hebben
        if coil_terug:
            log(f"  ↩ Terugschakelen: Coil[{coil_terug}]...")
            time.sleep(0.3)
            if write_coil(client, coil_terug, "terug naar standaard"):
                time.sleep(0.3)
            else:
                log(f"  ⚠ Kon niet terugschakelen! Handmatig herstellen.")

    # Samenvatting
    log("\n" + "=" * 70)
    log("  SAMENVATTING")
    log("=" * 70)

    gevonden = [(c, d, s, n) for c, d, s, n in results if s == "GEVONDEN"]
    geen_effect = [(c, d, s, n) for c, d, s, n in results if s == "GEEN EFFECT"]
    errors = [(c, d, s, n) for c, d, s, n in results if s == "ERROR"]
    skipped = [(c, d, s, n) for c, d, s, n in results if s == "SKIP"]

    if gevonden:
        log(f"\n★ Gevonden ({len(gevonden)}):")
        for coil, desc, _, note in gevonden:
            log(f"  Coil[{coil}]  {desc}  →  {note}")

    if geen_effect:
        log(f"\n✗ Geen effect ({len(geen_effect)}):")
        for coil, desc, _, _ in geen_effect:
            log(f"  Coil[{coil}]  {desc}")

    if errors:
        log(f"\n⚠ Fouten ({len(errors)}):")
        for coil, desc, _, note in errors:
            log(f"  Coil[{coil}]  {desc}  →  {note}")

    if skipped:
        log(f"\n– Overgeslagen ({len(skipped)}):")
        for coil, desc, _, _ in skipped:
            log(f"  Coil[{coil}]  {desc}")

    log(f"\nLogbestand: {LOG_FILE}")
    client.close()
    logfile.close()


if __name__ == "__main__":
    main()

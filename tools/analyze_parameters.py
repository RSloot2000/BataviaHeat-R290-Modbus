#!/usr/bin/env python3
"""
Vergelijk tablet installatieparameters (N/M/F/P/G codes) met gescande registers.

Probeert parametercodes te mappen naar HR-adressen in het config-blok HR[6400-7471].
"""
import json
from pathlib import Path

PROBE_FILE = Path(__file__).parent / "data" / "tablet_probe_20260317_152351.json"

# ─── Tablet parameters uit installatieboekje ───
# Formaat: (code, naam, eenheid, mogelijke_waarden_of_bereik)
TABLET_PARAMS = [
    # N-serie: Systeem / AAN-UIT configuratie
    ("N01", "Power-modus",                      None, {0: "Standaard", 1: "Krachtig", 2: "Eco", 3: "Auto"}),
    ("N02", "Verwarmings- en koeltype",         None, {0: "Alleen verwarmen", 1: "Verwarmen+koelen", 2: "Alleen koelen"}),
    ("N04", "Vierwegklep instelling",           None, {0: "Verwarming open", 1: "Koeling open"}),
    ("N05", "Type draadbedieningsschakelaar",   None, {0: "Tuimelschakelaar", 1: "Pulsschakelaar"}),
    ("N06", "Eenheid Start/Stop controle",      None, {0: "Unie", 1: "Afstandsbed.", 2: "Lokale", 3: "Draadsbed.", 4: "Netbediening"}),
    ("N07", "Geheugen uitschakelen",            None, {0: "Uit", 1: "Aan"}),
    ("N08", "Inkomende stroom zelfstart",       None, {0: "Uit", 1: "Aan"}),
    ("N11", "Warmwaterfunctie",                 None, {0: "Uit", 1: "Aan"}),
    ("N20", "Tank elektrische verwarming",      None, {0: "Uit", 1: "Aan"}),
    ("N21", "Onderste retourpomp",              None, {0: "Uit", 1: "Aan"}),
    ("N22", "Zonne",                            None, {0: "Uit", 1: "Aan"}),
    ("N23", "Koppelingsschakelaar instelling",  None, {0: "Uit", 1: "Koppelingsactie", 2: "Sluiting", 3: "Aan/Uit draad", 4: "Elektr.verw.", 5: "Ext.warmtebron"}),
    ("N26", "Bediening draadcontroller",        None, {0: "Enkele zone", 2: "Dubbele zone"}),
    ("N32", "Slim netwerk",                     None, {0: "Uit", 1: "Aan"}),
    ("N36", "Inlaattemp.sensor vloerverwarming",None, {0: "Uit", 1: "Aan"}),
    ("N37", "Systeem totale uitlaat water temp.",None, {0: "Uit", 1: "Aan"}),
    ("N38", "EVU PV-signaal",                   None, {0: "Normaal open", 1: "Normaal gesloten"}),
    ("N39", "SG-Grid-signaal",                  None, {0: "Normaal open", 1: "Normaal gesloten"}),
    ("N41", "Zonne-temperatuursensor",          None, {0: "Uit", 1: "Aan"}),
    ("N48", "Zone A koeling einde",             None, {0: "Radiator", 1: "Fan Coil", 2: "Vloerverwarming"}),
    ("N49", "Zone A verwarmingseinde",          None, {0: "Radiator", 1: "Fan Coil", 2: "Vloerverwarming"}),
    # M-serie: Temperatuur / curve instellingen
    ("M01", "Koeling instelling temp.",         "°C", (15, 35)),
    ("M02", "Verwarmingsinstelling temp.",       "°C", (0, 85)),
    ("M03", "Insteltemperatuur warm water",      "°C", (0, 80)),
    ("M08", "Verwarmingsinstelling temp. (B)",   "°C", (40, 60)),
    ("M10", "Zone A koelingscurve",             None, (0, 17)),  # 0=uit, 1-8=laag, 9-16=hoog, 17=custom
    ("M11", "Zone A verwarmingscurve",          None, (0, 17)),
    ("M12", "Zone B koelcurve",                 None, (0, 17)),
    ("M13", "Zone B verwarmingscurve",          None, (0, 17)),
    ("M14", "Custom koelomgevingstemp. 1",      "°C", (-5, 46)),
    ("M15", "Custom koelomgevingstemp. 2",      "°C", (-5, 46)),
    ("M16", "Custom koeluitlaattemp. 1",        "°C", (5, 25)),
    ("M17", "Custom koeluitlaattemp. 2",        "°C", (5, 25)),
    ("M18", "Custom verwarmingsomgevingstemp.1", "°C", (-25, 35)),
    ("M19", "Custom verwarmingsomgevingstemp.2", "°C", (-25, 35)),
    ("M20", "Custom verwarmingsuitlaattemp. 1",  "°C", (25, 65)),
    ("M21", "Custom verwarmingsuitlaattemp. 2",  "°C", (25, 65)),
    ("M35", "Min omgevingstemp. auto koeling",   "°C", (20, 29)),
    ("M36", "Max omgevingstemp. auto koeling",   "°C", (10, 17)),
    ("M37", "Vakantie weg verwarming",           "°C", (20, 25)),
    ("M38", "Vakantie weg warm water",           "°C", (20, 25)),
    ("M40", "Externe warmtebron",               None, {0: "Uit", 1: "Alleen verwarmen", 2: "Alleen DHW", 3: "Verwarmen+DHW"}),
    ("M55", "Voorverwarmingstemp. vloerverw.",  "°C", (25, 35)),
    ("M56", "Voorverwarmingsinterval vloerverw.","min", (10, 40)),
    ("M57", "Voorverwarmingstijd vloerverw.",   "uur", (48, 96)),
    ("M58", "Vloerverw. water temp. retour",    "°C", (0, 10)),
    ("M59", "Vloerverw. kamertemp. retourverschil","°C", (0, 10)),
    ("M60", "Vloerverw. voor droging",          "dag", (4, 15)),
    ("M61", "Vloerverw. tijdens droging",       "dag", (3, 7)),
    ("M62", "Vloerverw. na droging",            "dag", (4, 15)),
    ("M63", "Vloerverw. droogtemp.",            "°C", (30, 55)),
    # F-serie: Ventilator
    ("F06", "Ventilatorsnelheid regeling",      None, {0: "Handmatig", 1: "Omgevingstemp. lineair", 2: "Vintemp. lineair"}),
    ("F07", "Ventilator handmatig",             "rps", (0, 2000)),
    # P-serie: Waterpomp
    ("P01", "Werkingsmodus waterpomp",          None, {0: "Blijf draaien", 1: "Stop bij temp.", 2: "Intermitterend"}),
    ("P02", "Waterpomp regeltype",              None, {1: "Snelheid", 2: "Stroom", 3: "AAN/UIT", 4: "Vermogen"}),
    ("P03", "Doelsnelheid waterpomp",           "rpm", (1000, 4500)),
    ("P04", "Fabrikant waterpomp",              None, (0, 4)),
    ("P05", "Doelstroom waterpomp",             "L/h", (0, 4500)),
    ("P06", "Onderste retourwaterpomp interval","min", (5, 120)),
    ("P07", "Sterilisatie onderste retourpomp", None, {0: "Uit", 1: "Aan"}),
    ("P08", "Onderste retourpomp getimed",      None, {0: "Uit", 1: "Aan"}),
    # G-serie: Sterilisatie
    ("G01", "Sterilisatiefunctie",              None, {0: "Uit", 1: "Aan"}),
    ("G02", "Sterilisatietemperatuur",          "°C", (60, 70)),
    ("G03", "Sterilisatie max. cyclus",         "min", (90, 300)),
    ("G04", "Sterilisatie hoge temp. tijd",     "min", (5, 60)),
]


def load_probe() -> dict[int, int]:
    """Laad alle registerwaarden uit de probe JSON."""
    with open(PROBE_FILE, "r") as f:
        data = json.load(f)

    regs: dict[int, int] = {}
    for rng in data["ranges"].values():
        if rng.get("error"):
            continue
        for addr_str, val in rng.get("values", {}).items():
            regs[int(addr_str)] = val
    return regs


def analyze_config_blocks(regs: dict[int, int]):
    """Analyseer de configuratieblokken (HR[6400-7471]) per sub-range."""
    # Config sub-ranges die de tablet pollt
    CONFIG_RANGES = [
        (6400, 6444, "Mode + Setpoints"),
        (6464, 6511, "Enable/Disable flags"),
        (6528, 6575, "Timing/Limits"),
        (6592, 6638, "Humidity/Climate"),
        (6656, 6687, "DHW params"),
        (6720, 6822, "Weather curves"),
        (6848, 6887, "Defrost params"),
        (6912, 6959, "Scheduling"),
        (6976, 7023, "Protection limits"),
        (7040, 7087, "Feature flags"),
        (7104, 7151, "Compressor curves"),
        (7168, 7215, "EEV params"),
        (7296, 7343, "Weather curve data 1"),
        (7360, 7407, "Weather curve data 2"),
        (7424, 7471, "Misc config"),
    ]

    print("=" * 100)
    print("CONFIGURATIE-BLOKKEN ANALYSE (HR[6400-7471])")
    print("=" * 100)

    for start, end, label in CONFIG_RANGES:
        vals = []
        for addr in range(start, end + 1):
            if addr in regs:
                vals.append((addr, regs[addr]))

        non_zero = [(a, v) for a, v in vals if v != 0]
        if not vals:
            continue

        print(f"\n--- {label} (HR[{start}-{end}]) --- "
              f"[{len(vals)} regs, {len(non_zero)} non-zero]")

        for addr, val in vals:
            # Signed interpretatie als > 32767
            signed = val - 65536 if val > 32767 else val
            marker = ""
            if val == 0:
                marker = "  (zero)"
            elif val == 999:
                marker = "  ← disabled sentinel?"
            elif val == 0x8044:
                marker = "  ← disconnected sensor"
            elif val > 32767:
                marker = f"  (signed: {signed})"

            # Toon alleen non-zero of elke 5e
            if val != 0 or (addr - start) % 10 == 0:
                offset = addr - start
                print(f"  HR[{addr}] (offset {offset:2d}): {val:6d}{marker}")


def match_parameters(regs: dict[int, int]):
    """Probeer tablet parameters te matchen met registerwaarden."""
    print("\n" + "=" * 100)
    print("PARAMETER ↔ REGISTER MAPPING ANALYSE")
    print("=" * 100)

    # Bekende of sterke matches (uit eerdere analyse)
    KNOWN_MATCHES = {
        "M02": (6402, "Probe=50 → 50°C verwarmingsinstelling = HR[4]=500÷10"),
        "M03": (None, "DHW temp — niet geïdentificeerd, mogelijk in HR[6656-6687]"),
        "M08": (None, "Zone B verwarming — HR[95]=300=30°C, maar tablet config?"),
    }

    # Config regs gesorteerd
    config_start = 6400
    config_regs = {a: v for a, v in regs.items() if 6400 <= a <= 7471}

    # Tel parameters per serie
    series = {}
    for code, name, unit, vals in TABLET_PARAMS:
        s = code[0]
        series.setdefault(s, []).append((code, name, unit, vals))

    # Analyse per serie
    for s in ["N", "M", "F", "P", "G"]:
        params = series.get(s, [])
        print(f"\n{'─' * 80}")
        print(f"  {s}-SERIE: {len(params)} parameters")
        print(f"{'─' * 80}")

        for code, name, unit, vals in params:
            # Bepaal verwachte waardenbereik
            if isinstance(vals, dict):
                expected = f"enum: {list(vals.keys())}"
                possible_values = set(vals.keys())
                val_type = "enum"
            else:
                lo, hi = vals
                expected = f"range: {lo}-{hi}"
                possible_values = None
                val_type = "range"

            # Zoek bekende match
            if code in KNOWN_MATCHES:
                addr, note = KNOWN_MATCHES[code]
                if addr:
                    actual = regs.get(addr, "?")
                    print(f"  {code:4s} {name:45s} → HR[{addr}]={actual}  ★ {note}")
                else:
                    print(f"  {code:4s} {name:45s} → ???        ★ {note}")
                continue

            # Zoek kandidaat-registers in config block
            candidates = []
            for addr, val in sorted(config_regs.items()):
                signed = val - 65536 if val > 32767 else val
                if val_type == "enum":
                    if val in possible_values or signed in possible_values:
                        candidates.append((addr, val))
                else:
                    lo, hi = vals
                    if lo <= val <= hi or lo <= signed <= hi:
                        candidates.append((addr, val if lo <= val <= hi else signed))

            if candidates:
                cand_str = ", ".join(f"HR[{a}]={v}" for a, v in candidates[:5])
                extra = f" (+{len(candidates)-5} more)" if len(candidates) > 5 else ""
                print(f"  {code:4s} {name:45s} {expected:25s} → kandidaten: {cand_str}{extra}")
            else:
                print(f"  {code:4s} {name:45s} {expected:25s} → GEEN match")


def deep_analysis(regs: dict[int, int]):
    """Diepgaande analyse: probeer N-serie in volgorde te mappen op opeenvolgende adressen."""
    print("\n" + "=" * 100)
    print("SEQUENTIËLE OFFSET-ANALYSE")
    print("=" * 100)
    print("Hypothese: parameters staan in volgorde op vaste offsets binnen elk sub-blok.\n")

    # N-serie parameter nummers
    n_nums = [1, 2, 4, 5, 6, 7, 8, 11, 20, 21, 22, 23, 26, 32, 36, 37, 38, 39, 41, 48, 49]
    m_nums = [1, 2, 3, 8, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 35, 36, 37, 38,
              40, 55, 56, 57, 58, 59, 60, 61, 62, 63]
    p_nums = [1, 2, 3, 4, 5, 6, 7, 8]
    f_nums = [6, 7]
    g_nums = [1, 2, 3, 4]

    # Hypothese 1: N-params op offset = paramNr, in HR[6464+]
    # (6464 is "enable/disable flags" — veel N-params zijn aan/uit)
    print("─── Hypothese: N{xx} → HR[6464 + xx] ───")
    for n in n_nums:
        addr = 6464 + n
        val = regs.get(addr, None)
        param = next((p for p in TABLET_PARAMS if p[0] == f"N{n:02d}"), None)
        if param and val is not None:
            _, name, _, pvals = param
            if isinstance(pvals, dict):
                meaning = pvals.get(val, f"?? (niet in {list(pvals.keys())})")
            else:
                lo, hi = pvals
                meaning = f"{val}" + (" ✓ in bereik" if lo <= val <= hi else f" ✗ BUITEN bereik {lo}-{hi}")
            print(f"  N{n:02d} → HR[{addr}] = {val:5d}  → {name}: {meaning}")
        elif val is not None:
            print(f"  N{n:02d} → HR[{addr}] = {val:5d}  → (geen param def)")
        else:
            print(f"  N{n:02d} → HR[{addr}] = N/A   → niet in probe data")

    # Hypothese 2: M-params op offset = paramNr, in HR[6528+] (timing/limits) of HR[6400+]
    for base_label, base in [("HR[6400+M]", 6400), ("HR[6528+M]", 6528)]:
        print(f"\n─── Hypothese: M{{xx}} → {base_label}{{xx}} ───")
        for m in m_nums:
            addr = base + m
            val = regs.get(addr, None)
            param = next((p for p in TABLET_PARAMS if p[0] == f"M{m:02d}"), None)
            if param and val is not None:
                _, name, unit, pvals = param
                if isinstance(pvals, dict):
                    meaning = pvals.get(val, f"?? (niet in {list(pvals.keys())})")
                else:
                    lo, hi = pvals
                    meaning = f"{val}" + (" ✓ in bereik" if lo <= val <= hi else f" ✗ BUITEN bereik {lo}-{hi}")
                print(f"  M{m:02d} → HR[{addr}] = {val:5d}  → {name}: {meaning}")

    # Hypothese 3: P-params op offset = paramNr
    for base_label, base in [("HR[6912+P]", 6912), ("HR[6976+P]", 6976)]:
        print(f"\n─── Hypothese: P{{xx}} → {base_label}{{xx}} ───")
        for p in p_nums:
            addr = base + p
            val = regs.get(addr, None)
            param = next((par for par in TABLET_PARAMS if par[0] == f"P{p:02d}"), None)
            if param and val is not None:
                _, name, unit, pvals = param
                if isinstance(pvals, dict):
                    meaning = pvals.get(val, f"?? (niet in {list(pvals.keys())})")
                else:
                    lo, hi = pvals
                    meaning = f"{val}" + (" ✓ in bereik" if lo <= val <= hi else f" ✗ BUITEN bereik {lo}-{hi}")
                print(f"  P{p:02d} → HR[{addr}] = {val:5d}  → {name}: {meaning}")

    # Hypothese 4: G-params
    for base_label, base in [("HR[6656+G]", 6656)]:
        print(f"\n─── Hypothese: G{{xx}} → {base_label}{{xx}} ───")
        for g in g_nums:
            addr = base + g
            val = regs.get(addr, None)
            param = next((par for par in TABLET_PARAMS if par[0] == f"G{g:02d}"), None)
            if param and val is not None:
                _, name, unit, pvals = param
                if isinstance(pvals, dict):
                    meaning = pvals.get(val, f"?? (niet in {list(pvals.keys())})")
                else:
                    lo, hi = pvals
                    meaning = f"{val}" + (" ✓ in bereik" if lo <= val <= hi else f" ✗ BUITEN bereik {lo}-{hi}")
                print(f"  G{g:02d} → HR[{addr}] = {val:5d}  → {name}: {meaning}")


def dump_all_config(regs: dict[int, int]):
    """Dump alle non-zero config registers met offset."""
    print("\n" + "=" * 100)
    print("COMPLETE NON-ZERO CONFIG DUMP (HR[6400-7471])")
    print("=" * 100)

    ranges = [
        (6400, 6444), (6464, 6511), (6528, 6575), (6592, 6638),
        (6656, 6687), (6720, 6822), (6848, 6887), (6912, 6959),
        (6976, 7023), (7040, 7087), (7104, 7151), (7168, 7215),
        (7296, 7343), (7360, 7407), (7424, 7471),
    ]

    for start, end in ranges:
        vals = [(a, regs[a]) for a in range(start, end + 1) if a in regs and regs[a] != 0]
        if not vals:
            continue
        print(f"\n  HR[{start}-{end}] ({len(vals)} non-zero):")
        for addr, val in vals:
            signed = val - 65536 if val > 32767 else val
            s_note = f" (signed: {signed})" if val > 32767 else ""
            print(f"    [{addr}] off={addr-start:3d}  val={val:6d}{s_note}")


def main():
    regs = load_probe()
    print(f"Geladen: {len(regs)} registerwaarden uit probe\n")

    # Eerst alle config registers dumpen
    dump_all_config(regs)

    # Sequentiële offset analyse (de kern van het onderzoek)
    deep_analysis(regs)

    # Kandidaat matching
    match_parameters(regs)


if __name__ == "__main__":
    main()

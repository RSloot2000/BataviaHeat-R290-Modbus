"""Comprehensive comparison: tablet parameter values vs ALL Modbus data.

Merges main probe + gap scan data. For each parameter series, tests the
simple offset formula AND searches all registers for matching sequences.
"""

import json
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────
# Load and merge all probe data
# ──────────────────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent / "data"

hr_values: dict[int, int] = {}

# 1. Main probe (new format)
main_probe = DATA_DIR / "tablet_probe_20260317_180509.json"
with open(main_probe) as f:
    probe = json.load(f)
for slave_id, slave_data in probe["registers"].items():
    if "holding_registers" in slave_data:
        for addr_str, val in slave_data["holding_registers"].items():
            hr_values[int(addr_str)] = val

# 2. Gap scan
gap_files = sorted(DATA_DIR.glob("config_gap_scan_*.json"), reverse=True)
if gap_files:
    with open(gap_files[0]) as f:
        gap = json.load(f)
    for addr_str, val in gap["holding_registers"].items():
        hr_values[int(addr_str)] = val
    print(f"  Gap scan geladen: {gap_files[0].name} ({gap['count']} registers)")

print(f"  Totaal: {len(hr_values)} holding registers beschikbaar\n")


def signed(val: int) -> int:
    return val - 65536 if val > 32767 else val


def extract_number(code: str) -> int:
    return int("".join(ch for ch in code if ch.isdigit()))


# ──────────────────────────────────────────────────────────────────────
# Tablet parameter definitions
# ──────────────────────────────────────────────────────────────────────
N_PARAMS = [
    ("N01", "Power-modus",                   2),
    ("N02", "Verwarmings-/koeltype",          0),
    ("N04", "Vierwegklep instelling",         1),
    ("N05", "Schakelaartype",                 0),
    ("N06", "Start/Stop controle",            None),
    ("N07", "Geheugen bewaren",               1),
    ("N08", "Stroom zelfstart",               0),
    ("N11", "Warmwaterfunctie",               0),
    ("N20", "Tank elektr. verwarming",        0),
    ("N21", "Onderste retourpomp",            0),
    ("N22", "Zonne",                          0),
    ("N23", "Koppelingsschakelaar",           3),
    ("N26", "Draadcontroller type",           0),
    ("N27", "Load correction amplitude",      0),
    ("N32", "Slim netwerk",                   1),
    ("N36", "Inlaattemp.sensor vloerverw.",   0),
    ("N37", "Uitlaat water temp.sensor",      1),
    ("N38", "EVU PV-signaal",                 0),
    ("N39", "SG-Grid-signaal",                0),
    ("N41", "Zonne-temperatuursensor",        0),
    ("N48", "Zone A koeling einde",           2),
    ("N49", "Zone A verwarmingseinde",        2),
]

M_PARAMS = [
    ("M01", "Koeling instelling temp.",       10),
    ("M02", "Verwarmingsinstelling temp.",     50),
    ("M03", "Insteltemp. warm water",         50),
    ("M04", "Cooling target room temp.",      18),
    ("M05", "Heating target room temp.",      19),
    ("M08", "Verwarmingstemp. (B)",           30),
    ("M10", "Zone A koelingscurve",           0),
    ("M11", "Zone A verwarmingscurve",        0),
    ("M12", "Zone B koelcurve",              0),
    ("M13", "Zone B verwarmingscurve",        0),
    ("M14", "Koelomgevingstemp. 1",           35),
    ("M15", "Koelomgevingstemp. 2",           25),
    ("M16", "Koeluitlaattemp. 1",             10),
    ("M17", "Koeluitlaattemp. 2",             16),
    ("M18", "Verwarmingsomgevingstemp. 1",    7),
    ("M19", "Verwarmingsomgevingstemp. 2",    -5),
    ("M20", "Verwarmingsuitlaattemp. 1",      28),
    ("M21", "Verwarmingsuitlaattemp. 2",      35),
    ("M35", "Min omgevingstemp. auto koel",   25),
    ("M36", "Max omgevingstemp. auto koel",   17),
    ("M37", "Vakantie verwarming",            25),
    ("M38", "Vakantie warm water",            25),
    ("M39", "Aux. electric heater",           0),
    ("M40", "Externe warmtebron",             1),
    ("M55", "Voorverwarmingstemp. vloerverw.",25),
    ("M56", "Voorverwarmingsinterval",        30),
    ("M57", "Voorverwarmingstijd",            72),
    ("M58", "Vloerverw. water temp. retour",  None),
    ("M59", "Vloerverw. kamertemp. retour",   None),
    ("M60", "Vloerverw. voor droging",        8),
    ("M61", "Vloerverw. tijdens droging",     5),
    ("M62", "Vloerverw. na droging",          5),
    ("M63", "Vloerverw. droogtemp.",          45),
]

P_PARAMS = [
    ("P01", "Werkingsmodus waterpomp",        0),
    ("P02", "Waterpomp regeltype",            1),
    ("P03", "Doelsnelheid waterpomp",         6800),
    ("P04", "Fabrikant waterpomp",            8),
    ("P05", "Doelstroom waterpomp",           2100),
    ("P06", "Onderste retourpomp interval",   5),
    ("P07", "Sterilisatie onderste retourp.",  0),
    ("P08", "Onderste retourpomp getimed",    0),
    ("P09", "Pump intermittent stop time",    999),
    ("P20", "Pump intermittent running time", 5),
]

G_PARAMS = [
    ("G01", "Sterilisatiefunctie",            0),
    ("G02", "Sterilisatietemperatuur",        70),
    ("G03", "Sterilisatie max. cyclus",       210),
    ("G04", "Sterilisatie hoge temp. tijd",   15),
]


# ──────────────────────────────────────────────────────────────────────
# Simple base-offset comparison
# ──────────────────────────────────────────────────────────────────────
def compare_series(name: str, params: list, base: int, show_detail: bool = True) -> tuple[int, int, int]:
    matches = mismatches = missing = 0
    lines = []
    for code, desc, tablet_val in params:
        if tablet_val is None:
            continue
        num = extract_number(code)
        hr_addr = base + num
        raw = hr_values.get(hr_addr)
        if raw is None:
            missing += 1
            status = "❓ niet in probe"
            lines.append(f"  {code:<6} {desc:<35} {tablet_val:>8} {'N/A':>8} {hr_addr:>6}  {status}")
            continue
        # Compare with signed handling
        modbus = signed(raw) if tablet_val < 0 else raw
        if modbus == tablet_val or signed(raw) == tablet_val:
            matches += 1
            status = "✅"
            lines.append(f"  {code:<6} {desc:<35} {tablet_val:>8} {modbus:>8} {hr_addr:>6}  {status}")
        else:
            mismatches += 1
            s = signed(raw)
            extra = f" (signed={s})" if s != raw else ""
            status = f"❌ {extra}"
            lines.append(f"  {code:<6} {desc:<35} {tablet_val:>8} {modbus:>8} {hr_addr:>6}  {status}")

    if show_detail:
        print(f"\n{'─' * 90}")
        print(f"  {name}  base={base}  (HR[{base} + xx])")
        print(f"{'─' * 90}")
        print(f"  {'Code':<6} {'Parameter':<35} {'Tablet':>8} {'Modbus':>8} {'HR':>6}  Status")
        print(f"  {'─'*6} {'─'*35} {'─'*8} {'─'*8} {'─'*6}  {'─'*10}")
        for line in lines:
            print(line)
        print(f"\n  → {matches}✅  {mismatches}❌  {missing}❓")

    return matches, mismatches, missing


# ──────────────────────────────────────────────────────────────────────
# Smart sequence search: find where a series of values appears in memory
# ──────────────────────────────────────────────────────────────────────
def find_sequence(values: list[int], label: str = "", min_addr: int = 0, max_addr: int = 65535):
    """Find a sequence of consecutive register values."""
    if len(values) < 2:
        return []
    results = []
    sorted_addrs = sorted(a for a in hr_values if min_addr <= a <= max_addr)
    for i, addr in enumerate(sorted_addrs):
        if hr_values[addr] != values[0]:
            continue
        # Check if next values are consecutive
        match = True
        for j, expected in enumerate(values[1:], 1):
            next_addr = addr + j
            actual = hr_values.get(next_addr)
            if actual is None:
                match = False
                break
            # Handle signed comparison
            if expected < 0:
                if signed(actual) != expected:
                    match = False
                    break
            elif actual != expected:
                match = False
                break
        if match:
            results.append(addr)
    return results


# ══════════════════════════════════════════════════════════════════════
print("=" * 90)
print("  UITGEBREIDE VERGELIJKING: TABLET vs MODBUS (probe + gap scan)")
print("=" * 90)

# ──────────────────────────────────────────────────────────────────────
# N-SERIE: base 6464
# ──────────────────────────────────────────────────────────────────────
compare_series("N-SERIE", N_PARAMS, 6464)

# ──────────────────────────────────────────────────────────────────────
# M-SERIE: base 6400 — known to work for M01-M05, M08, M11, M40
# but fails for many higher params due to G-serie overlap
# ──────────────────────────────────────────────────────────────────────
compare_series("M-SERIE (interface)", M_PARAMS, 6400)

# ──────────────────────────────────────────────────────────────────────
# G-SERIE: base 6411
# ──────────────────────────────────────────────────────────────────────
compare_series("G-SERIE", G_PARAMS, 6411)

# ──────────────────────────────────────────────────────────────────────
# P-SERIE: SLIMME ZOEK
# ──────────────────────────────────────────────────────────────────────
print("\n" + "=" * 90)
print("  P-SERIE: SEQUENTIE ZOEK")
print("=" * 90)

# P03-P08 sequential values: 6800, 8, 2100, 5, 0, 0
p_seq = [6800, 8, 2100, 5, 0, 0]
hits = find_sequence(p_seq, "P03-P08")
print(f"\n  Sequentie [6800, 8, 2100, 5, 0, 0] (P03-P08) gevonden op:")
for addr in hits:
    base = addr - 3  # P03 offset
    print(f"    HR[{addr}] → als P03, dan base = {base}")

# Try best candidates
if hits:
    for addr in hits:
        base = addr - 3
        compare_series(f"P-SERIE (base={base})", P_PARAMS, base)

# If P09=999 not found with any base, search for it everywhere
print(f"\n  Zoek P09=999 in ALLE beschikbare registers:")
addrs_999 = [a for a, v in hr_values.items() if v == 999]
if addrs_999:
    for a in addrs_999:
        print(f"    HR[{a}] = 999")
else:
    print(f"    NIET gevonden in {len(hr_values)} registers")

# ──────────────────────────────────────────────────────────────────────
# M-SERIE: SLIMME ZOEK voor verplaatste parameters
# ──────────────────────────────────────────────────────────────────────
print("\n" + "=" * 90)
print("  M-SERIE: ZOEK VERPLAATSTE PARAMETERS IN 7200+ BLOK")
print("=" * 90)

# M14-M21 climate curve: 35, 25, 10, 16, 7, -5, 28, 35
m_curve = [35, 25, 10, 16, 7, 65531, 28, 35]  # -5 as uint16 = 65531
hits = find_sequence(m_curve, "M14-M21", 7000, 8000)
print(f"\n  Sequentie [35, 25, 10, 16, 7, -5, 28, 35] (M14-M21):")
for addr in hits:
    print(f"    GEVONDEN HR[{addr}..{addr+7}] → M14 offset = {addr - 14}")

# M55, M56, M57: 25, 30, 72
m_floor = [25, 30, 72]
hits = find_sequence(m_floor, "M55-M57", 7000, 8000)
print(f"\n  Sequentie [25, 30, 72] (M55-M57):")
for addr in hits:
    print(f"    GEVONDEN HR[{addr}..{addr+2}] → M55 offset = {addr - 55}")

# M35=25, M36=17: search for 25, 17 sequence
m_auto = [25, 17]
hits = find_sequence(m_auto, "M35-M36", 6400, 8000)
print(f"\n  Sequentie [25, 17] (M35-M36):")
if hits:
    for addr in hits:
        print(f"    GEVONDEN HR[{addr}..{addr+1}] → M35 offset = {addr - 35}")
else:
    print(f"    NIET gevonden")
    # Maybe M36=17 stored as unsigned, look for the value individually
    addrs_17 = [a for a, v in hr_values.items() if v == 17 and 6400 <= a <= 7500]
    print(f"    Waarde 17 gevonden op: HR[{', '.join(str(a) for a in addrs_17)}]")

# M37=25, M38=25 (not distinctive), M39=0 (too common)
# M60=8, M61=5, M62=5, M63=45
m_dry = [8, 5, 5, 45]
hits = find_sequence(m_dry, "M60-M63", 7000, 8000)
print(f"\n  Sequentie [8, 5, 5, 45] (M60-M63):")
for addr in hits:
    print(f"    GEVONDEN HR[{addr}..{addr+3}] → M60 offset = {addr - 60}")

# ──────────────────────────────────────────────────────────────────────
# N-SERIE: SLIMME ZOEK voor niet-matchende parameters
# ──────────────────────────────────────────────────────────────────────
print("\n" + "=" * 90)
print("  N-SERIE: ZOEK NIET-MATCHENDE WAARDEN")
print("=" * 90)

# N23=3, N48=2, N49=2 don't match at 6464+xx
# N23=3 → HR[6487] = 48 (wrong). Where is value 3?
# N48=2, N49=2: these are "Zone A koeling einde" and "Zone A verwarmingseinde"
# Let's search for N48=2 and N49=2 as 2,2 sequence near the N-block
print(f"\n  N23: tablet=3, HR[6487]={hr_values.get(6487)}")
print(f"  Waarde 3 in N-blok (6464-6520):")
addrs_3 = [a for a in range(6464, 6520) if hr_values.get(a) == 3]
for a in addrs_3:
    print(f"    HR[{a}] = 3 (offset N{a - 6464:02d})")

# ──────────────────────────────────────────────────────────────────────
# COMPLETE CONFIG DUMP: 7200-7260 met annotaties
# ──────────────────────────────────────────────────────────────────────
print("\n" + "=" * 90)
print("  CONFIG BLOK HR[7200-7260] — GEDETAILLEERDE DUMP MET HYPOTHESES")
print("=" * 90)

annotations: dict[int, str] = {
    # F-serie hypothese (base 7199, HR[7199+Fxx])
    7200: "F01? koeling delta temp",
    7201: "F02? koeling integratie",
    7202: "F03? verwarming delta temp",
    7203: "F04? verwarm. integratie",
    7204: "F05? WW delta temp",
    7205: "F06? WW integratie",
    # P-serie block 1 (P01 at 7216)
    7216: "P01? werkingsmodus pomp",
    7217: "P02? pomp regeltype",
    7218: "P03  doelsnelheid pomp = 6800",
    7219: "P04  fabrikant pomp = 8",
    7220: "P05  doelstroom pomp = 2100",
    7221: "P06  onderste retourpomp interval = 5",
    7222: "P07  sterilisatie = 0",
    7223: "P08  getimed = 0",
    # Possible M55-M57
    7224: "M55? voorverwarmingstemp = 25",
    7225: "M56? voorverwarmingsinterval = 30",
    7226: "M57? voorverwarmingstijd = 72",
    # P-serie block 2 (mirror)
    7232: "P01? (Zone B mirror)",
    7233: "P02? (Zone B mirror)",
    7234: "P03  (Zone B) = 6800",
    7235: "P04  (Zone B) = 8",
    7236: "P05  (Zone B) = 2100",
    7237: "P06  (Zone B) = 5",
    7240: "M55? (Zone B) = 25",
    7241: "M56? (Zone B) = 30",
    7242: "M57? (Zone B) = 72",
    7248: "M63? droogtemp = 45",
}

print(f"\n  {'Adres':>6}  {'Waarde':>6}  {'Signed':>7}  {'Hex':>6}  Annotatie")
print(f"  {'─'*6}  {'─'*6}  {'─'*7}  {'─'*6}  {'─'*40}")
for addr in range(7200, 7260):
    v = hr_values.get(addr)
    if v is None:
        continue
    s = signed(v)
    ann = annotations.get(addr, "")
    marker = "  ◄" if ann else ""
    print(f"  {addr:>6}  {v:>6}  {s:>7}  0x{v:04X}  {ann}{marker}")

# ──────────────────────────────────────────────────────────────────────
# CONFIG DUMP: 7390-7410 (M14-M21 climate curve area)
# ──────────────────────────────────────────────────────────────────────
print(f"\n  CONFIG BLOK HR[7390-7410]:")
print(f"  {'Adres':>6}  {'Waarde':>6}  {'Signed':>7}  Annotatie")
print(f"  {'─'*6}  {'─'*6}  {'─'*7}  {'─'*40}")
m_curve_ann = {
    7396: "M14 koelomgev.temp 1 = 35",
    7397: "M15 koelomgev.temp 2 = 25",
    7398: "M16 koeluitlaattemp 1 = 10",
    7399: "M17 koeluitlaattemp 2 = 16",
    7400: "M18 verwarmingsomgev.temp 1 = 7",
    7401: "M19 verwarmingsomgev.temp 2 = -5",
    7402: "M20 verwarmingsuitlaat 1 = 28",
    7403: "M21 verwarmingsuitlaat 2 = 35",
}
for addr in range(7390, 7410):
    v = hr_values.get(addr)
    if v is None:
        continue
    s = signed(v)
    ann = m_curve_ann.get(addr, "")
    print(f"  {addr:>6}  {v:>6}  {s:>7}  {ann}")

# ──────────────────────────────────────────────────────────────────────
# SAMENVATTING: BEVESTIGDE MAPPINGS
# ──────────────────────────────────────────────────────────────────────
print("\n" + "=" * 90)
print("  SAMENVATTING: ALLE BEVESTIGDE REGISTER-MAPPINGS")
print("=" * 90)

confirmed = []

# N-serie at 6464
for code, desc, val in N_PARAMS:
    if val is None:
        continue
    num = extract_number(code)
    addr = 6464 + num
    raw = hr_values.get(addr)
    if raw is not None:
        modbus = signed(raw) if val < 0 else raw
        if modbus == val or signed(raw) == val:
            confirmed.append((code, desc, val, addr, "6464+xx"))

# M-serie at 6400 (only the ones that actually match)
for code, desc, val in M_PARAMS:
    if val is None:
        continue
    num = extract_number(code)
    addr = 6400 + num
    raw = hr_values.get(addr)
    if raw is not None:
        modbus = signed(raw) if val < 0 else raw
        if modbus == val or signed(raw) == val:
            confirmed.append((code, desc, val, addr, "6400+xx"))

# G-serie at 6411
for code, desc, val in G_PARAMS:
    if val is None:
        continue
    num = extract_number(code)
    addr = 6411 + num
    raw = hr_values.get(addr)
    if raw is not None:
        if raw == val:
            confirmed.append((code, desc, val, addr, "6411+xx"))

# P-serie at 7215 (from gap scan)
for code, desc, val in P_PARAMS:
    if val is None:
        continue
    num = extract_number(code)
    addr = 7215 + num
    raw = hr_values.get(addr)
    if raw is not None:
        modbus = signed(raw) if val < 0 else raw
        if modbus == val or signed(raw) == val:
            confirmed.append((code, desc, val, addr, "7215+xx"))

# M14-M21 at 7382+xx (from gap scan sequence search)
m_curve_base = 7382
for code, desc, val in M_PARAMS:
    if val is None:
        continue
    num = extract_number(code)
    if num < 14 or num > 21:
        continue
    addr = m_curve_base + num
    raw = hr_values.get(addr)
    if raw is not None:
        modbus = signed(raw) if val < 0 else raw
        if modbus == val or signed(raw) == val:
            confirmed.append((code, desc, val, addr, f"{m_curve_base}+xx (7200 blok)"))

# M55-M57 at offset in 7200 block
m_floor_pairs = [(55, 7224), (56, 7225), (57, 7226)]
for mnum, addr in m_floor_pairs:
    for code, desc, val in M_PARAMS:
        if val is None:
            continue
        if extract_number(code) == mnum:
            raw = hr_values.get(addr)
            if raw is not None and raw == val:
                confirmed.append((code, desc, val, addr, "7200 blok"))

print(f"\n  {'Code':<6} {'Parameter':<35} {'Waarde':>8} {'HR':>6}  Mapping")
print(f"  {'─'*6} {'─'*35} {'─'*8} {'─'*6}  {'─'*25}")
for code, desc, val, addr, mapping in sorted(confirmed, key=lambda x: x[3]):
    print(f"  {code:<6} {desc:<35} {val:>8} {addr:>6}  {mapping}")

print(f"\n  Totaal bevestigd: {len(confirmed)} parameter-register mappings")

# ──────────────────────────────────────────────────────────────────────
# NIET-GEVONDEN parameters
# ──────────────────────────────────────────────────────────────────────
confirmed_codes = {c[0] for c in confirmed}
print(f"\n  NIET BEVESTIGDE parameters:")
for series_name, params in [("N", N_PARAMS), ("M", M_PARAMS), ("P", P_PARAMS), ("G", G_PARAMS)]:
    for code, desc, val in params:
        if val is None:
            continue
        if code not in confirmed_codes:
            print(f"    {code:<6} {desc:<35} tablet={val}")

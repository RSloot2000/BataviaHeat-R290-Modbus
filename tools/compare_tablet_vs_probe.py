"""Compare tablet parameter values with Modbus probe data.

Tablet values filled in by user (some changed on tablet AFTER the probe scan).
"""

import json
from pathlib import Path

PROBE_FILE = Path(__file__).parent / "data" / "tablet_probe_20260317_180509.json"

with open(PROBE_FILE) as f:
    probe = json.load(f)

# Build lookup: HR address → raw uint16 value
hr_values: dict[int, int] = {}

# Support both probe JSON formats
if "ranges" in probe:
    # Old format: ranges → {range_key: {values: {addr: val}}}
    for range_key, range_data in probe["ranges"].items():
        if "values" in range_data:
            for addr_str, val in range_data["values"].items():
                hr_values[int(addr_str)] = val
elif "registers" in probe:
    # New format: registers → {slave_id: {holding_registers: {addr: val}}}
    for slave_id, slave_data in probe["registers"].items():
        if "holding_registers" in slave_data:
            for addr_str, val in slave_data["holding_registers"].items():
                hr_values[int(addr_str)] = val


def signed(val: int) -> int:
    """Convert uint16 to signed int16."""
    return val - 65536 if val > 32767 else val


# ─── Tablet parameters with user-reported values ───
# Format: (code, description, tablet_value, tablet_value_is_numeric)
# tablet_value = None means not visible / not available

N_PARAMS = [
    ("N01", "Power-modus",                   2,    True),
    ("N02", "Verwarmings-/koeltype",          0,    True),
    ("N04", "Vierwegklep instelling",         1,    True),
    ("N05", "Schakelaartype",                 0,    True),
    ("N06", "Start/Stop controle",            None, False),  # niet beschikbaar
    ("N07", "Geheugen bewaren",               1,    True),
    ("N08", "Stroom zelfstart",               0,    True),
    ("N11", "Warmwaterfunctie",               0,    True),
    ("N20", "Tank elektr. verwarming",        0,    True),
    ("N21", "Onderste retourpomp",            0,    True),
    ("N22", "Zonne",                          0,    True),
    ("N23", "Koppelingsschakelaar",           3,    True),
    ("N26", "Draadcontroller type",           0,    True),
    ("N27", "Load correction amplitude",      0,    True),  # EXTRA - niet in boekje
    ("N32", "Slim netwerk",                   1,    True),
    ("N36", "Inlaattemp.sensor vloerverw.",   0,    True),
    ("N37", "Uitlaat water temp.sensor",      1,    True),
    ("N38", "EVU PV-signaal",                 0,    True),
    ("N39", "SG-Grid-signaal",                0,    True),
    ("N41", "Zonne-temperatuursensor",        0,    True),
    ("N48", "Zone A koeling einde",           2,    True),
    ("N49", "Zone A verwarmingseinde",        2,    True),
]

M_PARAMS = [
    ("M01", "Koeling instelling temp.",       10,   True),
    ("M02", "Verwarmingsinstelling temp.",     50,   True),
    ("M03", "Insteltemp. warm water",         50,   True),
    ("M04", "Cooling target room temp.",      18,   True),   # EXTRA
    ("M05", "Heating target room temp.",      19,   True),   # EXTRA
    ("M08", "Verwarmingstemp. (B)",           30,   True),
    ("M10", "Zone A koelingscurve",           0,    True),
    ("M11", "Zone A verwarmingscurve",        0,    True),
    ("M12", "Zone B koelcurve",              0,    True),
    ("M13", "Zone B verwarmingscurve",        0,    True),
    ("M14", "Koelomgevingstemp. 1",           35,   True),
    ("M15", "Koelomgevingstemp. 2",           25,   True),
    ("M16", "Koeluitlaattemp. 1",             10,   True),
    ("M17", "Koeluitlaattemp. 2",             16,   True),
    ("M18", "Verwarmingsomgevingstemp. 1",    7,    True),
    ("M19", "Verwarmingsomgevingstemp. 2",    -5,   True),
    ("M20", "Verwarmingsuitlaattemp. 1",      28,   True),
    ("M21", "Verwarmingsuitlaattemp. 2",      35,   True),
    ("M35", "Min omgevingstemp. auto koel",   25,   True),
    ("M36", "Max omgevingstemp. auto koel",   17,   True),
    ("M37", "Vakantie verwarming",            25,   True),
    ("M38", "Vakantie warm water",            25,   True),
    ("M39", "Aux. electric heater",           0,    True),   # EXTRA
    ("M40", "Externe warmtebron",             1,    True),
    ("M55", "Voorverwarmingstemp. vloerverw.",25,   True),
    ("M56", "Voorverwarmingsinterval",        30,   True),
    ("M57", "Voorverwarmingstijd",            72,   True),
    ("M58", "Vloerverw. water temp. retour",  None, False),  # niet zichtbaar
    ("M59", "Vloerverw. kamertemp. retour",   None, False),  # niet zichtbaar
    ("M60", "Vloerverw. voor droging",        8,    True),
    ("M61", "Vloerverw. tijdens droging",     5,    True),
    ("M62", "Vloerverw. na droging",          5,    True),
    ("M63", "Vloerverw. droogtemp.",          45,   True),
]

P_PARAMS = [
    ("P01", "Werkingsmodus waterpomp",        0,    True),
    ("P02", "Waterpomp regeltype",            1,    True),
    ("P03", "Doelsnelheid waterpomp",         6800, True),
    ("P04", "Fabrikant waterpomp",            8,    True),
    ("P05", "Doelstroom waterpomp",           2100, True),
    ("P06", "Onderste retourpomp interval",   5,    True),
    ("P07", "Sterilisatie onderste retourp.",  0,    True),
    ("P08", "Onderste retourpomp getimed",    0,    True),
    ("P09", "Pump intermittent stop time",    999,  True),   # EXTRA
    ("P20", "Pump intermittent running time", 5,    True),   # EXTRA
]

G_PARAMS = [
    ("G01", "Sterilisatiefunctie",            0,    True),
    ("G02", "Sterilisatietemperatuur",        70,   True),
    ("G03", "Sterilisatie max. cyclus",       210,  True),
    ("G04", "Sterilisatie hoge temp. tijd",   15,   True),
]


def extract_number(code: str) -> int:
    """Extract the numeric part of a parameter code like N01, M35, P03."""
    num = ""
    for ch in code:
        if ch.isdigit():
            num += ch
    return int(num)


def compare_series(name: str, params: list, base: int):
    """Compare a series of parameters against HR[base + xx]."""
    print(f"\n{'─' * 90}")
    print(f"  {name}-SERIE  →  base HR[{base}]  (formule: HR[{base} + Xxx])")
    print(f"{'─' * 90}")
    print(f"  {'Code':<6} {'Parameter':<35} {'Tablet':>8} {'Modbus':>8} {'HR':>6}  {'Status'}")
    print(f"  {'─'*6} {'─'*35} {'─'*8} {'─'*8} {'─'*6}  {'─'*20}")

    matches = 0
    mismatches = 0
    not_in_probe = 0
    not_available = 0

    for code, desc, tablet_val, is_numeric in params:
        num = extract_number(code)
        hr_addr = base + num
        raw = hr_values.get(hr_addr)

        if not is_numeric or tablet_val is None:
            status = "⚪ niet beschikbaar"
            not_available += 1
            print(f"  {code:<6} {desc:<35} {'n/a':>8} {str(raw) if raw is not None else 'N/A':>8} {hr_addr:>6}  {status}")
            continue

        if raw is None:
            status = "❓ niet in probe"
            not_in_probe += 1
            print(f"  {code:<6} {desc:<35} {tablet_val:>8} {'N/A':>8} {hr_addr:>6}  {status}")
            continue

        # For negative tablet values, compare with signed interpretation
        modbus_val = signed(raw) if tablet_val < 0 else raw

        if modbus_val == tablet_val:
            status = "✅ MATCH"
            matches += 1
        else:
            # Also check signed interpretation for positive values
            s = signed(raw)
            if s == tablet_val:
                status = f"✅ MATCH (signed={s})"
                matches += 1
            else:
                status = f"❌ VERSCHIL (signed={s})" if s != raw else "❌ VERSCHIL"
                mismatches += 1

        print(f"  {code:<6} {desc:<35} {tablet_val:>8} {modbus_val:>8} {hr_addr:>6}  {status}")

    print(f"\n  Resultaat: {matches} match, {mismatches} verschil, {not_in_probe} niet in probe, {not_available} n/a")
    return matches, mismatches


print("=" * 90)
print("  TABLET WAARDEN vs MODBUS PROBE DATA")
print("  Probe: tablet_probe_20260317_152351.json")
print("  Let op: gebruiker heeft sommige waarden GEWIJZIGD na de probe scan!")
print("=" * 90)

compare_series("N", N_PARAMS, 6464)
compare_series("M", M_PARAMS, 6400)

# ─── P-serie: probeer meerdere base-adressen ───
print("\n" + "=" * 90)
print("  P-SERIE: ZOEK NAAR CORRECT BASISADRES")
print("=" * 90)

# The P values from tablet: P03=6800, P05=2100, P09=999 are very distinctive
# Let's search all config blocks for these values
print("\n  Zoek naar kenmerkende P-waarden in alle config registers:")
print(f"  P03=6800 (rpm), P05=2100 (L/uur), P09=999 (min)")
for target_name, target_val in [("P03=6800", 6800), ("P05=2100", 2100), ("P09=999", 999)]:
    found = [addr for addr in range(6400, 7472) if hr_values.get(addr) == target_val]
    print(f"  {target_name}: gevonden op HR{found}")

# Try candidate bases
p_candidates = [6912, 6944, 6976, 7040]
print()
for base in p_candidates:
    m, mm = compare_series(f"P (base={base})", P_PARAMS, base)

# Also try: what if P is stored at a different offset pattern?
# P03=6800 is at HR[6948], P05=2100 is at HR[6949]
# If P03 → HR[base+3] = 6948, then base = 6945
# If P05 → HR[base+5] = 6949, then base = 6944
# Hmm, 6945 vs 6944 — off by one. Let's check base=6944 and base=6945
print("\n  Extra: probeer base 6944 en 6945 (afgeleid van P03=6800 @ HR[6948])")
for base in [6944, 6945]:
    m, mm = compare_series(f"P (base={base})", P_PARAMS, base)

# ─── G-serie: zoek kenmerkende waarden ───
print("\n" + "=" * 90)
print("  G-SERIE: ZOEK NAAR CORRECT BASISADRES")
print("=" * 90)
print("\n  Zoek naar kenmerkende G-waarden:")
print(f"  G02=70 (°C), G03=210 (min), G04=15 (min)")
for target_name, target_val in [("G03=210", 210), ("G02=70", 70), ("G04=15", 15)]:
    found = [addr for addr in range(6400, 7472) if hr_values.get(addr) == target_val]
    print(f"  {target_name}: gevonden op HR{found}")

# G03=210 at HR[?], if G03 → HR[base+3] → base = HR-3
# Let's look for sequences: G01=0, G02=70, G03=210, G04=15
print("\n  Zoek naar sequentie [0, 70, 210, 15] in config registers:")
for addr in range(6400, 7470):
    v1 = hr_values.get(addr)
    v2 = hr_values.get(addr + 1)
    v3 = hr_values.get(addr + 2)
    v4 = hr_values.get(addr + 3)
    if v1 == 0 and v2 == 70 and v3 == 210 and v4 == 15:
        print(f"  GEVONDEN op HR[{addr}..{addr+3}] → base zou zijn {addr} (G00) of {addr-1} (G01)")

# Also search with G01 offset: base+1=addr → G02=70, so base = addr-2
# Find addr where val=70 and addr+1=210 and addr+2=15
print("\n  Zoek naar sequentie [70, 210, 15] (G02,G03,G04):")
for addr in range(6400, 7470):
    v1 = hr_values.get(addr)
    v2 = hr_values.get(addr + 1)
    v3 = hr_values.get(addr + 2)
    if v1 == 70 and v2 == 210 and v3 == 15:
        base = addr - 2
        print(f"  HR[{addr}..{addr+2}] = [70, 210, 15] → G02-G04 → base = {base}")
        m, mm = compare_series(f"G (base={base})", G_PARAMS, base)

# ─── F-serie: niet op tablet, skip ───
print("\n" + "=" * 90)
print("  F-SERIE: niet beschikbaar op tablet — overgeslagen")
print("=" * 90)

# ─── Samenvatting mapping N en M met gewijzigde waarden ───
print("\n" + "=" * 90)
print("  DETAIL: N-SERIE WAARDEN DIE AFWIJKEN (gebruiker heeft instellingen gewijzigd)")
print("=" * 90)
print(f"\n  {'Code':<6} {'Parameter':<35} {'Tablet':>8} {'Probe':>8}  Analyse")
print(f"  {'─'*6} {'─'*35} {'─'*8} {'─'*8}  {'─'*40}")

for code, desc, tablet_val, is_numeric in N_PARAMS:
    if not is_numeric or tablet_val is None:
        continue
    num = extract_number(code)
    hr_addr = 6464 + num
    raw = hr_values.get(hr_addr)
    if raw is None:
        continue
    s = signed(raw)
    modbus = s if tablet_val < 0 else raw
    if modbus != tablet_val:
        print(f"  {code:<6} {desc:<35} {tablet_val:>8} {modbus:>8}  ← gebruiker heeft dit waarschijnlijk gewijzigd")

print(f"\n" + "=" * 90)
print("  DETAIL: M-SERIE WAARDEN DIE AFWIJKEN")
print("=" * 90)
print(f"\n  {'Code':<6} {'Parameter':<35} {'Tablet':>8} {'Probe':>8}  Analyse")
print(f"  {'─'*6} {'─'*35} {'─'*8} {'─'*8}  {'─'*40}")

for code, desc, tablet_val, is_numeric in M_PARAMS:
    if not is_numeric or tablet_val is None:
        continue
    num = extract_number(code)
    hr_addr = 6400 + num
    raw = hr_values.get(hr_addr)
    if raw is None:
        continue
    s = signed(raw)
    modbus = s if tablet_val < 0 else raw
    if modbus != tablet_val:
        print(f"  {code:<6} {desc:<35} {tablet_val:>8} {modbus:>8}  ← gewijzigd of ander schaal?")

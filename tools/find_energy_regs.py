"""Find energy-related registers (voltage, current, power) in overnight DB."""
import sqlite3

REG = 'holding'
db = sqlite3.connect('data/overnight_20260317_231919.db')
c = db.cursor()

# Correlatie-analyse: bekijk tijdreeksen van onbekende registers bij compressor AAN/UIT
# HR[1283]=1 is compressor AAN
print("=== Correlatie: energie-kandidaten vs compressor status ===\n")

# Haal een paar timestamps waar compressor AAN gaat en UIT gaat
c.execute("""SELECT timestamp, old_value, new_value FROM changes 
             WHERE reg_type='holding' AND address=1283 ORDER BY timestamp""")
transitions = c.fetchall()
print(f"Compressor transities: {len(transitions)}")
for t in transitions:
    print(f"  {t[0]}: {t[1]} -> {t[2]}")

# Pak waarden van onbekende registers bij een AAN-moment en een UIT-moment
candidates = [1325, 1327, 1328, 1335, 1364, 1370, 1371]
if transitions:
    # Eerste keer dat compressor AAN gaat
    on_ts = [t[0] for t in transitions if t[2] == 1]
    off_ts = [t[0] for t in transitions if t[2] == 0]
    
    if on_ts and off_ts:
        # Zoek data net na eerste AAN en net na eerste UIT
        print(f"\n--- Waarden net NA compressor AAN ({on_ts[0]}) ---")
        c.execute(f"""SELECT address, raw_value FROM readings 
                      WHERE reg_type='holding' AND address IN ({','.join(str(a) for a in candidates)})
                      AND timestamp > ? ORDER BY timestamp LIMIT {len(candidates)*3}""", (on_ts[0],))
        for r in c.fetchall():
            print(f"  HR[{r[0]}] = {r[1]} ({r[1]*0.1:.1f})")
        
        print(f"\n--- Waarden net NA compressor UIT ({off_ts[0]}) ---")
        c.execute(f"""SELECT address, raw_value FROM readings
                      WHERE reg_type='holding' AND address IN ({','.join(str(a) for a in candidates)})
                      AND timestamp > ? ORDER BY timestamp LIMIT {len(candidates)*3}""", (off_ts[0],))
        for r in c.fetchall():
            print(f"  HR[{r[0]}] = {r[1]} ({r[1]*0.1:.1f})")

# Bekijk T-serie tablet mapping hints
# T36 = Compressor bus voltage = 322.8V = raw 3228 bij ×0.1
# HR[1041] en HR[1368] zijn mirrors: 316.4-389.4 → past bij DC bus maar grotere range
# HR[20] heeft 310-349.8 → ook een kandidaat

print("\n\n=== Tablet T-serie vs HR mapping ===")
print("""
Tablet T-serie energie-registers (afgelezen op 17/3, compressor UIT):
  T29 Compressor running speed    = 0.0 rps    → HR[41] compressor_power? (0-1914, maar geen rps)
  T30 Module temp                 = 20.6°C     → ? 
  T31 Compressor power output     = 0.00 kW    → ? (niet gevonden als aparte W/kW register)
  T32 Compressor target speed     = 20.0 rps   → ?
  T33 Compressor current output   = 0.0 A      → HR[1325]? (1.3-15.5 scan3, 1.2-10.9 scan4)
  T34 Compressor torque output    = 0.0 %      → ?
  T35 Compressor voltage output   = 0.0 V      → HR[1335]? (95-3525 scan3, 0-2365 scan4)
  T36 Compressor bus voltage      = 322.8 V    → HR[1041]/HR[1368] (316-389, ×0.1)
  T38 Inverter current input      = 1.3 A      → HR[1370]? (1.3-15.5 scan3, 1.2-10.9 scan4)
""")

# Correlatie check HR[1325] vs HR[1370] - mirrors?
print("=== HR[1325] vs HR[1370] correlatie (beide 1.3-15.5 in scan 3) ===")
c.execute("""SELECT a.timestamp, a.raw_value as v1325, b.raw_value as v1370
             FROM readings a JOIN readings b ON a.timestamp = b.timestamp
             WHERE a.reg_type='holding' AND b.reg_type='holding'
             AND a.address=1325 AND b.address=1370
             ORDER BY a.timestamp LIMIT 20""")
for r in c.fetchall():
    match = "MATCH" if r[1] == r[2] else "DIFF"
    print(f"  {r[0]}: HR[1325]={r[1]:5d} ({r[1]*0.1:.1f}) HR[1370]={r[2]:5d} ({r[2]*0.1:.1f}) [{match}]")

# HR[1335] check - is dit compressor output voltage?
print("\n=== HR[1335] detail (mogelijke compressor voltage output) ===")
c.execute("""SELECT MIN(raw_value), MAX(raw_value), AVG(raw_value), COUNT(DISTINCT raw_value)
             FROM readings WHERE reg_type='holding' AND address=1335 AND raw_value!=32836""")
r = c.fetchone()
print(f"  range: {r[0]}-{r[1]} ({r[0]*0.1:.1f}-{r[1]*0.1:.1f}V?) avg={r[2]:.0f} ({r[2]*0.1:.1f}V?) dist={r[3]}")

# Zijn er waarden=0 in HR[1335]? (zou zo zijn als comp UIT en T35=0.0V)
c.execute("SELECT COUNT(*) FROM readings WHERE reg_type='holding' AND address=1335 AND raw_value=0")
print(f"  waarden=0: {c.fetchone()[0]} (compressor UIT → voltage=0)")

c.execute("SELECT COUNT(*) FROM readings WHERE reg_type='holding' AND address=1335 AND raw_value>0")
print(f"  waarden>0: {c.fetchone()[0]} (compressor AAN → voltage>0)")

# Check HR[1327] - 0-488/496 range - wat is dit?
print("\n=== HR[1327] detail (0-49.6, variabel) ===")
c.execute("""SELECT MIN(raw_value), MAX(raw_value), AVG(raw_value)
             FROM readings WHERE reg_type='holding' AND address=1327 AND raw_value!=32836""")
r = c.fetchone()
print(f"  range: {r[0]}-{r[1]} ({r[0]*0.1:.1f}-{r[1]*0.1:.1f}) avg={r[2]:.0f} ({r[2]*0.1:.1f})")

# Check HR[1371] - 25.7-42.0 - wat is dit? 
print("\n=== HR[1371] detail (13.6-42.0, variabel) ===")
c.execute("""SELECT MIN(raw_value), MAX(raw_value), AVG(raw_value)
             FROM readings WHERE reg_type='holding' AND address=1371 AND raw_value!=32836""")
r = c.fetchone()
print(f"  range: {r[0]}-{r[1]} ({r[0]*0.1:.1f}-{r[1]*0.1:.1f}) avg={r[2]:.0f} ({r[2]*0.1:.1f})")

# Wattage berekening: als we V en A kennen...
# HR[1338] = netspanning ~230V, HR[1325/1370] = stroom ~1-15A 
# Dan P = V × A = 230 × 15 = 3450W max → past bij een 3-8kW warmtepomp
print("\n=== Geschat vermogen via spanning × stroom ===")
print("  HR[1338] × HR[1325]: 230V × 10.9A = ~2507W max (scan 4)")
print("  HR[1338] × HR[1370]: 230V × 10.9A = ~2507W max (scan 4)")
print("  Past bij BataviaHeat R290 3-8kW warmtepomp!")

db.close()
HERE a.reg_type='holding' AND b.reg_type='holding'
             AND a.address=1325 AND b.address=1370
             ORDER BY a.timestamp LIMIT 20""")
for r in c.fetchall():
    match = "MATCH" if r[1] == r[2] else "DIFF"
    print(f"  {r[0]}: HR[1325]={r[1]:5d} ({r[1]*0.1:.1f}) HR[1370]={r[2]:5d} ({r[2]*0.1:.1f}) [{match}]")

# HR[1335] check - is dit compressor output voltage?
print("\n=== HR[1335] detail (mogelijke compressor voltage output) ===")
c.execute("""SELECT MIN(raw_value), MAX(raw_value), AVG(raw_value), COUNT(DISTINCT raw_value)
             FROM readings WHERE reg_type='holding' AND address=1335 AND raw_value!=32836""")
r = c.fetchone()
print(f"  range: {r[0]}-{r[1]} ({r[0]*0.1:.1f}-{r[1]*0.1:.1f}V?) avg={r[2]:.0f} ({r[2]*0.1:.1f}V?) dist={r[3]}")

# Zijn er waarden=0 in HR[1335]? (zou zo zijn als comp UIT en T35=0.0V)
c.execute("SELECT COUNT(*) FROM readings WHERE reg_type='holding' AND address=1335 AND raw_value=0")
print(f"  waarden=0: {c.fetchone()[0]} (compressor UIT → voltage=0)")

c.execute("SELECT COUNT(*) FROM readings WHERE reg_type='holding' AND address=1335 AND raw_value>0")
print(f"  waarden>0: {c.fetchone()[0]} (compressor AAN → voltage>0)")

# Check HR[1327] - 0-488/496 range - wat is dit?
print("\n=== HR[1327] detail (0-49.6, variabel) ===")
c.execute("""SELECT MIN(raw_value), MAX(raw_value), AVG(raw_value)
             FROM readings WHERE reg_type='holding' AND address=1327 AND raw_value!=32836""")
r = c.fetchone()
print(f"  range: {r[0]}-{r[1]} ({r[0]*0.1:.1f}-{r[1]*0.1:.1f}) avg={r[2]:.0f} ({r[2]*0.1:.1f})")

# Check HR[1371] - 25.7-42.0 - wat is dit? 
print("\n=== HR[1371] detail (13.6-42.0, variabel) ===")
c.execute("""SELECT MIN(raw_value), MAX(raw_value), AVG(raw_value)
             FROM readings WHERE reg_type='holding' AND address=1371 AND raw_value!=32836""")
r = c.fetchone()
print(f"  range: {r[0]}-{r[1]} ({r[0]*0.1:.1f}-{r[1]*0.1:.1f}) avg={r[2]:.0f} ({r[2]*0.1:.1f})")

# Wattage berekening: als we V en A kennen...
# HR[1338] = netspanning ~230V, HR[1325/1370] = stroom ~1-15A 
# Dan P = V × A = 230 × 15 = 3450W max → past bij een 3-8kW warmtepomp
print("\n=== Geschat vermogen via spanning × stroom ===")
print("  HR[1338] × HR[1325]: 230V × 10.9A = ~2507W max (scan 4)")
print("  HR[1338] × HR[1370]: 230V × 10.9A = ~2507W max (scan 4)")
print("  Past bij BataviaHeat R290 3-8kW warmtepomp!")

db.close()
HERE a.reg_type='holding' AND b.reg_type='holding'
             AND a.address=1325 AND b.address=1370
             ORDER BY a.timestamp LIMIT 20""")
for r in c.fetchall():
    match = "MATCH" if r[1] == r[2] else "DIFF"
    print(f"  {r[0]}: HR[1325]={r[1]:5d} ({r[1]*0.1:.1f}) HR[1370]={r[2]:5d} ({r[2]*0.1:.1f}) [{match}]")

# HR[1335] check - is dit compressor output voltage?
print("\n=== HR[1335] detail (mogelijke compressor voltage output) ===")
c.execute("""SELECT MIN(raw_value), MAX(raw_value), AVG(raw_value), COUNT(DISTINCT raw_value)
             FROM readings WHERE reg_type='holding' AND address=1335 AND raw_value!=32836""")
r = c.fetchone()
print(f"  range: {r[0]}-{r[1]} ({r[0]*0.1:.1f}-{r[1]*0.1:.1f}V?) avg={r[2]:.0f} ({r[2]*0.1:.1f}V?) dist={r[3]}")

# Zijn er waarden=0 in HR[1335]? (zou zo zijn als comp UIT en T35=0.0V)
c.execute("SELECT COUNT(*) FROM readings WHERE reg_type='holding' AND address=1335 AND raw_value=0")
print(f"  waarden=0: {c.fetchone()[0]} (compressor UIT → voltage=0)")

c.execute("SELECT COUNT(*) FROM readings WHERE reg_type='holding' AND address=1335 AND raw_value>0")
print(f"  waarden>0: {c.fetchone()[0]} (compressor AAN → voltage>0)")

# Check HR[1327] - 0-488/496 range - wat is dit?
print("\n=== HR[1327] detail (0-49.6, variabel) ===")
c.execute("""SELECT MIN(raw_value), MAX(raw_value), AVG(raw_value)
             FROM readings WHERE reg_type='holding' AND address=1327 AND raw_value!=32836""")
r = c.fetchone()
print(f"  range: {r[0]}-{r[1]} ({r[0]*0.1:.1f}-{r[1]*0.1:.1f}) avg={r[2]:.0f} ({r[2]*0.1:.1f})")

# Check HR[1371] - 25.7-42.0 - wat is dit? 
print("\n=== HR[1371] detail (13.6-42.0, variabel) ===")
c.execute("""SELECT MIN(raw_value), MAX(raw_value), AVG(raw_value)
             FROM readings WHERE reg_type='holding' AND address=1371 AND raw_value!=32836""")
r = c.fetchone()
print(f"  range: {r[0]}-{r[1]} ({r[0]*0.1:.1f}-{r[1]*0.1:.1f}) avg={r[2]:.0f} ({r[2]*0.1:.1f})")

# Wattage berekening: als we V en A kennen...
# HR[1338] = netspanning ~230V, HR[1325/1370] = stroom ~1-15A 
# Dan P = V × A = 230 × 15 = 3450W max → past bij een 3-8kW warmtepomp
print("\n=== Geschat vermogen via spanning × stroom ===")
print("  HR[1338] × HR[1325]: 230V × 10.9A = ~2507W max (scan 4)")
print("  HR[1338] × HR[1370]: 230V × 10.9A = ~2507W max (scan 4)")
print("  Past bij BataviaHeat R290 3-8kW warmtepomp!")

db.close()


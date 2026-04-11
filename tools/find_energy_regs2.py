"""Find energy-related registers (voltage, current, power) in overnight DB."""
import sqlite3

db = sqlite3.connect('data/overnight_20260317_231919.db')
c = db.cursor()

# Correlatie-analyse: bekijk energie-kandidaten bij compressor AAN/UIT
print("=== Correlatie: energie-kandidaten vs compressor status ===\n")

c.execute("""SELECT timestamp, old_value, new_value FROM changes 
             WHERE reg_type='holding' AND address=1283 ORDER BY timestamp""")
transitions = c.fetchall()
print(f"Compressor transities: {len(transitions)}")
for t in transitions:
    print(f"  {t[0]}: {t[1]} -> {t[2]}")

candidates = [1325, 1327, 1328, 1335, 1364, 1370, 1371]
if transitions:
    on_ts = [t[0] for t in transitions if t[2] == 1]
    off_ts = [t[0] for t in transitions if t[2] == 0]
    
    if on_ts and off_ts:
        print(f"\n--- Waarden net NA compressor AAN ({on_ts[0]}) ---")
        c.execute(
            "SELECT address, raw_value FROM readings "
            "WHERE reg_type='holding' AND address IN (" + ','.join(str(a) for a in candidates) + ") "
            "AND timestamp > ? ORDER BY timestamp LIMIT ?",
            (on_ts[0], len(candidates)*3))
        for r in c.fetchall():
            print(f"  HR[{r[0]}] = {r[1]} ({r[1]*0.1:.1f})")
        
        print(f"\n--- Waarden net NA compressor UIT ({off_ts[0]}) ---")
        c.execute(
            "SELECT address, raw_value FROM readings "
            "WHERE reg_type='holding' AND address IN (" + ','.join(str(a) for a in candidates) + ") "
            "AND timestamp > ? ORDER BY timestamp LIMIT ?",
            (off_ts[0], len(candidates)*3))
        for r in c.fetchall():
            print(f"  HR[{r[0]}] = {r[1]} ({r[1]*0.1:.1f})")

# Correlatie check HR[1325] vs HR[1370] - mirrors?
print("\n=== HR[1325] vs HR[1370] correlatie ===")
c.execute(
    "SELECT a.timestamp, a.raw_value, b.raw_value "
    "FROM readings a JOIN readings b ON a.timestamp = b.timestamp "
    "WHERE a.reg_type='holding' AND b.reg_type='holding' "
    "AND a.address=1325 AND b.address=1370 "
    "ORDER BY a.timestamp LIMIT 20")
for r in c.fetchall():
    match = "MATCH" if r[1] == r[2] else "DIFF"
    print(f"  {r[0]}: HR[1325]={r[1]:5d} ({r[1]*0.1:.1f}) HR[1370]={r[2]:5d} ({r[2]*0.1:.1f}) [{match}]")

# HR[1335] check
print("\n=== HR[1335] detail (mogelijke compressor voltage output) ===")
c.execute(
    "SELECT MIN(raw_value), MAX(raw_value), AVG(raw_value), COUNT(DISTINCT raw_value) "
    "FROM readings WHERE reg_type='holding' AND address=1335 AND raw_value!=32836")
r = c.fetchone()
if r[0] is not None:
    print(f"  range: {r[0]}-{r[1]} ({r[0]*0.1:.1f}-{r[1]*0.1:.1f}V?) avg={r[2]:.0f} ({r[2]*0.1:.1f}V?) dist={r[3]}")
c.execute("SELECT COUNT(*) FROM readings WHERE reg_type='holding' AND address=1335 AND raw_value=0")
print(f"  waarden=0: {c.fetchone()[0]} (compressor UIT -> voltage=0)")
c.execute("SELECT COUNT(*) FROM readings WHERE reg_type='holding' AND address=1335 AND raw_value>0 AND raw_value<32836")
print(f"  waarden>0: {c.fetchone()[0]} (compressor AAN -> voltage>0)")

# HR[1327]
print("\n=== HR[1327] detail (0-49.6, variabel) ===")
c.execute(
    "SELECT MIN(raw_value), MAX(raw_value), AVG(raw_value) "
    "FROM readings WHERE reg_type='holding' AND address=1327 AND raw_value!=32836")
r = c.fetchone()
if r[0] is not None:
    print(f"  range: {r[0]}-{r[1]} ({r[0]*0.1:.1f}-{r[1]*0.1:.1f}) avg={r[2]:.0f} ({r[2]*0.1:.1f})")

# HR[1371]
print("\n=== HR[1371] detail (13.6-42.0, variabel) ===")
c.execute(
    "SELECT MIN(raw_value), MAX(raw_value), AVG(raw_value) "
    "FROM readings WHERE reg_type='holding' AND address=1371 AND raw_value!=32836")
r = c.fetchone()
if r[0] is not None:
    print(f"  range: {r[0]}-{r[1]} ({r[0]*0.1:.1f}-{r[1]*0.1:.1f}) avg={r[2]:.0f} ({r[2]*0.1:.1f})")

# Check of HR[1322] en HR[1365] mirrors zijn (beide 0-11.1A, stroom?)
print("\n=== HR[1322] vs HR[1365] correlatie (beide 0-11.1A scan3) ===")
c.execute(
    "SELECT a.timestamp, a.raw_value, b.raw_value "
    "FROM readings a JOIN readings b ON a.timestamp = b.timestamp "
    "WHERE a.reg_type='holding' AND b.reg_type='holding' "
    "AND a.address=1322 AND b.address=1365 "
    "ORDER BY a.timestamp LIMIT 20")
for r in c.fetchall():
    match = "MATCH" if r[1] == r[2] else "DIFF"
    print(f"  {r[0]}: HR[1322]={r[1]:5d} ({r[1]*0.1:.1f}A?) HR[1365]={r[2]:5d} ({r[2]*0.1:.1f}A?) [{match}]")

# Watt berekening
print("\n=== Geschat vermogen via spanning x stroom ===")
print("  HR[1338] x HR[1322]: 230V x 7.2A = ~1656W max (scan 4)")
print("  HR[1338] x HR[1325]: 230V x 10.9A = ~2507W max (scan 4)")
print("  Past bij BataviaHeat R290 3-8kW warmtepomp!")

db.close()

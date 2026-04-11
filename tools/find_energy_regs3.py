"""Quick check HR[1322] vs HR[1365] during compressor ON."""
import sqlite3

db = sqlite3.connect('data/overnight_20260317_231919.db')
c = db.cursor()

# Check during first compressor ON period (03:29 - 04:14)
print("=== HR[1322] vs HR[1365] tijdens compressor AAN (03:29-04:14) ===")
c.execute(
    "SELECT a.timestamp, a.raw_value, b.raw_value "
    "FROM readings a JOIN readings b ON a.timestamp = b.timestamp "
    "WHERE a.reg_type='holding' AND b.reg_type='holding' "
    "AND a.address=1322 AND b.address=1365 "
    "AND a.timestamp > '2026-03-18T03:29:22' "
    "AND a.timestamp < '2026-03-18T04:14:40' "
    "ORDER BY a.timestamp LIMIT 20")
for r in c.fetchall():
    match = "MATCH" if r[1] == r[2] else "DIFF"
    print(f"  {r[0]}: HR[1322]={r[1]:5d} ({r[1]*0.1:.1f}A) HR[1365]={r[2]:5d} ({r[2]*0.1:.1f}A) [{match}]")

# Check HR[1325] vs HR[1370] during same period
print("\n=== HR[1325] vs HR[1370] tijdens compressor AAN (03:29-04:14) ===")
c.execute(
    "SELECT a.timestamp, a.raw_value, b.raw_value "
    "FROM readings a JOIN readings b ON a.timestamp = b.timestamp "
    "WHERE a.reg_type='holding' AND b.reg_type='holding' "
    "AND a.address=1325 AND b.address=1370 "
    "AND a.timestamp > '2026-03-18T03:29:22' "
    "AND a.timestamp < '2026-03-18T04:14:40' "
    "ORDER BY a.timestamp LIMIT 20")
for r in c.fetchall():
    match = "MATCH" if r[1] == r[2] else "DIFF"
    print(f"  {r[0]}: HR[1325]={r[1]:5d} ({r[1]*0.1:.1f}A) HR[1370]={r[2]:5d} ({r[2]*0.1:.1f}A) [{match}]")

# Check HR[41] (power) en HR[1335] (voltage) en HR[1325] (current) samen
# P = V_mains * I_input ?
print("\n=== Power check: HR[41] vs HR[1338]*HR[1325]/1000 ===")
c.execute(
    "SELECT r41.timestamp, r41.raw_value as power, "
    "r1338.raw_value as voltage, r1325.raw_value as current "
    "FROM readings r41 "
    "JOIN readings r1338 ON r41.timestamp = r1338.timestamp "
    "JOIN readings r1325 ON r41.timestamp = r1325.timestamp "
    "WHERE r41.reg_type='holding' AND r1338.reg_type='holding' AND r1325.reg_type='holding' "
    "AND r41.address=41 AND r1338.address=1338 AND r1325.address=1325 "
    "AND r41.timestamp > '2026-03-18T03:29:22' "
    "AND r41.timestamp < '2026-03-18T04:14:40' "
    "ORDER BY r41.timestamp LIMIT 15")
for r in c.fetchall():
    v = r[2] * 0.1   # voltage in V
    i = r[3] * 0.1   # current in A
    calc_w = v * i    # P = V * I
    print(f"  {r[0]}: HR[41]={r[1]:5d}W? V={v:.1f}V I={i:.1f}A V*I={calc_w:.0f}W")

# Check HR[1327] vs HR[1328] - mirrors?
print("\n=== HR[1327] vs HR[1328] (mirrors?) compressor AAN ===")
c.execute(
    "SELECT a.timestamp, a.raw_value, b.raw_value "
    "FROM readings a JOIN readings b ON a.timestamp = b.timestamp "
    "WHERE a.reg_type='holding' AND b.reg_type='holding' "
    "AND a.address=1327 AND b.address=1328 "
    "AND a.timestamp > '2026-03-18T03:29:22' "
    "AND a.timestamp < '2026-03-18T04:14:40' "
    "ORDER BY a.timestamp LIMIT 15")
for r in c.fetchall():
    print(f"  {r[0]}: HR[1327]={r[1]:5d} ({r[1]*0.1:.1f}) HR[1328]={r[2]:5d} ({r[2]*0.1:.1f})")

db.close()

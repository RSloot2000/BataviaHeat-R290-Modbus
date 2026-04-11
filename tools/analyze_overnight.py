"""Analyze overnight monitor database — deep dive into register behavior."""
import sqlite3
import json
from pathlib import Path
from collections import defaultdict

DB_PATH = Path(__file__).parent / "data" / "overnight_20260317_114908.db"

db = sqlite3.connect(str(DB_PATH))
db.row_factory = sqlite3.Row

# ── Basic stats ──────────────────────────────────────────────────────────────
print("=" * 80)
print("OVERNIGHT MONITOR ANALYSIS — 2h27m, 477 cycles, 531 registers")
print("=" * 80)

total = db.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
changes = db.execute("SELECT COUNT(*) FROM changes").fetchone()[0]
print(f"\nTotal readings: {total:,}")
print(f"Total changes:  {changes:,}")

# ── 1. Classify registers by behavior ────────────────────────────────────────
print("\n" + "=" * 80)
print("1. REGISTER CLASSIFICATION BY BEHAVIOR")
print("=" * 80)

rows = db.execute("""
    SELECT address, MIN(raw_value) as mn, MAX(raw_value) as mx,
           COUNT(DISTINCT raw_value) as nunique, COUNT(*) as nreads
    FROM readings WHERE reg_type = 'holding'
    GROUP BY address ORDER BY address
""").fetchall()

static_zero = []       # Always 0
static_nonzero = []    # Constant, non-zero
disconnected = []      # Always 0x8044/0x8042
slow_changing = []     # 2-10 unique values
fast_changing = []     # 11-100 unique
very_fast = []         # 100+ unique
signed_wrap = []       # Values near 0 AND near 65535 (signed negative)

for r in rows:
    addr, mn, mx, nu, nr = r['address'], r['mn'], r['mx'], r['nunique'], r['nreads']
    if nu == 1:
        if mn == 32836 or mn == 32834:
            disconnected.append(addr)
        elif mn == 0:
            static_zero.append(addr)
        else:
            static_nonzero.append((addr, mn))
    elif mn >= 65000 or (mn == 0 and mx >= 65000):
        signed_wrap.append((addr, mn, mx, nu))
    elif nu <= 10:
        slow_changing.append((addr, mn, mx, nu))
    elif nu <= 100:
        fast_changing.append((addr, mn, mx, nu))
    else:
        very_fast.append((addr, mn, mx, nu))

print(f"\nStatic zero (always 0):        {len(static_zero)} registers")
print(f"Disconnected (0x8044/0x8042):  {len(disconnected)} registers")
print(f"Static non-zero (constant):    {len(static_nonzero)} registers")
print(f"Signed/wrapping (near 65535):  {len(signed_wrap)} registers")
print(f"Slow-changing (2-10 unique):   {len(slow_changing)} registers")
print(f"Fast-changing (11-100 unique): {len(fast_changing)} registers")
print(f"Very fast (100+ unique):       {len(very_fast)} registers")

print(f"\n── Static non-zero (configuration/parameters) ──")
for addr, val in static_nonzero:
    # Try to decode if it looks like a temp (×10)
    note = ""
    if 50 <= val <= 900:
        note = f"  → {val/10:.1f}°C?"
    elif 1000 <= val <= 9999:
        note = f"  → {val} (RPM/Hz?)"
    print(f"  HR[{addr:>5}] = {val:>6} (0x{val:04X}){note}")

# ── 2. Signed registers analysis ────────────────────────────────────────────
print(f"\n── Signed/wrapping registers (values near 0 and 65535) ──")
print(f"  These are likely SIGNED int16 — values wrap around 0")
for addr, mn, mx, nu in signed_wrap:
    # Get actual distinct values to understand the range
    vals = [r[0] for r in db.execute(
        "SELECT DISTINCT raw_value FROM readings WHERE reg_type='holding' AND address=? ORDER BY raw_value",
        (addr,)).fetchall()]
    # Convert to signed
    signed_vals = [v - 65536 if v > 32767 else v for v in vals]
    signed_vals.sort()
    s_min, s_max = signed_vals[0], signed_vals[-1]
    print(f"  HR[{addr:>5}]: {nu:>3} unique, signed range [{s_min:>6} .. {s_max:>6}]  "
          f"(raw: {mn}..{mx})")

# ── 3. Energy accumulators ───────────────────────────────────────────────────
print(f"\n" + "=" * 80)
print("2. ENERGY ACCUMULATORS (monotonically increasing registers)")
print("=" * 80)

for addr in [163, 164, 165]:
    row = db.execute("""
        SELECT MIN(raw_value) as mn, MAX(raw_value) as mx, COUNT(*) as n
        FROM readings WHERE reg_type='holding' AND address=?
    """, (addr,)).fetchone()
    delta = row['mx'] - row['mn']
    rate_per_hour = delta / 2.45  # 2h27m ≈ 2.45h
    print(f"  HR[{addr}]: {row['mn']} → {row['mx']} (Δ={delta}, ~{rate_per_hour:.0f}/hr)")

# ── 4. Cross-correlation: find mirrors ───────────────────────────────────────
print(f"\n" + "=" * 80)
print("3. REGISTER MIRRORS — identical value sequences")
print("=" * 80)

# Get time-series for all dynamic registers
dynamic_addrs = [a for a, *_ in slow_changing + fast_changing + very_fast + signed_wrap]

# Build value vectors per register (values at each reading, ordered by time)
vectors = {}
for addr in dynamic_addrs:
    vals = [r[0] for r in db.execute("""
        SELECT raw_value FROM readings
        WHERE reg_type='holding' AND address=? AND source='active'
        ORDER BY timestamp
    """, (addr,)).fetchall()]
    if len(vals) >= 100:  # Need enough data points
        vectors[addr] = vals

# Find exact mirrors (identical sequences)
mirror_groups = []
seen = set()
addrs = sorted(vectors.keys())
for i, a1 in enumerate(addrs):
    if a1 in seen:
        continue
    group = [a1]
    for a2 in addrs[i+1:]:
        if a2 in seen:
            continue
        if vectors[a1] == vectors[a2]:
            group.append(a2)
            seen.add(a2)
    if len(group) > 1:
        mirror_groups.append(group)
        seen.add(a1)

print(f"\nFound {len(mirror_groups)} mirror groups (registers with identical time-series):")
for group in mirror_groups:
    print(f"  {' = '.join(f'HR[{a}]' for a in group)}")

# ── 5. Near-mirrors (same #unique, very similar ranges) ─────────────────────
print(f"\n" + "=" * 80)
print("4. NEAR-MIRRORS — same behavior but offset or different timing")
print("=" * 80)

# Compare register stats to find pairs with matching unique counts and similar ranges
all_changing = slow_changing + fast_changing + very_fast
stats = {}
for addr, mn, mx, nu in all_changing:
    stats[addr] = (mn, mx, nu)

# Find pairs with same #unique and similar range
near_mirrors = []
for i, (a1, mn1, mx1, nu1) in enumerate(all_changing):
    for a2, mn2, mx2, nu2 in all_changing[i+1:]:
        if abs(a2 - a1) < 5:  # Skip adjacent (likely same block)
            continue
        # Same unique count (±5%) and similar range
        if abs(nu1 - nu2) <= max(2, nu1 * 0.05):
            range1 = mx1 - mn1
            range2 = mx2 - mn2
            if range1 > 0 and range2 > 0 and 0.8 < range1/range2 < 1.25:
                near_mirrors.append((a1, a2, nu1, nu2, mn1, mx1, mn2, mx2))

# Deduplicate by showing only unique cross-block pairs
primary_block = set(range(0, 170))
param_block = set(range(770, 840))
secondary_1000 = set(range(1000, 1080))
secondary_1283 = set(range(1283, 1410))
shadow_3331 = set(range(3331, 3373))

def get_block(addr):
    if addr in primary_block: return "primary"
    if addr in param_block: return "param"
    if addr in secondary_1000: return "sec_1000"
    if addr in secondary_1283: return "sec_1283"
    if addr in shadow_3331: return "shadow_3331"
    return "other"

cross_block = [(a1, a2, nu1, nu2, mn1, mx1, mn2, mx2) 
               for a1, a2, nu1, nu2, mn1, mx1, mn2, mx2 in near_mirrors 
               if get_block(a1) != get_block(a2)]

print(f"\nCross-block near-mirrors (similar behavior, different blocks):")
shown = set()
for a1, a2, nu1, nu2, mn1, mx1, mn2, mx2 in sorted(cross_block):
    key = (min(a1,a2), max(a1,a2))
    if key in shown:
        continue
    shown.add(key)
    b1, b2 = get_block(a1), get_block(a2)
    print(f"  HR[{a1:>5}] ({b1:<12}) ↔ HR[{a2:>5}] ({b2:<12}) "
          f"  unique: {nu1:>3}/{nu2:>3}  range: [{mn1}-{mx1}] / [{mn2}-{mx2}]")

# ── 6. State transitions ────────────────────────────────────────────────────
print(f"\n" + "=" * 80)
print("5. STATE TRANSITIONS — registers with few discrete values")
print("=" * 80)

for addr, mn, mx, nu in sorted(slow_changing):
    vals = [r[0] for r in db.execute(
        "SELECT DISTINCT raw_value FROM readings WHERE reg_type='holding' AND address=? ORDER BY raw_value",
        (addr,)).fetchall()]
    if nu <= 10:
        # Count transitions
        n_trans = db.execute(
            "SELECT COUNT(*) FROM changes WHERE reg_type='holding' AND address=?",
            (addr,)).fetchone()[0]
        vals_str = ", ".join(str(v) for v in vals)
        print(f"  HR[{addr:>5}]: {nu} states [{vals_str}]  ({n_trans} transitions)")

# ── 7. Compressor cycle detection ────────────────────────────────────────────
print(f"\n" + "=" * 80)
print("6. COMPRESSOR CYCLE DETECTION")
print("=" * 80)

# HR[1283] operational_status_mirror: 0/1 — this is the compressor on/off
status_changes = db.execute("""
    SELECT timestamp, old_value, new_value 
    FROM changes WHERE reg_type='holding' AND address=1283
    ORDER BY timestamp
""").fetchall()

print(f"\nHR[1283] (operational_status_mirror) transitions: {len(status_changes)}")
for ts, old, new in status_changes[:20]:
    state = "ON" if new == 1 else "OFF"
    print(f"  {ts}: {old} → {new} ({state})")
if len(status_changes) > 20:
    print(f"  ... {len(status_changes) - 20} more transitions")

# ── 8. Evaporator target analysis ────────────────────────────────────────────
print(f"\n── HR[1319] evaporator_target_temp: step pattern analysis ──")
evap_changes = db.execute("""
    SELECT timestamp, old_value, new_value
    FROM changes WHERE reg_type='holding' AND address=1319
    ORDER BY timestamp
""").fetchall()
for ts, old, new in evap_changes[:20]:
    print(f"  {ts}: {old/10:.1f}°C → {new/10:.1f}°C")

# ── 9. HR[1289] analysis (unusual jumps: 1696→7835) ─────────────────────────
print(f"\n── HR[1289] unusual jumping register ──")
r1289_changes = db.execute("""
    SELECT timestamp, old_value, new_value
    FROM changes WHERE reg_type='holding' AND address=1289
    ORDER BY timestamp
""").fetchall()
for ts, old, new in r1289_changes:
    print(f"  {ts}: {old} → {new}  (Δ={new-old})")

# ── 10. Temperature register mapping ────────────────────────────────────────
print(f"\n" + "=" * 80)
print("7. TEMPERATURE REGISTER CANDIDATES (ranges plausible for ×10 temps)")
print("=" * 80)

for r in rows:
    addr, mn, mx, nu = r['address'], r['mn'], r['mx'], r['nunique']
    if nu == 1:
        continue
    # Temperature range for ×10: roughly -40°C to 120°C → -400 to 1200
    # Also check signed: 65136 (-40) to 1200
    if (0 <= mn <= 1200 and 0 <= mx <= 1200 and mx - mn >= 20) or \
       (mn >= 64536 and mx <= 1200):
        t_min = (mn - 65536 if mn > 32767 else mn) / 10
        t_max = (mx - 65536 if mx > 32767 else mx) / 10
        print(f"  HR[{addr:>5}]: {t_min:>6.1f}°C .. {t_max:>6.1f}°C  ({nu} unique)")

# ── 11. Pressure register candidates ────────────────────────────────────────
print(f"\n" + "=" * 80)
print("8. PRESSURE REGISTER CANDIDATES")
print("=" * 80)

for r in rows:
    addr, mn, mx, nu = r['address'], r['mn'], r['mx'], r['nunique']
    if nu < 5:
        continue
    # kPa range for R290: ~400-2500 kPa (4-25 bar)
    if 300 <= mn <= 600 and 400 <= mx <= 2600:
        print(f"  HR[{addr:>5}]: {mn:>5} .. {mx:>5} kPa?  ({nu} unique) "
              f"  [{mn/100:.1f} .. {mx/100:.1f} bar]")
    # Or raw with ×10: 40..250 → 4.0..25.0 bar
    if 30 <= mn <= 100 and 50 <= mx <= 300 and mx - mn >= 20:
        print(f"  HR[{addr:>5}]: {mn/10:.1f} .. {mx/10:.1f} bar?  ({nu} unique)")

# ── 12. RPM / frequency candidates ──────────────────────────────────────────
print(f"\n" + "=" * 80)
print("9. RPM/FREQUENCY CANDIDATES (range ~1000-8000)")
print("=" * 80)

for r in rows:
    addr, mn, mx, nu = r['address'], r['mn'], r['mx'], r['nunique']
    if nu < 10:
        continue
    if 1000 <= mn <= 4000 and 2000 <= mx <= 8000:
        print(f"  HR[{addr:>5}]: {mn:>5} .. {mx:>5}  ({nu} unique)")

# ── 13. Block 6400-6511 decode ───────────────────────────────────────────────
print(f"\n" + "=" * 80)
print("10. BLOCK HR[6400-6511] DECODE — tablet configuration")
print("=" * 80)

for addr in range(6400, 6512):
    row = db.execute("""
        SELECT MIN(raw_value) as mn, MAX(raw_value) as mx, COUNT(DISTINCT raw_value) as nu
        FROM readings WHERE reg_type='holding' AND address=?
    """, (addr,)).fetchone()
    if row and row['mn'] is not None:
        val = row['mn']
        note = ""
        if val == 65531:
            note = " (signed: -5)"
        elif val == 65476:
            note = " (signed: -60)"
        elif 50 <= val <= 900 and val != 0:
            note = f" (temp? {val/10:.1f}°C)"
        elif val == 999:
            note = " (sentinel/disabled?)"
        static = "" if row['nu'] > 1 else "static"
        if val != 0 or row['nu'] > 1:
            print(f"  HR[{addr}] = {val:>6}{note}  {static}")

# ── 14. Block 3331-3372 mapping ──────────────────────────────────────────────
print(f"\n" + "=" * 80)
print("11. BLOCK HR[3331-3372] — shadow of what?")
print("=" * 80)

# Compare HR[3331-3372] values with known registers
shadow_vals = {}
for addr in range(3331, 3373):
    row = db.execute("""
        SELECT MIN(raw_value) as mn, MAX(raw_value) as mx, COUNT(DISTINCT raw_value) as nu
        FROM readings WHERE reg_type='holding' AND address=?
    """, (addr,)).fetchone()
    if row and row['mn'] is not None:
        shadow_vals[addr] = (row['mn'], row['mx'], row['nu'])

# Cross-reference with known blocks
print("\nShadow     → Best match from primary/secondary blocks:")
for saddr in sorted(shadow_vals):
    smn, smx, snu = shadow_vals[saddr]
    if snu == 1 and smn == 32836:
        print(f"  HR[{saddr}] = 0x8044 (disconnected)")
        continue
    if snu == 1 and smn == 0:
        continue
    # Find matching register in other blocks
    best_match = None
    best_score = 0
    for r in rows:
        maddr = r['address']
        if 3331 <= maddr <= 3372:
            continue  # Skip self
        mmn, mmx, mnu = r['mn'], r['mx'], r['nunique']
        if mnu == snu and mmn == smn and mmx == smx:
            best_match = maddr
            best_score = 100
            break
        elif abs(mnu - snu) <= max(1, snu * 0.1) and snu > 1:
            if mmn == smn or mmx == smx:
                score = 80
                if score > best_score:
                    best_score = score
                    best_match = maddr
    if best_match:
        print(f"  HR[{saddr}] ({smn}-{smx}, {snu}u) → HR[{best_match}] (score={best_score}%)")
    elif snu > 1:
        print(f"  HR[{saddr}] ({smn}-{smx}, {snu}u) → NO MATCH")
    else:
        print(f"  HR[{saddr}] = {smn} (static)")

db.close()
print(f"\n{'=' * 80}")
print("ANALYSIS COMPLETE")
print("=" * 80)

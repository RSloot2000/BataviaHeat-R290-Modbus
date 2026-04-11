"""Show latest energy register values from the running scan DB."""
import sqlite3, glob, os, time, sys

# Find the newest DB in data/
dbs = sorted(glob.glob('data/overnight_202603*.db'), key=os.path.getmtime)
if not dbs:
    print("Geen database gevonden!")
    sys.exit(1)

dbfile = dbs[-1]
print(f"Database: {dbfile}")
print(f"{'='*72}")

# Energy registers we want to check against tablet
energy_regs = {
    41:   ("Compressor vermogen (W)",       1,   "W"),
    163:  ("Energieteller 1",               1,   "Wh"),
    164:  ("Energieteller 2",               1,   "Wh"),
    165:  ("Energieteller 3",               1,   "Wh"),
    1283: ("Compressor aan/uit",            1,   ""),
    1322: ("Comp output stroom (→T33)",     0.1, "A"),
    1325: ("Inverter input stroom (→T38)",  0.1, "A"),
    1335: ("Comp output spanning (→T35)",   0.1, "V"),
    1338: ("Netspanning AC (mains)",        0.1, "V"),
    1365: ("Mirror HR[1322] (→T33)",        0.1, "A"),
    1368: ("DC bus / comp speed (→T36)",    0.1, "V"),
    1370: ("Mirror HR[1325] (→T38)",        0.1, "A"),
    1327: ("Comp koppel? (→T34)",           0.1, "%"),
    1328: ("Koppel target?",                0.1, "%"),
    1289: ("Comp speed (×0.1 rps) (→T29)",  0.1, "rps"),
    1304: ("Variabel (→T32? target speed)", 0.1, ""),
    1348: ("Temperatuur? (→T30 module)",    0.1, "°C"),
    1371: ("Onbekend (13-42)",              0.1, ""),
}

while True:
    db = sqlite3.connect(f'file:{dbfile}?mode=ro', uri=True)
    c = db.cursor()
    
    c.execute("SELECT COUNT(*) FROM readings")
    total = c.fetchone()[0]
    
    c.execute("SELECT MAX(timestamp) FROM readings")
    last_ts = c.fetchone()[0]
    
    os.system('cls' if os.name == 'nt' else 'clear')
    print(f"Database: {dbfile}  |  {total} readings  |  Laatste: {last_ts}")
    print(f"{'='*72}")
    print(f"{'Register':>8s}  {'Waarde':>8s}  {'Scaled':>10s}  {'Beschrijving'}")
    print(f"{'-'*8:>8s}  {'-'*8:>8s}  {'-'*10:>10s}  {'-'*40}")
    
    for addr in sorted(energy_regs.keys()):
        label, scale, unit = energy_regs[addr]
        c.execute(
            "SELECT raw_value FROM readings WHERE reg_type='holding' AND address=? "
            "ORDER BY timestamp DESC LIMIT 1", (addr,))
        row = c.fetchone()
        if row:
            raw = row[0]
            if raw == 32836:  # 0x8044 = niet beschikbaar
                scaled_str = "N/A"
            else:
                scaled = raw * scale
                if scale == 1:
                    scaled_str = f"{scaled:.0f} {unit}"
                else:
                    scaled_str = f"{scaled:.1f} {unit}"
            print(f"HR[{addr:4d}]  {raw:8d}  {scaled_str:>10s}  {label}")
        else:
            print(f"HR[{addr:4d}]  {'---':>8s}  {'---':>10s}  {label} (niet gepolld)")
    
    db.close()
    
    print(f"\n{'='*72}")
    print("Vergelijk bovenstaande waarden met de tablet T-serie parameters:")
    print("  T29 = Compressor running speed (rps)  → HR[1289]")
    print("  T33 = Compressor current output (A)    → HR[1322]")
    print("  T34 = Compressor torque output (%)     → HR[1327]")
    print("  T35 = Compressor voltage output (V)    → HR[1335]")
    print("  T36 = Compressor bus voltage (V)       → HR[1368]")
    print("  T38 = Inverter current input (A)       → HR[1325]")
    print(f"\nDruk Ctrl+C om te stoppen. Verversing elke 10s...")
    
    try:
        time.sleep(10)
    except KeyboardInterrupt:
        print("\nGestopt.")
        break

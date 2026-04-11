"""
BataviaHeat R290 3-8kW Modbus Register Map

Discovered via modbus_scanner.py and scan_extended.py on 2026-03-15.
Cross-referenced with the BataviaHeat app (Statusquery / Modulestatus / Parameters).
Validated across four monitoring sessions:
  1) 9-hour combined active+passive (2026-03-15/16) — bus collisions from display
  2) 9.4-hour targeted (2026-03-16/17) — 851,978 readings, 67,792 changes
  3) 2h27m clean-bus scan (2026-03-17, display disconnected):
     - 477 cycles, 253,564 readings, 19,237 changes, 0 passive frames
     - 531 registers polled (HR only), 120 dynamic, 411 static
     - 1 compressor ON→OFF cycle captured with full shutdown profile
  4) 19h49m clean-bus scan (2026-03-17/18, post-optimization, display disconnected):
     - 2494 cycles, 3,085,078 readings, 67,614 changes
     - 1237 registers polled, M02=50→35, M11=0→17, P01=0→1
     - Weather curve ACTIVE: HR[816] dynamic 28-29°C (was static 50°C)
     - 6 compressor cycles, 19% duty cycle, avg 38 min run time
     - Energy: 224W average (was 1430W), pump OFF 76.8% of time

Connection: COM5, 9600 baud, 8N1, slave ID 1

IMPORTANT — HR = IR identity confirmed:
  On clean bus (display disconnected), holding registers (FC03) and input registers
  (FC04) return IDENTICAL values for all addresses. Only FC03 polling is needed.
  INPUT_REGISTERS below are kept for reference but are redundant.

Confirmed register address blocks (clean full scan HR/IR[0-2000] + tablet probe 2026-03-17):
  Block A: HR[0-165]    (primary config + sensors + energy accumulators)
  Block B: HR[256-269]  (firmware ASCII, internal PCB)
  Block C: HR[512-527]  (unknown, sometimes slow to respond)
  Block D: HR[770-839]  (system params, discharge temp, RPM limits)
  Block E: HR[1000-1079] (secondary sensor block, mirrors of primary)
  Block F: HR[1283-1409] (compressor live operational data)
  Shadow:  HR[3331-3372] (shadow of live data for tablet display)
  FW_Ext:  HR[4000-4015] (external PCB firmware ASCII)
  Config:  HR[6400-7471] (tablet configuration, setpoints, weather curves)
  History: HR[21500-21913] (daily energy history, paged)
  + 37 disconnected-sensor markers (0x8044) scattered throughout
  + Coil[8]: tablet heartbeat/watchdog (FC05)

Register mirroring architecture (triple-mirror):
  Many sensor values exist in three parallel copies:
    primary (HR[0-165]) = sec_1000 (HR[1000-1079]) = sec_1283 (HR[1283-1409])
  8 exact mirror groups confirmed with 100% match across 477 cycles.
  Only the primary block needs to be read for the HACS integration.

Notes:
  - All temperatures use scale ×0.1 (raw 500 = 50.0°C) unless noted
  - Energy history uses ×0.1 kWh, COP uses ×1%
  - Disconnected sensors return 0x8042 (32834) or 0x8044 (32836)
  - Overnight monitoring proved HR[72-76], HR[187-189] are NOT maintained
    by the heat pump — they are WRITTEN by the tablet app. Always 0 on clean bus.
  - ASCII strings use big-endian byte order (hi byte = first char, lo byte = second)
  - Confidence levels: CONFIRMED (matched with app + overnight), LIKELY (strong
    pattern/correlation), TENTATIVE (needs verification), DISPROVEN (contradicted)

Tablet emulator session (2026-03-17, 120s, display disconnected from heat pump):
  - Tablet is purely a Modbus MASTER (no slave ID, confirmed by probe)
  - Polls slave ID 1, FC03 only, 28 register blocks, ~21s cycle
  - Writes: FC06 HR[5010] (room temp), FC06 HR[6400] (mode), FC05 Coil[8] (heartbeat),
    FC06 HR[21500] (history page trigger)
  - Total: 1309 registers polled per cycle

Firmware strings (from controller tablet):
  - Internal PCB: X1.HL087A.K05.503-1.V100B25  → found at HR[260-269]
  - External PCB: X1.HL081B.K05.001-1.V100A03   → found at HR[4000-4013] (big-endian)
  - Driver board:  X1.VF281A.K51.V100A5           → NOT on slave ID 1
  - Hardware:      1GDNET60102KM070_WO11_4C        → NOT on slave ID 1
  - Software:      NET-DK-L1011-O-V1.6.5           → NOT on slave ID 1
"""

DEFAULT_SLAVE_ID = 1

# Special values
SENSOR_DISCONNECTED_1 = 32834  # 0x8042 - sensor not connected
SENSOR_DISCONNECTED_2 = 32836  # 0x8044 - sensor not connected

# === HOLDING REGISTERS (FC03/FC06/FC16) ===
# Since HR=IR is proven, this is the single authoritative register map.
# Registers are grouped by function and sorted by address within each group.

HOLDING_REGISTERS: dict[int, dict] = {

    # ═══════════════════════════════════════════════════════════════════════
    # PRIMARY BLOCK A: HR[0-165] — Config, Sensors, Energy
    # ═══════════════════════════════════════════════════════════════════════

    # ─── Operating Mode / Configuration (HR[0-4]) ───
    0: {
        "name": "control_switches_bitfield",
        "unit": None,
        "scale": 1,
        "description": "Control switches bitfield (NOT operating mode — see HR[6400]). "
                       "Clean-bus: static 90. Mosibi docs: bit-packed on/off switches. "
                       "The real operating mode is HR[6400] (tablet writes 2=heating).",
        "confidence": "TENTATIVE",
    },
    1: {
        "name": "water_outlet_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "Water outlet temperature. Clean-bus: 0-33.6°C range, 195 unique. "
                       "Mirrors HR[776], HR[1301]. Goes to 0 when compressor off. "
                       "Previously misidentified as 'silent_mode'.",
        "confidence": "CONFIRMED",
    },
    3: {
        "name": "water_outlet_temp_alt",
        "unit": "°C",
        "scale": 0.1,
        "description": "Water outlet temp (alternative). Clean-bus: 11.7-33.6°C range. "
                       "Retains last value when compressor off (never goes to 0).",
        "confidence": "LIKELY",
    },
    4: {
        "name": "heating_target_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "Heating target temperature. App: 'Doeltemperatuur verwarming: 50°C' → raw 500. "
                       "Clean-bus scan 3: static 500 (M11=0). "
                       "Clean-bus scan 4 (M11=17, weather curve active): dynamic 280-290 = 28.0-29.0°C. "
                       "Mirrors HR[816], HR[772].",
        "writable": True,
        "min": 200,
        "max": 600,
        "confidence": "CONFIRMED",
    },
    5: {
        "name": "buffer_tank_lower_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "Buffer tank lower temperature. App: 'buffertank onderste: 51.7°C'. "
                       "Clean-bus: static 385 = 38.5°C (setpoint, not live sensor?).",
        "confidence": "CONFIRMED",
    },

    # ─── System Water Temps (HR[8-12]) ───
    8: {
        "name": "system_water_temp_1",
        "unit": "°C",
        "scale": 0.1,
        "description": "System water temperature 1. Scan: 33.6°C. "
                       "Clean-bus: static 0 — likely tablet-written.",
        "confidence": "TENTATIVE",
    },
    9: {
        "name": "system_water_temp_2",
        "unit": "°C",
        "scale": 0.1,
        "description": "System water temperature 2. Scan: 33.6°C. "
                       "Clean-bus: static 0 — likely tablet-written.",
        "confidence": "TENTATIVE",
    },
    11: {
        "name": "high_pressure_raw",
        "unit": "kPa",
        "scale": 0.1,
        "description": "High side pressure raw (kPa scale). "
                       "Clean-bus: range 386.7-561.6 (3867-5616). Top changer in overnight2.",
        "confidence": "LIKELY",
    },
    12: {
        "name": "low_pressure_raw",
        "unit": "kPa",
        "scale": 0.1,
        "description": "Low side pressure raw (kPa scale). "
                       "Clean-bus: range 400.8-561.6 (4008-5616). Top changer in overnight2.",
        "confidence": "LIKELY",
    },

    # ─── Primary Sensor Block (HR[16-42]) ───
    # These are the PRIMARY live sensor readings from the outdoor unit.
    # They are mirrored in secondary blocks HR[1000-1079] and HR[1283-1409].
    16: {
        "name": "compressor_metric_16",
        "unit": None,
        "scale": 0.1,
        "description": "Compressor-related metric. Clean-bus: 0-548.5 range. "
                       "Only active when compressor running.",
        "confidence": "TENTATIVE",
    },
    19: {
        "name": "high_pressure_kpa",
        "unit": "kPa",
        "scale": 1,
        "description": "High side pressure (kPa, R290). Clean-bus: 1583-2203. "
                       "Mirrors HR[129].",
        "confidence": "LIKELY",
    },
    20: {
        "name": "low_pressure_kpa",
        "unit": "kPa",
        "scale": 1,
        "description": "Low side pressure (kPa, R290). Clean-bus: 2987-4093. "
                       "Mirrors HR[130].",
        "confidence": "LIKELY",
    },
    22: {
        "name": "ambient_temperature",
        "unit": "°C",
        "scale": 0.1,
        "description": "Outdoor ambient temperature. Clean-bus: 11.5-19.7°C, 74 unique. "
                       "Mirrors HR[1351], HR[3350]. App: '0#Omgevingstemp.: 14.10°C'.",
        "confidence": "CONFIRMED",
    },
    23: {
        "name": "fin_coil_temperature",
        "unit": "°C",
        "scale": 0.1,
        "description": "Fin/coil (evaporator) temperature. Clean-bus: 4.0-19.3°C. "
                       "Mirrors HR[1303]. App: '0#Vinnen temp'.",
        "confidence": "CONFIRMED",
    },
    24: {
        "name": "suction_temperature",
        "unit": "°C",
        "scale": 0.1,
        "description": "Compressor suction temperature. Clean-bus: 4.5-29.0°C. "
                       "Mirrors HR[1305]. App: '0#Zuigtemp'.",
        "confidence": "CONFIRMED",
    },
    25: {
        "name": "discharge_pressure_or_temp",
        "unit": None,
        "scale": 0.1,
        "description": "Discharge pressure or temp metric. Clean-bus: 43.8-94.0 (×0.1). "
                       "Mirrors HR[1304]. Very active: 541+ unique values.",
        "confidence": "LIKELY",
    },
    31: {
        "name": "signed_metric_31",
        "unit": None,
        "scale": 0.1,
        "description": "Signed int16. Clean-bus: steady -33.2 to -32.8. "
                       "Possibly calibration offset.",
        "signed": True,
        "confidence": "TENTATIVE",
    },
    32: {
        "name": "low_pressure",
        "unit": "bar",
        "scale": 0.1,
        "description": "Low pressure. App: '0#Lage drukwaarde: 7.30 bar'. "
                       "Clean-bus: 4.0-8.1 bar. Mirrors HR[1310].",
        "confidence": "CONFIRMED",
    },
    33: {
        "name": "high_pressure",
        "unit": "bar",
        "scale": 0.1,
        "description": "High pressure. App: '0#Hoge drukwaarde: 7.20 bar'. "
                       "Clean-bus: 7.5-25.0 bar. Mirrors HR[1311].",
        "confidence": "CONFIRMED",
    },
    35: {
        "name": "superheat_or_subcool_35",
        "unit": "°C",
        "scale": 0.1,
        "description": "Superheat or subcooling. Clean-bus: 1.8-23.4°C. "
                       "Mirrors HR[1308].",
        "confidence": "LIKELY",
    },
    36: {
        "name": "discharge_temperature",
        "unit": "°C",
        "scale": 0.1,
        "description": "Compressor discharge temperature. Clean-bus: 20.5-70.3°C. "
                       "Mirrors HR[1309], HR[773]. App: '0#Uitlaattemp'.",
        "confidence": "CONFIRMED",
    },
    38: {
        "name": "evaporator_target_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "Evaporator target temperature. Discrete steps: 0,30,36,42,46,48,50,70°C. "
                       "Mirrors HR[125], HR[1034], HR[1319]/HR[1361]. "
                       "Shutdown profile: 70→50→48→44→39→33→30→0°C.",
        "confidence": "CONFIRMED",
    },
    39: {
        "name": "condenser_target_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "Condenser/water target temperature. Clean-bus: 0-70.3°C. "
                       "Mirrors HR[126], HR[1045], HR[1320]/HR[1372].",
        "confidence": "CONFIRMED",
    },
    40: {
        "name": "plate_hx_inlet_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "Plate heat exchanger inlet temperature. Clean-bus: 24.9-36.3°C. "
                       "Mirrors HR[1035], HR[1323]/HR[1362]. 100% exact mirror confirmed.",
        "confidence": "CONFIRMED",
    },
    41: {
        "name": "compressor_power",
        "unit": None,
        "scale": 1,
        "description": "Compressor power/speed metric. Clean-bus: 0-1914. "
                       "Mirrors HR[1040], HR[1321]/HR[1367]. 0 = compressor off.",
        "confidence": "CONFIRMED",
    },
    42: {
        "name": "superheat",
        "unit": "°C",
        "scale": 0.1,
        "description": "Superheat. Clean-bus: 0-11.1°C. "
                       "Mirrors HR[1038], HR[1322]/HR[1365]. 100% exact mirror confirmed.",
        "confidence": "CONFIRMED",
    },
    43: {
        "name": "compressor_max_frequency",
        "unit": "rpm",
        "scale": 1,
        "description": "Compressor max frequency/speed limit. Static 7000.",
        "confidence": "LIKELY",
    },

    # ─── Pump / Flow (HR[53-54]) ───
    53: {
        "name": "pump_target_speed",
        "unit": "rpm",
        "scale": 1,
        "description": "Pump target speed. Static 6800. "
                       "Matches HR[811], HR[1352]. App: 'Doelsnelheid omvormerwaterpomp: 6800rpm'.",
        "confidence": "CONFIRMED",
    },
    54: {
        "name": "pump_flow_rate",
        "unit": "L/h",
        "scale": 1,
        "description": "Pump flow rate. Clean-bus: 2021-2079 L/h. "
                       "Mirrors HR[1353]. App: 'stroomsnelheid: 2053L/H'.",
        "confidence": "CONFIRMED",
    },

    # ─── Signed PID Registers (HR[56-69]) ───
    # Signed int16 values near zero — likely PID controller error/integral terms.
    56: {
        "name": "pid_error_1",
        "unit": None,
        "scale": 0.1,
        "description": "Signed PID error/integral term. Clean-bus: -6.3 to +0.4.",
        "signed": True,
        "confidence": "LIKELY",
    },
    60: {
        "name": "pid_error_2",
        "unit": None,
        "scale": 0.1,
        "description": "Signed PID error/integral term. Clean-bus: similar to HR[56].",
        "signed": True,
        "confidence": "LIKELY",
    },
    64: {
        "name": "pid_error_3",
        "unit": None,
        "scale": 0.1,
        "description": "Signed PID error/integral term. Clean-bus: -2.6 to 0.",
        "signed": True,
        "confidence": "LIKELY",
    },
    69: {
        "name": "pid_error_4",
        "unit": None,
        "scale": 0.1,
        "description": "Signed PID error/integral term. Clean-bus: -2.6 to 0.",
        "signed": True,
        "confidence": "LIKELY",
    },

    # ─── Floor Heating / Disconnected Sensors (HR[71]) ───
    71: {
        "name": "floor_heating_inlet_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "Floor heating water inlet temp. 0x8044 = disconnected sensor. "
                       "App: 'Waterinlaattemp. vloerverwarming: -3270.00'.",
        "confidence": "CONFIRMED",
    },

    # ─── DISPROVEN Tablet-Written Registers (HR[72-76]) ───
    # These only have values when the tablet app is actively writing them.
    # On clean bus (display disconnected) they are always 0.
    72: {
        "name": "tablet_written_72",
        "unit": None,
        "scale": 1,
        "description": "DISPROVEN as temperature. Tablet-written only. Clean-bus: always 0.",
        "confidence": "DISPROVEN",
    },
    73: {
        "name": "tablet_written_73",
        "unit": None,
        "scale": 1,
        "description": "DISPROVEN as solar boiler temp. Tablet-written only. Clean-bus: always 0.",
        "confidence": "DISPROVEN",
    },
    74: {
        "name": "tablet_written_74",
        "unit": None,
        "scale": 1,
        "description": "DISPROVEN as buffer tank upper. Tablet-written only. Clean-bus: always 0.",
        "confidence": "DISPROVEN",
    },
    75: {
        "name": "tablet_written_75",
        "unit": None,
        "scale": 1,
        "description": "DISPROVEN as buffer tank lower 2. Tablet-written only. Clean-bus: always 0.",
        "confidence": "DISPROVEN",
    },
    76: {
        "name": "tablet_written_76",
        "unit": None,
        "scale": 1,
        "description": "DISPROVEN as total water outlet. Tablet-written only. Clean-bus: always 0.",
        "confidence": "DISPROVEN",
    },

    # ─── Subcooling / Superheat (HR[77-78]) ───
    77: {
        "name": "subcooling",
        "unit": "°C",
        "scale": 0.1,
        "description": "Subcooling. Clean-bus: 0-5.6°C. Mirrors HR[783].",
        "confidence": "LIKELY",
    },
    78: {
        "name": "suction_superheat",
        "unit": "°C",
        "scale": 0.1,
        "description": "Suction superheat. Clean-bus: 0-45.0°C. Mirrors HR[785].",
        "confidence": "LIKELY",
    },

    # ─── Setpoints / Parameters (HR[94-103]) ───
    94: {
        "name": "cooling_target_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "Cooling target temperature. App: 'Koeldoeltemp: 10°C'. "
                       "Clean-bus: static 1000 — likely max/disabled sentinel.",
        "writable": True,
        "confidence": "TENTATIVE",
    },
    95: {
        "name": "heating_target_temp_zone_b",
        "unit": "°C",
        "scale": 0.1,
        "description": "Zone B heating target. App: 'Zone_B: 30°C' → raw 300. "
                       "Clean-bus: static 300.",
        "writable": True,
        "min": 200,
        "max": 600,
        "confidence": "CONFIRMED",
    },
    103: {
        "name": "dhw_max_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "DHW max temperature limit. Raw 666 = 66.6°C. Static.",
        "writable": True,
        "confidence": "TENTATIVE",
    },

    # ─── Evaporator/Condenser Target Mirrors (HR[125-130]) ───
    125: {
        "name": "evaporator_target_mirror",
        "unit": "°C",
        "scale": 0.1,
        "description": "Evaporator target mirror (= HR[38]). 100% match across 477 cycles.",
        "confidence": "CONFIRMED",
    },
    126: {
        "name": "condenser_target_mirror",
        "unit": "°C",
        "scale": 0.1,
        "description": "Condenser target mirror (= HR[39]). 100% match across 477 cycles.",
        "confidence": "CONFIRMED",
    },
    129: {
        "name": "pressure_or_rpm_129",
        "unit": "kPa",
        "scale": 1,
        "description": "Pressure or RPM metric. Clean-bus: 1627-2492. "
                       "Mirrors HR[19]. Active only when compressor running.",
        "confidence": "TENTATIVE",
    },
    130: {
        "name": "pressure_or_rpm_130",
        "unit": "kPa",
        "scale": 1,
        "description": "Pressure or RPM metric. Clean-bus: 1606-2503. "
                       "Mirrors HR[20]. Active only when compressor running.",
        "confidence": "TENTATIVE",
    },

    # ─── Pump Feedback (HR[147]) ───
    147: {
        "name": "pump_feedback",
        "unit": "%",
        "scale": 0.1,
        "description": "Pump feedback signal. Clean-bus: 31.4-32.3%. "
                       "Mirrors HR[1355]. App: 'Feedbacksignaal: 31.90%%'.",
        "confidence": "CONFIRMED",
    },

    # ─── Energy Accumulators (HR[163-165]) ───
    # All three grow at ~1435/hr. Likely Wh counters.
    163: {
        "name": "energy_accumulator_1",
        "unit": "Wh",
        "scale": 1,
        "description": "Energy counter 1. Clean-bus: 18434→21946 (Δ3512 in 2h27m, ~1433/hr). "
                       "Continuously growing. Likely heating energy.",
        "confidence": "CONFIRMED",
    },
    164: {
        "name": "energy_accumulator_2",
        "unit": "Wh",
        "scale": 1,
        "description": "Energy counter 2. Clean-bus: 18449→21964 (Δ3515, ~1435/hr). "
                       "Same rate as HR[163]. Possibly cooling or DHW energy.",
        "confidence": "CONFIRMED",
    },
    165: {
        "name": "energy_accumulator_3",
        "unit": "Wh",
        "scale": 1,
        "description": "Energy counter 3. Clean-bus: 18227→21751 (Δ3524, ~1438/hr). "
                       "Same rate as HR[163-164]. Possibly total energy.",
        "confidence": "CONFIRMED",
    },

    # ─── DISPROVEN Tablet-Written Registers (HR[187-189]) ───
    187: {
        "name": "tablet_written_room_temp",
        "unit": None,
        "scale": 1,
        "description": "DISPROVEN as room temp. Always 0 on clean bus. "
                       "Real room temp written by tablet to HR[5010].",
        "confidence": "DISPROVEN",
    },
    188: {
        "name": "tablet_written_dhw_temp",
        "unit": None,
        "scale": 1,
        "description": "DISPROVEN as DHW tank temp. Always 0 on clean bus.",
        "confidence": "DISPROVEN",
    },
    189: {
        "name": "tablet_written_ambient",
        "unit": None,
        "scale": 1,
        "description": "DISPROVEN as ambient temp. Always 0 on clean bus. "
                       "Real outdoor temp is HR[22].",
        "confidence": "DISPROVEN",
    },

    # ═══════════════════════════════════════════════════════════════════════
    # BLOCK B: HR[256-269] — Firmware ASCII
    # ═══════════════════════════════════════════════════════════════════════

    260: {
        "name": "internal_pcb_version_ascii",
        "description": "Internal PCB version ASCII (HR[260-269], swapped byte order). "
                       "Decodes to tail of 'X1.HL087A.K05.503-1.V100B25'.",
        "confidence": "CONFIRMED",
    },

    # ═══════════════════════════════════════════════════════════════════════
    # BLOCK C: HR[770-839] — System Configuration + Operational
    # ═══════════════════════════════════════════════════════════════════════

    768: {
        "name": "operational_status",
        "unit": None,
        "scale": 1,
        "description": "Operating status. Values: 0=standby, 1=starting, 4=running. "
                       "Top changer in overnight2 (3979 changes). "
                       "Mirrored in HR[1283], HR[3331].",
        "confidence": "CONFIRMED",
    },
    769: {
        "name": "operational_sub_status",
        "unit": None,
        "scale": 1,
        "description": "Operational sub-status. 0-246 range, 10 unique values. "
                       "Changes with HR[768].",
        "confidence": "LIKELY",
    },
    773: {
        "name": "compressor_discharge_temp_param",
        "unit": "°C",
        "scale": 0.1,
        "description": "Compressor discharge temp (param block). "
                       "Clean-bus: 41.6-56.2°C. Mirrors HR[36]/HR[1309]. "
                       "Mirrors HR[3355-3356] in shadow block.",
        "confidence": "CONFIRMED",
    },
    776: {
        "name": "water_outlet_temp_live",
        "unit": "°C",
        "scale": 0.1,
        "description": "Water outlet temperature (param block). "
                       "Clean-bus: 0-33.6°C. Mirrors HR[1]/HR[1301]. "
                       "Goes to 0 when compressor off.",
        "confidence": "CONFIRMED",
    },
    777: {
        "name": "compressor_metric_777",
        "unit": None,
        "scale": 1,
        "description": "Compressor metric. 0-16439 range. "
                       "Value 16439 appears in multiple registers (special code).",
        "confidence": "TENTATIVE",
    },
    783: {
        "name": "subcooling_param",
        "unit": "°C",
        "scale": 0.1,
        "description": "Subcooling (param block). Mirrors HR[77]. "
                       "Clean-bus: 0-5.6°C.",
        "confidence": "LIKELY",
    },
    785: {
        "name": "suction_superheat_param",
        "unit": "°C",
        "scale": 0.1,
        "description": "Suction superheat (param block). Mirrors HR[78]. "
                       "Clean-bus: 0-45.0°C.",
        "confidence": "LIKELY",
    },
    811: {
        "name": "pump_max_speed",
        "unit": "rpm",
        "scale": 1,
        "description": "Pump maximum speed setting. Static 6800. Matches HR[53]/HR[1352].",
        "confidence": "CONFIRMED",
    },
    812: {
        "name": "pump_min_speed",
        "unit": "rpm",
        "scale": 1,
        "description": "Pump minimum speed setting. Static 1550.",
        "confidence": "TENTATIVE",
    },
    813: {
        "name": "defrost_interval",
        "unit": "s",
        "scale": 1,
        "description": "Timer or defrost interval. Static 3600 (=1 hour).",
        "confidence": "TENTATIVE",
    },
    814: {
        "name": "system_temp_limit_814",
        "unit": "°C",
        "scale": 0.1,
        "description": "System temperature limit. Static 390 = 39.0°C.",
        "confidence": "TENTATIVE",
    },
    772: {
        "name": "weather_target_mirror",
        "unit": "°C",
        "scale": 0.1,
        "description": "Weather curve target mirror. Scan 3 (M11=0): static 500 = 50.0°C. "
                       "Scan 4 (M11=17): dynamic 280-290 = 28.0-29.0°C. Mirrors HR[4], HR[816].",
        "confidence": "CONFIRMED",
    },
    816: {
        "name": "weather_curve_target",
        "unit": "°C",
        "scale": 0.1,
        "description": "Weather curve calculated target. Scan 3 (M11=0): static 500 = 50.0°C. "
                       "Scan 4 (M11=17, custom curve active): dynamic 280-290 = 28.0-29.0°C. "
                       "Mirrors HR[4], HR[772]. Changes based on outdoor temp (HR[22]).",
        "confidence": "CONFIRMED",
    },

    # ─── Operation Flag (HR[910-911]) ───
    910: {
        "name": "operation_flag",
        "unit": None,
        "scale": 1,
        "description": "Binary operational flag (0/1). Overnight1: 3988×=0, 1520×=1, also 7000 (1×). "
                       "Overnight2: 4695 readings, 2122 changes. Strongly correlated with HR[911].",
        "confidence": "CONFIRMED",
    },
    911: {
        "name": "operation_setpoint",
        "unit": "°C",
        "scale": 0.1,
        "description": "Setpoint or parameter, coupled with HR[910]. "
                       "Values: 0, 300, 7000 (3 unique). 300 = 30.0°C = zone B target?",
        "confidence": "TENTATIVE",
    },

    # ═══════════════════════════════════════════════════════════════════════
    # BLOCK D: HR[1000-1079] — Secondary Sensor Block (mirrors primary)
    # ═══════════════════════════════════════════════════════════════════════
    # These registers mirror primary block A sensors. Not all mappings confirmed.

    1024: {
        "name": "week_number",
        "unit": None,
        "scale": 1,
        "description": "Week of the year. Clean-bus: 31→32 transition observed. "
                       "Mirrors HR[1025]/HR[1292]/HR[3340].",
        "confidence": "LIKELY",
    },
    1025: {
        "name": "week_number_mirror",
        "unit": None,
        "scale": 1,
        "description": "Week number mirror. 100% match with HR[1292].",
        "confidence": "CONFIRMED",
    },
    1033: {
        "name": "status_bitfield_1033",
        "unit": None,
        "scale": 1,
        "description": "Status bitfield. Values: 35, 16439. "
                       "100% mirror of HR[1360].",
        "confidence": "LIKELY",
    },
    1034: {
        "name": "evaporator_target_sec",
        "unit": "°C",
        "scale": 0.1,
        "description": "Evaporator target (secondary). Mirrors HR[38]/HR[1319].",
        "confidence": "CONFIRMED",
    },
    1035: {
        "name": "plate_hx_temp_sec",
        "unit": "°C",
        "scale": 0.1,
        "description": "Plate HX inlet temp (secondary). Clean-bus: 24.9-36.3°C. "
                       "Mirrors HR[40]/HR[1323].",
        "confidence": "CONFIRMED",
    },
    1038: {
        "name": "superheat_sec",
        "unit": "°C",
        "scale": 0.1,
        "description": "Superheat (secondary). Clean-bus: 0-11.1°C. "
                       "Mirrors HR[42]/HR[1322].",
        "confidence": "CONFIRMED",
    },
    1040: {
        "name": "compressor_power_sec",
        "unit": None,
        "scale": 1,
        "description": "Compressor power (secondary). Clean-bus: 0-1914. "
                       "Mirrors HR[41]/HR[1321].",
        "confidence": "CONFIRMED",
    },
    1041: {
        "name": "compressor_speed_high_sec",
        "unit": None,
        "scale": 1,
        "description": "Compressor speed high range (secondary). Clean-bus: 3164-3894. "
                       "Mirrors HR[1368].",
        "confidence": "LIKELY",
    },
    1045: {
        "name": "condenser_target_sec",
        "unit": "°C",
        "scale": 0.1,
        "description": "Condenser target temp (secondary). "
                       "Mirrors HR[39]/HR[1320].",
        "confidence": "CONFIRMED",
    },
    1046: {
        "name": "mode_flag_sec",
        "unit": None,
        "scale": 1,
        "description": "Mode flag (secondary). Values: 0, 7. "
                       "100% mirror of HR[1324]/HR[1373].",
        "confidence": "LIKELY",
    },

    # ═══════════════════════════════════════════════════════════════════════
    # BLOCK E: HR[1283-1409] — Compressor Live Operational Data
    # ═══════════════════════════════════════════════════════════════════════
    # Rich real-time data. Many registers → 0 or 0x8044 when compressor off.

    1283: {
        "name": "compressor_on_off",
        "unit": None,
        "scale": 1,
        "description": "Compressor ON/OFF status. Clean-bus: only 1 transition (1→0) at 13:06:50. "
                       "1=running, 0=off. Mirrors HR[768] operational_status concept.",
        "confidence": "CONFIRMED",
    },
    1289: {
        "name": "status_bitfield_1289",
        "unit": None,
        "scale": 1,
        "description": "Bit-packed status register. Jumps in ~2048 steps: "
                       "5787→7835→3739→1696→1700. NOT a sensor value.",
        "confidence": "LIKELY",
    },
    1292: {
        "name": "week_number_comp",
        "unit": None,
        "scale": 1,
        "description": "Week number (compressor block). 100% mirror of HR[1025].",
        "confidence": "CONFIRMED",
    },
    1301: {
        "name": "water_outlet_temp_comp",
        "unit": "°C",
        "scale": 0.1,
        "description": "Water outlet temp (compressor block). Mirrors HR[1]/HR[776]. "
                       "0x8044 when compressor off, else 0-33.6°C.",
        "confidence": "CONFIRMED",
    },
    1303: {
        "name": "fin_coil_temp_comp",
        "unit": "°C",
        "scale": 0.1,
        "description": "Fin/coil temp (compressor block). Mirrors HR[23].",
        "confidence": "CONFIRMED",
    },
    1304: {
        "name": "discharge_metric_comp",
        "unit": None,
        "scale": 0.1,
        "description": "Discharge pressure/temp metric. Mirrors HR[25]. "
                       "0x8044 when off, else 43.8-94.0. Most variable register.",
        "confidence": "LIKELY",
    },
    1305: {
        "name": "suction_temp_comp",
        "unit": "°C",
        "scale": 0.1,
        "description": "Suction temperature (compressor block). Mirrors HR[24].",
        "confidence": "CONFIRMED",
    },
    1308: {
        "name": "superheat_subcool_comp",
        "unit": "°C",
        "scale": 0.1,
        "description": "Superheat/subcool (compressor block). Mirrors HR[35].",
        "confidence": "LIKELY",
    },
    1309: {
        "name": "discharge_temp_comp",
        "unit": "°C",
        "scale": 0.1,
        "description": "Discharge temperature (compressor block). Clean-bus: 20.5-70.3°C. "
                       "Mirrors HR[36]/HR[773].",
        "confidence": "CONFIRMED",
    },
    1310: {
        "name": "low_pressure_comp",
        "unit": "bar",
        "scale": 0.1,
        "description": "Low pressure (compressor block). Clean-bus: 4.0-8.1 bar. "
                       "Mirrors HR[32].",
        "confidence": "CONFIRMED",
    },
    1311: {
        "name": "high_pressure_comp",
        "unit": "bar",
        "scale": 0.1,
        "description": "High pressure (compressor block). Clean-bus: 7.5-25.0 bar. "
                       "Mirrors HR[33].",
        "confidence": "CONFIRMED",
    },
    1313: {
        "name": "signed_metric_1313",
        "unit": None,
        "scale": 0.1,
        "description": "Signed int16. Clean-bus: -6.0 to +6.4. "
                       "Could be superheat error or PID term.",
        "signed": True,
        "confidence": "TENTATIVE",
    },
    1319: {
        "name": "evaporator_target_comp",
        "unit": "°C",
        "scale": 0.1,
        "description": "Evaporator target (compressor block). Mirrors HR[38]. "
                       "Discrete steps, shutdown profile captured: 70→50→48→44→39→33→30→0°C.",
        "confidence": "CONFIRMED",
    },
    1320: {
        "name": "condenser_target_comp",
        "unit": "°C",
        "scale": 0.1,
        "description": "Condenser target (compressor block). Mirrors HR[39].",
        "confidence": "CONFIRMED",
    },
    1321: {
        "name": "compressor_power_comp",
        "unit": None,
        "scale": 1,
        "description": "Compressor power (compressor block). Clean-bus: 0-1914. "
                       "100% mirror of HR[41]/HR[1367].",
        "confidence": "CONFIRMED",
    },
    1322: {
        "name": "superheat_or_comp_current",
        "unit": "°C or A",
        "scale": 0.1,
        "description": "Superheat OR compressor output current (compressor block). "
                       "Clean-bus: 0-11.1 (scan 3), 0-7.2 (scan 4). "
                       "100% mirror of HR[42]/HR[1365]. "
                       "CONFLICT: previously confirmed as superheat mirror of HR[42], "
                       "but tablet T33 (compressor current output A) matches this register. "
                       "Both are 0 when comp OFF — needs running-compressor verification.",
        "confidence": "CONFIRMED",
        "tablet_param": "T33",
    },
    1323: {
        "name": "plate_hx_temp_comp",
        "unit": "°C",
        "scale": 0.1,
        "description": "Plate HX inlet temp (compressor block). Clean-bus: 24.9-36.3°C. "
                       "100% mirror of HR[40]/HR[1362].",
        "confidence": "CONFIRMED",
    },
    1324: {
        "name": "mode_flag_comp",
        "unit": None,
        "scale": 1,
        "description": "Mode flag (compressor block). Values: 0, 7. "
                       "100% mirror of HR[1046]/HR[1373].",
        "confidence": "LIKELY",
    },
    1325: {
        "name": "inverter_input_current",
        "unit": "A",
        "scale": 0.1,
        "description": "Inverter input current (compressor block). "
                       "Standby: 1.2A (comp OFF), running: 6-10.9A (comp ON). "
                       "Tablet T38 = 1.2A confirmed exact match. "
                       "Mirror: HR[1370].",
        "confidence": "CONFIRMED",
        "tablet_param": "T38",
    },
    1326: {
        "name": "suction_temp_comp_2",
        "unit": "°C",
        "scale": 0.1,
        "description": "Suction temperature 2 (compressor block). 0-34.3°C. "
                       "100% mirror of HR[1363].",
        "confidence": "LIKELY",
    },
    1327: {
        "name": "compressor_torque",
        "unit": "%",
        "scale": 0.1,
        "description": "Compressor torque output (compressor block). "
                       "0% when comp OFF, 0-49.6% when comp ON. "
                       "Tablet T34 = 0.0% confirmed (comp OFF match). "
                       "HR[1328] tracks in ×5 steps (torque target?).",
        "confidence": "CONFIRMED",
        "tablet_param": "T34",
    },
    1335: {
        "name": "compressor_output_voltage",
        "unit": "V",
        "scale": 0.1,
        "description": "Compressor output voltage (compressor block). "
                       "0V when comp OFF (1913 samples), 0-236.5V when comp ON (581 samples). "
                       "Tablet T35 = 0.0V confirmed (comp OFF match).",
        "confidence": "CONFIRMED",
        "tablet_param": "T35",
    },
    1338: {
        "name": "mains_voltage",
        "unit": "V",
        "scale": 0.1,
        "description": "Mains supply voltage. Clean-bus: 223.9-230.5V. "
                       "Dutch mains = 230V ±10%.",
        "confidence": "CONFIRMED",
    },
    1348: {
        "name": "plate_hx_inlet_live",
        "unit": "°C",
        "scale": 0.1,
        "description": "Plate HX inlet temp (live). Clean-bus: 41.0-55.1°C. "
                       "Mirrors HR[3357].",
        "confidence": "CONFIRMED",
    },
    1349: {
        "name": "plate_hx_temp_2_live",
        "unit": "°C",
        "scale": 0.1,
        "description": "Plate HX temperature 2 (live). Clean-bus: 44.5-55.5°C.",
        "confidence": "CONFIRMED",
    },
    1350: {
        "name": "plate_hx_outlet_live",
        "unit": "°C",
        "scale": 0.1,
        "description": "Plate HX outlet temp (live). Clean-bus: 44.5-55.8°C.",
        "confidence": "CONFIRMED",
    },
    1351: {
        "name": "ambient_temp_comp",
        "unit": "°C",
        "scale": 0.1,
        "description": "Ambient temperature (compressor block). Clean-bus: 11.5-19.7°C. "
                       "Mirrors HR[22]/HR[3350].",
        "confidence": "CONFIRMED",
    },
    1352: {
        "name": "pump_speed_live",
        "unit": "rpm",
        "scale": 1,
        "description": "Live pump speed. Static 6800. Matches HR[53]/HR[811].",
        "confidence": "CONFIRMED",
    },
    1353: {
        "name": "pump_flow_rate_comp",
        "unit": "L/h",
        "scale": 1,
        "description": "Pump flow rate (compressor block). Clean-bus: 2021-2079 L/h. "
                       "Mirrors HR[54].",
        "confidence": "CONFIRMED",
    },
    1355: {
        "name": "pump_feedback_comp",
        "unit": "%",
        "scale": 0.1,
        "description": "Pump feedback (compressor block). Clean-bus: 31.4-32.3%. "
                       "Mirrors HR[147].",
        "confidence": "CONFIRMED",
    },
    1358: {
        "name": "superheat_subcool_live",
        "unit": "°C",
        "scale": 0.1,
        "description": "Superheat/subcooling (live). Clean-bus: 0-104.0°C. "
                       "Mirrors HR[3371].",
        "confidence": "LIKELY",
    },
    1360: {
        "name": "status_bitfield_1360",
        "unit": None,
        "scale": 1,
        "description": "Status bitfield. 100% mirror of HR[1033]. Values: 35, 16439.",
        "confidence": "LIKELY",
    },
    1361: {
        "name": "evaporator_target_comp_2",
        "unit": "°C",
        "scale": 0.1,
        "description": "Evaporator target mirror 2. Mirrors HR[38]/HR[1319].",
        "confidence": "CONFIRMED",
    },
    1362: {
        "name": "plate_hx_temp_comp_2",
        "unit": "°C",
        "scale": 0.1,
        "description": "Plate HX temp mirror 2. 100% mirror of HR[40]/HR[1323].",
        "confidence": "CONFIRMED",
    },
    1363: {
        "name": "suction_temp_comp_3",
        "unit": "°C",
        "scale": 0.1,
        "description": "Suction temp mirror 3. 100% mirror of HR[1326].",
        "confidence": "LIKELY",
    },
    1365: {
        "name": "superheat_or_comp_current_2",
        "unit": "°C or A",
        "scale": 0.1,
        "description": "Mirror of HR[1322]/HR[42]. See HR[1322] for superheat/current conflict.",
        "confidence": "CONFIRMED",
        "tablet_param": "T33 (mirror)",
    },
    1367: {
        "name": "compressor_power_comp_2",
        "unit": None,
        "scale": 1,
        "description": "Compressor power mirror 2. 100% mirror of HR[41]/HR[1321].",
        "confidence": "CONFIRMED",
    },
    1368: {
        "name": "dc_bus_voltage",
        "unit": "V",
        "scale": 0.1,
        "description": "DC bus voltage (compressor block). Clean-bus: 308-389V. "
                       "Tablet T36 = 324.1V confirmed (our reading: 324.0V). "
                       "Mirrors HR[1041].",
        "confidence": "CONFIRMED",
        "tablet_param": "T36",
    },
    1370: {
        "name": "inverter_input_current_2",
        "unit": "A",
        "scale": 0.1,
        "description": "Inverter input current mirror. 100% mirror of HR[1325]. "
                       "Tablet T38 mirror.",
        "confidence": "CONFIRMED",
        "tablet_param": "T38 (mirror)",
    },
    1372: {
        "name": "condenser_target_comp_2",
        "unit": "°C",
        "scale": 0.1,
        "description": "Condenser target mirror 2. Mirrors HR[39]/HR[1320].",
        "confidence": "CONFIRMED",
    },
    1373: {
        "name": "mode_flag_comp_2",
        "unit": None,
        "scale": 1,
        "description": "Mode flag mirror 2. 100% mirror of HR[1046]/HR[1324].",
        "confidence": "LIKELY",
    },

    # ═══════════════════════════════════════════════════════════════════════
    # TABLET COMMUNICATION REGISTERS (HR[5000-5010])
    # ═══════════════════════════════════════════════════════════════════════
    # Only present when tablet/display is active on the bus.

    5000: {
        "name": "clock_year",
        "unit": None,
        "scale": 1,
        "description": "Clock sync - year. Tablet writes via FC16. Value=2026.",
        "writable": True,
        "confidence": "CONFIRMED",
    },
    5001: {
        "name": "clock_month",
        "unit": None,
        "scale": 1,
        "description": "Clock sync - month. Tablet writes via FC16.",
        "writable": True,
        "confidence": "CONFIRMED",
    },
    5002: {
        "name": "clock_day",
        "unit": None,
        "scale": 1,
        "description": "Clock sync - day. Tablet writes via FC16.",
        "writable": True,
        "confidence": "CONFIRMED",
    },
    5003: {
        "name": "clock_day_of_week",
        "unit": None,
        "scale": 1,
        "description": "Clock sync - day of week. Tablet writes via FC16.",
        "writable": True,
        "confidence": "CONFIRMED",
    },
    5004: {
        "name": "clock_hour",
        "unit": None,
        "scale": 1,
        "description": "Clock sync - hour. Tablet writes via FC16.",
        "writable": True,
        "confidence": "CONFIRMED",
    },
    5005: {
        "name": "clock_minute",
        "unit": None,
        "scale": 1,
        "description": "Clock sync - minute. Tablet writes via FC16.",
        "writable": True,
        "confidence": "CONFIRMED",
    },
    5006: {
        "name": "clock_flag",
        "unit": None,
        "scale": 1,
        "description": "Clock sync - flag/seconds. Always 1.",
        "writable": True,
        "confidence": "CONFIRMED",
    },
    5010: {
        "name": "room_temperature_from_tablet",
        "unit": "°C",
        "scale": 0.1,
        "description": "Room temperature from tablet's built-in sensor, written via FC06. "
                       "Emulator session: values 236-244 (23.6-24.4°C), user confirmed 23.8°C. "
                       "Overnight: 571 writes, 21.6-22.2°C range, ~48s interval. "
                       "Write-only: FC03 reads return error (not a readable register).",
        "writable": True,
        "confidence": "CONFIRMED",
    },

    # ═══════════════════════════════════════════════════════════════════════
    # BLOCK FW_EXT: HR[4000-4015] — External PCB Firmware ASCII
    # ═══════════════════════════════════════════════════════════════════════

    4000: {
        "name": "external_pcb_firmware_ascii",
        "description": "External PCB firmware version ASCII (HR[4000-4013], big-endian). "
                       "Decodes to 'X1.HL081B.K05.001-1.V100A03'. "
                       "Previously could not be found — discovered via tablet poll ranges.",
        "confidence": "CONFIRMED",
    },

    # ═══════════════════════════════════════════════════════════════════════
    # CONFIG BLOCK: HR[6400-7471] — Tablet Configuration & Parameters
    # ═══════════════════════════════════════════════════════════════════════
    # Written by tablet during setup. Massive config block with 924 non-zero
    # values. Mostly static — only HR[6400] changes during normal operation.
    # Sub-blocks polled by tablet (28 ranges), grouped by function.

    # ─── Operating Mode & Setpoints (HR[6400-6444]) ───
    6400: {
        "name": "operating_mode_tablet",
        "unit": None,
        "scale": 1,
        "description": "Operating mode set by tablet. Emulator confirmed: user set 'Heating' → "
                       "FC06 write value 2. Probable values: 0=off, 1=cooling, 2=heating, "
                       "3=auto, 4=DHW. Installer has disabled cooling/auto/DHW on this unit.",
        "writable": True,
        "confidence": "CONFIRMED",
    },
    6401: {
        "name": "M01_cooling_setpoint",
        "unit": "°C",
        "scale": 1,
        "description": "M01 Koeling ingestelde temperatuur. Probe: 10°C.",
        "confidence": "LIKELY",
    },
    6402: {
        "name": "M02_heating_setpoint",
        "unit": "°C",
        "scale": 1,
        "description": "M02 Verwarming ingestelde temperatuur. Scan 3: 50°C. "
                       "Scan 4: 35°C (gewijzigd voor weercurve optimalisatie). "
                       "Matches HR[4]=500÷10 (scan 3) / HR[4]=280-290÷10 (scan 4).",
        "writable": True,
        "confidence": "CONFIRMED",
    },
    6403: {
        "name": "M03_dhw_setpoint",
        "unit": "°C",
        "scale": 1,
        "description": "M03 Warm tapwater ingestelde temperatuur. Probe: 50°C. "
                       "NOT cooling target (previously misidentified).",
        "writable": True,
        "confidence": "LIKELY",
    },
    6404: {
        "name": "M04_cooling_target_room",
        "unit": "°C",
        "scale": 1,
        "description": "M04 Koeling doeltemp. kamertemperatuur. Scan 3: 26°C. "
                       "Scan 4: 18°C (auto-aangepast door weercurve-modus).",
        "writable": True,
        "confidence": "CONFIRMED",
    },
    6405: {
        "name": "M05_heating_target_room",
        "unit": "°C",
        "scale": 1,
        "description": "M05 Verwarming doeltemp. kamertemperatuur. Scan 3: 23°C. "
                       "Scan 4: 19°C (auto-aangepast door weercurve-modus).",
        "writable": True,
        "confidence": "CONFIRMED",
    },

    # ─── Curve Mode & Sterilisation (HR[6410-6415]) ───
    6410: {
        "name": "M10_curve_mode_flag",
        "unit": None,
        "scale": 1,
        "description": "M10 Zone A koelingscurve / curve mode flag. Scan 3: 0. "
                       "Scan 4: 2 (auto-set when M11 changed to 17). "
                       "Values: 0=uit, 2=weercurve actief.",
        "confidence": "CONFIRMED",
    },
    6411: {
        "name": "config_6411",
        "unit": None,
        "scale": 1,
        "description": "Unknown config. Static 0 in both scans. "
                       "NOT M11 (M11 is at HR[6426]). Simple offset mapping breaks here.",
        "confidence": "TENTATIVE",
    },
    6412: {
        "name": "G01_sterilisation_enable",
        "unit": None,
        "scale": 1,
        "description": "G01 Sterilisatie AAN/UIT. Value: 0 = UIT. "
                       "G-serie registers overlap M-serie simple offset positions.",
        "confidence": "CONFIRMED",
    },
    6413: {
        "name": "G02_sterilisation_temp",
        "unit": "°C",
        "scale": 1,
        "description": "G02 Sterilisatietemperatuur. Value: 70°C.",
        "confidence": "CONFIRMED",
    },
    6414: {
        "name": "G03_sterilisation_max_cycle",
        "unit": "min",
        "scale": 1,
        "description": "G03 Max. sterilisatiecyclus. Value: 210 min.",
        "confidence": "CONFIRMED",
    },
    6415: {
        "name": "G04_sterilisation_high_temp_time",
        "unit": "min",
        "scale": 1,
        "description": "G04 Tijd hoge temp. Value: 15 min.",
        "confidence": "CONFIRMED",
    },

    # ─── Curve Selection (HR[6425-6428]) ───
    # M10-M13 curve selections at offset +15 from tablet parameter number.
    # Values: 0=Uit, 1-8=Lage temp. curve, 9-16=Hoge temp. curve, 17=Aangepast.
    6425: {
        "name": "M10_zone_A_cooling_curve",
        "unit": None,
        "scale": 1,
        "description": "M10 Zone A koelingscurve selectie. Value: 0 = Uit. "
                       "HR address = 6400 + 10 + 15 (offset +15 for M10+).",
        "confidence": "CONFIRMED",
    },
    6426: {
        "name": "M11_zone_A_heating_curve",
        "unit": None,
        "scale": 1,
        "description": "M11 Zone A verwarmingscurve selectie. Scan 3: 0 (Uit). "
                       "Scan 4: 17 (Aangepast). CONFIRMED by DB comparison: "
                       "HR[6411] stayed 0, HR[6426] changed 0→17.",
        "writable": True,
        "confidence": "CONFIRMED",
    },
    6427: {
        "name": "M12_zone_B_cooling_curve",
        "unit": None,
        "scale": 1,
        "description": "M12 Zone B koelingscurve selectie. Value: 0 = Uit.",
        "confidence": "CONFIRMED",
    },
    6428: {
        "name": "M13_zone_B_heating_curve",
        "unit": None,
        "scale": 1,
        "description": "M13 Zone B verwarmingscurve selectie. Scan 3: 0. Scan 4: 17. "
                       "Auto-synced with M11 (HR[6426]) because N26=0 (single zone mode).",
        "confidence": "CONFIRMED",
    },

    # ─── Custom Curve Data Points (HR[6429-6436]) ───
    # M14-M21 at offset +15. Define custom weather curve (M11/M13=17).
    6429: {
        "name": "M14_custom_cool_ambient_1",
        "unit": "°C",
        "scale": 1,
        "description": "M14 Aangepaste koeling omgevingstemp 1. Value: 35°C.",
        "confidence": "CONFIRMED",
    },
    6430: {
        "name": "M15_custom_cool_ambient_2",
        "unit": "°C",
        "scale": 1,
        "description": "M15 Aangepaste koeling omgevingstemp 2. Value: 25°C.",
        "confidence": "CONFIRMED",
    },
    6431: {
        "name": "M16_custom_cool_outlet_1",
        "unit": "°C",
        "scale": 1,
        "description": "M16 Aangepaste koeling uitlaattemp 1. Value: 10°C.",
        "confidence": "CONFIRMED",
    },
    6432: {
        "name": "M17_custom_cool_outlet_2",
        "unit": "°C",
        "scale": 1,
        "description": "M17 Aangepaste koeling uitlaattemp 2. Value: 16°C.",
        "confidence": "CONFIRMED",
    },
    6433: {
        "name": "M18_custom_heat_ambient_1",
        "unit": "°C",
        "scale": 1,
        "description": "M18 Aangepaste verwarming omgevingstemp 1. Value: 7°C.",
        "confidence": "CONFIRMED",
    },
    6434: {
        "name": "M19_custom_heat_ambient_2",
        "unit": "°C",
        "scale": 1,
        "signed": True,
        "description": "M19 Aangepaste verwarming omgevingstemp 2. Value: -5°C "
                       "(stored as uint16: 65531).",
        "confidence": "CONFIRMED",
    },
    6435: {
        "name": "M20_custom_heat_outlet_1",
        "unit": "°C",
        "scale": 1,
        "description": "M20 Aangepaste verwarming uitlaattemp 1. Value: 28°C.",
        "confidence": "CONFIRMED",
    },
    6436: {
        "name": "M21_custom_heat_outlet_2",
        "unit": "°C",
        "scale": 1,
        "description": "M21 Aangepaste verwarming uitlaattemp 2. Scan 3: 35°C. "
                       "Scan 4: 38°C (verhoogd voor betere curve).",
        "writable": True,
        "confidence": "CONFIRMED",
    },

    # ─── N-serie / P-serie (HR[6464-6511]) ───
    6472: {
        "name": "P01_pump_mode",
        "unit": None,
        "scale": 1,
        "description": "P01 Waterpomp werkingsmodus. Scan 3: 0 (continu). "
                       "Scan 4: 1 (intermitterend). Pump OFF 76.8% of time with P01=1. "
                       "Same address as N08 (dual-mapped or N08 mapping was wrong).",
        "writable": True,
        "confidence": "CONFIRMED",
    },

    # ─── Humidity / Climate (HR[6592-6638]) ───
    6594: {
        "name": "humidity_limit_max",
        "unit": "%",
        "scale": 0.1,
        "description": "Max humidity alarm threshold? Probe: 700 = 70.0%.",
        "confidence": "TENTATIVE",
    },
    6595: {
        "name": "room_humidity",
        "unit": "%",
        "scale": 0.1,
        "description": "Room humidity from tablet sensor. Probe: 520 = 52.0%. "
                       "User confirmed ~52% on tablet display.",
        "confidence": "CONFIRMED",
    },

    # ═══════════════════════════════════════════════════════════════════════
    # ENERGY HISTORY BLOCK: HR[21500-21913] — Daily Energy Records
    # ═══════════════════════════════════════════════════════════════════════
    # Paged history system. Tablet writes HR[21500] as page trigger (0→1).
    # Header at HR[21501-21505], then 6 daily records per page of 102 regs.
    #
    # Available views on tablet:
    #   - Last 24 hours  (1-hour blocks, resolution 0.1 kWh)
    #   - Last 30 days   (1-day blocks, resolution 0.1 kWh)
    #   - Last 12 months (1-month blocks, resolution 1 kWh)
    #   - Last 10 years  (1-year blocks, resolution 10 kWh)
    #
    # Daily record format (17 registers per record, CONFIRMED with tablet):
    #   Offset  Field                  Unit
    #   ──────────────────────────────────────
    #   0-4     Date ASCII             "DD/MM/YYYY" (5 regs, big-endian)
    #   5       Status/flags           byte (D=68, H=72, etc)
    #   6       unknown_1              ?
    #   7       unknown_2              ?
    #   8       Cooling capacity       ×0.1 kWh
    #   9       Heating capacity       ×0.1 kWh  ← CONFIRMED
    #   10      DHW capacity           ×0.1 kWh
    #   11      Cooling consumption    ×0.1 kWh
    #   12      Heating consumption    ×0.1 kWh  ← CONFIRMED
    #   13      DHW consumption        ×0.1 kWh
    #   14      Cooling COP%           ×1%
    #   15      Heating COP%           ×1%       ← CONFIRMED
    #   16      DHW COP%               ×1%
    #
    # Verification: 16/03/2026 tablet shows heating capacity=441, consumption=171,
    #   COP%=257 → 441/171 = 2.578 → rounds to 257% ✓

    21500: {
        "name": "history_page_trigger",
        "unit": None,
        "scale": 1,
        "description": "History page trigger. Tablet writes 0 then 1 via FC06 to request data. "
                       "Write-only: FC03 reads return error.",
        "writable": True,
        "confidence": "CONFIRMED",
    },
    21501: {
        "name": "history_num_days",
        "unit": None,
        "scale": 1,
        "description": "Number of days in history. Probe: 30.",
        "confidence": "CONFIRMED",
    },
    21502: {
        "name": "history_unit_ascii",
        "description": "Energy unit ASCII (HR[21502-21504]). Decodes to '0.1kWh'.",
        "confidence": "CONFIRMED",
    },
    21505: {
        "name": "history_pages_or_flags",
        "unit": None,
        "scale": 1,
        "description": "History flags/pages. Probe: 15.",
        "confidence": "TENTATIVE",
    },
}

# === SHADOW / MIRROR REGISTER RANGES ===
#
# HR[3331-3372]: Shadow of live data for tablet display.
#   Confirmed mappings from clean-bus overnight:
#   - HR[3340] = HR[1024] (week number, 100% match)
#   - HR[3350] = HR[22]   (ambient temp, 100% match)
#   - HR[3355] ≈ HR[773]  (discharge temp)
#   - HR[3356] ≈ HR[773]  (discharge temp, wider window)
#   - HR[3357] ≈ HR[1349] (plate HX temp 2)
#   - HR[3371] = HR[1358] (superheat/subcool, 100% match)
#   - Contains own 0x8044 disconnected markers
#
# HR[6400-7471]: Tablet configuration mega-block (924 non-zero values!).
#   Written by tablet during setup. Contains:
#   - HR[6400-6409]: M00-M09 operating mode + setpoints (simple offset M_xx → 6400+xx)
#   - HR[6410]:      M10 curve mode flag (0=off, 2=weather curve active)
#   - HR[6411]:      Unknown (NOT M11! Simple offset breaks here)
#   - HR[6412-6415]: G01-G04 sterilisation parameters (overlap M-serie offset space)
#   - HR[6425-6428]: M10-M13 curve SELECTION (offset +15: M_xx → 6400+xx+15)
#   - HR[6429-6436]: M14-M21 custom curve data points (offset +15)
#   - HR[6464-6511]: N-serie enable/disable flags + P-serie (HR[6472]=P01)
#   - HR[6528-6575]: Timing parameters, temperature limits
#   - HR[6592-6638]: Humidity, climate params (HR[6595] = room humidity)
#   - HR[6656-6687]: DHW parameters
#   - HR[6720-6822]: Weather compensation curves (96 non-zero!)
#   - HR[6848-6887]: Defrost parameters
#   - HR[6912-6959]: Scheduling/timer parameters
#   - HR[6976-7023]: Protection limits
#   - HR[7040-7087]: Feature enable flags
#   - HR[7104-7151]: Compressor limits/curves
#   - HR[7168-7215]: Expansion valve parameters
#   - HR[7296-7343]: Weather curve data points
#   - HR[7360-7407]: Weather curve data points 2
#   - HR[7424-7471]: Misc config (includes HR[7433]=4000 rpm?)
#
# IMPORTANT — M-serie register mapping is NON-LINEAR:
#   M00-M09: HR[6400+xx]       (simple offset)
#   M10-M21: HR[6400+xx+15]    (offset +15, due to G-serie overlap at 6412-6415)
#   M55-M63: HR[6400+xx]       (simple offset works again for high M-numbers)
#   G01-G04: HR[6412-6415]     (occupy M12-M15 simple offset positions)
#   N-serie: HR[6464+xx]       (simple offset from 6464)
#   P01:     HR[6472]          (= N08 address — dual-mapped?)
#
# Weather curve verification (scan 4, M11=17):
#   HR[816] = HR[772] = HR[4] (triple-mirrored). Dynamic 28.0-29.0°C based on
#   outdoor temp (HR[22]). Curve defined by M18/M19/M20/M21 = 7°C/-5°C/28°C/38°C.

# === CONFIRMED EXACT MIRROR GROUPS (clean-bus, 477 cycles) ===
# These register pairs have IDENTICAL values in every single reading:
EXACT_MIRRORS = [
    (1025, 1292),         # week_number
    (1033, 1360),         # status_bitfield
    (1037, 1364),         # evaporator target ×10 (= HR[38])
    (1046, 1324, 1373),   # mode_flag (0/7)
    (1321, 1367),         # compressor_power
    (1322, 1365),         # superheat OR comp current (T33) — see conflict note
    (1323, 1362),         # plate_hx_temp
    (1325, 1370),         # inverter_input_current (T38) — tablet confirmed
    (1326, 1363),         # suction_temp
]

# === CROSS-BLOCK NEAR-MIRRORS (primary → secondary → compressor) ===
# These register groups track the same physical value across blocks:
CROSS_BLOCK_MIRRORS = {
    "ambient_temp":       (22, None, 1351, 3350),
    "low_pressure_bar":   (32, None, 1310, None),
    "high_pressure_bar":  (33, None, 1311, None),
    "discharge_temp":     (36, 773, 1309, 3355),
    "evap_target":        (38, 125, 1319, None),
    "condenser_target":   (39, 126, 1320, None),
    "plate_hx_inlet":     (40, 1035, 1323, None),
    "compressor_power":   (41, 1040, 1321, None),
    "superheat":          (42, 1038, 1322, None),  # T33 conflict: may be comp current, not superheat
    "pump_flow_rate":     (54, None, 1353, None),
    "pump_feedback":      (147, None, 1355, None),
    "water_outlet_temp":  (1, 776, 1301, None),
    "weather_target":     (4, 816, 772, None),  # triple-mirror, dynamic with M11=17
}

# === TABLET T-SERIE CONFIRMED ENERGY REGISTERS ===
# Verified 2026-03-18 by comparing live Modbus reads with tablet display.
# Compressor was OFF during verification. Non-zero matches: T38=1.2A, T36=324.1V.
TABLET_ENERGY_REGISTERS = {
    "T33_comp_current":     {"primary": 1322, "mirror": 1365, "unit": "A", "scale": 0.1,
                             "note": "Conflicts with superheat mirror of HR[42]. Needs running-comp test."},
    "T34_comp_torque":      {"primary": 1327, "mirror": None,  "unit": "%", "scale": 0.1},
    "T35_comp_voltage":     {"primary": 1335, "mirror": None,  "unit": "V", "scale": 0.1},
    "T36_dc_bus_voltage":   {"primary": 1368, "mirror": None,  "unit": "V", "scale": 0.1},
    "T38_inverter_current": {"primary": 1325, "mirror": 1370,  "unit": "A", "scale": 0.1},
}

# === INPUT REGISTERS (FC04) — REDUNDANT, HR=IR CONFIRMED ===
# Kept for reference. On this controller, IR[addr] == HR[addr] for all addresses.
# The HACS integration should use HOLDING_REGISTERS only (FC03).

INPUT_REGISTERS: dict[int, dict] = {
    # ─── Refrigerant Circuit Temperatures ───
    22: {
        "name": "ambient_temperature",
        "unit": "°C",
        "scale": 0.1,
        "description": "= HR[22]. App: '0#Omgevingstemp.: 14.10°C'.",
        "confidence": "CONFIRMED",
    },
    23: {
        "name": "fin_coil_temperature",
        "unit": "°C",
        "scale": 0.1,
        "description": "= HR[23]. App: '0#Vinnen temp'.",
        "confidence": "CONFIRMED",
    },
    24: {
        "name": "suction_temperature",
        "unit": "°C",
        "scale": 0.1,
        "description": "= HR[24]. App: '0#Zuigtemp'.",
        "confidence": "CONFIRMED",
    },
    25: {
        "name": "discharge_temperature",
        "unit": "°C",
        "scale": 0.1,
        "description": "= HR[25]. App: '0#Uitlaattemp'.",
        "confidence": "CONFIRMED",
    },
    32: {
        "name": "low_pressure",
        "unit": "bar",
        "scale": 0.1,
        "description": "= HR[32]. App: '0#Lage drukwaarde'.",
        "confidence": "CONFIRMED",
    },
    33: {
        "name": "high_pressure",
        "unit": "bar",
        "scale": 0.1,
        "description": "= HR[33]. App: '0#Hoge drukwaarde'.",
        "confidence": "CONFIRMED",
    },
    53: {
        "name": "pump_target_speed",
        "unit": "rpm",
        "scale": 1,
        "description": "= HR[53]. App: 'Doelsnelheid omvormerwaterpomp: 6800rpm'.",
        "confidence": "CONFIRMED",
    },
    54: {
        "name": "pump_flow_rate",
        "unit": "L/h",
        "scale": 1,
        "description": "= HR[54]. App: 'stroomsnelheid: 2053L/H'.",
        "confidence": "CONFIRMED",
    },
    66: {
        "name": "pump_control_signal",
        "unit": "%",
        "scale": 0.1,
        "description": "= HR[66]. App: 'stuursignaal: 5.00%%'.",
        "confidence": "CONFIRMED",
    },
    84: {
        "name": "heating_target_temp_mirror",
        "unit": "°C",
        "scale": 0.1,
        "description": "= HR[4]. App: 'Instelbare doeltemperatuur: 50.00°C'.",
        "confidence": "CONFIRMED",
    },
    95: {
        "name": "zone_b_heating_target_mirror",
        "unit": "°C",
        "scale": 0.1,
        "description": "= HR[95]. Zone B heating target.",
        "confidence": "CONFIRMED",
    },
    135: {
        "name": "plate_hx_inlet_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "= HR[135]. App: 'Waterinlaattemp. platenwisselaar'.",
        "confidence": "CONFIRMED",
    },
    136: {
        "name": "plate_hx_outlet_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "= HR[136]. App: 'Wateruitlaattemp. platenwisselaar'.",
        "confidence": "CONFIRMED",
    },
    137: {
        "name": "module_total_water_outlet_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "= HR[137]. App: 'Totale wateruitlaattemp'.",
        "confidence": "CONFIRMED",
    },
    138: {
        "name": "module_ambient_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "= HR[138]. App: '0#Omgevingstemp'.",
        "confidence": "CONFIRMED",
    },
    142: {
        "name": "pump_feedback_signal",
        "unit": "%",
        "scale": 0.1,
        "description": "= HR[142]. App: 'Feedbacksignaal: 31.90%%'.",
        "confidence": "CONFIRMED",
    },
}

# === COILS (FC01/FC05/FC15) ===
# Discovered via tablet emulator session.
COILS: dict[int, dict] = {
    8: {
        "name": "tablet_heartbeat",
        "description": "Tablet heartbeat/watchdog. Tablet writes FC05 0xFF00 (=ON) "
                       "repeatedly (~every 3s). May signal to heat pump that tablet is alive. "
                       "Probe on heat pump: reads as 0.",
        "writable": True,
        "confidence": "CONFIRMED",
    },
}

# === DISCRETE INPUTS (FC02) ===
# Not yet scanned.
DISCRETE_INPUTS: dict[int, dict] = {}

# === ERROR CODES ===
ERROR_CODES: dict[int, str] = {}

# === OPERATING MODES ===
# HR[6400] operating mode (tablet write, CONFIRMED):
OPERATING_MODES_TABLET: dict[int, str] = {
    0: "off",
    1: "cooling",       # disabled by installer on this unit
    2: "heating",       # CONFIRMED via emulator + user test
    3: "auto",          # disabled by installer on this unit
    4: "dhw",           # disabled by installer on this unit
}

# HR[768] operational status (heat pump internal, CONFIRMED):
OPERATIONAL_STATUS: dict[int, str] = {
    0: "standby",
    1: "starting",
    4: "running",
}

# === TABLET POLL RANGES ===
# Complete list of all 28 FC03 register ranges the tablet polls per cycle (~21s).
# Discovered via slave emulator session (2026-03-17).
TABLET_POLL_RANGES: list[tuple[int, int]] = [
    (512, 16),      # HR[512-527]   unknown
    (768, 54),      # HR[768-821]   system params + operational
    (910, 1),       # HR[910]       operation flag
    (912, 2),       # HR[912-913]   operation flags
    (1000, 8),      # HR[1000-1007] secondary sensors
    (1024, 25),     # HR[1024-1048] secondary sensors
    (1283, 87),     # HR[1283-1369] compressor live data
    (3331, 42),     # HR[3331-3372] shadow block
    (4000, 16),     # HR[4000-4015] external PCB firmware
    (6400, 45),     # HR[6400-6444] mode + setpoints
    (6464, 48),     # HR[6464-6511] enable/disable
    (6528, 48),     # HR[6528-6575] timing/limits
    (6592, 47),     # HR[6592-6638] humidity/climate
    (6656, 32),     # HR[6656-6687] DHW params
    (6720, 103),    # HR[6720-6822] weather curves
    (6848, 40),     # HR[6848-6887] defrost params
    (6912, 48),     # HR[6912-6959] scheduling
    (6976, 48),     # HR[6976-7023] protection limits
    (7040, 48),     # HR[7040-7087] feature flags
    (7104, 48),     # HR[7104-7151] compressor curves
    (7168, 48),     # HR[7168-7215] EEV params
    (7296, 48),     # HR[7296-7343] weather curve data 1
    (7360, 48),     # HR[7360-7407] weather curve data 2
    (7424, 48),     # HR[7424-7471] misc config
    (21501, 5),     # HR[21501-21505] history header
    (21506, 102),   # HR[21506-21607] history page 1 (6 days)
    (21608, 102),   # HR[21608-21709] history page 2 (6 days)
    (21812, 102),   # HR[21812-21913] history page 3 (6 days)
]

# === ENERGY HISTORY RECORD FORMAT ===
# Each daily record = 17 registers. 6 records per page of 102 regs.
ENERGY_RECORD_SIZE = 17
ENERGY_RECORD_FIELDS = {
    0: "date_reg_0",         # ASCII date DD/MM/YYYY (5 regs)
    1: "date_reg_1",
    2: "date_reg_2",
    3: "date_reg_3",
    4: "date_reg_4",
    5: "status_flags",       # D=68, H=72, etc
    6: "unknown_1",
    7: "unknown_2",
    8: "cooling_capacity",   # ×0.1 kWh
    9: "heating_capacity",   # ×0.1 kWh  CONFIRMED
    10: "dhw_capacity",      # ×0.1 kWh
    11: "cooling_consumption",  # ×0.1 kWh
    12: "heating_consumption",  # ×0.1 kWh  CONFIRMED
    13: "dhw_consumption",      # ×0.1 kWh
    14: "cooling_cop_pct",      # ×1%
    15: "heating_cop_pct",      # ×1%  CONFIRMED
    16: "dhw_cop_pct",          # ×1%
}

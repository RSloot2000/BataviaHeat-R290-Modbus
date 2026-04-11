"""
BataviaHeat R290 3-8kW Modbus Register Map

Discovered via modbus_scanner.py and scan_extended.py on 2026-03-15.
Cross-referenced with the BataviaHeat app (Statusquery / Modulestatus / Parameters).
Validated across three overnight monitoring sessions:
  1) 9-hour combined active+passive (2026-03-15/16) — bus collisions from display
  2) 9.4-hour targeted (2026-03-16/17) — 851,978 readings, 67,792 changes
  3) 2h27m clean-bus scan (2026-03-17, display disconnected):
     - 477 cycles, 253,564 readings, 19,237 changes, 0 passive frames
     - 531 registers polled (HR only), 120 dynamic, 411 static
     - 1 compressor ON→OFF cycle captured with full shutdown profile

Connection: COM5, 9600 baud, 8N1, slave ID 1

IMPORTANT — HR = IR identity confirmed:
  On clean bus (display disconnected), holding registers (FC03) and input registers
  (FC04) return IDENTICAL values for all addresses. Only FC03 polling is needed.
  INPUT_REGISTERS below are kept for reference but are redundant.

Confirmed register address blocks (clean full scan HR/IR[0-2000]):
  Block A: HR[0-165]    (primary config + sensors + energy accumulators)
  Block B: HR[256-269]  (firmware ASCII + module config)
  Block C: HR[770-839]  (system params, discharge temp, RPM limits)
  Block D: HR[1000-1079] (secondary sensor block, mirrors of primary)
  Block E: HR[1283-1409] (compressor live operational data)
  Shadow:  HR[3331-3372] (shadow of live data for tablet display)
  Config:  HR[6400-6511] (100% static — tablet configuration/parameters)
  + 37 disconnected-sensor markers (0x8044) scattered throughout

Register mirroring architecture (triple-mirror):
  Many sensor values exist in three parallel copies:
    primary (HR[0-165]) = sec_1000 (HR[1000-1079]) = sec_1283 (HR[1283-1409])
  8 exact mirror groups confirmed with 100% match across 477 cycles.
  Only the primary block needs to be read for the HACS integration.

Notes:
  - All temperatures use scale ×0.1 (raw 500 = 50.0°C) unless noted
  - Disconnected sensors return 0x8042 (32834) or 0x8044 (32836)
  - Overnight monitoring proved HR[72-76], HR[187-189] are NOT maintained
    by the heat pump — they are WRITTEN by the tablet app. Always 0 on clean bus.
  - ASCII strings use swapped byte order (lo byte = first char, hi byte = second char)
  - Confidence levels: CONFIRMED (matched with app + overnight), LIKELY (strong
    pattern/correlation), TENTATIVE (needs verification), DISPROVEN (contradicted)

Firmware strings (from controller tablet):
  - Internal PCB: X1.HL087A.K05.503-1.V100B25  → found at HR[260-269]
  - External PCB: X1.HL081B.K05.001-1.V100A03   → NOT on slave ID 1
  - Driver board:  X1.VF281A.K51.V100A5           → NOT on slave ID 1
  - Hardware:      1GDNET60102KM070_WO11_4C        → NOT on slave ID 1
  - Software:      NET-DK-L1011-O-V1.6.5           → NOT on slave ID 1
"""

DEFAULT_SLAVE_ID = 1

# Special values
SENSOR_DISCONNECTED_1 = 32834  # 0x8042 - sensor not connected
SENSOR_DISCONNECTED_2 = 32836  # 0x8044 - sensor not connected

# === HOLDING REGISTERS (FC03/FC06/FC16) ===
# These contain both configuration/setpoints (writable) and mirrored sensor data.
HOLDING_REGISTERS: dict[int, dict] = {
    # ─── Operating Mode / Configuration ───
    0: {
        "name": "operating_mode",
        "unit": None,
        "scale": 1,
        "description": "Operating mode (4=heating observed). Needs more investigation.",
        "writable": True,
        "confidence": "TENTATIVE",
    },
    1: {
        "name": "water_outlet_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "Water outlet temperature. Clean-bus overnight: 0-33.6°C range, "
                       "mirrors HR[776] and HR[1301]. NOT silent_mode as previously thought. "
                       "Goes to 0 when compressor off.",
        "confidence": "CONFIRMED",
    },

    # ─── Temperature Setpoints ───
    3: {
        "name": "water_outlet_temp_alt",
        "unit": "°C",
        "scale": 0.1,
        "description": "Water outlet temp (alternative). Clean-bus: 11.7-33.6°C range, "
                       "never goes to 0 (retains last value when compressor off).",
        "confidence": "LIKELY",
    },
    4: {
        "name": "heating_target_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "Heating target temperature. App: 'Doeltemperatuur verwarming: 50°C' → raw 500",
        "writable": True,
        "min": 200,  # 20.0°C
        "max": 600,  # 60.0°C
        "confidence": "CONFIRMED",
    },
    94: {
        "name": "cooling_target_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "Cooling target temperature. App: 'Koeldoeltemp: 10°C' → raw 100. "
                       "Clean-bus: static 1000 (100.0°C) — likely a max/disabled sentinel.",
        "writable": True,
        "confidence": "TENTATIVE",
    },
    95: {
        "name": "heating_target_temp_zone_b",
        "unit": "°C",
        "scale": 0.1,
        "description": "Zone B heating target. App: 'Doeltemperatuur verwarming Zone_B: 30°C' → raw 300. "
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
        "description": "DHW max temperature limit. Raw 666 = 66.6°C. Clean-bus: static 666.",
        "writable": True,
        "confidence": "TENTATIVE",
    },

    # ─── Evaporator/Condenser Target Mirrors (HR[125-130]) ───
    125: {
        "name": "evaporator_target_mirror",
        "unit": "°C",
        "scale": 0.1,
        "description": "Evaporator target temp mirror (= HR[38]). Same discrete steps. "
                       "Clean-bus: 100% match with HR[38] across all 477 cycles.",
        "confidence": "CONFIRMED",
    },
    126: {
        "name": "condenser_target_mirror",
        "unit": "°C",
        "scale": 0.1,
        "description": "Condenser target temp mirror (= HR[39]). "
                       "Clean-bus: 100% match with HR[39] across all 477 cycles.",
        "confidence": "CONFIRMED",
    },
    129: {
        "name": "pressure_or_rpm_129",
        "unit": None,
        "scale": 1,
        "description": "Pressure (kPa) or compressor RPM metric. Clean-bus: 1627-2492. "
                       "Similar range to HR[19]. Active only when compressor running.",
        "confidence": "TENTATIVE",
    },
    130: {
        "name": "pressure_or_rpm_130",
        "unit": None,
        "scale": 1,
        "description": "Pressure (kPa) or compressor RPM metric. Clean-bus: 1606-2503. "
                       "Similar range to HR[20]. Active only when compressor running.",
        "confidence": "TENTATIVE",
    },

    # ─── Pump Feedback and Energy Accumulators ───
    147: {
        "name": "pump_feedback",
        "unit": "%",
        "scale": 0.1,
        "description": "Pump feedback signal. Clean-bus: 31.4-32.3% range. "
                       "Mirrors HR[1355]. App: 'Feedbacksignaal omvormerwaterpomp 31.90%%'.",
        "confidence": "CONFIRMED",
    },
    163: {
        "name": "energy_accumulator_1",
        "unit": "Wh",
        "scale": 1,
        "description": "Energy accumulator 1. Clean-bus: 18434→21946 (Δ=3512 over 2h27m, ~1433/hr). "
                       "Continuously growing counter. Likely heating energy (Wh).",
        "confidence": "CONFIRMED",
    },
    164: {
        "name": "energy_accumulator_2",
        "unit": "Wh",
        "scale": 1,
        "description": "Energy accumulator 2. Clean-bus: 18449→21964 (Δ=3515 over 2h27m, ~1435/hr). "
                       "Grows at same rate as HR[163]. Possibly cooling energy or total.",
        "confidence": "CONFIRMED",
    },
    165: {
        "name": "energy_accumulator_3",
        "unit": "Wh",
        "scale": 1,
        "description": "Energy accumulator 3. Clean-bus: 18227→21751 (Δ=3524 over 2h27m, ~1438/hr). "
                       "Grows at same rate as HR[163-164]. Possibly total energy.",
        "confidence": "CONFIRMED",
    },

    # ─── DISPROVEN Tablet-Written Registers (HR[187-189]) ───

    # ─── System Status (mirrored sensor data, read via holding registers) ───
    5: {
        "name": "buffer_tank_lower_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "Buffer tank lower temperature sensor. App: 'buffertank onderste: 51.7°C' → raw 517. "
                       "Clean-bus: static 385 = 38.5°C (setpoint, not live sensor?).",
        "confidence": "CONFIRMED",
    },
    8: {
        "name": "system_water_temp_1",
        "unit": "°C",
        "scale": 0.1,
        "description": "System water temperature 1 (33.6°C at scan). Possibly return water temp.",
        "confidence": "TENTATIVE",
    },
    9: {
        "name": "system_water_temp_2",
        "unit": "°C",
        "scale": 0.1,
        "description": "System water temperature 2 (33.6°C at scan). Possibly return water temp 2.",
        "confidence": "TENTATIVE",
    },
    11: {
        "name": "high_pressure_raw",
        "unit": "kPa",
        "scale": 0.1,
        "description": "High side pressure raw (5172 = 517.2 kPa at scan). Different scale from IR[33]. "
                       "Overnight2: range 386.7-562.5, 2627 changes — one of the top changers.",
        "confidence": "TENTATIVE",
    },
    12: {
        "name": "low_pressure_raw",
        "unit": "kPa",
        "scale": 0.1,
        "description": "Low side pressure raw (5166 = 516.6 kPa at scan). Different scale from HR[32]. "
                       "Overnight2: range 400.8-562.5, 2644 changes — one of the top changers.",
        "confidence": "TENTATIVE",
    },

    # ─── Primary Sensor Block (HR[16-42]) — live sensor data from outdoor unit ───
    # These registers are the PRIMARY source of sensor readings.
    # They are mirrored in HR[1000-1079] and HR[1283-1409].
    16: {
        "name": "compressor_metric_16",
        "unit": None,
        "scale": 0.1,
        "description": "Compressor-related metric. Clean-bus: 0-548.5 range. "
                       "Only active when compressor running. Correlates with HR[25].",
        "confidence": "TENTATIVE",
    },
    19: {
        "name": "high_pressure_kpa",
        "unit": "kPa",
        "scale": 1,
        "description": "High side pressure (kPa, R290). Clean-bus: 1583-2203. "
                       "Mirrors HR[129]. Maps to ~15.8-22.0 bar via R290 tables.",
        "confidence": "LIKELY",
    },
    20: {
        "name": "low_pressure_kpa",
        "unit": "kPa",
        "scale": 1,
        "description": "Low side pressure (kPa, R290). Clean-bus: 2987-4093. "
                       "Mirrors HR[130]. Could also be high-side (check R290 pressure range).",
        "confidence": "LIKELY",
    },
    22: {
        "name": "ambient_temperature",
        "unit": "°C",
        "scale": 0.1,
        "description": "Outdoor ambient temperature. Clean-bus: 11.5-19.7°C range, 74 unique. "
                       "Mirrors HR[1351], HR[3350]. Matches IR[22] and app '0#Omgevingstemp.'.",
        "confidence": "CONFIRMED",
    },
    23: {
        "name": "fin_coil_temperature",
        "unit": "°C",
        "scale": 0.1,
        "description": "Fin/coil (evaporator) temperature. Clean-bus: 4.0-19.3°C range. "
                       "Mirrors HR[1303]. App: '0#Vinnen temp'.",
        "confidence": "CONFIRMED",
    },
    24: {
        "name": "suction_temperature",
        "unit": "°C",
        "scale": 0.1,
        "description": "Compressor suction temperature. Clean-bus: 4.5-29.0°C range. "
                       "Mirrors HR[1305]. App: '0#Zuigtemp'.",
        "confidence": "CONFIRMED",
    },
    25: {
        "name": "discharge_pressure_or_temp",
        "unit": None,
        "scale": 0.1,
        "description": "Discharge pressure or temp metric. Clean-bus: 43.8-94.0 (×0.1). "
                       "Mirrors HR[1304]. Very active: 541+ unique values in overnight2.",
        "confidence": "LIKELY",
    },
    31: {
        "name": "signed_metric_31",
        "unit": None,
        "scale": 0.1,
        "description": "Signed int16. Clean-bus: range -33.2 to -32.8 (nearly constant). "
                       "Possibly a calibration offset or sensor delta.",
        "signed": True,
        "confidence": "TENTATIVE",
    },
    32: {
        "name": "low_pressure",
        "unit": "bar",
        "scale": 0.1,
        "description": "Low pressure value. App: '0#Lage drukwaarde: 7.30 bar' → raw 73. "
                       "Clean-bus: 4.0-8.1 bar. Mirrors HR[1310]. "
                       "Overnight2: 94.3% exact match with IR[32].",
        "confidence": "CONFIRMED",
    },
    33: {
        "name": "high_pressure",
        "unit": "bar",
        "scale": 0.1,
        "description": "High pressure value. App: '0#Hoge drukwaarde: 7.20 bar' → raw 72. "
                       "Clean-bus: 7.5-25.0 bar. Mirrors HR[1311]. "
                       "Overnight2: 94.8% exact match with IR[33].",
        "confidence": "CONFIRMED",
    },
    35: {
        "name": "superheat_or_subcool",
        "unit": "°C",
        "scale": 0.1,
        "description": "Superheat or subcooling. Clean-bus: 1.8-23.4°C range. "
                       "Mirrors HR[1308]. Changes with compressor operation.",
        "confidence": "LIKELY",
    },
    36: {
        "name": "discharge_temperature",
        "unit": "°C",
        "scale": 0.1,
        "description": "Compressor discharge temperature. Clean-bus: 20.5-70.3°C range. "
                       "Mirrors HR[1309] and HR[773]. App: '0#Uitlaattemp'.",
        "confidence": "CONFIRMED",
    },
    38: {
        "name": "evaporator_target_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "Evaporator target temperature. Discrete steps: 0,30,36,42,46,48,50,70°C. "
                       "Mirrors HR[125], HR[1034], HR[1319], HR[1361]. "
                       "Compressor shutdown profile: 70→50→48→44→39→33→30→0°C.",
        "confidence": "CONFIRMED",
    },
    39: {
        "name": "condenser_target_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "Condenser/water target temperature. Clean-bus: 0-70.3°C range. "
                       "Mirrors HR[126], HR[1045], HR[1320], HR[1372].",
        "confidence": "CONFIRMED",
    },
    40: {
        "name": "plate_hx_inlet_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "Plate heat exchanger inlet temperature. Clean-bus: 24.9-36.3°C. "
                       "Mirrors HR[1035], HR[1323], HR[1362]. Exact mirror confirmed.",
        "confidence": "CONFIRMED",
    },
    41: {
        "name": "compressor_power",
        "unit": None,
        "scale": 1,
        "description": "Compressor power or speed metric. Clean-bus: 0-1914. "
                       "Mirrors HR[1040], HR[1321], HR[1367]. 0 = compressor off. "
                       "Unit unclear (not RPM, not Hz — possibly 0.1W or control signal).",
        "confidence": "CONFIRMED",
    },
    42: {
        "name": "superheat",
        "unit": "°C",
        "scale": 0.1,
        "description": "Superheat. Clean-bus: 0-11.1°C range. "
                       "Mirrors HR[1038], HR[1322], HR[1365]. Exact mirror confirmed.",
        "confidence": "CONFIRMED",
    },
    43: {
        "name": "compressor_max_frequency",
        "unit": "rpm",
        "scale": 1,
        "description": "Compressor max frequency/speed limit. Static 7000. "
                       "Clean-bus: confirmed static.",
        "confidence": "LIKELY",
    },

    # ─── Pump / Flow Sensors ───
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
        "description": "Pump flow rate. Clean-bus: 2021-2079 L/h range. "
                       "Mirrors HR[1353]. App: 'Omvormer waterpomp stroomsnelheid: 2053L/H'.",
        "confidence": "CONFIRMED",
    },

    # ─── Signed PID Registers (HR[56-69]) ───
    # These registers contain signed int16 values near zero.
    # Likely PID controller error/integral terms for compressor regulation.
    56: {
        "name": "pid_error_1",
        "unit": None,
        "scale": 0.1,
        "description": "Signed PID error/integral term 1. Clean-bus: -6.3 to +0.4 range.",
        "signed": True,
        "confidence": "LIKELY",
    },
    60: {
        "name": "pid_error_2",
        "unit": None,
        "scale": 0.1,
        "description": "Signed PID error/integral term 2. Clean-bus: similar range to HR[56].",
        "signed": True,
        "confidence": "LIKELY",
    },
    64: {
        "name": "pid_error_3",
        "unit": None,
        "scale": 0.1,
        "description": "Signed PID error/integral term 3. Clean-bus: -2.6 to 0.",
        "signed": True,
        "confidence": "LIKELY",
    },
    69: {
        "name": "pid_error_4",
        "unit": None,
        "scale": 0.1,
        "description": "Signed PID error/integral term 4. Clean-bus: -2.6 to 0.",
        "signed": True,
        "confidence": "LIKELY",
    },
    71: {
        "name": "floor_heating_inlet_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "Floor heating water inlet temp. App: 'Waterinlaattemp. vloerverwarming: -3270.00' (disconnected). "
                       "Clean-bus: 0x8044 (disconnected sensor). Previous 0.1-20°C values were display artifacts.",
        "confidence": "CONFIRMED",
    },
    72: {
        "name": "tablet_written_72",
        "unit": None,
        "scale": 1,
        "description": "DISPROVEN as temperature. Written by tablet only. "
                       "Clean-bus: always 0 (display disconnected).",
        "confidence": "DISPROVEN",
    },
    73: {
        "name": "tablet_written_73",
        "unit": None,
        "scale": 1,
        "description": "DISPROVEN as solar boiler temp. Written by tablet only. "
                       "Clean-bus: always 0.",
        "confidence": "DISPROVEN",
    },
    74: {
        "name": "tablet_written_74",
        "unit": None,
        "scale": 1,
        "description": "DISPROVEN as buffer tank upper temp. Written by tablet only. "
                       "Clean-bus: always 0.",
        "confidence": "DISPROVEN",
    },
    75: {
        "name": "tablet_written_75",
        "unit": None,
        "scale": 1,
        "description": "DISPROVEN as buffer tank lower temp 2. Written by tablet only. "
                       "Clean-bus: always 0.",
        "confidence": "DISPROVEN",
    },
    76: {
        "name": "tablet_written_76",
        "unit": None,
        "scale": 1,
        "description": "DISPROVEN as total water outlet temp. Written by tablet only. "
                       "Clean-bus: always 0.",
        "confidence": "DISPROVEN",
    },
    77: {
        "name": "subcooling",
        "unit": "°C",
        "scale": 0.1,
        "description": "Subcooling temperature. Clean-bus: 0-5.6°C range. "
                       "Mirrors HR[783]. Small values typical for subcooling.",
        "confidence": "LIKELY",
    },
    78: {
        "name": "suction_superheat",
        "unit": "°C",
        "scale": 0.1,
        "description": "Suction superheat. Clean-bus: 0-45.0°C range. "
                       "Mirrors HR[785].",
        "confidence": "LIKELY",
    },

    # ─── Setpoints / Parameters (HR[94-103]) ───
    72: {
        "name": "system_total_water_outlet_temp_sensor",
        "unit": "°C",
        "scale": 0.1,
        "description": "System total water outlet temp sensor. App: 'Systeem totale wateruitlaattemperatuursensor: 30.90°C' → raw ~310. "
                       "DISPROVEN as temperature: Overnight1 values 0-23 (4 unique). "
                       "Overnight2 values 0, 1, 10 (3 unique). Tiny flag/enum values, not a maintained sensor.",
        "confidence": "DISPROVEN",
    },
    73: {
        "name": "solar_boiler_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "Solar boiler temperature. App: 'Temperatuur zonneboiler: -3270.00' (disconnected). "
                       "Overnight: values 0-10, 2 unique - NOT a temperature.",
        "confidence": "DISPROVEN",
    },
    74: {
        "name": "buffer_tank_upper_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "Buffer tank upper temperature sensor. App: 'Buffertank bovenste: 51.60°C' → raw ~517. "
                       "DISPROVEN: Overnight showed values 0-8 (2 unique) - NOT a temperature. "
                       "Likely written by tablet app.",
        "confidence": "DISPROVEN",
    },
    75: {
        "name": "buffer_tank_lower_temp_2",
        "unit": "°C",
        "scale": 0.1,
        "description": "Buffer tank lower temperature (second reading). 51.7°C at scan. "
                       "DISPROVEN: Overnight showed values 0-2 (2 unique) - NOT a temperature.",
        "confidence": "DISPROVEN",
    },
    76: {
        "name": "total_water_outlet_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "Total water outlet temp. App: 'Totale wateruitlaattemp: 50.40°C' → raw ~505. "
                       "DISPROVEN: Overnight showed values 0-10 (2 unique) - NOT a temperature.",
        "confidence": "DISPROVEN",
    },
    187: {
        "name": "room_temperature",
        "unit": "°C",
        "scale": 0.1,
        "description": "Room temperature. App: 'Kamertemp.: 21.80°C' → raw 218. "
                       "DISPROVEN as live sensor: Overnight1 ALWAYS 0 (781 reads). "
                       "Overnight2: values [0, 1, 1000]. Value 1000=100.0°C is a max setpoint flag, not a live reading. "
                       "Real room temp is written by tablet to HR[5010].",
        "confidence": "DISPROVEN",
    },
    188: {
        "name": "dhw_tank_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "DHW tank temperature. App: 'Warmwatertanktemp.: -3270.00' (disconnected). "
                       "DISPROVEN: Overnight1 ALWAYS 0. "
                       "Overnight2: values [0, 1, 300]. Value 300=30.0°C could be DHW setpoint mirror, not a live sensor.",
        "confidence": "DISPROVEN",
    },
    189: {
        "name": "ambient_temperature",
        "unit": "°C",
        "scale": 0.1,
        "description": "Outdoor ambient temperature. App: 'Omgevingstemperatuur: 14.10°C' → raw ~143. "
                       "DISPROVEN: Overnight was ALWAYS 0. Real outdoor temp is in IR[22]/IR[138]. "
                       "This register is only populated when the tablet app is active.",
        "confidence": "DISPROVEN",
    },

    # ─── Firmware / Internal PCB Version (ASCII, swapped byte order, 2 chars per register) ───
    # Full string: "X1.HL087A.K05.503-1.V100B25" (Internal PCB version)
    # HR[256-259] contain "X1.HL087" but were not captured in scan (likely read errors)
    # HR[260-269] contain "A.K05.503-1.V100B25" (confirmed via swapped byte decode)
    # HR[520-525] repeat the tail "-3.1.V100B2.5" (zone-repeat block)
    #
    # Firmware strings NOT on slave ID 1 (scanned 0-1999 completely):
    #   External PCB: X1.HL081B.K05.001-1.V100A03
    #   Driver board:  X1.VF281A.K51.V100A5
    #   Hardware:      1GDNET60102KM070_WO11_4C
    #   Software:      NET-DK-L1011-O-V1.6.5
    # These 4 strings likely come from the controller tablet (different slave ID).
    260: {
        "name": "internal_pcb_version_ascii",
        "description": "Internal PCB version ASCII block (HR[260-269], swapped byte order). "
                       "Decodes to tail of 'X1.HL087A.K05.503-1.V100B25'",
        "confidence": "CONFIRMED",
    },

    # ─── Extended Range: System Configuration (HR[600-846]) ───
    600: {
        "name": "system_param_600",
        "unit": None,
        "scale": 1,
        "description": "System parameter (75). Possibly module count or zone config.",
        "confidence": "TENTATIVE",
    },
    601: {
        "name": "system_param_601",
        "unit": None,
        "scale": 1,
        "description": "System parameter (78='N'). Recurring value throughout register space.",
        "confidence": "TENTATIVE",
    },
    616: {
        "name": "defrost_target_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "Possible defrost target temperature. Raw 390 = 39.0°C.",
        "confidence": "TENTATIVE",
    },
    626: {
        "name": "dhw_setpoint",
        "unit": "°C",
        "scale": 0.1,
        "description": "DHW or system setpoint. Raw 504 = 50.4°C.",
        "confidence": "TENTATIVE",
    },
    641: {
        "name": "outdoor_temp_config",
        "unit": "°C",
        "scale": 0.1,
        "description": "Outdoor temp reference or weather curve point. Raw 200 = 20.0°C.",
        "confidence": "TENTATIVE",
    },
    773: {
        "name": "compressor_discharge_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "Compressor discharge temperature. "
                       "Overnight1: 40.6-50.2°C range, correlated with HR[768]. "
                       "Overnight2: 0-56.2°C range, 167 unique values. Goes to 0 when compressor off.",
        "confidence": "CONFIRMED",
    },
    811: {
        "name": "pump_max_speed",
        "unit": "rpm",
        "scale": 1,
        "description": "Pump maximum speed setting. Raw 6800 (matches IR[53] pump speed).",
        "confidence": "LIKELY",
    },
    812: {
        "name": "pump_min_speed",
        "unit": "rpm",
        "scale": 1,
        "description": "Pump minimum speed setting? Raw 1550.",
        "confidence": "TENTATIVE",
    },
    813: {
        "name": "defrost_interval",
        "unit": "s",
        "scale": 1,
        "description": "Timer or defrost interval? Raw 3600 (=1 hour in seconds).",
        "confidence": "TENTATIVE",
    },
    814: {
        "name": "system_temp_limit_814",
        "unit": "°C",
        "scale": 0.1,
        "description": "System temperature limit. Raw 390 = 39.0°C.",
        "confidence": "TENTATIVE",
    },
    816: {
        "name": "heating_target_mirror",
        "unit": "°C",
        "scale": 0.1,
        "description": "Heating target temp mirror. Raw 500 = 50.0°C (same as HR[4]).",
        "confidence": "LIKELY",
    },

    # ─── Extended Range: Live Compressor Data (HR[1279-1376]) ───
    # This block contains rich real-time operational data. Many registers go to 0
    # or disconnected marker (32836) when compressor is off.
    1283: {
        "name": "operational_status_mirror",
        "unit": None,
        "scale": 1,
        "description": "Mirror of HR[768] operational status. Same range 0-2080. "
                       "Also mirrored in HR[3331], HR[6400], HR[6464].",
        "confidence": "CONFIRMED",
    },
    1301: {
        "name": "compressor_water_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "Compressor block water temp. Raw 206 = 20.6°C. "
                       "Overnight2: 0-32836 range, 228 unique. Shows disconnected marker when off.",
        "confidence": "TENTATIVE",
    },
    1304: {
        "name": "compressor_live_metric",
        "unit": None,
        "scale": 0.1,
        "description": "Compressor live measurement. Overnight2: 0-32836 range, 541 unique values (most variable register). "
                       "Shows disconnected marker when off. Possibly current or power.",
        "confidence": "TENTATIVE",
    },
    1309: {
        "name": "compressor_discharge_temp_live",
        "unit": "°C",
        "scale": 0.1,
        "description": "Live compressor discharge temp. Overnight2: 16.8-72.1°C range, 281 unique values. "
                       "Wide range matches discharge temp behavior.",
        "confidence": "LIKELY",
    },
    1319: {
        "name": "evaporator_target_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "Evaporator target temp. Raw 300 = 30.0°C.",
        "confidence": "TENTATIVE",
    },
    1321: {
        "name": "compressor_speed_or_power",
        "unit": None,
        "scale": 0.1,
        "description": "Compressor speed or power metric. Overnight2: 0-193.6 range, 367 unique values (highest unique count in block). "
                       "Active during compressor operation.",
        "confidence": "TENTATIVE",
    },
    1338: {
        "name": "mains_voltage",
        "unit": "V",
        "scale": 0.1,
        "description": "Mains supply voltage. Overnight2: 220.2-245.9V range, 116 unique values. "
                       "Matches expected Dutch mains voltage (230V ±10%).",
        "confidence": "CONFIRMED",
    },
    1348: {
        "name": "plate_hx_inlet_live",
        "unit": "°C",
        "scale": 0.1,
        "description": "Live plate HX inlet temp. Overnight2: 38.4-55.1°C range, 156 unique values.",
        "confidence": "LIKELY",
    },
    1349: {
        "name": "plate_hx_temp_2",
        "unit": "°C",
        "scale": 0.1,
        "description": "Second plate HX temperature. Overnight2: 40.1-55.3°C range, 144 unique values.",
        "confidence": "LIKELY",
    },
    1350: {
        "name": "plate_hx_outlet_live",
        "unit": "°C",
        "scale": 0.1,
        "description": "Live plate HX outlet temp. Overnight2: 40.2-55.5°C range, 145 unique values.",
        "confidence": "LIKELY",
    },
    1351: {
        "name": "ambient_temp_mirror",
        "unit": "°C",
        "scale": 0.1,
        "description": "Ambient temperature mirror in compressor block. Overnight2: 6.7-16.4°C range, 98 unique values. "
                       "Matches IR[22] ambient temp behavior exactly.",
        "confidence": "CONFIRMED",
    },
    1352: {
        "name": "pump_speed_live",
        "unit": "rpm",
        "scale": 1,
        "description": "Live pump speed. Raw 6800 (matches IR[53] and HR[811]). Constant 6800.",
        "confidence": "CONFIRMED",
    },
    1353: {
        "name": "pump_flow_rate_live",
        "unit": "L/h",
        "scale": 1,
        "description": "Live pump flow rate. Overnight2: 2021-2111 range, 12 unique values. "
                       "Matches IR[54] pump flow rate pattern.",
        "confidence": "LIKELY",
    },
    1355: {
        "name": "pump_feedback_live",
        "unit": "%",
        "scale": 0.1,
        "description": "Live pump feedback signal. Raw 319 = 31.9% (matches IR[142]). "
                       "Overnight2: 31.4-32.8% range.",
        "confidence": "CONFIRMED",
    },
    1358: {
        "name": "superheat_or_subcool",
        "unit": "°C",
        "scale": 0.1,
        "description": "Possible superheat or subcooling value. Overnight2: 0-94.0°C range, 146 unique values.",
        "confidence": "TENTATIVE",
    },
    1368: {
        "name": "compressor_speed_high",
        "unit": None,
        "scale": 0.1,
        "description": "Compressor speed or power (high range). Overnight2: 312.8-409.9 range, 166 unique values, "
                       "1962 changes. Strongly correlated with HR[1304].",
        "confidence": "TENTATIVE",
    },

    # ─── Overnight-discovered: Status/Operational Registers ───
    768: {
        "name": "operational_status",
        "unit": None,
        "scale": 1,
        "description": "Operating status register. "
                       "Overnight1: values 0 (standby), 1 (starting), 4 (running), 7000 (rare). "
                       "Overnight2: mostly 4 (2650x), also 1/37/72-75/105-107/2080. "
                       "Strongly correlated with HR[773]. 3979 total changes — top changer. "
                       "Mirrored in HR[1283], HR[3331], HR[6400], HR[6464].",
        "confidence": "CONFIRMED",
    },
    776: {
        "name": "water_outlet_temp_live",
        "unit": "°C",
        "scale": 0.1,
        "description": "Water outlet temperature (live from outdoor unit). "
                       "Overnight1: 18.4-33.8°C range, varies with compressor cycles. "
                       "Overnight2: 0-43.2°C range, 238 unique values. Goes to 0 when compressor off.",
        "confidence": "CONFIRMED",
    },
    910: {
        "name": "operation_flag",
        "unit": None,
        "scale": 1,
        "description": "Binary operational flag (0/1). Overnight1: 3988×=0, 1520×=1, also 7000 (1×). "
                       "Overnight2: captured via passive only (4695 readings), 2122 changes. "
                       "Strongly correlated with HR[911].",
        "confidence": "CONFIRMED",
    },
    911: {
        "name": "operation_setpoint",
        "unit": "°C",
        "scale": 0.1,
        "description": "Setpoint or parameter, coupled with HR[910]. "
                       "Overnight: values 0, 300, 7000 (3 unique, 2270 reads). "
                       "300 = 30.0°C = zone B target?",
        "confidence": "TENTATIVE",
    },

    # ─── Overnight2-discovered: Additional Operational Registers ───
    769: {
        "name": "operational_sub_status",
        "unit": None,
        "scale": 1,
        "description": "Operational sub-status. Overnight2: 0-246 range, 10 unique values. "
                       "Changes with HR[768].",
        "confidence": "LIKELY",
    },
    777: {
        "name": "compressor_metric_777",
        "unit": None,
        "scale": 1,
        "description": "Compressor metric (speed or power?). Overnight2: 0-16439 range, 251 unique values. "
                       "Value 16439 appears in multiple registers and may be a special code.",
        "confidence": "TENTATIVE",
    },
    785: {
        "name": "compressor_metric_785",
        "unit": None,
        "scale": 0.1,
        "description": "Compressor metric. Overnight2: 0-388.5 range, 244 unique values. Highly variable.",
        "confidence": "TENTATIVE",
    },

    # ─── Overnight-discovered: Tablet Communication Registers ───
    5000: {
        "name": "clock_year",
        "unit": None,
        "scale": 1,
        "description": "Clock sync - year. Tablet writes via FC16 (write_multiple). "
                       "Overnight1: 6 writes, value=2026. "
                       "Overnight2: only 2 writes (00:41 and 01:39), data=0x07EA=2026. "
                       "Tablet syncs clock infrequently.",
        "writable": True,
        "confidence": "CONFIRMED",
    },
    5001: {
        "name": "clock_month",
        "unit": None,
        "scale": 1,
        "description": "Clock sync - month. Tablet writes via FC16. Value=3 (March).",
        "writable": True,
        "confidence": "CONFIRMED",
    },
    5002: {
        "name": "clock_day",
        "unit": None,
        "scale": 1,
        "description": "Clock sync - day. Tablet writes via FC16. Values 15, 16.",
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
        "description": "Clock sync - flag/seconds. Always 1 in observed writes.",
        "writable": True,
        "confidence": "CONFIRMED",
    },
    5010: {
        "name": "room_temperature_from_tablet",
        "unit": "°C",
        "scale": 0.1,
        "description": "Room temperature written by controller tablet via FC06. "
                       "Overnight1: 683 writes, values 215-223 (21.5-22.3°C), avg interval 48s. "
                       "Overnight2: 571 writes, values 216-222 (21.6-22.2°C). "
                       "Most common: 217 (168x), 218 (119x), 219 (112x). "
                       "Active reads of this register return garbage (36864, 59392) due to bus collision — "
                       "passive sniffing is the only reliable way to read this value.",
        "writable": True,
        "confidence": "CONFIRMED",
    },
}

# === SHADOW / MIRROR REGISTER RANGES (Overnight Discovery) ===
# The tablet polls registers far beyond the initial 0-1999 scan range.
# Three shadow/mirror ranges were discovered via passive and active monitoring:
#
# HR[3331-3375]: Shadow range — mirrors operational block HR[768-821] + compressor block.
#   - HR[3331]: Status (0-36864), mirrors HR[768]/HR[1283]. 720 passive reads.
#   - HR[3340]: 2.3-16439 (includes special code 16439)
#   - HR[3350]: 1.3-16.4°C — ambient temp mirror (101 unique, matches IR[22])
#   - HR[3353]: 0-40.8°C — 133 unique values, temperature
#   - HR[3355-3357]: 0-56.3°C — plate HX temps (matches HR[1348-1350])
#   - HR[3368]: 0.1-34.3 — 180 unique values
#   - HR[3371]: 0-94.0 — 148 unique values (matches HR[1358] superheat range)
#   - Many registers show disconnected markers (32836) = unused sensor slots
#
# HR[6400-6447]: Second shadow range — similar to HR[3331], possibly zone/module 2.
#   - HR[6400]: Status (0-2080), 71 passive reads
#   - HR[6419]: 0-15.5°C — outdoor temp (9 unique)
#   - HR[6424-6426]: 0-55.5°C — plate HX temps
#   - HR[6443-6447]: Constants [6800, 1550, 3600, 390, 8] — match HR[811-815]
#
# HR[6464-6517]: Third shadow range — more granular copy of operational data.
#   - HR[6464]: Status (0-2080), 10 unique values, 125 passive reads
#   - HR[6483]: 0-16.4°C — ambient temp (25 unique, most detailed shadow)
#   - HR[6488-6490]: 0-55.4°C — plate HX temps (20+ unique each)
#   - HR[6507]: 99.9-680.0 — pump speed constant/match
#
# All three shadows appear to be periodic snapshots of the same operational data,
# possibly for different controller modules or historical logging buffers.
# Reading them is NOT necessary — the primary registers (HR[768-821], HR[1283-1370])
# contain the same live data more reliably.

# === CORRELATION DATA (Overnight Discovery) ===
# Strongly correlated register pairs (changed within the same second):
#   HR[910] <-> HR[911]:  840 co-occurrences (operation flag + setpoint)
#   HR[768] <-> HR[773]:  555 co-occurrences (status + compressor discharge temp)
#   HR[1348] <-> HR[1349]: 549 co-occurrences (plate HX temps cluster)
#   HR[3355] <-> HR[3357]: 520 co-occurrences (shadow range plate HX temps)
#   IR[16] <-> IR[17]:     492 co-occurrences (compressor metrics)
#   HR[1304] <-> HR[1368]: 475 co-occurrences (compressor live data pair)
#   HR[1035] <-> HR[1041]: 416 co-occurrences (temperature + compressor)
#
# The top 30 most-changing registers (overnight2, 67,792 total changes):
#   HR[768]:  3,979 changes — operational status
#   HR[12]:   2,644 changes — low pressure raw (kPa)
#   HR[11]:   2,627 changes — high pressure raw (kPa)
#   HR[910]:  2,122 changes — operation flag (0/1)
#   HR[1368]: 1,962 changes — compressor speed/power
#   HR[1304]: 1,709 changes — compressor live metric
#   IR[25]:   1,047 changes — discharge temperature
#   IR[22]:     901 changes — ambient temperature

# === INPUT REGISTERS (Read-only, FC04) ===
# These are read-only sensor/status values from the heat pump.
INPUT_REGISTERS: dict[int, dict] = {
    # ─── Refrigerant Circuit Temperatures ───
    22: {
        "name": "ambient_temperature",
        "unit": "°C",
        "scale": 0.1,
        "description": "Module ambient/outdoor temperature. App: '0#Omgevingstemp.: 14.10°C' → raw ~143",
        "confidence": "CONFIRMED",
    },
    23: {
        "name": "fin_coil_temperature",
        "unit": "°C",
        "scale": 0.1,
        "description": "Fin/coil temperature. App: '0#Vinnen temp: 10.50°C' → raw ~112 at scan (11.2°C, fluctuating)",
        "confidence": "LIKELY",
    },
    24: {
        "name": "suction_temperature",
        "unit": "°C",
        "scale": 0.1,
        "description": "Compressor suction temp. App: '0#Zuigtemp: 24.20°C' → raw ~246 at scan (24.6°C, fluctuating)",
        "confidence": "CONFIRMED",
    },
    25: {
        "name": "discharge_temperature",
        "unit": "°C",
        "scale": 0.1,
        "description": "Compressor discharge temp. App: '0#Uitlaattemp: 41.30°C' → raw ~429 at scan (42.9°C, fluctuating)",
        "confidence": "CONFIRMED",
    },

    # ─── Pressures ───
    32: {
        "name": "low_pressure",
        "unit": "bar",
        "scale": 0.1,
        "description": "Low side pressure. App: '0#Lage drukwaarde: 7.30' → raw 73",
        "confidence": "CONFIRMED",
    },
    33: {
        "name": "high_pressure",
        "unit": "bar",
        "scale": 0.1,
        "description": "High side pressure. App: '0#Hoge drukwaarde: 7.20' → raw 72",
        "confidence": "CONFIRMED",
    },

    # ─── Compressor ───
    # ─── Compressor Metrics (active only when running) ───
    # These registers were originally labeled as pressure in kPa but overnight2 data
    # shows they correlate with compressor activity, NOT with bar pressure readings.
    # IR[16-18] have similar ranges (~0-550), IR[19] has different scale (~0-186),
    # IR[20] yet another (~0-408). Only 290-347 readings vs 1459 for IR[22],
    # confirming they only respond when compressor active.

    # App shows "Compressor snelheid: 0.00rpm". Exact register unknown;
    # needs identification during active compressor operation.
    20: {
        "name": "compressor_metric_e",
        "unit": None,
        "scale": 0.1,
        "description": "Compressor-related metric E. Overnight2: 0-407.5 range, 169 unique values. "
                       "Different scale from IR[16-18].",
        "confidence": "TENTATIVE",
    },

    # ─── Water Circuit / Pump ───
    53: {
        "name": "pump_target_speed",
        "unit": "rpm",
        "scale": 1,
        "description": "Inverter water pump target speed. App: '0# Doelsnelheid omvormerwaterpomp: 6800rpm' → raw 6800",
        "confidence": "CONFIRMED",
    },
    54: {
        "name": "pump_flow_rate",
        "unit": "L/h",
        "scale": 1,
        "description": "Inverter water pump flow rate. App: '0# Omvormer waterpomp stroomsnelheid: 2053L/H' → raw 2053",
        "confidence": "CONFIRMED",
    },
    66: {
        "name": "pump_control_signal",
        "unit": "%",
        "scale": 0.1,
        "description": "Pump control signal. App: '0#Omvormer waterpomp stuursignaal: 5.00%%' → raw 50",
        "confidence": "CONFIRMED",
    },

    # ─── Module 0# Temperatures (sequential block) ───
    134: {
        "name": "module0_sensor_slot",
        "unit": None,
        "scale": 0.1,
        "description": "Module 0 sensor slot. Initially showed 0x8044 (disconnected). "
                       "Overnight2: 0-5.0 range, 3 unique values, 2998 readings. "
                       "Small values suggest a control signal, not a sensor.",
        "confidence": "TENTATIVE",
    },
    135: {
        "name": "plate_hx_inlet_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "0# Plate heat exchanger water inlet temp. App: '0#Waterinlaattemp. platenwisselaar: 49.90°C' → raw ~504",
        "confidence": "CONFIRMED",
    },
    136: {
        "name": "plate_hx_outlet_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "0# Plate heat exchanger water outlet temp. App: '0#Wateruitlaattemp. platenwisselaar: 49.90°C' → raw ~504",
        "confidence": "CONFIRMED",
    },
    137: {
        "name": "module_total_water_outlet_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "0# Total water outlet temp. App: '0#Totale wateruitlaattemp: 49.90°C' → raw ~504",
        "confidence": "CONFIRMED",
    },
    138: {
        "name": "module_ambient_temp",
        "unit": "°C",
        "scale": 0.1,
        "description": "0# Module ambient temp. App: '0#Omgevingstemp.: 14.10°C' → raw ~143",
        "confidence": "CONFIRMED",
    },
    139: {
        "name": "module_pump_target_speed",
        "unit": "rpm",
        "scale": 1,
        "description": "0# Pump target speed (duplicate of IR[53]). Raw 6800",
        "confidence": "CONFIRMED",
    },
    142: {
        "name": "pump_feedback_signal",
        "unit": "%",
        "scale": 0.1,
        "description": "Pump feedback signal. App: '0# Feedbacksignaal omvormerwaterpomp 31.90%%' → raw 319. "
                       "Overnight2: 0-54.4% range, 190 unique values.",
        "confidence": "CONFIRMED",
    },
    141: {
        "name": "module_water_temp_or_flow",
        "unit": "°C",
        "scale": 0.1,
        "description": "Module water temperature or flow metric. "
                       "Overnight2: 0-62.2°C range, 132 unique values, 2983 readings.",
        "confidence": "TENTATIVE",
    },

    # ─── System parameters that also appear in input registers ───
    84: {
        "name": "heating_target_temp_mirror",
        "unit": "°C",
        "scale": 0.1,
        "description": "Mirror of heating target temp (same as HR[4]). App: 'Instelbare doeltemperatuur: 50.00°C' → raw 500",
        "confidence": "CONFIRMED",
    },
    85: {
        "name": "buffer_tank_upper_temp_mirror",
        "unit": "°C",
        "scale": 0.1,
        "description": "Buffer tank upper temp (mirror). Raw 516 = 51.6°C",
        "confidence": "LIKELY",
    },
    95: {
        "name": "zone_b_heating_target_mirror",
        "unit": "°C",
        "scale": 0.1,
        "description": "Zone B heating target (mirror of HR[95]). Raw 300 = 30.0°C",
        "confidence": "CONFIRMED",
    },

    # ─── Miscellaneous system data ───
    16: {
        "name": "compressor_metric_a",
        "unit": None,
        "scale": 0.1,
        "description": "Compressor-related metric A. Previously labeled as high_pressure_kPa but does not match IR[33]. "
                       "Overnight2: 0-548.5 range, 225 unique values. Only active when compressor running. "
                       "Correlates with IR[25] discharge temp. Could be compressor power or speed.",
        "confidence": "TENTATIVE",
    },
    17: {
        "name": "compressor_metric_b",
        "unit": None,
        "scale": 0.1,
        "description": "Compressor-related metric B. Similar pattern to IR[16]. "
                       "Overnight2: 0-547.5 range, 223 unique values. Strongly correlated with IR[16] (492 co-occurrences).",
        "confidence": "TENTATIVE",
    },
    18: {
        "name": "compressor_metric_c",
        "unit": None,
        "scale": 0.1,
        "description": "Compressor-related metric C. Similar pattern to IR[16-17]. "
                       "Overnight2: 0-550.2 range, 229 unique values.",
        "confidence": "TENTATIVE",
    },
    19: {
        "name": "compressor_metric_d",
        "unit": None,
        "scale": 0.1,
        "description": "Compressor-related metric D. Different scale from IR[16-18]. "
                       "Overnight2: 0-185.8 range, 185 unique values. Possibly current (A).",
        "confidence": "TENTATIVE",
    },
}

# === COILS (FC01/FC05/FC15) ===
# Not yet scanned. Needs separate coil/discrete scan.
COILS: dict[int, dict] = {}

# === DISCRETE INPUTS (FC02) ===
# Not yet scanned.
DISCRETE_INPUTS: dict[int, dict] = {}

# === ERROR CODES ===
ERROR_CODES: dict[int, str] = {
    # 0x8042 (32834) and 0x8044 (32836) appear as "sensor disconnected" marker values
    # Exact error code registers not yet identified; needs investigation during fault conditions
}

# === REGISTER BLOCK PATTERNS ===
# The controller repeats register blocks at regular intervals.
# This suggests multiple zones or circuit copies in the register map.
#
# Confirmed repeating patterns (HR[0-9] ≈ HR[570-579]):
#   Offset +570: Almost exact copy (HR[5] differs by 1 = live temp fluctuation)
#
# Input registers also show repeating blocks:
#   IR[135-142] ≈ IR[315-319] ≈ IR[505-512] (module temp/pump data)
#
# Registers needing identification with compressor running:
#   - Compressor speed/frequency register (was 0 during scan)
#   - EEV (expansion valve) opening
#   - Defrost status
#   - Current/power consumption


# === OPERATING MODES ===
OPERATING_MODES: dict[int, str] = {
    # Map mode register values to descriptions
    # 0: "Standby",
    # 1: "Heating",
    # 2: "Cooling",
    # 3: "Domestic Hot Water",
    # 4: "Defrost",
    # ...
}

"""Constants for the BataviaHeat R290 integration."""

DOMAIN = "batavia_heat"
MANUFACTURER = "BataviaHeat"
MODEL = "R290 3-8kW Monobloc"

# === Connection defaults ===
DEFAULT_TCP_PORT = 502
DEFAULT_SLAVE_ID = 1

CONF_HOST = "host"
CONF_TCP_PORT = "tcp_port"
CONF_SLAVE_ID = "slave_id"

# Update interval in seconds
DEFAULT_SCAN_INTERVAL = 30

# Special marker values for disconnected sensors
SENSOR_DISCONNECTED = (32834, 32836)  # 0x8042, 0x8044 → -3270.x°C

# === Register definitions ===
# Discovered via Modbus scanner on 2026-03-15, cross-referenced with EcoHome App.
# Validated with 9-hour overnight combined active+passive monitoring (2026-03-15/16).
# Further validated with 9.4-hour targeted monitoring (2026-03-16/17):
#   851,978 readings, 388 distinct holding + 41 input register addresses.
#
# entity_type: "sensor" = read-only sensor, "number" = writable setpoint,
#              "select" = writable enum, "switch" = writable boolean
#
# IMPORTANT: Overnight monitoring revealed that holding register "sensor" values
# (HR[5,72,74-76,187-189]) are NOT maintained by the heat pump itself. They showed
# 0 or inconsistent values all night. These values are likely written by the
# controller tablet when its app is active. Only Input Registers contain reliable
# real-time sensor data from the heat pump hardware.
#
# HR[768], HR[773], HR[776], HR[1338] are from the operational/compressor block.
# These registers go to 0 when the compressor is off — this is expected behavior.

# ── Holding registers (read/write) - FC03/FC06 ──
HOLDING_REGISTERS: dict[int, dict] = {
    # ─── Writable Setpoints ───
    4: {
        "name": "heating_target_temperature",
        "device_class": "temperature",
        "unit": "°C",
        "scale": 0.1,
        "min": 20.0,
        "max": 60.0,
        "entity_type": "number",
        "icon": "mdi:thermometer",
    },
    # NOTE: Holding register sensors (HR[5,72,74-76,187-189]) were removed after
    # overnight monitoring proved they are NOT maintained by the heat pump.
    # They showed 0 or nonsensical values throughout 9 hours of monitoring.
    # Real sensor data is available only via Input Registers (FC04).

    # ─── Operational Status & Live Sensors (from outdoor unit) ───
    # These go to 0 when compressor is off. This is normal behavior.
    768: {
        "name": "operational_status",
        "device_class": None,
        "unit": None,
        "scale": 1,
        "entity_type": "sensor",
        "icon": "mdi:heat-pump-outline",
    },
    773: {
        "name": "compressor_discharge_temperature",
        "device_class": "temperature",
        "unit": "°C",
        "scale": 0.1,
        "entity_type": "sensor",
    },
    776: {
        "name": "water_outlet_temperature",
        "device_class": "temperature",
        "unit": "°C",
        "scale": 0.1,
        "entity_type": "sensor",
    },
    # ─── Energy & Power Monitoring ───
    # HR[41] (compressor_power), HR[1325] (inverter_current), HR[1338] (mains_voltage),
    # HR[1368] (dc_bus_voltage) removed — HomeWizard kWh meter replaces these.
    1283: {
        "name": "compressor_running",
        "device_class": None,
        "unit": None,
        "scale": 1,
        "entity_type": "binary_sensor",
        "icon": "mdi:heat-pump",
    },

    # ─── Stooklijn / Heating Curve Parameters (M-registers) ───
    # Non-linear HR mapping: M00-M09 = HR[6400+Mxx], M10+ = HR[6400+Mxx+15]
    6402: {
        "name": "max_heating_temperature",
        "device_class": "temperature",
        "unit": "°C",
        "scale": 1,
        "min": 0,
        "max": 85,
        "entity_type": "number",
        "icon": "mdi:thermometer-chevron-up",
    },
    6426: {
        "name": "heating_curve_mode",
        "device_class": None,
        "unit": None,
        "scale": 1,
        "min": 0,
        "max": 17,
        "entity_type": "number",
        "icon": "mdi:chart-line",
    },
    6433: {
        "name": "curve_outdoor_temp_high",
        "device_class": "temperature",
        "unit": "°C",
        "scale": 1,
        "min": -25,
        "max": 35,
        "entity_type": "number",
        "icon": "mdi:thermometer-plus",
    },
    6434: {
        "name": "curve_outdoor_temp_low",
        "device_class": "temperature",
        "unit": "°C",
        "scale": 1,
        "min": -25,
        "max": 35,
        "entity_type": "number",
        "icon": "mdi:thermometer-minus",
    },
    6435: {
        "name": "curve_water_temp_mild",
        "device_class": "temperature",
        "unit": "°C",
        "scale": 1,
        "min": 25,
        "max": 65,
        "entity_type": "number",
        "icon": "mdi:thermometer-water",
    },
    6436: {
        "name": "curve_water_temp_cold",
        "device_class": "temperature",
        "unit": "°C",
        "scale": 1,
        "min": 25,
        "max": 65,
        "entity_type": "number",
        "icon": "mdi:thermometer-water",
    },
}

# ── Calculated sensors (derived from multiple registers) ──
# These don't have a Modbus address — they're computed in sensor.py.
#
# NOTE: HR[163-165] are 16-bit Wh counters that overflow every ~65.5 kWh (~12 days
# at optimized settings). Too unreliable as primary energy source.
# Instead, use HA's Riemann Sum Integration helper on compressor_power (HR[41])
# for accurate kWh tracking with zero data loss.
#
# For delivered thermal energy (kWh), use Riemann Sum Integration on thermal_power.
CALCULATED_SENSORS: dict[str, dict] = {
    "thermal_power": {
        "name": "thermal_power",
        "device_class": "power",
        "unit": "kW",
        "icon": "mdi:fire",
        "description": "Berekend: flow_rate × (outlet − inlet) × 4.186 / 3600",
        # Sources: IR[54] flow L/h, IR[135] inlet °C, IR[136] outlet °C
    },
}

# ── Input registers (read-only) - FC04 ──
INPUT_REGISTERS: dict[int, dict] = {
    # ─── Refrigerant Temperatures ───
    22: {
        "name": "ambient_temperature",
        "device_class": "temperature",
        "unit": "°C",
        "scale": 0.1,
        "entity_type": "sensor",
    },
    23: {
        "name": "fin_coil_temperature",
        "device_class": "temperature",
        "unit": "°C",
        "scale": 0.1,
        "entity_type": "sensor",
    },
    24: {
        "name": "suction_temperature",
        "device_class": "temperature",
        "unit": "°C",
        "scale": 0.1,
        "entity_type": "sensor",
    },
    25: {
        "name": "discharge_temperature",
        "device_class": "temperature",
        "unit": "°C",
        "scale": 0.1,
        "entity_type": "sensor",
    },

    # ─── Pressures ───
    32: {
        "name": "low_pressure",
        "device_class": "pressure",
        "unit": "bar",
        "scale": 0.1,
        "entity_type": "sensor",
    },
    33: {
        "name": "high_pressure",
        "device_class": "pressure",
        "unit": "bar",
        "scale": 0.1,
        "entity_type": "sensor",
    },

    # ─── Water Circuit / Pump ───
    53: {
        "name": "pump_target_speed",
        "device_class": None,
        "unit": "rpm",
        "scale": 1,
        "entity_type": "sensor",
        "icon": "mdi:pump",
    },
    54: {
        "name": "pump_flow_rate",
        "device_class": None,
        "unit": "L/h",
        "scale": 1,
        "entity_type": "sensor",
        "icon": "mdi:water-pump",
    },
    66: {
        "name": "pump_control_signal",
        "device_class": None,
        "unit": "%",
        "scale": 0.1,
        "entity_type": "sensor",
        "icon": "mdi:pump",
    },
    142: {
        "name": "pump_feedback_signal",
        "device_class": None,
        "unit": "%",
        "scale": 0.1,
        "entity_type": "sensor",
        "icon": "mdi:pump",
    },

    # ─── Module 0# Temperatures ───
    135: {
        "name": "plate_hx_inlet_temperature",
        "device_class": "temperature",
        "unit": "°C",
        "scale": 0.1,
        "entity_type": "sensor",
    },
    136: {
        "name": "plate_hx_outlet_temperature",
        "device_class": "temperature",
        "unit": "°C",
        "scale": 0.1,
        "entity_type": "sensor",
    },
    137: {
        "name": "module_water_outlet_temperature",
        "device_class": "temperature",
        "unit": "°C",
        "scale": 0.1,
        "entity_type": "sensor",
    },
    138: {
        "name": "module_ambient_temperature",
        "device_class": "temperature",
        "unit": "°C",
        "scale": 0.1,
        "entity_type": "sensor",
    },
}

# ── Coils (pulse-based, FC05) ──
# BataviaHeat uses separate coils per direction (no toggle).
# Each write is a pulse (0xFF00) — there is no readable coil state.
# The current state is inferred from holding registers.
COILS: dict[int, dict] = {
    1024: {
        "name": "unit_power",
        "on_coil": 1024,
        "off_coil": 1025,
        "entity_type": "switch",
        "icon": "mdi:power",
    },
    1073: {
        "name": "silent_mode",
        "on_coil": 1073,
        "off_coil": 1074,
        "entity_type": "switch",
        "icon": "mdi:volume-off",
    },
    1076: {
        "name": "silent_level_2",
        "on_coil": 1076,
        "off_coil": 1075,
        "entity_type": "switch",
        "icon": "mdi:volume-low",
    },
}

# Discrete inputs (read-only boolean) - FC02
# Not yet discovered. Needs dedicated discrete input scan.
DISCRETE_INPUTS: dict[int, dict] = {}

# Error code mapping (not yet identified)
ERROR_CODES: dict[int, str] = {}


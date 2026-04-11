"""
Online Modbus Register Maps for Midea-based Heat Pumps (incl. Newntide/BataviaHeat)

Combined from multiple open-source projects found on GitHub:

Sources:
  1. Mosibi/Midea-heat-pump-ESPHome (v9.1.0, 118 stars, 38 forks)
     - URL: https://github.com/Mosibi/Midea-heat-pump-ESPHome
     - Files: source/heatpump-base.yaml + source/models/R290-generic.yaml
     - Protocol: Modbus RTU via wired controller port (H1/H2), slave ID 1, 9600 baud
     - Known clones: Airwell, Artel, Ferroli, Kaisai, Inventor, Kaysun, YORK
     - Type: Active read/write (ESPHome modbus_controller)
     - Note: R290 model removes some R32-specific registers

  2. TheMiniatureGamer/Midea_Kaisai_modbus_sniffer
     - URL: https://github.com/TheMiniatureGamer/Midea_Kaisai_modbus_sniffer
     - File: heatpump-monitor.yaml
     - Protocol: Passive Modbus sniffer on same bus (RX only)
     - Note: Same register addresses as Mosibi, but read passively

  3. 0xAHA/Midea-Heat-Pump-HA
     - URL: https://github.com/0xAHA/Midea-Heat-Pump-HA
     - File: custom_components/midea_heatpump_hws/const.py
     - Protocol: Modbus TCP (hot water heater variant)
     - Note: Uses configurable register addresses with defaults,
       default temp scaling: raw * 0.5 - 15.0 (different from other sources!)

IMPORTANT NOTES:
  - The Midea "wired controller" protocol uses holding registers ONLY (FC03/FC06).
    BataviaHeat also has input registers (FC04) — these may not exist in Midea protocol.
  - Midea temperatures in registers 100-141 are in WHOLE DEGREES (°C, signed int16).
    BataviaHeat uses scale ×0.1 throughout. This is a key difference to investigate.
  - The 0xAHA hot water heater uses yet another scaling: raw * 0.5 - 15.0
  - Register addresses listed are Modbus holding register addresses (0-based).
  - All three sources agree on the core register layout (0-274).

Created: 2026-03-17
Purpose: Compare with BataviaHeat register_map.py to identify unknown registers.
"""


# ============================================================================
#  SOURCE 1: Mosibi/Midea-heat-pump-ESPHome (base + R290 model)
#  All registers are HOLDING registers (FC03 read, FC06/FC16 write)
# ============================================================================

MOSIBI_REGISTERS: dict[int, dict] = {

    # ─── Control Registers (0-10) ───

    0: {
        "name": "control_switches",
        "unit": None,
        "scale": 1,
        "type": "bitfield",
        "description": (
            "Control bitfield: "
            "bit 0 = Room temperature control, "
            "bit 1 = Water flow temperature control Zone 1, "
            "bit 2 = Power DHW T5S, "
            "bit 3 = Water flow temperature control Zone 2"
        ),
        "writable": True,
        "r290": True,
    },
    1: {
        "name": "operational_mode",
        "unit": None,
        "scale": 1,
        "type": "select",
        "description": "Operational mode: 1=Auto, 2=Cool, 3=Heat",
        "writable": True,
        "r290": True,
    },
    2: {
        "name": "set_water_temperature_t1s",
        "unit": "°C",
        "scale": 1,
        "type": "packed",
        "description": "Set water temp T1S: low byte = Zone 1, high byte = Zone 2",
        "writable": True,
        "r290": True,
    },
    3: {
        "name": "air_temperature_ts",
        "unit": "°C",
        "scale": 0.5,
        "description": "Air temperature Ts (raw ÷ 2.0 = °C). Config parameter.",
        "writable": True,
        "r290": True,
    },
    4: {
        "name": "set_dhw_tank_temperature_t5s",
        "unit": "°C",
        "scale": 1,
        "description": "Set DHW tank temperature T5S",
        "writable": True,
        "r290": True,
    },
    5: {
        "name": "function_settings",
        "unit": None,
        "scale": 1,
        "type": "bitfield",
        "description": (
            "Function settings bitfield: "
            "bit 4 = Disinfect, "
            "bit 6 = Silent mode, "
            "bit 10 = ECO mode, "
            "bit 12 = Weather compensation Zone 1, "
            "bit 13 = Weather compensation Zone 2"
        ),
        "writable": True,
        "r290": True,
    },
    6: {
        "name": "weather_curve_selection",
        "unit": None,
        "scale": 1,
        "type": "packed",
        "description": "Weather curve: low byte = Zone 1, high byte = Zone 2",
        "writable": True,
        "r290": True,
    },
    7: {
        "name": "quiet_mode_hp",
        "unit": None,
        "scale": 1,
        "type": "switch",
        "description": "Quiet mode for heat pump on/off",
        "writable": True,
        "r290": True,
    },
    8: {
        "name": "holiday_away_mode",
        "unit": None,
        "scale": 1,
        "type": "switch",
        "description": "Holiday/away mode on/off",
        "writable": True,
        "r290": True,
    },
    9: {
        "name": "forced_hydraulic_module_rear_electric_heater_1",
        "unit": None,
        "scale": 1,
        "description": "Forced hydraulic module rear electric heater 1",
        "writable": False,
        "r290": True,
    },
    10: {
        "name": "t_sg_max",
        "unit": "hr",
        "scale": 1,
        "description": "t_SG_MAX (hours)",
        "writable": False,
        "r290": True,
    },

    # ─── Operational / Sensor Data (100-141) ───
    # NOTE: Temperatures here are in WHOLE DEGREES (°C, signed int16)!

    100: {
        "name": "compressor_operating_frequency",
        "unit": "Hz",
        "scale": 1,
        "description": "Compressor operating frequency. 0 = compressor off.",
        "writable": False,
        "r290": True,
    },
    101: {
        "name": "operating_mode_status",
        "unit": None,
        "scale": 1,
        "description": "Operating mode status: 2=Cooling, 3=Heating, 5=DHW Heating, else=OFF/Idle",
        "writable": False,
        "r290": True,
    },
    102: {
        "name": "fan_speed",
        "unit": "r/min",
        "scale": 1,
        "description": "Fan speed in RPM",
        "writable": False,
        "r290": True,
    },
    103: {
        "name": "pmv_openness",
        "unit": "%",
        "scale": 1,  # raw ÷ 4.8 for Kaisai, or calibrate_linear 0-480 → 0-100%
        "description": "PMV (EEV) openness. Raw 0-480 maps to 0-100%. Divide by 4.8.",
        "writable": False,
        "r290": True,
    },
    104: {
        "name": "water_inlet_temperature",
        "unit": "°C",
        "scale": 1,  # signed int16, whole degrees
        "description": "Water inlet temperature (°C, signed int16, whole degrees)",
        "writable": False,
        "r290": True,
    },
    105: {
        "name": "water_outlet_temperature",
        "unit": "°C",
        "scale": 1,
        "description": "Water outlet temperature (°C, signed int16, whole degrees)",
        "writable": False,
        "r290": True,
    },
    106: {
        "name": "condenser_temperature_t3",
        "unit": "°C",
        "scale": 1,
        "description": "Condenser temperature T3 (°C, signed int16)",
        "writable": False,
        "r290": True,
    },
    107: {
        "name": "outdoor_ambient_temperature",
        "unit": "°C",
        "scale": 1,
        "description": "Outdoor ambient temperature (°C, signed int16)",
        "writable": False,
        "r290": True,
    },
    108: {
        "name": "discharge_temperature",
        "unit": "°C",
        "scale": 1,
        "description": "Compressor discharge temperature (°C, signed int16)",
        "writable": False,
        "r290": True,
    },
    109: {
        "name": "return_air_temperature",
        "unit": "°C",
        "scale": 1,
        "description": "Return air / suction temperature (°C, signed int16)",
        "writable": False,
        "r290": True,
    },
    110: {
        "name": "total_water_outlet_temperature_t1",
        "unit": "°C",
        "scale": 1,
        "description": "Total water outlet temperature T1 (°C, signed int16)",
        "writable": False,
        "r290": True,
    },
    111: {
        "name": "system_total_water_outlet_temperature_t1b",
        "unit": "°C",
        "scale": 1,
        "description": "System total water outlet temperature T1B (°C, signed int16)",
        "writable": False,
        "r290": True,
    },
    112: {
        "name": "refrigerant_liquid_side_temperature_t2",
        "unit": "°C",
        "scale": 1,
        "description": "Refrigerant liquid side temperature T2 (°C, signed int16)",
        "writable": False,
        "r290": True,
    },
    113: {
        "name": "refrigerant_gas_side_temperature_t2b",
        "unit": "°C",
        "scale": 1,
        "description": "Refrigerant gas side temperature T2B (°C, signed int16)",
        "writable": False,
        "r290": True,
    },
    114: {
        "name": "room_temperature_ta",
        "unit": "°C",
        "scale": 1,
        "description": "Room temperature Ta (°C, signed int16)",
        "writable": False,
        "r290": True,
    },
    115: {
        "name": "water_tank_temperature_t5",
        "unit": "°C",
        "scale": 1,
        "description": "Water tank temperature T5 (°C, signed int16)",
        "writable": False,
        "r290": True,
    },
    116: {
        "name": "outdoor_unit_high_pressure",
        "unit": "kPa",
        "scale": 1,
        "description": "Outdoor unit high pressure (kPa, unsigned)",
        "writable": False,
        "r290": True,
    },
    117: {
        "name": "outdoor_unit_low_pressure",
        "unit": "kPa",
        "scale": 1,
        "description": "Outdoor unit low pressure (kPa, unsigned)",
        "writable": False,
        "r290": True,
    },
    118: {
        "name": "outdoor_unit_current",
        "unit": "A",
        "scale": 0.1,
        "description": "Outdoor unit current (raw ÷ 10 = Amps)",
        "writable": False,
        "r290": True,
    },
    119: {
        "name": "outdoor_unit_voltage",
        "unit": "V",
        "scale": 1,
        "description": "Outdoor unit voltage (V)",
        "writable": False,
        "r290": True,
    },
    120: {
        "name": "tbt1",
        "unit": "°C",
        "scale": 1,
        "description": "TBT1 temperature",
        "writable": False,
        "r290": True,
    },
    121: {
        "name": "tbt2",
        "unit": "°C",
        "scale": 1,
        "description": "TBT2 temperature",
        "writable": False,
        "r290": True,
    },
    122: {
        "name": "compressor_operation_time",
        "unit": "hr",
        "scale": 1,
        "description": "Compressor operation time (hours, cumulative)",
        "writable": False,
        "r290": True,
    },
    123: {
        "name": "unit_capacity",
        "unit": "kWh",
        "scale": 1,
        "description": "Unit capacity (kWh)",
        "writable": False,
        "r290": True,
    },
    124: {
        "name": "current_fault",
        "unit": None,
        "scale": 1,
        "description": "Current fault code (0 = no fault)",
        "writable": False,
        "r290": True,
    },
    125: {
        "name": "fault_1",
        "unit": None,
        "scale": 1,
        "description": "Fault history 1",
        "writable": False,
        "r290": True,
    },
    126: {
        "name": "fault_2",
        "unit": None,
        "scale": 1,
        "description": "Fault history 2",
        "writable": False,
        "r290": True,
    },
    127: {
        "name": "fault_3",
        "unit": None,
        "scale": 1,
        "description": "Fault history 3",
        "writable": False,
        "r290": True,
    },
    128: {
        "name": "status_bits",
        "unit": None,
        "scale": 1,
        "type": "bitfield",
        "description": "Status bits: bit 1 = Defrosting",
        "writable": False,
        "r290": True,
    },
    129: {
        "name": "load_outputs",
        "unit": None,
        "scale": 1,
        "type": "bitfield",
        "description": (
            "Load output bits: "
            "bit 3 = Internal circ pump PUMP_I, "
            "bit 4 = SV1 (DHW valve), "
            "bit 6 = External circ pump PUMP_O, "
            "bit 13 = RUN (compressor)"
        ),
        "writable": False,
        "r290": True,
    },
    130: {
        "name": "software_version",
        "unit": None,
        "scale": 1,
        "description": "Software version number",
        "writable": False,
        "r290": True,
    },
    131: {
        "name": "wired_controller_version_number",
        "unit": None,
        "scale": 1,
        "description": "Wired controller version number",
        "writable": False,
        "r290": True,
    },
    132: {
        "name": "compressor_target_frequency",
        "unit": "Hz",
        "scale": 1,
        "description": "Compressor target frequency (Hz)",
        "writable": False,
        "r290": True,
    },
    133: {
        "name": "dc_bus_current",
        "unit": "A",
        "scale": 1,
        "description": "DC bus current (A). Used for power calculation.",
        "writable": False,
        "r290": True,
    },
    134: {
        "name": "dc_bus_voltage",
        "unit": "V",
        "scale": 10,  # raw × 10 = V
        "description": "DC bus voltage (raw × 10 = V)",
        "writable": False,
        "r290": True,
    },
    135: {
        "name": "tf_module_temperature",
        "unit": "°C",
        "scale": 1,
        "description": "TF module (inverter) temperature (°C, signed int16)",
        "writable": False,
        "r290": True,
    },
    136: {
        "name": "climate_curve_t1s_calculated_value_1",
        "unit": "°C",
        "scale": 1,
        "description": "Climate curve T1S calculated value Zone 1 (°C, signed int16)",
        "writable": False,
        "r290": True,
    },
    137: {
        "name": "climate_curve_t1s_calculated_value_2",
        "unit": "°C",
        "scale": 1,
        "description": "Climate curve T1S calculated value Zone 2 (°C, signed int16)",
        "writable": False,
        "r290": True,
    },
    138: {
        "name": "water_flow",
        "unit": "m3/h",
        "scale": 0.01,
        "description": "Water flow rate (raw × 0.01 = m³/h)",
        "writable": False,
        "r290": True,
    },
    139: {
        "name": "limit_scheme_outdoor_unit_current",
        "unit": "kW",
        "scale": 1,
        "description": "Limit scheme of outdoor unit current (kW)",
        "writable": False,
        "r290": True,
    },
    140: {
        "name": "ability_of_hydraulic_module",
        "unit": "kW",
        "scale": 0.01,
        "description": "Ability of hydraulic module (raw × 0.01 = kW)",
        "writable": False,
        "r290": True,
    },
    141: {
        "name": "tsolar",
        "unit": "°C",
        "scale": 1,
        "description": "Solar panel temperature sensor (°C, signed int16)",
        "writable": False,
        "r290": True,
    },

    # ─── Energy Counters (143-186) ───

    143: {
        "name": "electricity_consumption_hi",
        "unit": "kWh",
        "scale": 0.01,  # R290 uses ×0.01, R32 uses ×1
        "type": "dword_hi",
        "description": "Electricity consumption high word (DWORD with reg 144). R290: ×0.01",
        "writable": False,
        "r290": True,
    },
    144: {
        "name": "electricity_consumption_lo",
        "unit": "kWh",
        "scale": 1,
        "type": "dword_lo",
        "description": "Electricity consumption low word (DWORD with reg 143)",
        "writable": False,
        "r290": True,
    },
    145: {
        "name": "power_output_hi",
        "unit": "kWh",
        "scale": 0.01,
        "type": "dword_hi",
        "description": "Power output high word (DWORD with reg 146). R290: ×0.01",
        "writable": False,
        "r290": True,
    },
    146: {
        "name": "power_output_lo",
        "unit": "kWh",
        "scale": 1,
        "type": "dword_lo",
        "description": "Power output low word (DWORD with reg 145)",
        "writable": False,
        "r290": True,
    },
    148: {
        "name": "realtime_heating_capacity",
        "unit": "kW",
        "scale": 0.01,
        "description": "Real-time heating capacity (raw × 0.01 = kW). R290 specific.",
        "writable": False,
        "r290": True,
    },
    149: {
        "name": "realtime_renewable_heating_capacity",
        "unit": "kW",
        "scale": 0.01,
        "description": "Real-time renewable heating capacity (raw × 0.01 = kW). R290 specific.",
        "writable": False,
        "r290": True,
    },
    150: {
        "name": "realtime_heating_power_consumption",
        "unit": "kW",
        "scale": 0.01,
        "description": "Real-time heating power consumption (raw × 0.01 = kW). R290 specific.",
        "writable": False,
        "r290": True,
    },
    151: {
        "name": "realtime_heating_cop",
        "unit": "COP",
        "scale": 0.01,
        "description": "Real-time heating COP (raw × 0.01). R290 specific.",
        "writable": False,
        "r290": True,
    },
    152: {
        "name": "total_heating_energy_produced_hi",
        "unit": "kWh",
        "scale": 0.01,
        "type": "dword_hi",
        "description": "Total heating energy produced (DWORD hi, ×0.01). R290 specific.",
        "writable": False,
        "r290": True,
    },
    153: {
        "name": "total_heating_energy_produced_lo",
        "unit": "kWh",
        "type": "dword_lo",
        "scale": 1,
        "description": "Total heating energy produced (DWORD lo)",
        "writable": False,
        "r290": True,
    },
    154: {
        "name": "total_renewable_heating_energy_hi",
        "unit": "kWh",
        "scale": 0.01,
        "type": "dword_hi",
        "description": "Total renewable heating energy (DWORD hi, ×0.01). R290 specific.",
        "writable": False,
        "r290": True,
    },
    155: {
        "name": "total_renewable_heating_energy_lo",
        "unit": "kWh",
        "type": "dword_lo",
        "scale": 1,
        "description": "Total renewable heating energy (DWORD lo)",
        "writable": False,
        "r290": True,
    },
    156: {
        "name": "total_heating_power_consumed_hi",
        "unit": "kWh",
        "scale": 0.01,
        "type": "dword_hi",
        "description": "Total heating power consumed (DWORD hi, ×0.01). R290 specific.",
        "writable": False,
        "r290": True,
    },
    157: {
        "name": "total_heating_power_consumed_lo",
        "unit": "kWh",
        "type": "dword_lo",
        "scale": 1,
        "description": "Total heating power consumed (DWORD lo)",
        "writable": False,
        "r290": True,
    },
    158: {
        "name": "total_heating_produced_master_hi",
        "unit": "kWh",
        "scale": 0.01,
        "type": "dword_hi",
        "description": "Total heating power produced for master unit (DWORD hi, ×0.01). R290 specific.",
        "writable": False,
        "r290": True,
    },
    159: {
        "name": "total_heating_produced_master_lo",
        "unit": "kWh",
        "type": "dword_lo",
        "scale": 1,
        "description": "Total heating power produced for master unit (DWORD lo)",
        "writable": False,
        "r290": True,
    },
    160: {
        "name": "total_renewable_heating_master_hi",
        "unit": "kWh",
        "scale": 0.01,
        "type": "dword_hi",
        "description": "Total renewable heating produced for master (DWORD hi, ×0.01). R290.",
        "writable": False,
        "r290": True,
    },
    161: {
        "name": "total_renewable_heating_master_lo",
        "unit": "kWh",
        "type": "dword_lo",
        "scale": 1,
        "description": "Total renewable heating produced for master (DWORD lo)",
        "writable": False,
        "r290": True,
    },
    162: {
        "name": "total_heating_consumed_master_hi",
        "unit": "kWh",
        "scale": 0.01,
        "type": "dword_hi",
        "description": "Total heating power consumed for master (DWORD hi, ×0.01). R290.",
        "writable": False,
        "r290": True,
    },
    163: {
        "name": "total_heating_consumed_master_lo",
        "unit": "kWh",
        "type": "dword_lo",
        "scale": 1,
        "description": "Total heating power consumed for master (DWORD lo)",
        "writable": False,
        "r290": True,
    },
    164: {
        "name": "total_cop_heating_master",
        "unit": "COP",
        "scale": 0.01,
        "description": "Total COP in heating mode for master unit (×0.01)",
        "writable": False,
        "r290": True,
    },
    165: {
        "name": "total_cooling_energy_produced_hi",
        "unit": "kWh",
        "scale": 0.01,
        "type": "dword_hi",
        "description": "Total cooling energy produced (DWORD hi, ×0.01)",
        "writable": False,
        "r290": True,
    },
    166: {
        "name": "total_cooling_energy_produced_lo",
        "unit": "kWh",
        "type": "dword_lo",
        "scale": 1,
        "description": "Total cooling energy produced (DWORD lo)",
        "writable": False,
        "r290": True,
    },
    167: {
        "name": "total_cooling_renewable_energy_hi",
        "unit": "kWh",
        "scale": 0.01,
        "type": "dword_hi",
        "description": "Total cooling renewable energy produced (DWORD hi, ×0.01). R290.",
        "writable": False,
        "r290": True,
    },
    168: {
        "name": "total_cooling_renewable_energy_lo",
        "unit": "kWh",
        "type": "dword_lo",
        "scale": 1,
        "description": "Total cooling renewable energy produced (DWORD lo)",
        "writable": False,
        "r290": True,
    },
    169: {
        "name": "total_cooling_power_consumed_hi",
        "unit": "kWh",
        "scale": 0.01,
        "type": "dword_hi",
        "description": "Total cooling power consumed (DWORD hi, ×0.01)",
        "writable": False,
        "r290": True,
    },
    170: {
        "name": "total_cooling_power_consumed_lo",
        "unit": "kWh",
        "type": "dword_lo",
        "scale": 1,
        "description": "Total cooling power consumed (DWORD lo)",
        "writable": False,
        "r290": True,
    },
    171: {
        "name": "total_cop_cooling_master",
        "unit": "COP",
        "scale": 0.01,
        "description": "Total COP in cooling mode for master unit (×0.01)",
        "writable": False,
        "r290": True,
    },
    172: {
        "name": "total_dhw_energy_produced_hi",
        "unit": "kWh",
        "scale": 0.01,
        "type": "dword_hi",
        "description": "Total DHW energy produced (DWORD hi, ×0.01)",
        "writable": False,
        "r290": True,
    },
    173: {
        "name": "total_dhw_energy_produced_lo",
        "unit": "kWh",
        "type": "dword_lo",
        "scale": 1,
        "description": "Total DHW energy produced (DWORD lo)",
        "writable": False,
        "r290": True,
    },
    174: {
        "name": "total_dhw_renewable_energy_hi",
        "unit": "kWh",
        "scale": 0.01,
        "type": "dword_hi",
        "description": "Total DHW renewable energy produced (DWORD hi, ×0.01). R290.",
        "writable": False,
        "r290": True,
    },
    175: {
        "name": "total_dhw_renewable_energy_lo",
        "unit": "kWh",
        "type": "dword_lo",
        "scale": 1,
        "description": "Total DHW renewable energy produced (DWORD lo)",
        "writable": False,
        "r290": True,
    },
    176: {
        "name": "total_dhw_power_consumed_hi",
        "unit": "kWh",
        "scale": 0.01,
        "type": "dword_hi",
        "description": "Total DHW power consumed (DWORD hi, ×0.01)",
        "writable": False,
        "r290": True,
    },
    177: {
        "name": "total_dhw_power_consumed_lo",
        "unit": "kWh",
        "type": "dword_lo",
        "scale": 1,
        "description": "Total DHW power consumed (DWORD lo)",
        "writable": False,
        "r290": True,
    },
    178: {
        "name": "total_cop_dhw_master",
        "unit": "COP",
        "scale": 0.01,
        "description": "Total COP in DHW mode for master unit (×0.01)",
        "writable": False,
        "r290": True,
    },
    179: {
        "name": "realtime_renewable_cooling_capacity",
        "unit": "kW",
        "scale": 0.01,
        "description": "Real-time renewable cooling capacity (×0.01). R290 specific.",
        "writable": False,
        "r290": True,
    },
    180: {
        "name": "realtime_cooling_capacity",
        "unit": "kW",
        "scale": 0.01,
        "description": "Real-time cooling capacity (raw × 0.01 = kW)",
        "writable": False,
        "r290": True,
    },
    181: {
        "name": "realtime_cooling_power_consumption",
        "unit": "kW",
        "scale": 0.01,
        "description": "Real-time cooling power consumption (raw × 0.01 = kW)",
        "writable": False,
        "r290": True,
    },
    182: {
        "name": "realtime_cooling_eer",
        "unit": "COP",
        "scale": 0.01,
        "description": "Real-time cooling EER (raw × 0.01)",
        "writable": False,
        "r290": True,
    },
    183: {
        "name": "realtime_dhw_heating_capacity",
        "unit": "kW",
        "scale": 0.01,
        "description": "Real-time DHW heating capacity (raw × 0.01 = kW)",
        "writable": False,
        "r290": True,
    },
    185: {
        "name": "realtime_dhw_heating_power_consumption",
        "unit": "kW",
        "scale": 0.01,
        "description": "Real-time DHW heating power consumption (raw × 0.01 = kW)",
        "writable": False,
        "r290": True,
    },
    186: {
        "name": "realtime_dhw_heating_cop",
        "unit": "COP",
        "scale": 0.01,
        "description": "Real-time DHW heating COP (raw × 0.01)",
        "writable": False,
        "r290": True,
    },

    # ─── Appliance Type (200) ───
    # NOTE: NOT present in R290 model (removed)

    200: {
        "name": "home_appliance_type_and_subtype",
        "unit": None,
        "scale": 1,
        "type": "packed",
        "description": "Home appliance type (low byte) and sub-type (high byte). NOT present in R290.",
        "writable": False,
        "r290": False,
    },

    # ─── Configuration Parameters (201-274) ───

    201: {
        "name": "temp_upper_limit_t1s_cooling",
        "unit": "°C",
        "scale": 1,
        "type": "packed",
        "description": "Temp upper limit T1S cooling: low byte = Zone 1, high byte = Zone 2",
        "writable": True,
        "r290": True,
    },
    202: {
        "name": "temp_lower_limit_t1s_cooling",
        "unit": "°C",
        "scale": 1,
        "type": "packed",
        "description": "Temp lower limit T1S cooling: low byte = Zone 1, high byte = Zone 2",
        "writable": True,
        "r290": True,
    },
    203: {
        "name": "temp_upper_limit_t1s_heating",
        "unit": "°C",
        "scale": 1,
        "type": "packed",
        "description": "Temp upper limit T1S heating: low byte = Zone 1, high byte = Zone 2",
        "writable": True,
        "r290": True,
    },
    204: {
        "name": "temp_lower_limit_t1s_heating",
        "unit": "°C",
        "scale": 1,
        "type": "packed",
        "description": "Temp lower limit T1S heating: low byte = Zone 1, high byte = Zone 2",
        "writable": True,
        "r290": True,
    },
    205: {
        "name": "temp_upper_limit_ts_setting",
        "unit": "°C",
        "scale": 0.5,
        "description": "Temp upper limit of TS setting (raw ÷ 2.0 = °C)",
        "writable": True,
        "r290": True,
    },
    206: {
        "name": "temp_lower_limit_ts_setting",
        "unit": "°C",
        "scale": 0.5,
        "description": "Temp lower limit of TS setting (raw ÷ 2.0 = °C)",
        "writable": True,
        "r290": True,
    },
    207: {
        "name": "temp_upper_limit_water_heating",
        "unit": "°C",
        "scale": 1,
        "description": "Temp upper limit of water heating",
        "writable": True,
        "r290": True,
    },
    208: {
        "name": "temp_lower_limit_water_heating",
        "unit": "°C",
        "scale": 1,
        "description": "Temp lower limit of water heating",
        "writable": True,
        "r290": True,
    },
    209: {
        "name": "dhw_pump_return_running_time",
        "unit": "min",
        "scale": 1,
        "description": "DHW pump return running time (minutes)",
        "writable": True,
        "r290": True,
    },
    210: {
        "name": "timer_settings",
        "unit": None,
        "scale": 1,
        "type": "packed",
        "description": "Timer on/off settings (bitfield with packed schedule data)",
        "writable": True,
        "r290": True,
    },
    211: {
        "name": "timer_time_settings",
        "unit": None,
        "scale": 1,
        "type": "packed",
        "description": "Timer time settings",
        "writable": True,
        "r290": True,
    },
    212: {
        "name": "dt5_on",
        "unit": "°C",
        "scale": 1,
        "description": "dT5 On (°C) — DHW on hysteresis",
        "writable": True,
        "r290": True,
    },
    213: {
        "name": "dt1s5",
        "unit": "°C",
        "scale": 1,
        "description": "dT1S5 (°C)",
        "writable": True,
        "r290": True,
    },
    214: {
        "name": "t_interval_dhw",
        "unit": "min",
        "scale": 1,
        "description": "Time interval DHW (minutes). NOT present in R290.",
        "writable": True,
        "r290": False,
    },
    215: {
        "name": "t4_dhw_max",
        "unit": "°C",
        "scale": 1,
        "description": "T4 DHW max (°C). R290 max: 46°C.",
        "writable": True,
        "r290": True,
    },
    216: {
        "name": "t4_dhw_min",
        "unit": "°C",
        "scale": 1,
        "description": "T4 DHW min (°C, signed int16)",
        "writable": True,
        "r290": True,
    },
    217: {
        "name": "t_tbh_delay",
        "unit": "min",
        "scale": 1,
        "description": "t TBH delay (minutes) — backup heater delay",
        "writable": True,
        "r290": True,
    },
    218: {
        "name": "dt5_tbh_off",
        "unit": "°C",
        "scale": 1,
        "description": "dT5 TBH off (°C) — backup heater off hysteresis",
        "writable": True,
        "r290": True,
    },
    219: {
        "name": "t4_tbh_on",
        "unit": "°C",
        "scale": 1,
        "description": "T4 TBH on (°C, signed int16) — ambient temp to trigger backup heater",
        "writable": True,
        "r290": True,
    },
    220: {
        "name": "temp_disinfection_operation",
        "unit": "°C",
        "scale": 1,
        "description": "Temp for disinfection operation (°C)",
        "writable": True,
        "r290": True,
    },
    221: {
        "name": "maximum_disinfection_duration",
        "unit": "min",
        "scale": 1,
        "description": "Maximum disinfection duration (minutes)",
        "writable": True,
        "r290": True,
    },
    222: {
        "name": "disinfection_high_temp_duration",
        "unit": "min",
        "scale": 1,
        "description": "Disinfection high temperature duration (minutes)",
        "writable": True,
        "r290": True,
    },
    223: {
        "name": "t_interval_compressor_cooling",
        "unit": "min",
        "scale": 1,
        "description": "Time interval compressor startup cooling mode (min). NOT in R290.",
        "writable": True,
        "r290": False,
    },
    224: {
        "name": "dt1sc",
        "unit": "°C",
        "scale": 1,
        "description": "dT1SC (°C) — cooling hysteresis",
        "writable": True,
        "r290": True,
    },
    225: {
        "name": "dtsc",
        "unit": "°C",
        "scale": 1,
        "description": "dTSC (°C) — cooling hysteresis 2",
        "writable": True,
        "r290": True,
    },
    226: {
        "name": "t4cmax",
        "unit": "°C",
        "scale": 1,
        "description": "T4cmax (°C) — max ambient for cooling. R290 max: 52°C.",
        "writable": True,
        "r290": True,
    },
    227: {
        "name": "t4cmin",
        "unit": "°C",
        "scale": 1,
        "description": "T4cmin (°C, signed int16) — min ambient for cooling",
        "writable": True,
        "r290": True,
    },
    228: {
        "name": "t_interval_compressor_heating",
        "unit": "min",
        "scale": 1,
        "description": "Time interval compressor startup heating mode (minutes)",
        "writable": True,
        "r290": True,
    },
    229: {
        "name": "dt1sh",
        "unit": "°C",
        "scale": 1,
        "description": "dT1SH (°C) — heating hysteresis",
        "writable": True,
        "r290": True,
    },
    230: {
        "name": "dtsh",
        "unit": "°C",
        "scale": 1,
        "description": "dTSH (°C)",
        "writable": True,
        "r290": True,
    },
    231: {
        "name": "t4hmax",
        "unit": "°C",
        "scale": 1,
        "description": "T4hmax (°C) — max ambient for heating",
        "writable": True,
        "r290": True,
    },
    232: {
        "name": "t4hmin",
        "unit": "°C",
        "scale": 1,
        "description": "T4hmin (°C, signed int16) — min ambient for heating",
        "writable": True,
        "r290": True,
    },
    233: {
        "name": "t4_ibh_on",
        "unit": "°C",
        "scale": 1,
        "description": "Ambient temp for enabling IBH (°C, signed int16). Internal backup heater.",
        "writable": True,
        "r290": True,
    },
    234: {
        "name": "dt1_ibh_on",
        "unit": "°C",
        "scale": 1,
        "description": "Temp return diff for enabling IBH (°C)",
        "writable": True,
        "r290": True,
    },
    235: {
        "name": "t_ibh_delay",
        "unit": "min",
        "scale": 1,
        "description": "Delay time of enabling IBH (minutes)",
        "writable": True,
        "r290": True,
    },
    237: {
        "name": "t4_ahs_on",
        "unit": "°C",
        "scale": 1,
        "description": "Ambient temp trigger for AHS (°C, signed int16). Auxiliary heat source.",
        "writable": True,
        "r290": True,
    },
    238: {
        "name": "dt1_ahs_on",
        "unit": "°C",
        "scale": 1,
        "description": "Trigger temp diff for AHS (°C)",
        "writable": True,
        "r290": True,
    },
    240: {
        "name": "t_ahs_delay",
        "unit": "min",
        "scale": 1,
        "description": "Delay time for enabling AHS (minutes)",
        "writable": True,
        "r290": True,
    },
    241: {
        "name": "t_dhwhp_max",
        "unit": "min",
        "scale": 1,
        "description": "Water heating max duration (minutes)",
        "writable": True,
        "r290": True,
    },
    242: {
        "name": "t_dhwhp_restrict",
        "unit": "min",
        "scale": 1,
        "description": "T DHWHP restrict (minutes)",
        "writable": True,
        "r290": True,
    },
    243: {
        "name": "t4autocmin",
        "unit": "°C",
        "scale": 1,
        "description": "T4autocmin (°C) — auto cool min",
        "writable": True,
        "r290": True,
    },
    244: {
        "name": "t4autohmax",
        "unit": "°C",
        "scale": 1,
        "description": "T4autohmax (°C) — auto heat max",
        "writable": True,
        "r290": True,
    },
    245: {
        "name": "t1s_h_a_h",
        "unit": "°C",
        "scale": 1,
        "description": "Temp when holiday mode is active for heating (°C). R290 max: 25°C.",
        "writable": True,
        "r290": True,
    },
    246: {
        "name": "t5s_h_a_dhw",
        "unit": "°C",
        "scale": 1,
        "description": "DHW temp when holiday mode is active (°C)",
        "writable": True,
        "r290": True,
    },
    247: {
        "name": "per_start_ratio",
        "unit": None,
        "scale": 1,
        "description": "Per start ratio. NOT present in R290.",
        "writable": True,
        "r290": False,
    },
    248: {
        "name": "time_adjust",
        "unit": None,
        "scale": 1,
        "description": "Time adjust. NOT present in R290.",
        "writable": True,
        "r290": False,
    },
    249: {
        "name": "dtbt2",
        "unit": "°C",
        "scale": 1,
        "description": "dTBT2 (°C). NOT present in R290.",
        "writable": True,
        "r290": False,
    },
    250: {
        "name": "ibh1_power",
        "unit": "kW",
        "scale": 1,
        "description": "IBH1 power (kW). Modbus ERROR in R290!",
        "writable": True,
        "r290": False,
    },
    251: {
        "name": "ibh2_power",
        "unit": "kW",
        "scale": 1,
        "description": "IBH2 power (kW). Modbus ERROR in R290!",
        "writable": True,
        "r290": False,
    },
    252: {
        "name": "tbh_power",
        "unit": "kW",
        "scale": 1,
        "description": "TBH power (kW). Modbus ERROR in R290!",
        "writable": True,
        "r290": False,
    },
    253: {
        "name": "comfort_parameter_3",
        "unit": None,
        "scale": 1,
        "description": "Comfort parameter 3. NOT present in R290.",
        "writable": False,
        "r290": False,
    },
    254: {
        "name": "comfort_parameter_4",
        "unit": None,
        "scale": 1,
        "description": "Comfort parameter 4. NOT present in R290.",
        "writable": False,
        "r290": False,
    },
    255: {
        "name": "t_dryup",
        "unit": None,
        "scale": 1,
        "description": "Temp rise day number (floor drying program)",
        "writable": True,
        "r290": True,
    },
    256: {
        "name": "t_highpeak",
        "unit": None,
        "scale": 1,
        "description": "Drying day number (floor drying program)",
        "writable": True,
        "r290": True,
    },
    257: {
        "name": "t_dryd",
        "unit": None,
        "scale": 1,
        "description": "Temp drop day number (floor drying program)",
        "writable": True,
        "r290": True,
    },
    258: {
        "name": "t_drypeak",
        "unit": "°C",
        "scale": 1,
        "description": "Highest drying temp (°C)",
        "writable": True,
        "r290": True,
    },
    259: {
        "name": "t_firstfh",
        "unit": "hr",
        "scale": 1,
        "description": "Running time of floor heating first time (hours)",
        "writable": True,
        "r290": True,
    },
    260: {
        "name": "t1s_firstfh",
        "unit": "°C",
        "scale": 1,
        "description": "T1S of floor heating first time (°C)",
        "writable": True,
        "r290": True,
    },
    261: {
        "name": "t1setc1",
        "unit": "°C",
        "scale": 1,
        "description": "T1SetC1 (°C) — climate curve cooling point 1 temp",
        "writable": True,
        "r290": True,
    },
    262: {
        "name": "t1setc2",
        "unit": "°C",
        "scale": 1,
        "description": "T1SetC2 (°C) — climate curve cooling point 2 temp",
        "writable": True,
        "r290": True,
    },
    263: {
        "name": "t4c1",
        "unit": "°C",
        "scale": 1,
        "description": "T4C1 (°C, signed int16) — climate curve cooling ambient point 1",
        "writable": True,
        "r290": True,
    },
    264: {
        "name": "t4c2",
        "unit": "°C",
        "scale": 1,
        "description": "T4C2 (°C, signed int16) — climate curve cooling ambient point 2",
        "writable": True,
        "r290": True,
    },
    265: {
        "name": "t1seth1",
        "unit": "°C",
        "scale": 1,
        "description": "T1SetH1 (°C) — climate curve heating point 1 temp. R290 max: 80°C.",
        "writable": True,
        "r290": True,
    },
    266: {
        "name": "t1seth2",
        "unit": "°C",
        "scale": 1,
        "description": "T1SetH2 (°C) — climate curve heating point 2 temp. R290 max: 80°C.",
        "writable": True,
        "r290": True,
    },
    267: {
        "name": "t4h1",
        "unit": "°C",
        "scale": 1,
        "description": "T4H1 (°C, signed int16) — climate curve heating ambient point 1. R290 max: 35.",
        "writable": True,
        "r290": True,
    },
    268: {
        "name": "t4h2",
        "unit": "°C",
        "scale": 1,
        "description": "T4H2 (°C, signed int16) — climate curve heating ambient point 2. R290 max: 35.",
        "writable": True,
        "r290": True,
    },
    269: {
        "name": "power_input_limitation_type",
        "unit": None,
        "scale": 1,
        "type": "select",
        "description": "Power input limitation type: 0=None, 1-8=limit levels",
        "writable": True,
        "r290": True,
    },
    271: {
        "name": "t_delay_pump",
        "unit": "min",
        "scale": 2.0,  # raw × 2.0 = minutes
        "description": "Built-in circulating pump delay (raw × 2.0 = minutes)",
        "writable": True,
        "r290": True,
    },
    272: {
        "name": "emission_types",
        "unit": None,
        "scale": 1,
        "type": "bitfield",
        "description": (
            "Emission type settings (4×4 bits): "
            "bits 0-3 = Zone1 heating (0=UFH/FCU, 1=Radiator, 2=UFH), "
            "bits 4-7 = Zone2 heating, "
            "bits 8-11 = Zone1 cooling, "
            "bits 12-15 = Zone2 cooling"
        ),
        "writable": True,
        "r290": True,
    },
    273: {
        "name": "solar_function_and_deltatsol",
        "unit": None,
        "scale": 1,
        "type": "packed",
        "description": (
            "Solar function: low byte (0=no function, 1=Solar+HP, 2=Only Solar), "
            "high byte = Deltatsol temp diff (°C)"
        ),
        "writable": True,
        "r290": True,
    },
    274: {
        "name": "enswitchpdc",
        "unit": None,
        "scale": 1,
        "type": "bitfield",
        "description": "EnSwitchPDC: bit 0 = enable power demand control",
        "writable": True,
        "r290": True,
    },
}


# ============================================================================
#  SOURCE 3: 0xAHA/Midea-Heat-Pump-HA (Hot Water Heater variant)
#  Uses CONFIGURABLE register addresses — these are the DEFAULTS
#  Temperature scaling: raw * 0.5 - 15.0 (DIFFERENT from Mosibi!)
# ============================================================================

MIDEA_HWS_DEFAULTS = {
    "power_register": 0,       # Power on/off (0=off, 1=on)
    "mode_register": 1,        # Mode: 1=eco, 2=performance, 4=electric
    "temp_register": 102,      # Current water temperature
    "target_temp_register": 2,  # Target temperature setpoint
    "sterilize_register": 3,   # Sterilize mode on/off
    "tank_top_temp_register": 101,   # Tank top temperature sensor
    "tank_bottom_temp_register": 102, # Tank bottom temperature sensor
    "condensor_temp_register": 103,   # Condensor temperature sensor
    "outdoor_temp_register": 104,     # Outdoor temperature sensor
    "exhaust_temp_register": 105,     # Exhaust temperature sensor (NO scaling!)
    "suction_temp_register": 106,     # Suction temperature sensor
    # Temperature scaling defaults:
    "temp_scale": 0.5,          # raw × 0.5
    "temp_offset": -15.0,       # + (-15.0) → value = raw * 0.5 - 15.0
    "target_temp_scale": 1.0,   # raw × 1.0 (no scaling)
    "target_temp_offset": 0.0,  # + 0.0
}


# ============================================================================
#  HELPER: Compare with BataviaHeat register_map.py
# ============================================================================

def print_comparison():
    """Print a comparison between online register maps and BataviaHeat findings."""
    try:
        from register_map import HOLDING_REGISTERS as BH_HR, INPUT_REGISTERS as BH_IR
    except ImportError:
        print("ERROR: Cannot import register_map.py. Run from the 'Modbus snooper' directory.")
        return

    print("=" * 90)
    print("VERGELIJKING: Online Midea registers vs BataviaHeat register_map.py")
    print("=" * 90)

    # Section 1: Mosibi registers that ALSO exist in BataviaHeat HR
    print("\n" + "─" * 90)
    print("1. OVERLAP: Midea HR adressen die OOK in BataviaHeat HR voorkomen")
    print("─" * 90)
    overlap_hr = sorted(set(MOSIBI_REGISTERS.keys()) & set(BH_HR.keys()))
    if overlap_hr:
        print(f"{'Addr':>5} │ {'Midea naam':<45} │ {'BataviaHeat naam':<30}")
        print(f"{'─'*5:>5} │ {'─'*45:<45} │ {'─'*30:<30}")
        for addr in overlap_hr:
            m_name = MOSIBI_REGISTERS[addr]["name"]
            b_name = BH_HR[addr]["name"]
            match = "✓" if m_name.lower() == b_name.lower() else "≠"
            print(f"{addr:>5} │ {m_name:<45} │ {b_name:<30} {match}")
    else:
        print("  (geen overlap gevonden)")

    # Section 2: Mosibi registers NOT in BataviaHeat HR
    print("\n" + "─" * 90)
    print("2. NIEUW: Midea HR adressen die NIET in BataviaHeat HR voorkomen")
    print("   → Deze adressen kunnen we bij BataviaHeat uitlezen om te vergelijken!")
    print("─" * 90)
    new_regs = sorted(set(MOSIBI_REGISTERS.keys()) - set(BH_HR.keys()))
    r290_new = [a for a in new_regs if MOSIBI_REGISTERS[a].get("r290", True)]
    print(f"\n  R290-relevante registers ({len(r290_new)} stuks):")
    print(f"  {'Addr':>5} │ {'Naam':<45} │ {'Eenheid':<8} │ {'Schaal':<8}")
    print(f"  {'─'*5:>5} │ {'─'*45:<45} │ {'─'*8:<8} │ {'─'*8:<8}")
    for addr in r290_new:
        reg = MOSIBI_REGISTERS[addr]
        if reg.get("r290", True):
            unit = reg.get("unit") or "-"
            scale = reg.get("scale", 1)
            print(f"  {addr:>5} │ {reg['name']:<45} │ {unit:<8} │ {scale:<8}")

    # Section 3: BataviaHeat HR registers NOT in Midea
    print("\n" + "─" * 90)
    print("3. UNIEK BATAVIA: BataviaHeat HR adressen die NIET in Midea voorkomen")
    print("   → Mogelijk BataviaHeat/Newntide-specifieke registers")
    print("─" * 90)
    bh_only = sorted(set(BH_HR.keys()) - set(MOSIBI_REGISTERS.keys()))
    print(f"\n  BataviaHeat-unieke HR registers ({len(bh_only)} stuks):")
    for addr in bh_only:
        reg = BH_HR[addr]
        conf = reg.get("confidence", "?")
        print(f"  HR[{addr:>5}]: {reg['name']:<35} [{conf}]")

    # Section 4: BataviaHeat Input Registers (Midea has no IR)
    print("\n" + "─" * 90)
    print("4. INPUT REGISTERS: BataviaHeat IR (Midea protocol kent GEEN input registers)")
    print("─" * 90)
    for addr in sorted(BH_IR.keys()):
        reg = BH_IR[addr]
        conf = reg.get("confidence", "?")
        print(f"  IR[{addr:>5}]: {reg['name']:<45} [{conf}]")

    # Section 5: Key differences summary
    print("\n" + "─" * 90)
    print("5. SAMENVATTING BELANGRIJKE VERSCHILLEN")
    print("─" * 90)
    print("""
  TEMPERATUUR SCHALING:
    Midea (Mosibi):  Hele graden (°C), signed int16, GEEN schaalfactor
    Midea (0xAHA):   raw × 0.5 - 15.0  (hot water heater variant)
    BataviaHeat:     raw × 0.1 = °C  (altijd schaalfactor 0.1)

  PROTOCOL:
    Midea (Mosibi):  Alleen holding registers (FC03/FC06), 0-274 range
    BataviaHeat:     Holding (FC03) + Input (FC04) registers, 0-6500+ range

  DRUK:
    Midea HR[116]:   High pressure in kPa (unsigned)
    Midea HR[117]:   Low pressure in kPa (unsigned)
    BataviaHeat:     IR[32]/IR[33] = druk × 0.1 bar, HR[32]/HR[33] = mirrors

  DEBIET:
    Midea HR[138]:   Water flow in m³/h × 0.01
    BataviaHeat:     IR[54] = pump flow rate in L/h (×0.1?)

  ENERGIE:
    Midea HR[143-186]: Complete energiemonitor (verbruik, opbrengst, COP)
    BataviaHeat:       Nog niet gevonden in scan!
    """)

    # Section 6: Potentially valuable Midea registers to check
    print("─" * 90)
    print("6. AANBEVOLEN OM TE CONTROLEREN bij BataviaHeat")
    print("─" * 90)
    valuable = {
        100: "Compressor frequentie → is dit onze HR[1321] of HR[1368]?",
        103: "EEV opening → was 0 bij onze scan (compressor uit)",
        116: "Hoge druk kPa → vergelijk met IR[32] (bar × 0.1)",
        117: "Lage druk kPa → vergelijk met IR[33] (bar × 0.1)",
        118: "Outdoor unit stroom → vergelijk met HR[1338] (spanning)",
        119: "Outdoor unit spanning → vergelijk met HR[1338]",
        122: "Compressor draaiuren",
        124: "Storingscode",
        128: "Status bits (ontdooien)",
        129: "Uitgangen (pomp, compressor, klep)",
        130: "Software versie",
        132: "Compressor doelfrequentie",
        133: "DC bus stroom",
        134: "DC bus spanning",
        138: "Water debiet → vergelijk met IR[54]",
        143: "Elektriciteitsverbruik (DWORD, kWh)",
        145: "Thermisch vermogen (DWORD, kWh)",
        148: "Realtime verwarmingsvermogen (kW)",
        150: "Realtime stroomverbruik (kW)",
        151: "Realtime COP",
    }
    for addr, hint in valuable.items():
        r290 = MOSIBI_REGISTERS.get(addr, {}).get("r290", True)
        tag = "[R290]" if r290 else "[R32] "
        print(f"  HR[{addr:>3}] {tag}: {hint}")


if __name__ == "__main__":
    print_comparison()

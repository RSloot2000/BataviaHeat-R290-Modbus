# BataviaHeat R290 - Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Custom Home Assistant integration for the **BataviaHeat R290 3-8kW Monobloc** heat pump via Modbus TCP.

## Features

- **Climate entity**: Control heating mode and target temperature via pulse-coils
- **Sensors**: Temperatures (ambient, refrigerant, water circuit), pressures, pump data, operational status
- **Calculated sensors**: Thermal power (kW), energy delivered (kWh via Riemann sum)
- **Binary sensors**: Compressor running
- **Switches**: Unit power on/off, silent mode, silent level 2 (pulse-coil based)
- **Number entities**: Heating target temperature, heating curve (stooklijn) parameters

## Hardware Requirements

- **BataviaHeat R290 3-8kW** heat pump
- **DR164 RS485-to-WiFi converter** (or similar Modbus TCP gateway) connected to the heat pump's RS-485 port
- Home Assistant instance with network access to the converter

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu → **Custom repositories**
3. Add this repository URL and select **Integration** as the category
4. Click **Download**
5. Restart Home Assistant

### Manual

1. Copy the `custom_components/batavia_heat` folder to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for **BataviaHeat R290**
3. Configure the connection:
   - **Host**: IP address of your DR164 / Modbus TCP gateway
   - **TCP port**: 502 (default)
   - **Slave ID**: 1 (default Modbus address)

## Entities

### Sensors
| Entity | Description | Unit |
|--------|-------------|------|
| Ambient temperature | Outdoor temperature (IR[22]) | °C |
| Fin coil temperature | Evaporator fin temperature (IR[23]) | °C |
| Suction temperature | Compressor suction line (IR[24]) | °C |
| Discharge temperature | Compressor discharge line (IR[25]) | °C |
| Low pressure | Refrigerant low-side pressure (IR[32]) | bar |
| High pressure | Refrigerant high-side pressure (IR[33]) | bar |
| Pump target speed | Water pump target (IR[53]) | rpm |
| Pump flow rate | Water flow rate (IR[54]) | L/h |
| Pump control signal | Pump PWM output (IR[66]) | % |
| Pump feedback signal | Pump feedback (IR[142]) | % |
| Plate HX inlet temperature | Heat exchanger inlet (IR[135]) | °C |
| Plate HX outlet temperature | Heat exchanger outlet (IR[136]) | °C |
| Module water outlet temperature | Module outlet (IR[137]) | °C |
| Module ambient temperature | Module ambient (IR[138]) | °C |
| Operational status | Operating state (HR[768]) | - |
| Compressor discharge temperature | Compressor discharge (HR[773]) | °C |
| Water outlet temperature | System water outlet (HR[776]) | °C |
| Thermal power | Calculated: flow × ΔT × 4.186 / 3600 | kW |
| Energy delivered | Riemann sum of thermal power | kWh |

### Controls
| Entity | Description | Type |
|--------|-------------|------|
| Heat Pump | Heating on/off + target temperature | Climate |
| Unit power | Turn heat pump on/off (Coil 1024/1025) | Switch |
| Silent mode | Enable/disable silent mode (Coil 1073/1074) | Switch |
| Silent level 2 | Toggle silent level 1/2 (Coil 1076/1075) | Switch |
| Heating target temperature | CV target setpoint (HR[4]) | Number |
| Max heating temperature | Stooklijn max temp (HR[6402]) | Number |
| Heating curve mode | Stooklijn curve selector (HR[6426]) | Number |
| Curve outdoor temp high | Stooklijn outdoor high (HR[6433]) | Number |
| Curve outdoor temp low | Stooklijn outdoor low (HR[6434]) | Number |
| Curve water temp mild | Stooklijn water mild (HR[6435]) | Number |
| Curve water temp cold | Stooklijn water cold (HR[6436]) | Number |

### Binary Sensors
| Entity | Description |
|--------|-------------|
| Compressor running | Whether the compressor is currently active (HR[1283]) |

## COP Calculation

This integration provides **thermal power** and **energy delivered** sensors. For COP calculation, use a Home Assistant template sensor that divides energy delivered by electrical consumption from an external kWh meter (e.g., HomeWizard P1):

```yaml
template:
  - sensor:
      - name: "Heat Pump COP"
        unit_of_measurement: ""
        state: >
          {% set delivered = states('sensor.batavia_heat_energy_delivered') | float(0) %}
          {% set consumed = states('sensor.homewizard_energy') | float(0) %}
          {% if consumed > 0 %}
            {{ (delivered / consumed) | round(2) }}
          {% else %}
            unknown
          {% endif %}
```

## Technical Notes

- **Pulse-coils**: BataviaHeat uses separate coils for ON and OFF per function (no toggle). Each write is a 0xFF00 pulse — there is no readable coil state.
- **Stooklijn M-registers**: Non-linear HR mapping: M00-M09 = HR[6400+Mxx], M10+ = HR[6400+Mxx+15].
- **HR sensors**: Holding register sensors (HR[768], HR[773], HR[776]) go to 0 when the compressor is off — this is normal.
- **Electrical monitoring**: HR[41] (compressor_power) was removed in favor of external metering (HomeWizard kWh meter) for accuracy.

## Troubleshooting

### Cannot connect
- Verify the DR164 converter is powered and connected to your WiFi network
- Check the IP address is correct and reachable from your HA instance
- Verify TCP port (default 502) and Modbus slave ID (default 1)
- Ensure correct RS-485 wiring: A+ to A+, B− to B−

### No data / entities unavailable
- Check Home Assistant logs for Modbus communication errors
- Ensure the tablet controller is **disconnected** from the RS-485 bus (two masters cause conflicts)
- Try increasing the scan interval if the bus is unstable

## Contributing

This integration is built through reverse-engineering the Modbus protocol. Contributions are welcome:

1. Use the [Modbus Snooper tools](https://github.com/RSloot2000/BataviaHeat-R290-Modbus/tree/main/tools) to scan your heat pump
2. Share discovered register definitions
3. Report issues with register values or entity behavior
4. Share ideas for new additions or updates

## License

MIT

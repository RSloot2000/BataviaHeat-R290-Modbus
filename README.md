# BataviaHeat R290 - Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

> **🚧 This project is in extremely early development.** Expect breaking changes, incomplete features and undiscovered registers. Use at your own risk and please report any issues you encounter.

Custom Home Assistant integration for the **BataviaHeat R290 3–8 kW Monobloc** heat pump via Modbus TCP.

## Table of contents

- [Features](#features)
- [Hardware Requirements](#hardware-requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Entities](#entities)
  - [Sensors](#sensors)
  - [Binary sensors](#binary-sensors)
  - [Switches](#switches)
  - [Number entities](#number-entities)
  - [Climate](#climate)
- [COP calculation](#cop-calculation)
- [Troubleshooting](#troubleshooting)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [RS-485 adapter installation](#rs-485-adapter-installation)
- [License](#license)

Built by reverse-engineering the Modbus protocol using passive bus sniffing and systematic register scanning. The register map was validated over multiple overnight monitoring sessions totalling 850 000+ readings.

## Features

- **Climate entity:** heating on/off and target temperature control via pulse-coils
- **17 sensors:** temperatures, pressures, water pump data, operational status, thermal power, energy delivered
- **1 binary sensor:** compressor running
- **3 switches:** unit power, silent mode, silent level 2 (pulse-coil based)
- **7 number entities:** heating target temperature and 6 heating curve (stooklijn) parameters
- **5-second polling interval** via Modbus TCP

## Hardware Requirements

| Component | Description |
|-----------|-------------|
| Heat pump | BataviaHeat R290 3–8 kW Monobloc |
| Modbus gateway | DR164 RS485-to-WiFi converter (or any Modbus TCP gateway) |
| Wiring | Gateway connected to the heat pump's RS-485 port (A+ to A+, B− to B−) |

> **Important:** The RS-485 bus supports only one master. Disconnect the tablet controller from the bus before using this integration, or use the secondary RS-485 port located on the mainboard of the heatpump.

> **Note:** For a step-by-step guide on wiring the RS-485 to TCP adapter, see [RS-485 adapter installation](#rs-485-adapter-installation) below.

## Installation

### HACS (recommended)

1. Open **HACS** in Home Assistant
2. Click the three-dot menu → **Custom repositories**
3. Add `https://github.com/RSloot2000/BataviaHeat-R290-Modbus` and select **Integration**
4. Click **Download**
5. Restart Home Assistant

### Manual

1. Copy the `custom_components/batavia_heat` folder into your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **BataviaHeat R290**
3. Enter the connection details:
   - **Host:** IP address of the Modbus TCP gateway
   - **TCP port:** Gateway TCP port (default: `502`)
   - **Slave ID:** Modbus device address (default: `1`)

## Entities

### Sensors

| Entity | Register | Unit | Description |
|--------|----------|------|-------------|
| Ambient temperature | IR[22] | °C | Outdoor temperature measured by the heat pump |
| Fin coil temperature | IR[23] | °C | Evaporator fin temperature |
| Suction temperature | IR[24] | °C | Compressor suction line temperature |
| Discharge temperature | IR[25] | °C | Compressor discharge line temperature |
| Low pressure | IR[32] | bar | Refrigerant low-side pressure |
| High pressure | IR[33] | bar | Refrigerant high-side pressure |
| Pump target speed | IR[53] | rpm | Water pump target speed |
| Pump flow rate | IR[54] | L/h | Water flow rate |
| Pump control signal | IR[66] | % | Pump PWM control signal |
| Pump feedback signal | IR[142] | % | Pump feedback signal |
| Plate HX inlet temperature | IR[135] | °C | Plate heat exchanger inlet (water return) |
| Plate HX outlet temperature | IR[136] | °C | Plate heat exchanger outlet (water supply) |
| Module water outlet temperature | IR[137] | °C | Module water outlet |
| Module ambient temperature | IR[138] | °C | Module ambient |
| Operational status | HR[768] | - | Operating state (0 = off) |
| Compressor discharge temperature | HR[773] | °C | Compressor discharge (from outdoor unit) |
| Water outlet temperature | HR[776] | °C | System water outlet (from outdoor unit) |
| Thermal power | calculated | kW | flow × ΔT × 4.186 / 3600 |
| Energy delivered | integrated | kWh | Riemann sum of thermal power |

> HR[768], HR[773] and HR[776] go to 0 when the compressor is off. This is normal behaviour.

### Binary sensors

| Entity | Register | Description |
|--------|----------|-------------|
| Compressor running | HR[1283] | Whether the compressor is currently active |

### Switches

| Entity | ON coil | OFF coil | Description |
|--------|---------|----------|-------------|
| Unit power | 1024 | 1025 | Turn the heat pump on or off |
| Silent mode | 1073 | 1074 | Enable or disable silent mode |
| Silent level 2 | 1076 | 1075 | Switch between silent level 1 and 2 |

Switches use **pulse-coils** (FC05, 0xFF00). Each function has a separate ON and OFF coil; there is no toggle. Coil state is not readable; the UI uses assumed state.

### Number entities

| Entity | Register | Range | Description |
|--------|----------|-------|-------------|
| Heating target temperature | HR[4] | 20–60 °C | Central heating setpoint |
| Max heating temperature | HR[6402] | 0–85 °C | Maximum heating temperature |
| Heating curve mode | HR[6426] | 0–17 | Heating curve preset selector |
| Curve outdoor temp high | HR[6433] | −25–35 °C | Outdoor temperature at which minimum water temp applies |
| Curve outdoor temp low | HR[6434] | −25–35 °C | Outdoor temperature at which maximum water temp applies |
| Curve water temp mild | HR[6435] | 25–65 °C | Water temperature at mild outdoor conditions |
| Curve water temp cold | HR[6436] | 25–65 °C | Water temperature at cold outdoor conditions |

The heating curve registers use the M-register mapping: M00–M09 = HR[6400 + M], M10+ = HR[6400 + M + 15].

### Climate

| Entity | Description |
|--------|-------------|
| Heat Pump | HVAC modes: **Heat** / **Off**. Current temperature from IR[136], target temperature from HR[4]. On/off via coils 1024/1025. |

## COP calculation

This integration provides **thermal power** (kW) and **energy delivered** (kWh) sensors. Electrical consumption is **not** read from the heat pump since the pump only provides a power reading for the compressor and not the whole system. An external kWh meter (e.g. HomeWizard) is needed for this function.

To calculate COP, create a template sensor in Home Assistant:

```yaml
template:
  - sensor:
      - name: "Heat Pump COP"
        unit_of_measurement: ""
        state: >
          {% set delivered = states('sensor.batavia_heat_energy_delivered') | float(0) %}
          {% set consumed = states('sensor.your_kwh_sensor') | float(0) %}
          {% if consumed > 0 %}
            {{ (delivered / consumed) | round(2) }}
          {% else %}
            unknown
          {% endif %}
```

## Troubleshooting

### Cannot connect
- Verify the Modbus TCP gateway is powered on and connected to your network
- Check that the IP address is correct and reachable from your Home Assistant instance
- Confirm the TCP port (default 502) and slave ID (default 1)
- Check RS-485 wiring

### Entities unavailable
- Check Home Assistant logs for Modbus communication errors
- Make sure the **tablet controller is disconnected** from the RS-485 bus if you are using this bus. Two masters on the same bus cause conflicts
- If readings are intermittent, try increasing the scan interval

### Sensors show 0
- HR[768], HR[773] and HR[776] return 0 when the compressor is off; this is expected
- If input register sensors show 0, verify your gateway connection is stable

## Documentation

The [`docs/`](docs/) folder contains reference documentation for the BataviaHeat R290:

- **[tablet-parameters.md](docs/tablet-parameters.md)** - Complete list of all installer parameters (N/M/F/P/G series) with HR-addresses, ranges, default values, error codes (E/F series), and optimization tips

## Contributing

This integration was built by reverse-engineering the Modbus protocol. Contributions are welcome:

1. Use the [Modbus snooper tools](https://github.com/RSloot2000/BataviaHeat-R290-Modbus/tree/main/tools) to scan your heat pump
2. Share discovered register definitions
3. Report issues with register values or entity behaviour
4. Suggest new features or improvements

## RS-485 adapter installation

> **🚧 Work in progress** - detailed instructions and photos will be added soon.

## License

MIT

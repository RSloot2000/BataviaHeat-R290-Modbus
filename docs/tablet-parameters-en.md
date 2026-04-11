# BataviaHeat R290 - Tablet Installer Parameters

> Range/option values are taken from the supplied manual (7-inch wire controller, Nov 2024).

## N-series: System Configuration

| Code | Parameter | Unit | Range / Options | HR address |
|------|-----------|------|-----------------|------------|
| N01 | Power mode | - | 0=Standard / 1=Powerful / 2=Eco / 3=Auto | 6465 |
| N02 | Heating and cooling type | - | 0=Heating only / 1=Heating+cooling / 2=Cooling only | 6466 |
| N04 | Four-way valve setting | - | 0=Heating open / 1=Cooling open | 6468 |
| N05 | Wire controller switch type | - | 0=Toggle switch / 1=Pulse switch | 6469 |
| N06 | Unit start/stop control | - | 0=Union / 1=Remote / 2=Local / 3=Wire ctrl / 4=Network ctrl | 6470 |
| N07 | Power-off memory | - | 0=Off / 1=On | 6471 |
| N08 | Power-on auto-start | - | 0=Off / 1=On | 6472 ⚠ = P01! |
| N11 | DHW function | - | 0=Off / 1=On | 6475 |
| N20 | Tank electric heater | - | 0=Off / 1=On | 6484 |
| N21 | Lower return pump | - | 0=Off / 1=On | 6485 |
| N22 | Solar | - | 0=Off / 1=On | 6486 |
| N23 | Coupling switch setting | - | 0=Off / 1=Coupling action / 2=Coupling closure / 3=On-off wire / 4=DHW electric heater / 5=External heat source | 6487 |
| N26 | Wire controller operation type | - | 0=Single zone / 2=Dual zone | 6490 |
| N27 | Load correction amplitude | °C | range | |
| N32 | Smart network | - | 0=Off / 1=On | 6496 |
| N36 | Underfloor heating inlet temp sensor | - | 0=Off / 1=On | 6500 |
| N37 | System total outlet water temp sensor | - | 0=Off / 1=On | 6501 |
| N38 | EVU PV signal | - | 0=Normally open / 1=Normally closed | 6502 |
| N39 | SG Grid signal | - | 0=Normally open / 1=Normally closed | 6503 |
| N41 | Solar temperature sensor | - | 0=Off / 1=On | 6505 |
| N48 | Zone A cooling terminal | - | 0=Radiator / 1=Fan Coil / 2=Underfloor heating | 6512 |
| N49 | Zone A heating terminal | - | 0=Radiator / 1=Fan Coil / 2=Underfloor heating | 6513 |

## M-series: Temperature & Curve Settings

> **Note: Non-linear HR mapping!** M00-M09 use a simple offset (HR = 6400 + Mxx).
> From M10 onwards the mapping shifts by +15: HR = 6400 + Mxx + 15.
> This is because G01-G04 occupy HR[6412-6415] (overlapping with M12-M15 simple offset).
> HR[6411] is NOT M11.

| Code | Parameter | Unit | Range / Options | HR address |
|------|-----------|------|-----------------|------------|
| M01 | Cooling setpoint temp | °C | 15-35 | 6401 |
| M02 | Heating setpoint temp | °C | 0-85 | 6402 |
| M03 | DHW setpoint temp | °C | 0-80 | 6403 |
| M04 | Cooling room target temp | °C | 0-80 | 6404 |
| M05 | Heating room target temp | °C | 0-80 | 6405 |
| M08 | Heating setpoint temp (zone B) | °C | 40-60 | 6408 |
| M10 | Zone A cooling curve | - | 0=Off / 1-8=Low temp curve / 9-16=High temp curve / 17=Custom | **6425** |
| M11 | Zone A heating curve | - | 0=Off / 1-8=Low temp curve / 9-16=High temp curve / 17=Custom | **6426** |
| M12 | Zone B cooling curve | - | 0=Off / 1-8=Low temp curve / 9-16=High temp curve / 17=Custom | **6427** |
| M13 | Zone B heating curve | - | 0=Off / 1-8=Low temp curve / 9-16=High temp curve / 17=Custom | **6428** |
| M14 | Custom cooling outdoor temp 1 | °C | -5 - 46 | **6429** |
| M15 | Custom cooling outdoor temp 2 | °C | -5 - 46 | **6430** |
| M16 | Custom cooling outlet temp 1 | °C | 5-25 | **6431** |
| M17 | Custom cooling outlet temp 2 | °C | 5-25 | **6432** |
| M18 | Custom heating outdoor temp 1 | °C | -25 - 35 | **6433** |
| M19 | Custom heating outdoor temp 2 | °C | -25 - 35 | **6434** |
| M20 | Custom heating outlet temp 1 | °C | 25-65 | **6435** |
| M21 | Custom heating outlet temp 2 | °C | 25-65 | **6436** |
| M35 | Min outdoor temp auto cooling | °C | 20-29 | **6450?** |
| M36 | Max outdoor temp auto cooling | °C | 10-17 | **6451?** |
| M37 | Holiday away heating | °C | 20-25 | **6452?** |
| M38 | Holiday away DHW | °C | 20-25 | **6453?** |
| M39 | Auxiliary electric heater setting | - | 0=Off / 1=Heating only / 2=DHW only / 3=Heating+DHW | |
| M40 | External heat source | - | 0=Off / 1=Heating only / 2=DHW only / 3=Heating+DHW | 6440 |
| M55 | Underfloor heating preheat temp | °C | 25-35 | 6455 |
| M56 | Underfloor heating preheat interval | min | 10-40 | 6456 |
| M57 | Underfloor heating preheat duration | hr | 48-96 | 6457 |
| M58 | Underfloor heating water temp return | °C | 0-10 | 6458 |
| M59 | Underfloor heating room temp return diff | °C | 0-10 | 6459 |
| M60 | Underfloor heating pre-drying | days | 4-15 | 6460 |
| M61 | Underfloor heating during drying | days | 3-7 | 6461 |
| M62 | Underfloor heating post-drying | days | 4-15 | 6462 |
| M63 | Underfloor heating drying temp | °C | 30-55 | 6463 |

## F-series: Fan

| Code | Parameter | Unit | Range / Options | HR address |
|------|-----------|------|-----------------|------------|
| F06 | Fan speed control | - | 0=Manual / 1=Ambient temp linear / 2=Fin temp linear | ? |
| F07 | Fan manual control | rps | 0-2000 | ? |

## P-series: Water Pump

| Code | Parameter | Unit | Range / Options | HR address |
|------|-----------|------|-----------------|------------|
| P01 | Water pump operating mode | - | 0=Continuous / 1=Stop at temp / 2=Intermittent | **6472** |
| P02 | Water pump control type | - | 1=Speed / 2=Flow / 3=ON-OFF / 4=Power | ? |
| P03 | Water pump target speed | rpm | 1000-4500 | ? |
| P04 | Water pump manufacturer | - | 0-4 | ? |
| P05 | Water pump target flow | L/hr | 0-4500 | ? |
| P06 | Lower return water pump interval | min | 5-120 | ? |
| P07 | Lower return pump sterilization | - | 0=Off / 1=On | ? |
| P08 | Lower return pump timed | - | 0=Off / 1=On | ? |
| P09 | Water pump intermittent stop time | min | ? | ? |
| P20 | Water pump intermittent running time | min | ? | ? |

## G-series: Sterilization (DHW)

| Code | Parameter | Unit | Range / Options | HR address |
|------|-----------|------|-----------------|------------|
| G01 | Sterilization function | - | 0=Off / 1=On | **6412** |
| G02 | Sterilization temperature | °C | 60-70 | **6413** |
| G03 | Sterilization max cycle | min | 90-300 | **6414** |
| G04 | Sterilization high temp duration | min | 5-60 | **6415** |

## T-series: Temperature & Status Monitor

> **Live status values** - read-only, recorded on 17 March 2026.

### Temperature Sensors

| Code | Parameter | Value | Unit | Notes |
|------|-----------|-------|------|-------|
| T01 | Ambient temp | 15.6 | °C | = HR[22] (x0.1) |
| T02 | DHW water temp | off | °C | N11=0 (DHW disabled) |
| T03 | Total water outlet temp | 48.5 | °C | = HR[1] (x0.1) |
| T04 | Total system water outlet temp | 30.5 | °C | N37=1 (sensor enabled) |
| T05 | Solar heater temp | off | °C | N22=0 (solar disabled) |
| T06 | Buffer tank upper temp sensor | 51.9 | °C | |
| T07 | Buffer tank lower temp sensor | 51.8 | °C | = HR[5]? (was 38.5°C) |
| T08 | Underfloor heating water inlet temp | off | °C | N36=0 (sensor disabled) |

### Valve Status

| Code | Parameter | Value | Notes |
|------|-----------|-------|-------|
| T09 | 3-way valve 1 status | 409 | Raw value |
| T10 | 3-way valve 2 status | 410 | Raw value |
| T11 | 3-way valve 3 status | 409 | Raw value |

### System & Mode Status

| Code | Parameter | Value | Notes |
|------|-----------|-------|-------|
| T12 | Unit status | 4 | |
| T13 | Inverter status | 35 | |
| T14 | Module compressor numbers | 1 | |
| T15 | Mode | 2 | 2=Heating |
| T16 | Current mode | 2 | 2=Heating |
| T17 | Adjustable target temp | 28.0 | °C - = HR[4] (x0.1) |
| T18 | Adjustable control temp | 51.8 | °C |

### Module Information

| Code | Parameter | Value | Notes |
|------|-----------|-------|-------|
| T19 | 0# module enabled | ● green | Active |
| T20-T26 | 1-7# module enabled | ● grey | Inactive |
| T27 | Module numbers | 1 | |

### Runtime & Compressor

| Code | Parameter | Value | Unit | Notes |
|------|-----------|-------|------|-------|
| T28 | HP system running time | 127 | hr | |
| T29 | Compressor running speed | 0.0 | rps | Compressor was off at time of reading |
| T30 | Module temp | 20.6 | °C | |
| T31 | Compressor power output | 0.00 | kW | |
| T32 | Compressor target speed | 20.0 | rps | |
| T33 | Compressor current output | 0.0 | A | |
| T34 | Compressor torque output | 0.0 | % | |
| T35 | Compressor voltage output | 0.0 | V | |
| T36 | Compressor bus voltage | 322.8 | V | DC bus voltage inverter |
| T37 | Error code | 0 | - | No fault |
| T38 | Inverter current input | 1.3 | A | |
| T39 | PFC temp | 21.4 | °C | Power Factor Correction module |
| T40 | Current speed | 0.0 | rps | |
| T41 | Frequency limit information | 7 | - | Bitfield? |
| T42 | 0# module compressor numbers | 1 | - | |
| T43-T49 | 1-7# compressor numbers | 0 | - | Inactive |

### Limits & Other

| Code | Parameter | Value | Unit | Notes |
|------|-----------|-------|------|-------|
| T89 | Compressor running time | 34 | hr | Less than T28 (127h) - active compressor time only |
| T90 | DHW max temp | 75 | °C | |
| T91 | DHW min temp | 18 | °C | |
| T92 | Cooling max temp | 35 | °C | |
| T93 | Cooling min temp | 10 | °C | |
| T94 | Heating max temp | 28 | °C | |
| T95 | Heating min temp | 28 | °C | Equal to max -> fixed target? |
| T96 | Zone B heating max temp | 0 | °C | Zone B not active (N26=0) |
| T97 | Zone B heating min temp | 0 | °C | |
| T98 | Preheating remaining minutes | 0 | min | |
| T101 | Room temp | 24.7 | °C | = HR[5010] (from tablet sensor) |
| T102 | Cooling power | 0 | - | |
| T103 | Heating power | 0 | - | Compressor was off |
| T104 | DHW power | 0 | - | |
| T105 | Cooling capacity | 0 | - | |
| T106 | Heating capacity | 0 | - | |
| T107 | DHW capacity | 0 | - | |

## O-series: Load Relay Status

> **Relay/actuator status** - read-only, ● green = active, ● grey = inactive.

| Code | Parameter | Status | Notes |
|------|-----------|--------|-------|
| O01 | Defrost indication | ● grey | No defrost |
| O02 | Fault indication | ● grey | No fault |
| O03 | External heat source setting | ● grey | M40=1, but not active at this time |
| O04 | 3-way valve 1 | ● grey | |
| O05 | 3-way valve 3 | ● grey | |
| O06 | 3-way valve 2 | ● green | Active - directing water to heating circuit |
| O07 | DHW tank electric heater | ● grey | N11=0, N20=0 |
| O09 | DHW return water pump | ● grey | N21=0 |
| O10 | Solar water pump | ● grey | N22=0 |
| O11 | Underfloor heating water pump | ● grey | |
| O12 | External circulation pump | ● green | Central heating circulation pump running |

## S-series: Unit Status (Input Signals)

> **Input signals** - read-only, ● green = active, ● grey = inactive.

| Code | Parameter | Status | Notes |
|------|-----------|--------|-------|
| S01 | Wire controller switch | ● grey | No wired thermostat |
| S02 | DHW tank electric heater feedback | ● green | Feedback signal active (despite N20=0) |
| S03 | Thermostat C signal | ● grey | No cooling demand |
| S04 | Thermostat H signal | ● grey | No heating demand at this time |
| S05 | Solar heater signal | ● grey | N22=0 |
| S06 | Smart grid SG signal | ● grey | N32=1 but no SG signal |
| S07 | Smart grid EVU signal | ● grey | No EVU signal |

---

## Coils: Tablet Buttons (FC05)

> **Discovered via passive bus sniffer** on 9 April 2026.
> The tablet sends FC05 (Write Single Coil) with value 0xFF00 as a pulse command.
> There is no toggle - each action direction has a separate coil.

### Unit On/Off

| Coil | Function | Value | Notes |
|------|----------|-------|-------|
| 1024 | Unit ON | 0xFF00 | Turns the heat pump on |
| 1025 | Unit OFF | 0xFF00 | Turns the heat pump off |

### Silent Mode

| Coil | Function | Value | Notes |
|------|----------|-------|-------|
| 1073 | Silent mode ON | 0xFF00 | Enables silent mode |
| 1074 | Silent mode OFF | 0xFF00 | Disables silent mode |
| 1075 | Silent level 1 (low) | 0xFF00 | Sets noise reduction to level 1 |
| 1076 | Silent level 2 (high) | 0xFF00 | Sets noise reduction to level 2 |

### Tablet Write Registers (FC06/FC16)

| Address | Function | Value | Notes |
|---------|----------|-------|-------|
| HR[5010] | Room temperature (tablet sensor) | 248 = 24.8°C (x0.1) | Periodically written by tablet |
| HR[5000..5006] | Tablet config/status block | - | FC16 write action, contents unknown |

---

## Error Codes

> Source: Operating manual 7-inch wire controller (Nov 2024).
> T37 = "Error code" on the tablet (value 0 = no fault).
> E-codes = faults (unit stops), F-codes = warnings (unit can continue running).

### E-codes (Faults)

| Code | Description | Possible causes |
|------|-------------|-----------------|
| E01 | Wire controller communication error | Bad connection, controller/mainboard fault, strong current interference |
| E03 | Compressor high pressure | Refrigerant leak, gas valve housing dirty/blocked, compressor bearing damaged, HP switch defective |
| E04 | Compressor low pressure | Insufficient water flow, low inlet temp, refrigerant leak, evaporator limescale |
| E06 | Inverter communication error | Power supply fault, inverter PCB defective, mainboard defective |
| E06 | Module communication error | Communication/power wires too close, bad connection module-mainboard |
| E10 | Underfloor heating inlet water temp error | Loose/damaged wiring, sensor defective, mainboard defective |
| E11 | Outlet water temp error | Loose/damaged wiring, sensor defective, mainboard defective |
| E12 | DHW tank / buffer tank temp error | Loose/damaged wiring, sensor defective, mainboard defective |
| E13 | Indoor temperature error | Loose/damaged wiring, sensor defective, mainboard defective |
| E14 | Ambient temperature error | Loose/damaged wiring, sensor defective, mainboard defective |
| E16 | Discharge temperature error | Loose/damaged wiring, sensor defective, mainboard defective |
| E21 | EEPROM data error | Data read error -> power off and restart |
| E24 | High plate return water temp | Heat exchanger blocked, sensor defective, low water flow |
| E25 | Cooling evaporation / plate HX temp too low | - |
| E26 | Outlet/inlet water temp difference abnormal | - |
| E27 | Discharge temperature too high | - |
| E31 | J5 pressure sensor error | Loose/damaged wiring, sensor defective, mainboard defective |
| E32 | J6 pressure sensor error | Loose/damaged wiring, sensor defective, mainboard defective |
| E44 | Plate heat exchanger inlet water temp error | Loose/damaged wiring, sensor defective, mainboard defective |
| E55 | Suction temperature error | Loose/damaged wiring, sensor defective, mainboard defective |
| E56 | Solar temperature sensor error | Loose/damaged wiring, sensor defective, mainboard defective |
| E58 | Coil temperature error | Loose/damaged wiring, sensor defective, mainboard defective |
| E59 | Suction temperature too low | Too much/too little refrigerant, sensor/mainboard defective |
| E60 | Frequent emergency defrost | Ambient sensor damaged, dirty heat exchanger, refrigerant shortage |
| E61 | Abnormal suction/discharge temp difference | Sensor defective, valve closed, waterway blockage, pump wrong, heat exchanger fouled |
| E62 | Fan coil unit 1-32 communication error | Connection cable defective, power supply, mainboard |
| E63 | Communication abnormal (internal/external) | Communication/power wires too close, bad connection, mainboard |
| E64 | Protocol version too low | Program error -> update procedure |
| E65 | Abnormal model setting | Mainboard code error, factory settings not restored |
| E66 | System maintenance data error | -> Restore parameters in parameter settings |
| E67 | Water tank electric heater overload | Power input error, water tank damage |
| E68 | Insufficient water flow | Water system blocked, pump unsuitable, piping too small, flow switch stuck |
| E69 | Refrigerant gas side temp error | Loose/damaged wiring, sensor defective, mainboard defective |
| E70 | Refrigerant liquid side temp error | Loose/damaged wiring, sensor defective, mainboard defective |
| E75 | R290 sensor error | Loose/damaged wiring, R290 sensor broken, mainboard broken |
| E76 | R290 leak alarm ⚠ | Gas leak, external gas interference, sensor defective |
| E77 | Water flow sensor error | Loose/damaged wiring, flow sensor broken, mainboard broken |

### F-codes (Warnings)

| Code | Description | Possible causes |
|------|-------------|-----------------|
| F16 | Compressor low pressure too low | Insufficient water flow, low inlet temp, refrigerant leak, limescale |
| F17 | Compressor high pressure too high | Refrigerant shortage, gas valve housing dirty, compressor bearing damaged, HP switch |
| F61 | Abnormal fan 1/2 speed | Loose cable, unstable voltage, mainboard/fan defective |
| F62 | Fan coil 01-32 fault | Power supply, motor stuck, fan coil blocked/damaged |
| F63 | Ambient temp limiting compressor | Loose/damaged wiring, sensor defective, mainboard defective |
| F64 | Inverter fault | Loose cable, unstable voltage, mainboard/driver board defective |
| F65 | Inverter model setting in progress | Loose cable, pump/inverter/mainboard defective |
| F66 | Inverter pump fault/warning | Water system blocked, loose cable, pump/inverter/mainboard defective |

---

## Optimization Overview (17 March 2026)

> **Situation:** Well-insulated terraced house (1989, 108 m², mid-terrace), underfloor heating + radiators, central heating only (no DHW), thermostat at 19°C.
> **Problem:** Pump runs continuously, heats water to 50°C, cycles every hour - even without heating demand.

### Changes Made

| # | Code | Parameter | Old | New | HR address | Reason |
|---|------|-----------|-----|-----|------------|--------|
| 1 | **P01** | Water pump operating mode | 0 (continuous) | **1** (stop at temp) | 6472 | Prevents unnecessary circulation and heat loss through piping |
| 2 | **M02** | Heating setpoint temp | 50°C | **35°C** | 6402 | Lowers max water temp (serves as upper limit for weather curve) |
| 3 | **M11** | Zone A heating curve | 0 (off) | **17** (custom curve) | 6426 | Activates weather-dependent control using existing M18-M21 points |
| 4 | **M21** | Custom heating outlet temp 2 | 35°C | **38°C** | 6436 | Extra margin during frost |

### Automatically Changed by Controller

| Code | Parameter | Old | New | HR address | Notes |
|------|-----------|-----|-----|------------|-------|
| M10 | Curve mode flag | 0 | 2 | 6410 | Auto-enabled when M11 was set to non-zero |
| M13 | Zone B heating curve | 0 | 17 | 6428 | Auto-sync with M11 (N26=0 = single zone) |

### Active Weather Curve After Changes (M11=17, custom)

| Outdoor temp | Water temp |
|:------------:|:----------:|
| 7°C (mild) | 28°C |
| 0°C (frost) | ~31°C |
| -5°C (cold) | 38°C |

---

## Post-optimization Verification (scan 4, 17-18 March 2026)

> 19 hours 49 minutes of measurement with tablet disconnected. 3,085,078 readings, 67,614 changes, 1,237 registers.

### Energy Consumption

| Metric | Before (scan 3) | After (scan 4) | Reduction |
|--------|-----------------|-----------------|-----------|
| Average power | 1,430 W | 224 W | **84%** |
| Estimated COP | ~2.5 | ~4.0+ | +60% |

### Compressor

| Metric | Before | After |
|--------|--------|-------|
| Cycles per 20 hours | ~20 | **6** |
| Average run time | ~12 min | **38.2 min** |
| Duty cycle | ~33% | **19%** |
| Average pause | ~48 min | **87.7 min** |

### Water Pump (P01=1)

| Metric | Before | After |
|--------|--------|-------|
| Pump mode | Continuous (P01=0) | Stop at temp (P01=1) |
| Pump OFF time | 0% | **76.8%** |

### Weather Curve (M11=17)

| Metric | Before | After |
|--------|--------|-------|
| HR[816] water temp target | Static 50.0°C | **Dynamic 28.0-29.0°C** |
| Status | INACTIVE | **ACTIVE** |
| Curve response | - | 28°C at 15°C outdoor, 29°C below 6°C |

### Temperatures (average)

| Sensor | Before | After |
|--------|--------|-------|
| Discharge temp (HR[36]) | 45.6°C | **23.7°C** |
| Plate HX inlet (HR[40]) | 30.5°C | **17.1°C** |
| Water outlet (HR[1]) | 23.6°C | **30.1°C** |

### Conclusion

The three changes (M02=35, M11=17, P01=1) plus the optional M21=38 resulted in:
- **84% lower power consumption** (1,430 W -> 224 W average)
- **76.8% less pump run time** (pump stops when no heating demand)
- **Longer compressor cycles** (38 min instead of ~12 min = less wear, better efficiency)
- **Lower water temperature** (28-29°C instead of 50°C = much higher COP)
- **Higher outlet temp** (30.1°C instead of 23.6°C - more effective due to longer cycles)

"""Live monitor: total power (U×I) vs compressor power (HR[41]).

Shows the difference between total system consumption and compressor-only power.
Run while triggering the heat pump to see the standby draw vs running draw.

Press Ctrl+C to stop.
"""
import time
from datetime import datetime
from pymodbus.client import ModbusSerialClient

PORT = "COM5"
SLAVE = 1

client = ModbusSerialClient(port=PORT, baudrate=9600, parity="N", stopbits=1, timeout=2)
client.connect()

print(f"{'Tijd':<12} {'Netspanning':>11} {'Inv.stroom':>11} {'Totaal P':>9} {'Compr.P':>8} {'Verschil':>9}")
print(f"{'':.<12} {'(V)':>11} {'(A)':>11} {'(W)':>9} {'(W)':>8} {'(W)':>9}")
print("-" * 75)

try:
    while True:
        # HR[1338] = mains voltage (×0.1)
        r1 = client.read_holding_registers(1338, 1, device_id=SLAVE)
        voltage = r1.registers[0] * 0.1 if not r1.isError() else None

        # HR[1325] = inverter input current (×0.1)
        r2 = client.read_holding_registers(1325, 1, device_id=SLAVE)
        current = r2.registers[0] * 0.1 if not r2.isError() else None

        # HR[41] = compressor power (W)
        r3 = client.read_holding_registers(41, 1, device_id=SLAVE)
        comp_w = r3.registers[0] if not r3.isError() else None

        now = datetime.now().strftime("%H:%M:%S")

        if voltage is not None and current is not None and comp_w is not None:
            total_w = voltage * current
            diff = total_w - comp_w
            print(f"{now:<12} {voltage:>10.1f}V {current:>10.1f}A {total_w:>8.0f}W {comp_w:>7d}W {diff:>8.0f}W")
        else:
            print(f"{now:<12} LEESFOUT")

        time.sleep(5)

except KeyboardInterrupt:
    print("\nGestopt.")
finally:
    client.close()

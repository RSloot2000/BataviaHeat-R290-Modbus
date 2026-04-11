"""Quick probe: try a few addresses above 730 and show exact Modbus responses."""
import logging
from pymodbus.client import ModbusSerialClient

# Show all pymodbus detail
logging.basicConfig(level=logging.DEBUG)

client = ModbusSerialClient(port="COM5", baudrate=9600, parity="N", stopbits=1, bytesize=8, timeout=1)
client.connect()

test_addrs = [730, 740, 750, 800, 1000]

for addr in test_addrs:
    print(f"\n{'='*60}")
    print(f"HR[{addr}]:")
    resp = client.read_holding_registers(addr, count=1, device_id=1)
    print(f"  isError: {resp.isError()}")
    if resp.isError():
        print(f"  Response type: {type(resp).__name__}")
        print(f"  Response: {resp}")
        if hasattr(resp, 'exception_code'):
            codes = {1: "Illegal Function", 2: "Illegal Data Address",
                     3: "Illegal Data Value", 4: "Slave Device Failure"}
            print(f"  Exception code: {resp.exception_code} = {codes.get(resp.exception_code, 'Unknown')}")
    else:
        print(f"  Value: {resp.registers[0]}")

client.close()

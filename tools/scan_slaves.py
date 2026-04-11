#!/usr/bin/env python3
"""
Scan all Modbus slave addresses (1-247) to discover devices on the RS-485 bus.

Uses raw serial + manual Modbus RTU framing for full control over the bus.
This avoids pymodbus's internal response matching which can hang when
slave 1 responds to requests meant for other slaves.

Known: Slave ID 1 = heat pump outdoor unit.
Looking for: controller tablet (which may hold the missing firmware strings).
"""

import struct
import time
import serial
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table

console = Console()

PORT = "COM5"
BAUDRATE = 9600
TIMEOUT = 0.15  # Very short — real slaves respond within ~50ms at 9600 baud
SLAVE_RANGE = range(1, 248)  # Modbus valid range: 1-247


def crc16(data: bytes) -> int:
    """Modbus CRC-16 calculation."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def build_read_request(slave_id: int, function_code: int, start_addr: int, count: int) -> bytes:
    """Build a Modbus RTU request frame."""
    pdu = struct.pack(">BBHH", slave_id, function_code, start_addr, count)
    crc = crc16(pdu)
    return pdu + struct.pack("<H", crc)


def parse_response(data: bytes, expected_slave: int) -> tuple[int | None, list[int]]:
    """Parse a Modbus RTU response. Returns (actual_slave_id, register_values)."""
    if len(data) < 5:
        return None, []

    actual_slave = data[0]
    func_code = data[1]

    # Check for exception response
    if func_code & 0x80:
        return actual_slave, []

    # Normal response: slave_id, func_code, byte_count, data..., crc_lo, crc_hi
    byte_count = data[2]
    if len(data) < 3 + byte_count + 2:
        return actual_slave, []

    # Verify CRC
    payload = data[:3 + byte_count]
    expected_crc = crc16(payload)
    actual_crc = struct.unpack("<H", data[3 + byte_count:5 + byte_count])[0]
    if expected_crc != actual_crc:
        return actual_slave, []

    # Parse register values
    values = []
    for i in range(0, byte_count, 2):
        values.append(struct.unpack(">H", data[3 + i:5 + i])[0])

    return actual_slave, values


def probe_slave(ser: serial.Serial, slave_id: int) -> list[tuple[str, int, int, int]]:
    """
    Probe a slave with holding and input register reads.
    Returns list of (type, addr, actual_slave_id, value) tuples.
    """
    hits = []

    for func_code, reg_type, addr in [(0x03, "holding", 0), (0x04, "input", 0)]:
        ser.reset_input_buffer()
        time.sleep(0.01)  # Let buffer clear

        request = build_read_request(slave_id, func_code, addr, 1)
        ser.write(request)
        ser.flush()  # Ensure bytes are sent

        # Wait for full response: at 9600 baud, 7 bytes = ~7.3ms + device processing
        # Normal response is 7 bytes (slave+fc+count+2data+2crc)
        time.sleep(0.05)  # 50ms — enough for device to process and respond
        response = bytearray()
        deadline = time.monotonic() + TIMEOUT
        while time.monotonic() < deadline:
            waiting = ser.in_waiting
            if waiting:
                response.extend(ser.read(waiting))
                if len(response) >= 7:  # Minimum valid response length
                    break
                time.sleep(0.01)
            else:
                time.sleep(0.02)

        if response:
            actual_slave, values = parse_response(bytes(response), slave_id)
            if actual_slave == slave_id and values:
                hits.append((reg_type, addr, actual_slave, values[0]))

    return hits


def main():
    console.print("[bold cyan]BataviaHeat Modbus Slave Address Scanner[/bold cyan]")
    console.print(f"Port: {PORT}, Baud: {BAUDRATE}, Response timeout: {TIMEOUT}s")
    console.print(f"Scanning slave IDs {SLAVE_RANGE.start}-{SLAVE_RANGE.stop - 1}...")
    console.print("[dim]Using raw serial for reliable slave ID matching[/dim]\n")

    ser = serial.Serial(
        port=PORT, baudrate=BAUDRATE, parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE, bytesize=serial.EIGHTBITS,
        timeout=TIMEOUT,
    )
    ser.reset_input_buffer()

    found_slaves: dict[int, list] = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[cyan]Scanning slaves"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("[dim]ID {task.fields[current]}, found: {task.fields[found]}[/dim]"),
        console=console,
        refresh_per_second=4,
    ) as progress:
        task = progress.add_task("scan", total=len(SLAVE_RANGE), current=0, found=0)

        for slave_id in SLAVE_RANGE:
            progress.update(task, current=slave_id)
            hits = probe_slave(ser, slave_id)
            if hits:
                found_slaves[slave_id] = hits
                console.print(f"  [green]Slave {slave_id} RESPONDED![/green] {len(hits)} register(s)")
            progress.advance(task)
            progress.update(task, found=len(found_slaves))

    ser.close()

    # Summary
    console.print(f"\n[bold]Scan complete. Found {len(found_slaves)} active slave(s).[/bold]\n")

    if found_slaves:
        table = Table(title="Active Modbus Slaves")
        table.add_column("Slave ID", style="cyan", justify="right")
        table.add_column("Registers", style="green")
        table.add_column("Values", style="yellow")

        for slave_id, hits in sorted(found_slaves.items()):
            regs = ", ".join(f"{t}[{a}]" for t, a, _, _ in hits)
            vals = ", ".join(f"{v} (0x{v:04X})" for _, _, _, v in hits)
            table.add_row(str(slave_id), regs, vals)

        console.print(table)
    else:
        console.print("[yellow]No slaves responded.[/yellow]")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]Scan interrupted.[/yellow]")

"""DataUpdateCoordinator for BataviaHeat R290."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from pymodbus.client import ModbusSerialClient, ModbusTcpClient
from pymodbus.exceptions import ModbusException

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_BAUDRATE,
    CONF_CONNECTION_TYPE,
    CONF_HOST,
    CONF_SERIAL_PORT,
    CONF_SLAVE_ID,
    CONF_TCP_PORT,
    CONNECTION_SERIAL,
    CONNECTION_TCP,
    DEFAULT_BAUDRATE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    HOLDING_REGISTERS,
    INPUT_REGISTERS,
    SENSOR_DISCONNECTED,
)

_LOGGER = logging.getLogger(__name__)

# Efficient bulk-read groups: (start_address, count)
# Split by function code — FC03=FC04 is NOT true for all address ranges.
# Addresses 135+ return wrong data via FC03; must use FC04.

# FC03 — Holding registers (operational, config, setpoints)
_HOLDING_READ_GROUPS: list[tuple[int, int]] = [
    (768, 9),     # HR[768-776]: operational status .. water outlet temp
    (1283, 1),    # HR[1283]: compressor running
    (1348, 3),    # HR[1348-1350]: plate HX inlet/outlet (T78/T79) + total water outlet (T80)
    (3230, 2),    # HR[3230-3231]: buffer inlet/outlet temperatures
    (6402, 1),    # HR[6402]: max heating temperature
    (6426, 11),   # HR[6426-6436]: heating curve params
    (6465, 1),    # HR[6465]: N01 power mode
]

# FC04 — Input registers (live sensor data from heat pump hardware)
_INPUT_READ_GROUPS: list[tuple[int, int]] = [
    (22, 4),      # IR[22-25]: ambient, fin coil, suction, discharge temps
    (32, 2),      # IR[32-33]: low/high pressure
    (53, 2),      # IR[53-54]: pump target speed, flow rate
    (66, 1),      # IR[66]: pump control signal
    (135, 8),     # IR[135-142]: HX temps, module temps, pump feedback
]

# Build lookup: address → (dict_key, reg_info) for fast dispatch after bulk read
_ADDR_MAP: dict[int, tuple[str, dict]] = {}
for _addr, _info in HOLDING_REGISTERS.items():
    _ADDR_MAP[_addr] = ("holding", _info)
for _addr, _info in INPUT_REGISTERS.items():
    _ADDR_MAP[_addr] = ("input", _info)


class BataviaHeatCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage fetching data from BataviaHeat R290 via Modbus."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.config_entry = entry
        self._connection_type = entry.data.get(CONF_CONNECTION_TYPE, CONNECTION_TCP)
        self._slave_id = entry.data[CONF_SLAVE_ID]
        self._client: ModbusTcpClient | ModbusSerialClient | None = None

        if self._connection_type == CONNECTION_SERIAL:
            self._serial_port = entry.data[CONF_SERIAL_PORT]
            self._baudrate = entry.data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE)
        else:
            self._host = entry.data[CONF_HOST]
            self._tcp_port = entry.data[CONF_TCP_PORT]

    def _get_client(self) -> ModbusTcpClient | ModbusSerialClient:
        """Get or create the Modbus client."""
        if self._client is None or not self._client.connected:
            if self._connection_type == CONNECTION_SERIAL:
                self._client = ModbusSerialClient(
                    port=self._serial_port,
                    baudrate=self._baudrate,
                    stopbits=1,
                    bytesize=8,
                    parity="N",
                    timeout=5,
                )
                if not self._client.connect():
                    raise ConnectionError(f"Cannot open serial port {self._serial_port}")
            else:
                self._client = ModbusTcpClient(
                    host=self._host,
                    port=self._tcp_port,
                    timeout=5,
                )
                if not self._client.connect():
                    raise ConnectionError(f"Cannot connect to {self._host}:{self._tcp_port}")
        return self._client

    def _reset_client(self) -> None:
        """Force-close the client so the next poll creates a fresh connection."""
        if self._client:
            try:
                self._client.close()
            except Exception:  # noqa: BLE001
                pass
            self._client = None

    def _read_all_registers(self) -> dict[str, Any]:
        """Read all configured registers using FC03 (holding) and FC04 (input).

        FC03 and FC04 return identical data for low addresses (0-100),
        but for addresses 135+ FC04 is required for correct sensor data.
        """
        client = self._get_client()
        data: dict[str, Any] = {
            "holding": {},
            "input": {},
            "coil": {},
            "discrete": {},
        }

        def _process_registers(start_addr: int, registers: list[int]) -> None:
            for i, raw in enumerate(registers):
                addr = start_addr + i
                if addr not in _ADDR_MAP:
                    continue
                if raw in SENSOR_DISCONNECTED:
                    continue
                dict_key, reg_info = _ADDR_MAP[addr]
                scale = reg_info.get("scale", 1)
                if reg_info.get("signed", True) and raw > 32767:
                    raw = raw - 65536
                data[dict_key][addr] = raw * scale

        # FC03 — Holding registers
        for start_addr, count in _HOLDING_READ_GROUPS:
            try:
                result = client.read_holding_registers(
                    start_addr, count=count, device_id=self._slave_id
                )
                if result.isError():
                    _LOGGER.debug("Error reading HR[%d..%d]: %s", start_addr, start_addr + count - 1, result)
                    continue
                _process_registers(start_addr, result.registers)
            except ModbusException as err:
                _LOGGER.debug("Modbus error reading HR[%d..%d]: %s", start_addr, start_addr + count - 1, err)

        # FC04 — Input registers
        for start_addr, count in _INPUT_READ_GROUPS:
            try:
                result = client.read_input_registers(
                    start_addr, count=count, device_id=self._slave_id
                )
                if result.isError():
                    _LOGGER.debug("Error reading IR[%d..%d]: %s", start_addr, start_addr + count - 1, result)
                    continue
                _process_registers(start_addr, result.registers)
            except ModbusException as err:
                _LOGGER.debug("Modbus error reading IR[%d..%d]: %s", start_addr, start_addr + count - 1, err)

        return data

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the heat pump."""
        try:
            return await self.hass.async_add_executor_job(self._read_all_registers)
        except ConnectionError as err:
            self._reset_client()
            raise UpdateFailed(f"Connection error: {err}") from err
        except Exception as err:
            self._reset_client()
            raise UpdateFailed(f"Error communicating with heat pump: {err}") from err

    async def async_write_register(self, address: int, value: int) -> None:
        """Write a value to a holding register."""
        def _write() -> None:
            client = self._get_client()
            result = client.write_register(address, value, device_id=self._slave_id)
            if result.isError():
                raise ModbusException(f"Failed to write register {address}")

        await self.hass.async_add_executor_job(_write)
        await self.async_request_refresh()

    async def async_write_coil(self, address: int, value: bool) -> None:
        """Write a value to a coil."""
        def _write() -> None:
            client = self._get_client()
            result = client.write_coil(address, value, device_id=self._slave_id)
            if result.isError():
                raise ModbusException(f"Failed to write coil {address}")

        await self.hass.async_add_executor_job(_write)
        await self.async_request_refresh()

    async def async_close(self) -> None:
        """Close the Modbus connection."""
        if self._client:
            await self.hass.async_add_executor_job(self._client.close)
            self._client = None

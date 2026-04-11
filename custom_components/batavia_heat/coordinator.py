"""DataUpdateCoordinator for BataviaHeat R290."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    COILS,
    CONF_HOST,
    CONF_SLAVE_ID,
    CONF_TCP_PORT,
    DEFAULT_SCAN_INTERVAL,
    DISCRETE_INPUTS,
    DOMAIN,
    HOLDING_REGISTERS,
    INPUT_REGISTERS,
    SENSOR_DISCONNECTED,
)

_LOGGER = logging.getLogger(__name__)


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
        self._host = entry.data[CONF_HOST]
        self._tcp_port = entry.data[CONF_TCP_PORT]
        self._slave_id = entry.data[CONF_SLAVE_ID]
        self._client: ModbusTcpClient | None = None

    def _get_client(self) -> ModbusTcpClient:
        """Get or create the Modbus client."""
        if self._client is None or not self._client.connected:
            self._client = ModbusTcpClient(
                host=self._host,
                port=self._tcp_port,
                timeout=3,
            )
            if not self._client.connect():
                raise ConnectionError(f"Cannot connect to {self._host}:{self._tcp_port}")
        return self._client

    def _read_all_registers(self) -> dict[str, Any]:
        """Read all configured registers from the heat pump."""
        client = self._get_client()
        data: dict[str, Any] = {
            "holding": {},
            "input": {},
            "coil": {},
            "discrete": {},
        }

        # Read holding registers
        for addr, reg_info in HOLDING_REGISTERS.items():
            try:
                result = client.read_holding_registers(addr, count=1, device_id=self._slave_id)
                if not result.isError():
                    raw = result.registers[0]
                    if raw in SENSOR_DISCONNECTED:
                        continue  # Skip disconnected sensors
                    scale = reg_info.get("scale", 1)
                    # Handle signed values (skip for unsigned counters)
                    if reg_info.get("signed", True) and raw > 32767:
                        raw = raw - 65536
                    data["holding"][addr] = raw * scale
            except (ModbusException, Exception) as err:
                _LOGGER.debug("Error reading holding register %d: %s", addr, err)

        # Read input registers
        for addr, reg_info in INPUT_REGISTERS.items():
            try:
                result = client.read_input_registers(addr, count=1, device_id=self._slave_id)
                if not result.isError():
                    raw = result.registers[0]
                    if raw in SENSOR_DISCONNECTED:
                        continue  # Skip disconnected sensors
                    scale = reg_info.get("scale", 1)
                    if raw > 32767:
                        raw = raw - 65536
                    data["input"][addr] = raw * scale
            except (ModbusException, Exception) as err:
                _LOGGER.debug("Error reading input register %d: %s", addr, err)

        # Read coils
        for addr in COILS:
            try:
                result = client.read_coils(addr, count=1, device_id=self._slave_id)
                if not result.isError():
                    data["coil"][addr] = bool(result.bits[0])
            except (ModbusException, Exception) as err:
                _LOGGER.debug("Error reading coil %d: %s", addr, err)

        # Read discrete inputs
        for addr in DISCRETE_INPUTS:
            try:
                result = client.read_discrete_inputs(addr, count=1, device_id=self._slave_id)
                if not result.isError():
                    data["discrete"][addr] = bool(result.bits[0])
            except (ModbusException, Exception) as err:
                _LOGGER.debug("Error reading discrete input %d: %s", addr, err)

        return data

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the heat pump."""
        try:
            return await self.hass.async_add_executor_job(self._read_all_registers)
        except ConnectionError as err:
            raise UpdateFailed(f"Connection error: {err}") from err
        except Exception as err:
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

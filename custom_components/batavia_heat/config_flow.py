"""Config flow for BataviaHeat R290 integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
)

from .const import (
    CONF_BAUDRATE,
    CONF_CONNECTION_TYPE,
    CONF_ENERGY_ENTITY,
    CONF_HOST,
    CONF_SERIAL_PORT,
    CONF_SLAVE_ID,
    CONF_TCP_PORT,
    CONNECTION_SERIAL,
    CONNECTION_TCP,
    DEFAULT_BAUDRATE,
    DEFAULT_SLAVE_ID,
    DEFAULT_TCP_PORT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def validate_tcp_connection(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Validate TCP connection to the heat pump."""
    from pymodbus.client import ModbusTcpClient

    def _test() -> None:
        # NumberSelector returns float — pymodbus needs int for port and device_id
        port = int(data[CONF_TCP_PORT])
        slave = int(data[CONF_SLAVE_ID])
        client = ModbusTcpClient(
            host=data[CONF_HOST],
            port=port,
            timeout=5,
        )
        try:
            if not client.connect():
                raise ConnectionError("Cannot connect to host")
            # Read HR[22] (ambient temperature) — confirmed working register
            result = client.read_holding_registers(22, count=1, device_id=slave)
            if result.isError():
                raise ConnectionError("No Modbus response from device")
        finally:
            client.close()

    await hass.async_add_executor_job(_test)


async def validate_serial_connection(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Validate serial (RTU) connection to the heat pump."""
    from pymodbus.client import ModbusSerialClient

    def _test() -> None:
        slave = int(data[CONF_SLAVE_ID])
        baudrate = int(data[CONF_BAUDRATE])
        client = ModbusSerialClient(
            port=data[CONF_SERIAL_PORT],
            baudrate=baudrate,
            stopbits=1,
            bytesize=8,
            parity="N",
            timeout=5,
        )
        try:
            if not client.connect():
                raise ConnectionError("Cannot open serial port")
            result = client.read_holding_registers(22, count=1, device_id=slave)
            if result.isError():
                raise ConnectionError("No Modbus response from device")
        finally:
            client.close()

    await hass.async_add_executor_job(_test)


class BataviaHeatConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BataviaHeat R290."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._connection_type: str = CONNECTION_TCP

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> BataviaHeatOptionsFlow:
        """Get the options flow handler."""
        return BataviaHeatOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: Choose connection type."""
        if user_input is not None:
            self._connection_type = user_input[CONF_CONNECTION_TYPE]
            if self._connection_type == CONNECTION_SERIAL:
                return await self.async_step_serial()
            return await self.async_step_tcp()

        data_schema = vol.Schema(
            {
                vol.Required(CONF_CONNECTION_TYPE, default=CONNECTION_TCP): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=CONNECTION_TCP, label="Modbus TCP"),
                            SelectOptionDict(value=CONNECTION_SERIAL, label="Modbus RTU (Serial)"),
                        ],
                    )
                ),
            }
        )

        return self.async_show_form(step_id="user", data_schema=data_schema)

    async def async_step_tcp(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2a: Configure TCP connection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # NumberSelector returns float — cast to int for pymodbus
            user_input[CONF_TCP_PORT] = int(user_input[CONF_TCP_PORT])
            user_input[CONF_SLAVE_ID] = int(user_input[CONF_SLAVE_ID])

            await self.async_set_unique_id(
                f"tcp_{user_input[CONF_HOST]}:{user_input[CONF_TCP_PORT]}_{user_input[CONF_SLAVE_ID]}"
            )
            self._abort_if_unique_id_configured()

            try:
                await validate_tcp_connection(self.hass, user_input)
            except ConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception during setup")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"BataviaHeat R290 ({user_input[CONF_HOST]}:{user_input[CONF_TCP_PORT]})",
                    data={CONF_CONNECTION_TYPE: CONNECTION_TCP, **user_input},
                )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_TCP_PORT, default=DEFAULT_TCP_PORT): NumberSelector(
                    NumberSelectorConfig(min=1, max=65535, step=1, mode=NumberSelectorMode.BOX)
                ),
                vol.Required(CONF_SLAVE_ID, default=DEFAULT_SLAVE_ID): NumberSelector(
                    NumberSelectorConfig(min=1, max=247, step=1, mode=NumberSelectorMode.BOX)
                ),
            }
        )

        return self.async_show_form(
            step_id="tcp", data_schema=data_schema, errors=errors
        )

    async def async_step_serial(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2b: Configure serial (RTU) connection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input.setdefault(CONF_BAUDRATE, DEFAULT_BAUDRATE)
            user_input[CONF_SLAVE_ID] = int(user_input[CONF_SLAVE_ID])
            user_input[CONF_BAUDRATE] = int(user_input[CONF_BAUDRATE])
            await self.async_set_unique_id(
                f"serial_{user_input[CONF_SERIAL_PORT]}_{user_input[CONF_SLAVE_ID]}"
            )
            self._abort_if_unique_id_configured()

            try:
                await validate_serial_connection(self.hass, user_input)
            except ConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception during setup")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"BataviaHeat R290 ({user_input[CONF_SERIAL_PORT]})",
                    data={CONF_CONNECTION_TYPE: CONNECTION_SERIAL, **user_input},
                )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_SERIAL_PORT): str,
                vol.Required(CONF_SLAVE_ID, default=DEFAULT_SLAVE_ID): NumberSelector(
                    NumberSelectorConfig(min=1, max=247, step=1, mode=NumberSelectorMode.BOX)
                ),
                vol.Optional(CONF_BAUDRATE, default=DEFAULT_BAUDRATE): NumberSelector(
                    NumberSelectorConfig(min=1200, max=115200, step=1, mode=NumberSelectorMode.BOX)
                ),
            }
        )

        return self.async_show_form(
            step_id="serial", data_schema=data_schema, errors=errors
        )


class BataviaHeatOptionsFlow(OptionsFlow):
    """Handle options flow for BataviaHeat R290."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            # Ensure empty optional field is stored explicitly
            if CONF_ENERGY_ENTITY not in user_input:
                user_input[CONF_ENERGY_ENTITY] = ""
            return self.async_create_entry(data=user_input)

        current = self._config_entry.options.get(CONF_ENERGY_ENTITY, "")
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_ENERGY_ENTITY,
                    description={"suggested_value": current} if current else {},
                ): EntitySelector(
                    EntitySelectorConfig(
                        domain="sensor",
                        device_class="energy",
                    )
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)

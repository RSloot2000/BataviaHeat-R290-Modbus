"""Config flow for BataviaHeat R290 integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import (
    CONF_HOST,
    CONF_SLAVE_ID,
    CONF_TCP_PORT,
    DEFAULT_SLAVE_ID,
    DEFAULT_TCP_PORT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def validate_connection(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, str]:
    """Validate the user input allows us to connect to the heat pump."""
    from pymodbus.client import ModbusTcpClient

    def _test_connection() -> None:
        client = ModbusTcpClient(
            host=data[CONF_HOST],
            port=data[CONF_TCP_PORT],
            timeout=3,
        )
        try:
            if not client.connect():
                raise ConnectionError("Cannot connect to host")

            # Try reading a register to verify communication
            result = client.read_holding_registers(0, count=1, device_id=data[CONF_SLAVE_ID])
            if result.isError():
                raise ConnectionError("No Modbus response from device")
        finally:
            client.close()

    await hass.async_add_executor_job(_test_connection)
    return {"title": f"BataviaHeat R290 ({data[CONF_HOST]}:{data[CONF_TCP_PORT]})"}


class BataviaHeatConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BataviaHeat R290."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(
                f"{user_input[CONF_HOST]}:{user_input[CONF_TCP_PORT]}_{user_input[CONF_SLAVE_ID]}"
            )
            self._abort_if_unique_id_configured()

            try:
                info = await validate_connection(self.hass, user_input)
            except ConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception during setup")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

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
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

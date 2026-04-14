"""Climate platform for BataviaHeat R290."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import BataviaHeatCoordinator
from .entity import BataviaHeatEntity

_LOGGER = logging.getLogger(__name__)

# Coil addresses for unit on/off (pulse-based, FC05)
COIL_UNIT_ON = 1024
COIL_UNIT_OFF = 1025

# Register addresses
REG_TARGET_TEMP = 772     # HR[772]: Calculated heating curve setpoint (°C, scale=0.1)
REG_WRITE_TEMP = 6402     # HR[6402]: Max heating temperature / M02 (°C, scale=1)
REG_CURRENT_TEMP = 1350   # HR[1350]: T80 total water outlet temperature (°C, scale=0.1)
REG_OP_STATUS = 768       # HR[768]: Operational status (0 = off, >0 = running)
REG_CURVE_MODE = 6426     # HR[6426]: Heating curve mode (0 = off, >0 = curve active)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BataviaHeat climate entity."""
    coordinator: BataviaHeatCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BataviaHeatClimate(coordinator)])


class BataviaHeatClimate(BataviaHeatEntity, ClimateEntity):
    """Climate entity for BataviaHeat R290 heat pump (CV heating only)."""

    _attr_has_entity_name = True
    _attr_name = "Heat Pump"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 1.0
    _attr_min_temp = 20.0
    _attr_max_temp = 60.0
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator: BataviaHeatCoordinator) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator, "holding", REG_OP_STATUS, {
            "name": "climate",
            "icon": "mdi:heat-pump",
        })

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return supported features; hide target temp when heating curve is active."""
        base = ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        if not self._is_curve_active:
            base |= ClimateEntityFeature.TARGET_TEMPERATURE
        return base

    @property
    def _is_curve_active(self) -> bool:
        """Return True if heating curve mode is active (HR[6426] > 0)."""
        if self.coordinator.data is None:
            return False
        curve = self.coordinator.data.get("holding", {}).get(REG_CURVE_MODE)
        return curve is not None and curve > 0

    @property
    def current_temperature(self) -> float | None:
        """Return the current water outlet temperature (HR[776])."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("holding", {}).get(REG_CURRENT_TEMP)

    @property
    def target_temperature(self) -> float | None:
        """Return the heating setpoint (HR[6402] = M02 parameter)."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("holding", {}).get(REG_TARGET_TEMP)

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC mode based on operational status."""
        if self.coordinator.data is None:
            return HVACMode.OFF
        status = self.coordinator.data.get("holding", {}).get(REG_OP_STATUS)
        if status is not None and status > 0:
            return HVACMode.HEAT
        return HVACMode.OFF

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature via HR[6402] (scale=1, raw = temp).

        Only allowed when heating curve is off (HR[6426] = 0).
        """
        if self._is_curve_active:
            _LOGGER.warning(
                "Cannot set temperature: heating curve is active (HR[6426] > 0). "
                "Disable the heating curve first or adjust curve parameters."
            )
            return
        if (temp := kwargs.get("temperature")) is not None:
            await self.coordinator.async_write_register(REG_WRITE_TEMP, int(temp))

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode by pulsing unit on/off coils."""
        if hvac_mode == HVACMode.HEAT:
            await self.coordinator.async_write_coil(COIL_UNIT_ON, True)
        else:
            await self.coordinator.async_write_coil(COIL_UNIT_OFF, True)

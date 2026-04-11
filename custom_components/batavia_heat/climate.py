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
REG_TARGET_TEMP = 4       # HR[4]: Heating target temperature (°C, scale already applied)
REG_CURRENT_TEMP = 136    # IR[136]: Water outlet temperature module (°C)
REG_OP_STATUS = 768       # HR[768]: Operational status (0 = off, >0 = running)


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
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator: BataviaHeatCoordinator) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator, "holding", REG_TARGET_TEMP, {
            "name": "climate",
            "icon": "mdi:heat-pump",
        })

    @property
    def current_temperature(self) -> float | None:
        """Return the current water outlet temperature (IR[136])."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("input", {}).get(REG_CURRENT_TEMP)

    @property
    def target_temperature(self) -> float | None:
        """Return the target heating temperature (HR[4])."""
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
        """Set new target temperature via HR[4]."""
        if (temp := kwargs.get("temperature")) is not None:
            await self.coordinator.async_write_register(REG_TARGET_TEMP, int(temp))

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode by pulsing unit on/off coils."""
        if hvac_mode == HVACMode.HEAT:
            await self.coordinator.async_write_coil(COIL_UNIT_ON, True)
        else:
            await self.coordinator.async_write_coil(COIL_UNIT_OFF, True)

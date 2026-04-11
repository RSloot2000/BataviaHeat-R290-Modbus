"""Number platform for BataviaHeat R290."""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, HOLDING_REGISTERS
from .coordinator import BataviaHeatCoordinator
from .entity import BataviaHeatEntity

_LOGGER = logging.getLogger(__name__)

UNIT_MAP = {
    "°C": UnitOfTemperature.CELSIUS,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BataviaHeat number entities (setpoints)."""
    coordinator: BataviaHeatCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[BataviaHeatNumber] = []

    for addr, reg_info in HOLDING_REGISTERS.items():
        if reg_info.get("entity_type") == "number":
            entities.append(BataviaHeatNumber(coordinator, "holding", addr, reg_info))

    async_add_entities(entities)


class BataviaHeatNumber(BataviaHeatEntity, NumberEntity):
    """Representation of a BataviaHeat number entity (setpoint)."""

    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: BataviaHeatCoordinator,
        reg_type: str,
        address: int,
        reg_info: dict,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, reg_type, address, reg_info)

        self._scale = reg_info.get("scale", 1)

        if unit := reg_info.get("unit"):
            self._attr_native_unit_of_measurement = UNIT_MAP.get(unit, unit)

        self._attr_native_min_value = reg_info.get("min", 0)
        self._attr_native_max_value = reg_info.get("max", 100)
        self._attr_native_step = self._scale

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("holding", {}).get(self._address)

    async def async_set_native_value(self, value: float) -> None:
        """Set a new value."""
        raw_value = int(value / self._scale)
        await self.coordinator.async_write_register(self._address, raw_value)

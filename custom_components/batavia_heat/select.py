"""Select platform for BataviaHeat R290."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, HOLDING_REGISTERS
from .coordinator import BataviaHeatCoordinator
from .entity import BataviaHeatEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BataviaHeat select entities."""
    coordinator: BataviaHeatCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[BataviaHeatSelect] = []

    for addr, reg_info in HOLDING_REGISTERS.items():
        if reg_info.get("entity_type") == "select":
            entities.append(BataviaHeatSelect(coordinator, addr, reg_info))

    async_add_entities(entities)


class BataviaHeatSelect(BataviaHeatEntity, SelectEntity):
    """Representation of a BataviaHeat select entity (enum parameter)."""

    def __init__(
        self,
        coordinator: BataviaHeatCoordinator,
        address: int,
        reg_info: dict,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator, "holding", address, reg_info)

        # options dict: {raw_value: label_key, ...}
        self._options_map: dict[int, str] = reg_info["options"]
        self._reverse_map: dict[str, int] = {v: k for k, v in self._options_map.items()}
        self._attr_options = list(self._options_map.values())

    @property
    def current_option(self) -> str | None:
        """Return the currently selected option."""
        if self.coordinator.data is None:
            return None
        raw = self.coordinator.data.get("holding", {}).get(self._address)
        if raw is None:
            return None
        return self._options_map.get(int(raw))

    async def async_select_option(self, option: str) -> None:
        """Write the selected option to the holding register."""
        if (raw := self._reverse_map.get(option)) is not None:
            await self.coordinator.async_write_register(self._address, raw)

"""Switch platform for BataviaHeat R290."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import COILS, DOMAIN
from .coordinator import BataviaHeatCoordinator
from .entity import BataviaHeatEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BataviaHeat switch entities."""
    coordinator: BataviaHeatCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[BataviaHeatSwitch] = []

    for addr, reg_info in COILS.items():
        if reg_info.get("entity_type") == "switch":
            entities.append(BataviaHeatSwitch(coordinator, addr, reg_info))

    async_add_entities(entities)


class BataviaHeatSwitch(BataviaHeatEntity, SwitchEntity):
    """Representation of a BataviaHeat pulse-coil switch.

    BataviaHeat uses separate coils for ON and OFF (fire-and-forget pulses).
    There is no readable coil state — we use assumed_state for the UI.
    """

    _attr_assumed_state = True

    def __init__(
        self,
        coordinator: BataviaHeatCoordinator,
        address: int,
        reg_info: dict,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, "coil", address, reg_info)
        self._on_coil = reg_info["on_coil"]
        self._off_coil = reg_info["off_coil"]
        self._is_on: bool | None = None

    @property
    def is_on(self) -> bool | None:
        """Return the assumed state of the switch."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on by writing the ON coil."""
        await self.coordinator.async_write_coil(self._on_coil, True)
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off by writing the OFF coil."""
        await self.coordinator.async_write_coil(self._off_coil, True)
        self._is_on = False
        self.async_write_ha_state()

"""Base entity for BataviaHeat R290."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import BataviaHeatCoordinator


class BataviaHeatEntity(CoordinatorEntity[BataviaHeatCoordinator]):
    """Base class for BataviaHeat entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BataviaHeatCoordinator,
        reg_type: str,
        address: int,
        reg_info: dict,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._reg_type = reg_type
        self._address = address
        self._reg_info = reg_info

        name = reg_info.get("name", f"{reg_type}_{address}")
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{reg_type}_{address}"
        self._attr_translation_key = name

        # Set icon if specified
        if icon := reg_info.get("icon"):
            self._attr_icon = icon

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.config_entry.entry_id)},
            name="BataviaHeat R290",
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            super().available
            and self.coordinator.data is not None
            and self._address in self.coordinator.data.get(self._reg_type, {})
        )

"""Sensor platform for BataviaHeat R290."""
from __future__ import annotations

from datetime import datetime, timezone

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfPressure,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CALCULATED_SENSORS, DOMAIN, INPUT_REGISTERS, HOLDING_REGISTERS
from .coordinator import BataviaHeatCoordinator
from .entity import BataviaHeatEntity

# Map unit strings to HA unit constants
UNIT_MAP = {
    "°C": UnitOfTemperature.CELSIUS,
    "Hz": UnitOfFrequency.HERTZ,
    "bar": UnitOfPressure.BAR,
    "W": UnitOfPower.WATT,
    "kW": UnitOfPower.KILO_WATT,
    "kWh": UnitOfEnergy.KILO_WATT_HOUR,
    "A": UnitOfElectricCurrent.AMPERE,
    "V": UnitOfElectricPotential.VOLT,
    "%": PERCENTAGE,
    "rpm": "rpm",
    "L/h": "L/h",
}

DEVICE_CLASS_MAP = {
    "temperature": SensorDeviceClass.TEMPERATURE,
    "frequency": SensorDeviceClass.FREQUENCY,
    "pressure": SensorDeviceClass.PRESSURE,
    "power": SensorDeviceClass.POWER,
    "energy": SensorDeviceClass.ENERGY,
    "voltage": SensorDeviceClass.VOLTAGE,
    "current": SensorDeviceClass.CURRENT,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BataviaHeat sensor entities."""
    coordinator: BataviaHeatCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[BataviaHeatSensor] = []

    # Sensors from input registers
    for addr, reg_info in INPUT_REGISTERS.items():
        if reg_info.get("entity_type") == "sensor":
            entities.append(BataviaHeatSensor(coordinator, "input", addr, reg_info))

    # Sensors from holding registers (read-only display)
    for addr, reg_info in HOLDING_REGISTERS.items():
        if reg_info.get("entity_type") == "sensor":
            entities.append(BataviaHeatSensor(coordinator, "holding", addr, reg_info))

    # Calculated sensors (derived from multiple registers)
    for key, calc_info in CALCULATED_SENSORS.items():
        entities.append(BataviaHeatCalculatedSensor(coordinator, key, calc_info))

    # Energy integration sensor (built-in Riemann sum)
    entities.append(BataviaHeatEnergySensor(
        coordinator,
        key="energy_delivered",
        name="energy_delivered",
        icon="mdi:fire",
        power_source="thermal_power",
        power_unit_watts=False,
    ))

    async_add_entities(entities)


class BataviaHeatSensor(BataviaHeatEntity, SensorEntity):
    """Representation of a BataviaHeat sensor."""

    def __init__(
        self,
        coordinator: BataviaHeatCoordinator,
        reg_type: str,
        address: int,
        reg_info: dict,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, reg_type, address, reg_info)

        # Device class
        if dc := reg_info.get("device_class"):
            self._attr_device_class = DEVICE_CLASS_MAP.get(dc)

        # Unit of measurement
        if unit := reg_info.get("unit"):
            self._attr_native_unit_of_measurement = UNIT_MAP.get(unit, unit)

        # State class — override from register definition (e.g. total_increasing for energy)
        sc = reg_info.get("state_class")
        if sc == "total_increasing":
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        else:
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._reg_type, {}).get(self._address)


class BataviaHeatCalculatedSensor(SensorEntity):
    """Sensor calculated from multiple Modbus registers."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: BataviaHeatCoordinator,
        key: str,
        calc_info: dict,
    ) -> None:
        """Initialize the calculated sensor."""
        self.coordinator = coordinator
        self._key = key
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_calc_{key}"
        self._attr_translation_key = calc_info["name"]

        if dc := calc_info.get("device_class"):
            self._attr_device_class = DEVICE_CLASS_MAP.get(dc)
        if unit := calc_info.get("unit"):
            self._attr_native_unit_of_measurement = UNIT_MAP.get(unit, unit)
        if icon := calc_info.get("icon"):
            self._attr_icon = icon

    @property
    def device_info(self):
        """Return device info."""
        from .const import MANUFACTURER, MODEL
        from homeassistant.helpers.device_registry import DeviceInfo
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.config_entry.entry_id)},
            name="BataviaHeat R290",
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self.coordinator.data is not None

    @property
    def native_value(self) -> float | None:
        """Return the calculated sensor value."""
        if self.coordinator.data is None:
            return None
        data = self.coordinator.data

        if self._key == "thermal_power":
            # thermal_power = flow_rate(L/h) × (outlet−inlet)(°C) × 4.186(J/g·°C) / 3600
            # Result in kW
            flow = data.get("input", {}).get(54)      # L/h
            inlet = data.get("input", {}).get(135)     # °C (water inlet plate HX)
            outlet = data.get("input", {}).get(136)    # °C (water outlet plate HX)
            if flow is None or inlet is None or outlet is None:
                return None
            if flow <= 0:
                return 0.0
            result = round(flow * (outlet - inlet) * 4.186 / 3600, 3)
            # Sanity check: 3-8kW heat pump, max ~15kW realistic
            if abs(result) > 30:
                return None
            # Heating mode: thermal power should be positive
            return max(result, 0.0)

        return None

    async def async_added_to_hass(self) -> None:
        """Register update listener."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )


class BataviaHeatEnergySensor(RestoreEntity, SensorEntity):
    """Energy sensor with built-in Riemann sum integration.

    Integrates a power source (W or kW) over time to produce kWh.
    Uses RestoreEntity to persist the accumulated value across HA restarts.
    Uses state_class TOTAL_INCREASING so HA's energy dashboard accepts it.
    """

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self,
        coordinator: BataviaHeatCoordinator,
        key: str,
        name: str,
        icon: str,
        power_source: tuple[str, int] | str,
        power_unit_watts: bool,
    ) -> None:
        """Initialize the energy sensor.

        Args:
            power_source: Either (reg_type, address) tuple for a register,
                          or a string key for a calculated sensor.
            power_unit_watts: True if source is in W, False if in kW.
        """
        self.coordinator = coordinator
        self._key = key
        self._power_source = power_source
        self._power_unit_watts = power_unit_watts
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_energy_{key}"
        self._attr_translation_key = name
        self._attr_icon = icon
        self._accumulated: float = 0.0
        self._last_update: datetime | None = None

    @property
    def device_info(self):
        """Return device info."""
        from .const import MANUFACTURER, MODEL
        from homeassistant.helpers.device_registry import DeviceInfo
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.config_entry.entry_id)},
            name="BataviaHeat R290",
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self.coordinator.data is not None

    @property
    def native_value(self) -> float | None:
        """Return the accumulated energy in kWh."""
        return round(self._accumulated, 3)

    def _get_power_kw(self) -> float | None:
        """Get current power in kW from the source."""
        if self.coordinator.data is None:
            return None
        data = self.coordinator.data

        if isinstance(self._power_source, tuple):
            reg_type, addr = self._power_source
            val = data.get(reg_type, {}).get(addr)
            if val is None:
                return None
            return val / 1000.0 if self._power_unit_watts else val

        # Calculated sensor: compute inline
        if self._power_source == "thermal_power":
            flow = data.get("input", {}).get(54)
            inlet = data.get("input", {}).get(135)
            outlet = data.get("input", {}).get(136)
            if flow is None or inlet is None or outlet is None or flow <= 0:
                return 0.0
            return flow * (outlet - inlet) * 4.186 / 3600

        return None

    def _integrate(self) -> None:
        """Perform trapezoidal integration step."""
        now = datetime.now(timezone.utc)
        power_kw = self._get_power_kw()

        if power_kw is not None and power_kw >= 0 and self._last_update is not None:
            dt_hours = (now - self._last_update).total_seconds() / 3600.0
            if 0 < dt_hours < 1:  # Skip if gap > 1 hour (HA was offline)
                self._accumulated += power_kw * dt_hours

        self._last_update = now

    async def async_added_to_hass(self) -> None:
        """Restore state and register update listener."""
        if (last_state := await self.async_get_last_state()) is not None:
            if last_state.state not in (None, "unknown", "unavailable"):
                try:
                    self._accumulated = float(last_state.state)
                except (ValueError, TypeError):
                    pass

        # Set initial timestamp (don't integrate first interval after restart)
        self._last_update = datetime.now(timezone.utc)

        def _on_update() -> None:
            self._integrate()
            self.async_write_ha_state()

        self.async_on_remove(
            self.coordinator.async_add_listener(_on_update)
        )

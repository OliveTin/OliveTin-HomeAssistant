"""The OliveTin integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.components.sensor import SensorEntity

import logging

# TODO List the platforms that you want to support.
# For your initial PR, limit it to 1 platform.
_PLATFORMS: list[Platform] = [Platform.BUTTON]

# TODO Create ConfigEntry type alias with API object
# TODO Rename type alias and update all entry annotations
#type ConfigEntry = ConfigEntry[MyApi]  # noqa: F821

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class OTClient:
    pass

class OliveTinActionEntity(SensorEntity):
    def __init__(self, name):
        self._attr_name = name
        self._attr_state = 42

    @property
    def name(self):
        return self._attr_name

    @property
    def state(self):
        return self._attr_state

# TODO Update entry annotation
async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up OliveTin from a config entry."""

    # TODO 1. Create API instance
    # TODO 2. Validate the API connection (and authentication)
    # TODO 3. Store an API object for your platforms to access
    # entry.runtime_data = MyAPI(...)

    ent1 = OliveTinActionEntity("foo")

    return True


# TODO Update entry annotation
async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)


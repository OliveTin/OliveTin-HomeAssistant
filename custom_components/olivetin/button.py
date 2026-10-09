"""Button platform for OliveTin actions."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, PlatformNotReady
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OliveTinConfigEntry
from .api import OliveTinApiError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OliveTinConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up OliveTin buttons from a config entry."""
    client = entry.runtime_data.client
    try:
        actions = await client.async_get_actions()
    except OliveTinApiError as err:
        raise PlatformNotReady(str(err)) from err

    if not actions:
        _LOGGER.warning(
            "No argument-free executable OliveTin actions found on %s",
            client.host,
        )

    async_add_entities(
        OliveTinActionButton(entry, action) for action in actions
    )


class OliveTinActionButton(ButtonEntity):
    """Button that starts an OliveTin action."""

    _attr_has_entity_name = True

    def __init__(self, entry: OliveTinConfigEntry, action: dict[str, Any]) -> None:
        """Initialize the button."""
        self._entry = entry
        self._client = entry.runtime_data.client
        self._binding_id = action.get("bindingId") or action["binding_id"]
        title = action.get("title") or self._binding_id
        self._attr_name = title
        self._attr_unique_id = f"{entry.unique_id}_{self._binding_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            name=entry.title,
            manufacturer="OliveTin",
            sw_version=entry.runtime_data.version,
            configuration_url=self._client.configuration_url,
        )
        icon = action.get("icon")
        if isinstance(icon, str) and icon.startswith("mdi:"):
            self._attr_icon = icon

    async def async_press(self) -> None:
        """Handle the button press by starting the OliveTin action."""
        _LOGGER.info(
            "Starting OliveTin action %s (%s)",
            self._attr_name,
            self._binding_id,
        )
        try:
            tracking_id = await self._client.async_start_action(self._binding_id)
        except OliveTinApiError as err:
            _LOGGER.exception(
                "Failed to start OliveTin action %s", self._binding_id
            )
            raise HomeAssistantError(
                f"Failed to start OliveTin action {self._binding_id}: {err}"
            ) from err

        _LOGGER.debug(
            "OliveTin action %s started (tracking_id=%s)",
            self._binding_id,
            tracking_id,
        )

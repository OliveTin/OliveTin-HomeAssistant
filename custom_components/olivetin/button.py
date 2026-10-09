"""Button platform for OliveTin actions."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OliveTinConfigEntry
from .api import OliveTinApiError
from .const import (
    ATTR_BINDING_ID,
    ATTR_CONFIG_ENTRY_ID,
    DOMAIN,
    EVENT_ACTION_FAILED,
    EVENT_ACTION_FINISHED,
    EVENT_ACTION_STARTED,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OliveTinConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up OliveTin buttons from a config entry."""
    client = entry.runtime_data.client
    try:
        actions = await client.async_get_actions(argument_free_only=True)
    except OliveTinApiError as err:
        raise PlatformNotReady(str(err)) from err

    if not actions:
        _LOGGER.warning(
            "No argument-free executable OliveTin actions found on %s; "
            "use olivetin.start_action with arguments for parameterized actions",
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
        """Start the action and notify HA when the log entry is available."""
        _LOGGER.info(
            "Starting OliveTin action %s (%s)",
            self._attr_name,
            self._binding_id,
        )
        # Keep the button press non-blocking for the UI; wait in a task so
        # automations can consume the finished event with log entry fields.
        self.hass.async_create_task(self._async_run_action())

    async def _async_run_action(self) -> None:
        """Wait for OliveTin completion and fire HA bus events."""
        event_base = {
            ATTR_BINDING_ID: self._binding_id,
            ATTR_CONFIG_ENTRY_ID: self._entry.entry_id,
            "entity_id": self.entity_id,
            "action_title": self._attr_name,
            "host": self._client.host,
        }
        self.hass.bus.async_fire(EVENT_ACTION_STARTED, event_base)

        try:
            result = await self._client.async_start_action_and_wait(self._binding_id)
        except OliveTinApiError as err:
            _LOGGER.exception(
                "Failed to start OliveTin action %s", self._binding_id
            )
            self.hass.bus.async_fire(
                EVENT_ACTION_FAILED,
                {**event_base, "error": str(err)},
            )
            return

        self.hass.bus.async_fire(EVENT_ACTION_FINISHED, {**event_base, **result})
        _LOGGER.debug(
            "OliveTin action %s finished (tracking_id=%s, exit_code=%s)",
            self._binding_id,
            result.get("execution_tracking_id"),
            result.get("exit_code"),
        )

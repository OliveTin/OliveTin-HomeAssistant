"""Service actions for the OliveTin integration."""

from __future__ import annotations

import logging
from typing import Any, cast

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import (
    OliveTinApiError,
    action_binding_id,
    coerce_arguments,
    resolve_action_arguments,
    serialize_action_for_ha,
)
from .const import (
    ATTR_ARGUMENTS,
    ATTR_BINDING_ID,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_JUSTIFICATION,
    ATTR_WAIT,
    DOMAIN,
    EVENT_ACTION_FAILED,
    EVENT_ACTION_FINISHED,
    EVENT_ACTION_STARTED,
    SERVICE_LIST_ACTIONS,
    SERVICE_START_ACTION,
)

_LOGGER = logging.getLogger(__name__)

ARGUMENT_LIST_SCHEMA = vol.All(
    cv.ensure_list,
    [
        vol.Schema(
            {
                vol.Required("name"): cv.string,
                vol.Required("value"): vol.Any(str, int, float, bool),
            }
        )
    ],
)

START_ACTION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_BINDING_ID): cv.string,
        vol.Optional(ATTR_WAIT, default=True): cv.boolean,
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_JUSTIFICATION, default=""): cv.string,
        vol.Optional(ATTR_ARGUMENTS): vol.Any(
            {cv.string: vol.Any(str, int, float, bool)},
            ARGUMENT_LIST_SCHEMA,
        ),
    }
)

LIST_ACTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional("refresh", default=False): cv.boolean,
    }
)


def _async_get_entry(hass: HomeAssistant, config_entry_id: str | None):
    """Resolve a loaded OliveTin config entry."""
    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]
    if config_entry_id:
        for entry in entries:
            if entry.entry_id == config_entry_id:
                return entry
        raise ServiceValidationError(
            f"OliveTin config entry {config_entry_id} is not loaded"
        )
    if not entries:
        raise ServiceValidationError("No loaded OliveTin config entries")
    if len(entries) > 1:
        raise ServiceValidationError(
            "Multiple OliveTin entries loaded; set config_entry_id"
        )
    return entries[0]


async def _async_resolve_arguments(
    entry, binding_id: str, raw_arguments: Any
) -> list[dict[str, str]]:
    """Coerce and merge arguments using the cached action catalog when present."""
    try:
        provided = coerce_arguments(raw_arguments)
    except ValueError as err:
        raise ServiceValidationError(str(err)) from err

    action = entry.runtime_data.actions.get(binding_id)
    try:
        return resolve_action_arguments(action, provided)
    except ValueError as err:
        raise ServiceValidationError(str(err)) from err


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register OliveTin domain services."""

    async def async_start_action(call: ServiceCall) -> ServiceResponse:
        """Start an OliveTin action, optionally waiting for the log entry."""
        entry = _async_get_entry(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
        client = entry.runtime_data.client
        binding_id = cast(str, call.data[ATTR_BINDING_ID])
        wait = bool(call.data.get(ATTR_WAIT, True))
        justification = call.data.get(ATTR_JUSTIFICATION) or None
        arguments = await _async_resolve_arguments(
            entry, binding_id, call.data.get(ATTR_ARGUMENTS)
        )

        event_base = {
            ATTR_BINDING_ID: binding_id,
            ATTR_CONFIG_ENTRY_ID: entry.entry_id,
            ATTR_ARGUMENTS: arguments,
            "host": client.host,
        }

        try:
            if wait:
                hass.bus.async_fire(EVENT_ACTION_STARTED, event_base)
                result = await client.async_start_action_and_wait(
                    binding_id,
                    arguments=arguments,
                    justification=justification,
                )
                hass.bus.async_fire(EVENT_ACTION_FINISHED, {**event_base, **result})
            else:
                result = await client.async_start_action(
                    binding_id,
                    arguments=arguments,
                    justification=justification,
                )
                hass.bus.async_fire(EVENT_ACTION_STARTED, {**event_base, **result})
        except OliveTinApiError as err:
            hass.bus.async_fire(
                EVENT_ACTION_FAILED,
                {**event_base, "error": str(err)},
            )
            raise HomeAssistantError(
                f"Failed to start OliveTin action {binding_id}: {err}"
            ) from err

        if call.return_response:
            return result
        return None

    async def async_list_actions(call: ServiceCall) -> ServiceResponse:
        """Return the OliveTin action catalog, including argument schemas."""
        entry = _async_get_entry(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
        client = entry.runtime_data.client

        if call.data.get("refresh"):
            try:
                actions = await client.async_get_actions()
            except OliveTinApiError as err:
                raise HomeAssistantError(
                    f"Failed to refresh OliveTin actions: {err}"
                ) from err
            entry.runtime_data.actions = {
                action_binding_id(action): action for action in actions
            }

        catalog = [
            serialize_action_for_ha(action)
            for action in entry.runtime_data.actions.values()
        ]
        catalog.sort(key=lambda item: (item["title"].lower(), item["binding_id"]))
        return {"actions": catalog, "count": len(catalog)}

    hass.services.async_register(
        DOMAIN,
        SERVICE_START_ACTION,
        async_start_action,
        schema=START_ACTION_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LIST_ACTIONS,
        async_list_actions,
        schema=LIST_ACTIONS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )

    _LOGGER.debug("Registered OliveTin services")

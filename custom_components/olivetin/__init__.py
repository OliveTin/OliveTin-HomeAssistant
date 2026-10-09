"""The OliveTin integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import (
    OliveTinApiClient,
    OliveTinAuthError,
    OliveTinConnectionError,
    action_binding_id,
)
from .const import PLATFORMS
from .services import async_setup_services

type OliveTinConfigEntry = ConfigEntry[OliveTinData]


@dataclass
class OliveTinData:
    """Runtime data for an OliveTin config entry."""

    client: OliveTinApiClient
    version: str | None = None
    actions: dict[str, dict[str, Any]] = field(default_factory=dict)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the OliveTin integration (registers domain services)."""
    await async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: OliveTinConfigEntry) -> bool:
    """Set up OliveTin from a config entry."""
    # Cookie-backed LocalUserLogin needs a dedicated session (not the shared one).
    session = async_create_clientsession(hass)
    client = OliveTinApiClient(
        session,
        entry.data[CONF_HOST],
        entry.data.get(CONF_USERNAME),
        entry.data.get(CONF_PASSWORD),
    )

    try:
        init = await client.async_authenticate()
        actions = await client.async_get_actions()
    except OliveTinAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except OliveTinConnectionError as err:
        raise ConfigEntryNotReady(str(err)) from err

    version = init.get("currentVersion") or init.get("current_version")
    entry.runtime_data = OliveTinData(
        client=client,
        version=version,
        actions={action_binding_id(action): action for action in actions},
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OliveTinConfigEntry) -> bool:
    """Unload an OliveTin config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

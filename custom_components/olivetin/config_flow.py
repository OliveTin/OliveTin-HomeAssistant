"""Config flow for the OliveTin integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    OliveTinApiClient,
    OliveTinAuthError,
    OliveTinConnectionError,
    normalize_host,
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): TextSelector(),
        vol.Optional(CONF_USERNAME, default=""): TextSelector(),
        vol.Optional(CONF_PASSWORD, default=""): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, str]:
    """Validate the user input allows us to connect.

    Returns info used for the config entry title and normalized host.
    """
    host = normalize_host(data[CONF_HOST])
    session = async_create_clientsession(hass)
    client = OliveTinApiClient(
        session,
        host,
        data.get(CONF_USERNAME),
        data.get(CONF_PASSWORD),
    )

    init = await client.async_authenticate()
    # Confirm dashboard access (auth may succeed while ACLs still block).
    await client.async_get_dashboard("")

    title = init.get("pageTitle") or init.get("page_title") or "OliveTin"
    version = init.get("currentVersion") or init.get("current_version")
    if version:
        title = f"{title} ({version})"

    return {"title": title, "host": host}


class OliveTinConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OliveTin."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except ValueError:
                errors["base"] = "invalid_host"
            except OliveTinConnectionError:
                errors["base"] = "cannot_connect"
            except OliveTinAuthError:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception while configuring OliveTin")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(info["host"])
                self._abort_if_unique_id_configured()

                data = {
                    CONF_HOST: info["host"],
                    CONF_USERNAME: user_input.get(CONF_USERNAME, ""),
                    CONF_PASSWORD: user_input.get(CONF_PASSWORD, ""),
                }
                return self.async_create_entry(title=info["title"], data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

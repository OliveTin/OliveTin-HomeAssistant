"""Constants for the OliveTin integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "olivetin"

PLATFORMS: list[Platform] = [Platform.BUTTON]

# Connect RPC service path under the OliveTin HTTP API base (…/api).
API_SERVICE_PREFIX = "/olivetin.api.v1.OliveTinApiService"

DEFAULT_PORT = 1337

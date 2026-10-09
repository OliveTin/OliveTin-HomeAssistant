"""Constants for the OliveTin integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "olivetin"

PLATFORMS: list[Platform] = [Platform.BUTTON]

# Connect RPC service path under the OliveTin HTTP API base (…/api).
API_SERVICE_PREFIX = "/olivetin.api.v1.OliveTinApiService"

DEFAULT_PORT = 1337

# Allow long-running OliveTin actions when waiting for completion.
START_ACTION_WAIT_TIMEOUT = 900

ATTR_BINDING_ID = "binding_id"
ATTR_WAIT = "wait"
ATTR_ARGUMENTS = "arguments"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_JUSTIFICATION = "justification"

SERVICE_START_ACTION = "start_action"
SERVICE_LIST_ACTIONS = "list_actions"

EVENT_ACTION_STARTED = "olivetin_action_started"
EVENT_ACTION_FINISHED = "olivetin_action_finished"
EVENT_ACTION_FAILED = "olivetin_action_failed"

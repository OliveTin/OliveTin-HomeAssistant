"""HTTP API client for OliveTin (Connect RPC JSON)."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from aiohttp import ClientError, ClientResponseError, ClientSession, ClientTimeout

from .const import API_SERVICE_PREFIX, DEFAULT_PORT, START_ACTION_WAIT_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class OliveTinApiError(Exception):
    """Base exception for OliveTin API errors."""


class OliveTinConnectionError(OliveTinApiError):
    """Raised when OliveTin cannot be reached."""


class OliveTinAuthError(OliveTinApiError):
    """Raised when authentication fails."""


def normalize_host(host: str) -> str:
    """Normalize user input into an OliveTin API base URL ending with /api."""
    cleaned = host.strip().rstrip("/")
    if not cleaned:
        raise ValueError("Host is required")

    if "://" not in cleaned:
        # host, host:port, or host:port/api
        cleaned = f"http://{cleaned}"

    parsed = urlparse(cleaned)
    if not parsed.hostname:
        raise ValueError("Invalid host")

    path = (parsed.path or "").rstrip("/")
    if path in ("", "/"):
        netloc = parsed.netloc
        if ":" not in parsed.netloc and parsed.hostname:
            netloc = f"{parsed.hostname}:{DEFAULT_PORT}"
        cleaned = f"{parsed.scheme}://{netloc}/api"
    elif not path.endswith("/api"):
        cleaned = f"{parsed.scheme}://{parsed.netloc}{path}/api"
    else:
        cleaned = f"{parsed.scheme}://{parsed.netloc}{path}"

    return cleaned


class OliveTinApiClient:
    """Async client for the OliveTin Connect RPC API."""

    def __init__(
        self,
        session: ClientSession,
        host: str,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        """Initialize the client."""
        self._session = session
        self.host = normalize_host(host)
        self._username = (username or "").strip()
        self._password = password or ""
        # Username empty + password set → treat password as local-user API key.
        self._use_bearer = bool(self._password) and not self._username

    @property
    def configuration_url(self) -> str:
        """Web UI URL derived from the API base."""
        if self.host.endswith("/api"):
            return self.host[: -len("/api")] or self.host
        return self.host

    def _url(self, method: str) -> str:
        return f"{self.host}{API_SERVICE_PREFIX}/{method}"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._use_bearer:
            headers["Authorization"] = f"Bearer {self._password}"
        return headers

    async def _request(
        self,
        method: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: ClientTimeout | None = None,
    ) -> dict[str, Any]:
        """POST a Connect RPC method and return the JSON body."""
        url = self._url(method)
        try:
            async with self._session.post(
                url,
                json=payload or {},
                headers=self._headers(),
                timeout=timeout,
            ) as response:
                if response.status in (401, 403):
                    raise OliveTinAuthError("Authentication failed")
                try:
                    data = await response.json(content_type=None)
                except ValueError as err:
                    text = await response.text()
                    raise OliveTinConnectionError(
                        f"Invalid JSON from OliveTin ({response.status}): {text[:200]}"
                    ) from err

                if response.status >= 400:
                    # Connect errors often include a code/message body.
                    message = (
                        data.get("message")
                        if isinstance(data, dict)
                        else None
                    ) or f"HTTP {response.status}"
                    if response.status in (401, 403) or (
                        isinstance(data, dict)
                        and data.get("code") in ("unauthenticated", "permission_denied")
                    ):
                        raise OliveTinAuthError(message)
                    raise OliveTinConnectionError(message)

                if not isinstance(data, dict):
                    raise OliveTinConnectionError("Unexpected OliveTin response type")
                return data
        except OliveTinApiError:
            raise
        except TimeoutError as err:
            raise OliveTinConnectionError("Timeout connecting to OliveTin") from err
        except (ClientResponseError, ClientError, OSError) as err:
            raise OliveTinConnectionError(str(err)) from err

    async def async_authenticate(self) -> dict[str, Any]:
        """Authenticate (if needed) and return Init payload."""
        if self._username:
            login = await self._request(
                "LocalUserLogin",
                {"username": self._username, "password": self._password},
            )
            if not login.get("success"):
                raise OliveTinAuthError("Invalid username or password")

        init = await self.async_init()
        if init.get("loginRequired") and not (self._username or self._use_bearer):
            raise OliveTinAuthError("OliveTin requires login")
        return init

    async def async_init(self) -> dict[str, Any]:
        """Call Init and return server/session information."""
        return await self._request("Init")

    async def async_get_dashboard(self, title: str = "") -> dict[str, Any]:
        """Fetch a dashboard (empty title → default actions dashboard)."""
        return await self._request(
            "GetDashboard",
            {"title": title, "entityType": "", "entityKey": ""},
        )

    async def async_start_action(
        self,
        binding_id: str,
        arguments: list[dict[str, str]] | None = None,
        justification: str | None = None,
    ) -> dict[str, Any]:
        """Start an action without waiting; return tracking metadata."""
        payload: dict[str, Any] = {
            "bindingId": binding_id,
            "arguments": arguments or [],
        }
        if justification:
            payload["justification"] = justification

        data = await self._request("StartAction", payload)
        tracking_id = data.get("executionTrackingId") or data.get(
            "execution_tracking_id", ""
        )
        _LOGGER.debug(
            "Started OliveTin action %s (tracking_id=%s)", binding_id, tracking_id
        )
        return {
            "binding_id": binding_id,
            "execution_tracking_id": tracking_id,
            "waited": False,
        }

    async def async_start_action_and_wait(
        self,
        binding_id: str,
        arguments: list[dict[str, str]] | None = None,
        justification: str | None = None,
    ) -> dict[str, Any]:
        """Start an action, wait for completion, return normalized log entry."""
        payload: dict[str, Any] = {
            # StartActionAndWait uses actionId; OliveTin resolves it like binding IDs.
            "actionId": binding_id,
            "arguments": arguments or [],
        }
        if justification:
            payload["justification"] = justification

        data = await self._request(
            "StartActionAndWait",
            payload,
            timeout=ClientTimeout(total=START_ACTION_WAIT_TIMEOUT),
        )
        log_entry = data.get("logEntry") or data.get("log_entry") or {}
        if not isinstance(log_entry, dict):
            raise OliveTinConnectionError("OliveTin returned an invalid log entry")

        result = normalize_log_entry(log_entry)
        result["waited"] = True
        if not result.get("binding_id"):
            result["binding_id"] = binding_id
        _LOGGER.debug(
            "Finished OliveTin action %s (tracking_id=%s, exit_code=%s)",
            binding_id,
            result.get("execution_tracking_id"),
            result.get("exit_code"),
        )
        return result

    async def async_get_actions(
        self, *, argument_free_only: bool = False
    ) -> list[dict[str, Any]]:
        """Return executable actions from all root dashboards."""
        init = await self.async_init()
        titles = list(init.get("rootDashboards") or init.get("root_dashboards") or [])
        # Empty title resolves to OliveTin's default/actions dashboard.
        if "" not in titles:
            titles.insert(0, "")

        actions: list[dict[str, Any]] = []
        for title in titles:
            try:
                dashboard_response = await self.async_get_dashboard(title)
            except OliveTinApiError as err:
                _LOGGER.debug(
                    "Skipping OliveTin dashboard %r while listing actions: %s",
                    title,
                    err,
                )
                continue
            dashboard = dashboard_response.get("dashboard") or {}
            actions.extend(_collect_actions(dashboard.get("contents") or []))

        # Deduplicate by binding ID while preserving order.
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for action in actions:
            binding_id = action.get("bindingId") or action.get("binding_id")
            if not binding_id or binding_id in seen:
                continue
            can_exec = action.get("canExec", action.get("can_exec", True))
            if not can_exec:
                continue
            if argument_free_only and action_arguments(action):
                _LOGGER.debug(
                    "Skipping OliveTin action %s for buttons (requires arguments)",
                    binding_id,
                )
                continue
            seen.add(binding_id)
            result.append(action)
        return result


def _collect_actions(components: list[Any]) -> list[dict[str, Any]]:
    """Recursively collect Action messages from dashboard components."""
    actions: list[dict[str, Any]] = []
    for component in components:
        if not isinstance(component, dict):
            continue
        action = component.get("action")
        if isinstance(action, dict) and (
            action.get("bindingId") or action.get("binding_id")
        ):
            actions.append(action)
        nested = component.get("contents") or []
        if nested:
            actions.extend(_collect_actions(nested))
    return actions


def action_binding_id(action: dict[str, Any]) -> str:
    """Return the binding ID for an action dict."""
    return str(action.get("bindingId") or action.get("binding_id") or "")


def action_arguments(action: dict[str, Any]) -> list[dict[str, Any]]:
    """Return argument definitions for an action."""
    arguments = action.get("arguments") or []
    return [arg for arg in arguments if isinstance(arg, dict) and arg.get("name")]


def serialize_action_for_ha(action: dict[str, Any]) -> dict[str, Any]:
    """Serialize an OliveTin action definition for HA service responses."""
    arguments = []
    for arg in action_arguments(action):
        choices = arg.get("choices") or []
        arguments.append(
            {
                "name": arg.get("name", ""),
                "title": arg.get("title") or arg.get("name", ""),
                "type": arg.get("type") or "",
                "description": arg.get("description") or "",
                "default": arg.get("defaultValue", arg.get("default_value", "")) or "",
                "choices": [
                    {
                        "value": choice.get("value", ""),
                        "title": choice.get("title") or choice.get("value", ""),
                    }
                    for choice in choices
                    if isinstance(choice, dict)
                ],
            }
        )
    return {
        "binding_id": action_binding_id(action),
        "title": action.get("title") or action_binding_id(action),
        "can_exec": bool(action.get("canExec", action.get("can_exec", True))),
        "arguments": arguments,
    }


def coerce_arguments(
    raw: list[dict[str, Any]] | dict[str, Any] | None,
) -> list[dict[str, str]]:
    """Normalize HA service arguments to OliveTin [{name, value}] objects.

    Accepts either:
    - mapping: {"container": "jellyfin", "version": "latest"}
    - list: [{"name": "container", "value": "jellyfin"}, ...]
    """
    if raw is None:
        return []

    if isinstance(raw, dict):
        return [{"name": str(key), "value": str(value)} for key, value in raw.items()]

    if isinstance(raw, list):
        result: list[dict[str, str]] = []
        for item in raw:
            if not isinstance(item, dict) or "name" not in item or "value" not in item:
                raise ValueError(
                    "List arguments must be objects with name and value keys"
                )
            result.append({"name": str(item["name"]), "value": str(item["value"])})
        return result

    raise ValueError("arguments must be a mapping or a list of {name, value} objects")


def resolve_action_arguments(
    action: dict[str, Any] | None,
    provided: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Merge provided arguments with action defaults; reject unknown names."""
    provided_map = {item["name"]: item["value"] for item in provided}

    if action is None:
        return [{"name": name, "value": value} for name, value in provided_map.items()]

    defined = action_arguments(action)
    defined_names = {str(arg["name"]) for arg in defined}
    unknown = sorted(name for name in provided_map if name not in defined_names)
    if unknown:
        raise ValueError(
            "Unknown argument(s) for action "
            f"{action_binding_id(action)}: {', '.join(unknown)}"
        )

    resolved: list[dict[str, str]] = []
    for arg in defined:
        name = str(arg["name"])
        if name in provided_map:
            value = provided_map[name]
        else:
            value = str(arg.get("defaultValue", arg.get("default_value", "")) or "")
        resolved.append({"name": name, "value": value})
    return resolved


def normalize_log_entry(log_entry: dict[str, Any]) -> dict[str, Any]:
    """Normalize an OliveTin LogEntry into HA-friendly snake_case fields."""

    def _get(*keys: str, default: Any = None) -> Any:
        for key in keys:
            if key in log_entry:
                return log_entry[key]
        return default

    arguments = _get("arguments", default=[]) or []
    normalized_arguments = [
        {
            "name": arg.get("name", ""),
            "value": arg.get("value", ""),
        }
        for arg in arguments
        if isinstance(arg, dict)
    ]

    exit_code = _get("exitCode", "exit_code")
    if exit_code is not None:
        try:
            exit_code = int(exit_code)
        except (TypeError, ValueError):
            pass

    return {
        "binding_id": _get("bindingId", "binding_id", default="") or "",
        "action_title": _get("actionTitle", "action_title", default="") or "",
        "output": _get("output", default="") or "",
        "exit_code": exit_code,
        "timed_out": bool(_get("timedOut", "timed_out", default=False)),
        "blocked": bool(_get("blocked", default=False)),
        "queued": bool(_get("queued", default=False)),
        "execution_started": bool(
            _get("executionStarted", "execution_started", default=False)
        ),
        "execution_finished": bool(
            _get("executionFinished", "execution_finished", default=False)
        ),
        "execution_tracking_id": _get(
            "executionTrackingId", "execution_tracking_id", default=""
        )
        or "",
        "datetime_started": _get("datetimeStarted", "datetime_started", default="")
        or "",
        "datetime_finished": _get("datetimeFinished", "datetime_finished", default="")
        or "",
        "user": _get("user", default="") or "",
        "justification": _get("justification", default="") or "",
        "arguments": normalized_arguments,
        "success": (
            exit_code == 0
            and not bool(_get("timedOut", "timed_out", default=False))
            and not bool(_get("blocked", default=False))
        ),
    }

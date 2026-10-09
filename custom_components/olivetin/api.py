"""HTTP API client for OliveTin (Connect RPC JSON)."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from aiohttp import ClientError, ClientResponseError, ClientSession

from .const import API_SERVICE_PREFIX, DEFAULT_PORT

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
        self, method: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """POST a Connect RPC method and return the JSON body."""
        url = self._url(method)
        try:
            async with self._session.post(
                url, json=payload or {}, headers=self._headers()
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
    ) -> str:
        """Start an action by binding ID; return execution tracking ID."""
        data = await self._request(
            "StartAction",
            {
                "bindingId": binding_id,
                "arguments": arguments or [],
            },
        )
        tracking_id = data.get("executionTrackingId") or data.get(
            "execution_tracking_id", ""
        )
        _LOGGER.debug(
            "Started OliveTin action %s (tracking_id=%s)", binding_id, tracking_id
        )
        return tracking_id

    async def async_get_actions(self) -> list[dict[str, Any]]:
        """Return executable, argument-free actions from all root dashboards."""
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
            arguments = action.get("arguments") or []
            if arguments:
                # Buttons cannot collect arguments; skip parameterized actions.
                _LOGGER.debug(
                    "Skipping OliveTin action %s (requires arguments)", binding_id
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

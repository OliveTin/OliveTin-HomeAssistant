"""Tests for OliveTin action argument coercion and defaults."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_api_module():
    ha = types.ModuleType("homeassistant")
    ha_const = types.ModuleType("homeassistant.const")

    class Platform:
        BUTTON = "button"

    ha_const.Platform = Platform
    sys.modules["homeassistant"] = ha
    sys.modules["homeassistant.const"] = ha_const
    sys.modules.setdefault("custom_components", types.ModuleType("custom_components"))
    sys.modules.setdefault(
        "custom_components.olivetin", types.ModuleType("custom_components.olivetin")
    )

    for name in ("const", "api"):
        path = REPO_ROOT / "custom_components" / "olivetin" / f"{name}.py"
        full = f"custom_components.olivetin.{name}"
        spec = importlib.util.spec_from_file_location(full, path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules[full] = mod
        spec.loader.exec_module(mod)
    return sys.modules["custom_components.olivetin.api"]


@pytest.fixture(scope="module")
def api():
    return _load_api_module()


ACTION = {
    "bindingId": "container_upgrade",
    "title": "Upgrade Podman container",
    "canExec": True,
    "arguments": [
        {
            "name": "container",
            "title": "Container",
            "type": "regex:^[a-zA-Z0-9].*$",
            "defaultValue": "",
            "description": "Container name",
            "choices": [],
        },
        {
            "name": "version",
            "title": "Image tag",
            "type": "regex:^.*$",
            "defaultValue": "latest",
            "description": "Optional tag",
            "choices": [{"value": "latest", "title": "Latest"}],
        },
    ],
}


def test_coerce_arguments_mapping(api):
    assert api.coerce_arguments({"container": "jellyfin", "version": 1}) == [
        {"name": "container", "value": "jellyfin"},
        {"name": "version", "value": "1"},
    ]


def test_coerce_arguments_list(api):
    assert api.coerce_arguments(
        [{"name": "container", "value": "jellyfin"}]
    ) == [{"name": "container", "value": "jellyfin"}]


def test_coerce_arguments_rejects_bad_list(api):
    with pytest.raises(ValueError, match="name and value"):
        api.coerce_arguments([{"name": "container"}])


def test_resolve_merges_defaults_and_rejects_unknown(api):
    provided = api.coerce_arguments({"container": "jellyfin"})
    resolved = api.resolve_action_arguments(ACTION, provided)
    assert resolved == [
        {"name": "container", "value": "jellyfin"},
        {"name": "version", "value": "latest"},
    ]

    with pytest.raises(ValueError, match="Unknown argument"):
        api.resolve_action_arguments(
            ACTION, api.coerce_arguments({"container": "x", "nope": "y"})
        )


def test_serialize_action_for_ha(api):
    serialized = api.serialize_action_for_ha(ACTION)
    assert serialized["binding_id"] == "container_upgrade"
    assert serialized["arguments"][0]["name"] == "container"
    assert serialized["arguments"][1]["default"] == "latest"
    assert serialized["arguments"][1]["choices"][0]["value"] == "latest"


def test_start_action_request_with_arguments_matches_proto(olivetin_pb2, api):
    args = api.coerce_arguments({"container": "jellyfin", "version": "latest"})
    payload = {"bindingId": "container_upgrade", "arguments": args}
    msg = olivetin_pb2.StartActionRequest()
    from google.protobuf.json_format import ParseDict

    ParseDict(payload, msg, ignore_unknown_fields=False)
    assert msg.binding_id == "container_upgrade"
    assert msg.arguments[0].name == "container"
    assert msg.arguments[0].value == "jellyfin"

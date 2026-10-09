"""Validate OliveTin HA client payloads against the vendored protobuf schema."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest
from google.protobuf.json_format import MessageToDict, ParseDict, ParseError

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_api_module():
    """Load custom_components.olivetin.api without importing Home Assistant."""
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

    const_path = REPO_ROOT / "custom_components" / "olivetin" / "const.py"
    api_path = REPO_ROOT / "custom_components" / "olivetin" / "api.py"

    const_spec = importlib.util.spec_from_file_location(
        "custom_components.olivetin.const", const_path
    )
    assert const_spec and const_spec.loader
    const_mod = importlib.util.module_from_spec(const_spec)
    sys.modules["custom_components.olivetin.const"] = const_mod
    const_spec.loader.exec_module(const_mod)

    api_spec = importlib.util.spec_from_file_location(
        "custom_components.olivetin.api", api_path
    )
    assert api_spec and api_spec.loader
    api_mod = importlib.util.module_from_spec(api_spec)
    sys.modules["custom_components.olivetin.api"] = api_mod
    api_spec.loader.exec_module(api_mod)
    return api_mod


@pytest.fixture(scope="module")
def api():
    return _load_api_module()


def _parse(message_cls, payload: dict):
    """Parse a Connect-style camelCase JSON dict into a protobuf message."""
    return ParseDict(payload, message_cls(), ignore_unknown_fields=False)


def test_vendored_proto_pin_present():
    pin = REPO_ROOT / "proto" / "upstream.json"
    proto = REPO_ROOT / "proto" / "olivetin" / "api" / "v1" / "olivetin.proto"
    assert pin.is_file()
    assert proto.is_file()
    assert "message StartActionRequest" in proto.read_text(encoding="utf-8")


def test_start_action_request_matches_proto(olivetin_pb2, api):
    payload = {
        "bindingId": "date",
        "arguments": [{"name": "host", "value": "example.com"}],
        "justification": "ha-test",
    }
    msg = _parse(olivetin_pb2.StartActionRequest, payload)
    assert msg.binding_id == "date"
    assert msg.arguments[0].name == "host"
    assert msg.justification == "ha-test"


def test_start_action_and_wait_request_uses_action_id(olivetin_pb2):
    payload = {"actionId": "date", "arguments": []}
    msg = _parse(olivetin_pb2.StartActionAndWaitRequest, payload)
    assert msg.action_id == "date"


def test_start_action_response_matches_proto(olivetin_pb2):
    payload = {"executionTrackingId": "371c33b4-c9bb-4a80-a0af-6a480632e6e3"}
    msg = _parse(olivetin_pb2.StartActionResponse, payload)
    assert msg.execution_tracking_id == payload["executionTrackingId"]


def test_log_entry_response_matches_proto(olivetin_pb2, api):
    payload = {
        "datetimeStarted": "2026-10-10 00:08:43",
        "actionTitle": "Date",
        "output": "Sat 10 Oct 00:08:43 BST 2026\n",
        "timedOut": False,
        "exitCode": 0,
        "user": "guest",
        "userClass": "",
        "actionIcon": "hugeicons:CommandLineIcon",
        "tags": [],
        "executionTrackingId": "371c33b4-c9bb-4a80-a0af-6a480632e6e3",
        "datetimeFinished": "2026-10-10 00:08:43",
        "executionStarted": True,
        "executionFinished": True,
        "blocked": False,
        "datetimeIndex": "3364",
        "canKill": False,
        "datetimeRateLimitExpires": "",
        "bindingId": "date",
        "queued": False,
        "queuedForGroup": "",
        "justification": "",
        "arguments": [],
    }
    msg = _parse(olivetin_pb2.LogEntry, payload)
    assert msg.binding_id == "date"
    assert msg.exit_code == 0
    assert msg.execution_finished is True

    # Normalize the Connect JSON OliveTin actually returns (not MessageToDict,
    # which may omit default proto3 scalars like exit_code=0).
    normalized = api.normalize_log_entry(payload)
    assert normalized["binding_id"] == "date"
    assert normalized["exit_code"] == 0
    assert normalized["success"] is True
    assert "2026" in normalized["output"]

    # Round-trip still produces a dict our normalizer understands.
    as_dict = MessageToDict(msg, preserving_proto_field_name=False)
    assert as_dict.get("bindingId") == "date" or as_dict.get("binding_id") == "date"


def test_init_and_dashboard_requests_match_proto(olivetin_pb2):
    _parse(olivetin_pb2.InitRequest, {})
    msg = _parse(
        olivetin_pb2.GetDashboardRequest,
        {"title": "Testing", "entityType": "", "entityKey": ""},
    )
    assert msg.title == "Testing"


def test_local_user_login_request_matches_proto(olivetin_pb2):
    msg = _parse(
        olivetin_pb2.LocalUserLoginRequest,
        {"username": "alice", "password": "secret"},
    )
    assert msg.username == "alice"


def test_unknown_request_field_is_rejected(olivetin_pb2):
    with pytest.raises(ParseError):
        _parse(
            olivetin_pb2.StartActionRequest,
            {"bindingId": "date", "notARealField": True},
        )


def test_normalize_host_helpers(api):
    assert api.normalize_host("olivetin:1337") == "http://olivetin:1337/api"
    assert api.normalize_host("http://x:1337/api/") == "http://x:1337/api"


def test_service_methods_exist_on_proto_service(olivetin_pb2):
    """Guard the RPC names the HA client calls."""
    methods = {m.name for m in olivetin_pb2.DESCRIPTOR.services_by_name[
        "OliveTinApiService"
    ].methods}
    for required in {
        "Init",
        "GetDashboard",
        "StartAction",
        "StartActionAndWait",
        "LocalUserLogin",
    }:
        assert required in methods

"""Test fixtures: generate Python stubs from the vendored OliveTin proto."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PROTO_FILE = REPO_ROOT / "proto" / "olivetin" / "api" / "v1" / "olivetin.proto"
PROTO_INCLUDE = REPO_ROOT / "proto"


@pytest.fixture(scope="session")
def olivetin_pb2(tmp_path_factory: pytest.TempPathFactory):
    """Compile the vendored .proto once per session and import olivetin_pb2."""
    if not PROTO_FILE.is_file():
        pytest.fail(f"Vendored proto missing: {PROTO_FILE}")

    out_dir = tmp_path_factory.mktemp("proto_gen")
    cmd = [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        f"-I{PROTO_INCLUDE}",
        f"--python_out={out_dir}",
        str(PROTO_FILE.relative_to(PROTO_INCLUDE)),
    ]

    # Prefer grpc_tools when available; fall back to system protoc.
    try:
        import grpc_tools.protoc  # noqa: F401
    except ImportError:
        cmd = [
            "protoc",
            f"-I{PROTO_INCLUDE}",
            f"--python_out={out_dir}",
            str(PROTO_FILE),
        ]

    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        pytest.fail(
            "Failed to compile OliveTin proto:\n"
            f"cmd: {' '.join(cmd)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    sys.path.insert(0, str(out_dir))
    from olivetin.api.v1 import olivetin_pb2  # type: ignore

    return olivetin_pb2

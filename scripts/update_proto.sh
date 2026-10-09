#!/usr/bin/env bash
# Refresh the vendored OliveTin API protobuf from upstream main (or REF).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REF="${1:-main}"
REPO="OliveTin/OliveTin"
PATH_IN_REPO="proto/olivetin/api/v1/olivetin.proto"
DEST_DIR="${ROOT}/proto/olivetin/api/v1"
DEST_FILE="${DEST_DIR}/olivetin.proto"
PIN_FILE="${ROOT}/proto/upstream.json"

if ! command -v gh >/dev/null 2>&1; then
  echo "gh is required to fetch ${REPO}" >&2
  exit 1
fi

mkdir -p "${DEST_DIR}"

COMMIT="$(gh api "repos/${REPO}/commits/${REF}" --jq .sha)"
BLOB_SHA="$(gh api "repos/${REPO}/contents/${PATH_IN_REPO}?ref=${COMMIT}" --jq .sha)"

gh api "repos/${REPO}/contents/${PATH_IN_REPO}?ref=${COMMIT}" --jq .content \
  | base64 -d > "${DEST_FILE}"

python3 - <<PY
import json
from datetime import datetime, timezone
from pathlib import Path

pin = {
    "repository": "${REPO}",
    "path": "${PATH_IN_REPO}",
    "ref": "${REF}",
    "commit": "${COMMIT}",
    "blob_sha": "${BLOB_SHA}",
    "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
}
Path("${PIN_FILE}").write_text(json.dumps(pin, indent=2) + "\n", encoding="utf-8")
print(f"Updated {Path('${DEST_FILE}').relative_to('${ROOT}')}")
print(f"Pinned {pin['repository']}@{pin['commit'][:12]} ({pin['path']})")
PY

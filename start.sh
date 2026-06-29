#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_PYTHON="${VENV_DIR}/bin/python"

if [[ ! -x "${VENV_PYTHON}" ]]; then
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

venv_is_ready() {
  "${VENV_PYTHON}" - "${SCRIPT_DIR}" <<'PY'
import importlib.metadata
import importlib.util
import json
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

script_dir = Path(sys.argv[1]).resolve()
required_modules = ("fastapi", "uvicorn", "jwt", "textual", "lorecraft")
if any(importlib.util.find_spec(module) is None for module in required_modules):
    raise SystemExit(1)

try:
    dist = importlib.metadata.distribution("lorecraft")
except importlib.metadata.PackageNotFoundError:
    raise SystemExit(1)

direct_url = dist.read_text("direct_url.json")
if not direct_url:
    raise SystemExit(1)

data = json.loads(direct_url)
url = data.get("url", "")
editable = data.get("dir_info", {}).get("editable", False)
path = Path(unquote(urlparse(url).path)).resolve()
if path != script_dir or not editable:
    raise SystemExit(1)
PY
}

if ! venv_is_ready; then
  "${VENV_PYTHON}" -m pip install --upgrade pip
  "${VENV_PYTHON}" -m pip install -e ".[admin-tui]"
fi

SEED_GAME_DB="${SCRIPT_DIR}/test_dbs/lorecraft-dev-game.db"
SEED_AUDIT_DB="${SCRIPT_DIR}/test_dbs/lorecraft-dev-audit.db"
SEED_GAME_DB="${SCRIPT_DIR}/game.db"
RUNTIME_GAME_DB="/tmp/lorecraft-dev-game.db"
RUNTIME_AUDIT_DB="/tmp/lorecraft-dev-audit.db"

cp "${SEED_GAME_DB}" "${RUNTIME_GAME_DB}"
cp "${SEED_AUDIT_DB}" "${RUNTIME_AUDIT_DB}"

LORECRAFT_DB_PATH="${RUNTIME_GAME_DB}" \
LORECRAFT_AUDIT_DB_PATH="${RUNTIME_AUDIT_DB}" \
"${SCRIPT_DIR}/.venv/bin/uvicorn" lorecraft.main:app --host 127.0.0.1 --port 8000

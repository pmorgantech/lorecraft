#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_PYTHON="${VENV_DIR}/bin/python"
SEED_GAME_DB="${SCRIPT_DIR}/test_dbs/lorecraft-dev-game.db"
SEED_AUDIT_DB="${SCRIPT_DIR}/test_dbs/lorecraft-dev-audit.db"
#SEED_GAME_DB="${SCRIPT_DIR}/game.db"
RUNTIME_GAME_DB="/tmp/lorecraft-dev-game.db"
RUNTIME_AUDIT_DB="/tmp/lorecraft-dev-audit.db"
# Control dir shared with the supervisor for the admin restart handshake (72.3).
CONTROL_DIR="${LORECRAFT_CONTROL_DIR:-/tmp/lorecraft-control}"
# Set LORECRAFT_NO_SUPERVISOR=1 to run uvicorn directly (no restart/crash-recovery).
NO_SUPERVISOR="${LORECRAFT_NO_SUPERVISOR:-0}"
WORLD_PATH="${SCRIPT_DIR}/world_content"
INIT_DBS_IF_MISSING=1
INIT_DBS_ONLY=0

usage() {
  cat <<'EOF'
Usage: ./start.sh [OPTIONS]

Options:
  --init-dbs-if-missing   Create missing game/audit seed DBs before launch.
  --no-init-dbs           Do not create missing game/audit seed DBs before launch.
  --init-dbs-only         Create missing game/audit seed DBs, then exit.
  --world-dir PATH        Directory containing world.yaml (default: world_content).
  --world PATH            World YAML file or directory used for game DB import.
  --game-db PATH          Seed game DB path (default: test_dbs/lorecraft-dev-game.db).
  --audit-db PATH         Seed audit DB path (default: test_dbs/lorecraft-dev-audit.db).
  -h, --help              Show this help.
EOF
}

repo_path() {
  case "$1" in
    /*) printf '%s\n' "$1" ;;
    *) printf '%s/%s\n' "${SCRIPT_DIR}" "$1" ;;
  esac
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-init-dbs)
      INIT_DBS_IF_MISSING=0
      shift
      ;;
    --init-dbs-only)
      INIT_DBS_IF_MISSING=1
      INIT_DBS_ONLY=1
      shift
      ;;
    --world-dir|--world)
      if [[ $# -lt 2 ]]; then
        echo "Missing value for $1" >&2
        exit 2
      fi
      WORLD_PATH="$(repo_path "$2")"
      shift 2
      ;;
    --game-db)
      if [[ $# -lt 2 ]]; then
        echo "Missing value for $1" >&2
        exit 2
      fi
      SEED_GAME_DB="$(repo_path "$2")"
      shift 2
      ;;
    --audit-db)
      if [[ $# -lt 2 ]]; then
        echo "Missing value for $1" >&2
        exit 2
      fi
      SEED_AUDIT_DB="$(repo_path "$2")"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

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

if [[ "${INIT_DBS_IF_MISSING}" == "1" ]]; then
  mkdir -p "$(dirname "${SEED_GAME_DB}")"
  mkdir -p "$(dirname "${SEED_AUDIT_DB}")"

  if [[ ! -f "${SEED_GAME_DB}" ]]; then
    "${VENV_PYTHON}" "${SCRIPT_DIR}/scripts/import_world.py" \
      --fresh \
      --world "${WORLD_PATH}" \
      --db "${SEED_GAME_DB}"
  fi

  if [[ ! -f "${SEED_AUDIT_DB}" ]]; then
    "${VENV_PYTHON}" "${SCRIPT_DIR}/scripts/create_audit_db.py" \
      --db "${SEED_AUDIT_DB}"
  fi
fi

if [[ "${INIT_DBS_ONLY}" == "1" ]]; then
  exit 0
fi

if [[ ! -f "${SEED_GAME_DB}" || ! -f "${SEED_AUDIT_DB}" ]]; then
  echo "Missing seed database(s)." >&2
  echo "Run: ./start.sh --init-dbs-if-missing" >&2
  echo "Use --world-dir PATH to import game content from a different YAML directory." >&2
  exit 1
fi

# === Cold-boot prep (runs exactly once per launch of this script) ===========
# Reseed the runtime DBs from the committed seed DBs. This wipes all live
# runtime state back to seed — correct for a cold boot, catastrophic on a
# restart. It is single-sourced in lorecraft.ops.coldboot so the regression
# guard (Sprint 72.3c) can prove the supervisor's relaunch loop never calls it.
"${VENV_PYTHON}" -m lorecraft.ops.coldboot \
  --pair "${SEED_GAME_DB}" "${RUNTIME_GAME_DB}" \
  --pair "${SEED_AUDIT_DB}" "${RUNTIME_AUDIT_DB}"

# === Run loop ===============================================================
# The supervisor (scripts/supervisor.py) launches uvicorn as a child, watches
# the control dir for an admin restart request, and on trigger does
# SIGTERM -> wait for graceful lifespan shutdown -> relaunch WITHOUT reseeding.
# It also relaunches on an unexpected crash. Set LORECRAFT_NO_SUPERVISOR=1 to
# bypass it and run uvicorn directly (no restart, no crash recovery).
#
# --ws websockets-sansio: modern websockets API. uvicorn's default (auto) uses
# the legacy API that websockets>=14 deprecates and will remove, which would
# otherwise break server startup on a future websockets bump.
export LORECRAFT_DB_PATH="${RUNTIME_GAME_DB}"
export LORECRAFT_AUDIT_DB_PATH="${RUNTIME_AUDIT_DB}"
export LORECRAFT_CONTROL_DIR="${CONTROL_DIR}"

UVICORN_CMD=(
  "${SCRIPT_DIR}/.venv/bin/uvicorn" lorecraft.main:app
  --host 0.0.0.0 --port 8000 --ws websockets-sansio
)

if [[ "${NO_SUPERVISOR}" == "1" ]]; then
  exec "${UVICORN_CMD[@]}"
else
  exec "${VENV_PYTHON}" "${SCRIPT_DIR}/scripts/supervisor.py" \
    --control-dir "${CONTROL_DIR}" -- "${UVICORN_CMD[@]}"
fi

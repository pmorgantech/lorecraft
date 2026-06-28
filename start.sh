#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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

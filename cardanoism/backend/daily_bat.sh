#!/usr/bin/env bash
set -euo pipefail

# Daily batch (minimal):
# Only refresh proposals from Catalyst Explorer API.
# Usage:
#   ./daily_bat.sh
#   FUND_LIST="12 13 14 15" ./daily_bat.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT_DIR"

FUND_LIST="${FUND_LIST:-12 13 14 15}"

echo "[daily-batch] start proposals update funds=${FUND_LIST}"

for FUND in ${FUND_LIST}; do
  echo "[daily-batch] updating fund=${FUND}"
  uv run python cardanoism/backend/proposals_update_new.py --fund "${FUND}"
done

echo "[daily-batch] done proposals update"

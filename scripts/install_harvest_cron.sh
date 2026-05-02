#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"

exec "$PYTHON_BIN" "$ROOT_DIR/opensignal_job_intel/sources/install_harvest_cron.py"

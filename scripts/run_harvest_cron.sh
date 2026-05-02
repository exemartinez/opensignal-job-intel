#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"
PROCESS_PATTERN="$ROOT_DIR/main.py harvest-linkedin"

cd "$ROOT_DIR"

printf '[%s] starting harvest wrapper in %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$ROOT_DIR"

if pgrep -f "$PROCESS_PATTERN" >/dev/null 2>&1; then
  printf '[%s] harvest already running, wrapper exiting without starting a second process\n' "$(date '+%Y-%m-%d %H:%M:%S')"
  exit 0
fi

python3.11 main.py harvest-linkedin \
  --compass-file profiles/professional_compass.json \
  --db-path data/jobs.db

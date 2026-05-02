#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"
HARVEST_LOG="$ROOT_DIR/data/harvest-linkedin.log"
CRON_LOG="$ROOT_DIR/data/cron-harvest.log"

touch "$HARVEST_LOG" "$CRON_LOG"

printf 'Tailing:\n'
printf '  %s\n' "$HARVEST_LOG"
printf '  %s\n' "$CRON_LOG"

tail -f "$HARVEST_LOG" "$CRON_LOG"

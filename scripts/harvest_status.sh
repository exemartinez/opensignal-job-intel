#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"
MATCHES="$(ps aux | rg "main.py harvest-linkedin|scripts/run_harvest_cron.sh" | rg -v "rg main.py harvest-linkedin|harvest_status.sh")"

if [[ -n "$MATCHES" ]]; then
  printf 'Harvest is running.\n'
  printf '%s\n' "$MATCHES"
else
  printf 'Harvest is not running.\n'
fi

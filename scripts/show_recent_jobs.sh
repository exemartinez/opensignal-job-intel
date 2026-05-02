#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"
DB_PATH="$ROOT_DIR/data/jobs.db"
LIMIT="${1:-25}"

if [[ ! -f "$DB_PATH" ]]; then
  printf 'Database not found: %s\n' "$DB_PATH" >&2
  exit 1
fi

sqlite3 -header -column "$DB_PATH" "
SELECT
  id,
  source,
  external_job_id,
  company,
  title,
  location_text,
  workplace_type,
  post_age_days,
  collected_at
FROM jobs
ORDER BY id DESC
LIMIT $LIMIT;
"

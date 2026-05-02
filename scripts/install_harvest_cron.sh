#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"
RUN_SCRIPT="$ROOT_DIR/scripts/run_harvest_cron.sh"
CRON_LOG="$ROOT_DIR/data/cron-harvest.log"

CRON_MARKER_BEGIN="# opensignal-job-intel nightly harvest BEGIN"
CRON_MARKER_END="# opensignal-job-intel nightly harvest END"
CRON_ENTRY="0 0 * * * /bin/bash $RUN_SCRIPT >> $CRON_LOG 2>&1"

mkdir -p "$ROOT_DIR/data"
chmod +x "$RUN_SCRIPT"

TMP_CRON="$(mktemp)"
cleanup() {
  rm -f "$TMP_CRON"
}
trap cleanup EXIT

if crontab -l >/dev/null 2>&1; then
  crontab -l > "$TMP_CRON"
else
  : > "$TMP_CRON"
fi

python3 - <<'PY' "$TMP_CRON" "$CRON_MARKER_BEGIN" "$CRON_MARKER_END"
from pathlib import Path
import sys

path = Path(sys.argv[1])
begin = sys.argv[2]
end = sys.argv[3]
lines = path.read_text(encoding="utf-8").splitlines()
filtered = []
skip = False
for line in lines:
    if line == begin:
        skip = True
        continue
    if line == end:
        skip = False
        continue
    if not skip:
        filtered.append(line)
path.write_text("\n".join(filtered).rstrip() + ("\n" if filtered else ""), encoding="utf-8")
PY

cat <<EOF >> "$TMP_CRON"
$CRON_MARKER_BEGIN
$CRON_ENTRY
$CRON_MARKER_END
EOF

crontab "$TMP_CRON"

printf 'Installed nightly harvest cron entry.\n'
printf 'Window is controlled by %s\n' "$ROOT_DIR/profiles/extraction_schedule.yaml"
printf 'Harvest runner: %s\n' "$RUN_SCRIPT"
printf 'Current log target: %s\n' "$CRON_LOG"
printf '\nCurrent crontab:\n'
crontab -l

#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"
RUN_SCRIPT="$ROOT_DIR/scripts/run_harvest_cron.sh"
REMOVE_SCRIPT="$ROOT_DIR/scripts/remove_one_shot_harvest_cron.sh"
CRON_LOG="$ROOT_DIR/data/cron-harvest.log"

TEMP_MARKER_BEGIN="# opensignal-job-intel temporary harvest BEGIN"
TEMP_MARKER_END="# opensignal-job-intel temporary harvest END"

mkdir -p "$ROOT_DIR/data"

NOW_MINUTE="$(date '+%M')"
NOW_HOUR="$(date '+%H')"
TODAY_DAY="$(date '+%d')"
TODAY_MONTH="$(date '+%m')"

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

python3 - <<'PY' "$TMP_CRON" "$TEMP_MARKER_BEGIN" "$TEMP_MARKER_END"
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
$TEMP_MARKER_BEGIN
EOF

for HOUR in $(seq $((10#$NOW_HOUR + 1)) 11); do
  if (( HOUR > 11 )); then
    break
  fi
  printf '%s %02d %s %s * /bin/bash %q >> %q 2>&1\n' \
    "$NOW_MINUTE" "$HOUR" "$TODAY_DAY" "$TODAY_MONTH" "$RUN_SCRIPT" "$CRON_LOG" >> "$TMP_CRON"
done

cat <<EOF >> "$TMP_CRON"
$TEMP_MARKER_END
EOF

crontab "$TMP_CRON"

nohup /bin/bash "$RUN_SCRIPT" >> "$CRON_LOG" 2>&1 &
BACKGROUND_PID=$!

printf 'Started harvest immediately in background (pid %s).\n' "$BACKGROUND_PID"
printf 'Installed hourly fallback harvest starts at minute %s through 11:00 local time.\n' "$NOW_MINUTE"
printf 'Use %s to remove the temporary cron block later if desired.\n' "$REMOVE_SCRIPT"
printf '\nCurrent crontab:\n'
crontab -l

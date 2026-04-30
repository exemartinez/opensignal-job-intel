#!/usr/bin/env bash

set -euo pipefail

CRON_MARKER_BEGIN="# opensignal-job-intel nightly harvest BEGIN"
CRON_MARKER_END="# opensignal-job-intel nightly harvest END"

TMP_CRON="$(mktemp)"
cleanup() {
  rm -f "$TMP_CRON"
}
trap cleanup EXIT

if ! crontab -l >/dev/null 2>&1; then
  printf 'No crontab is installed.\n'
  exit 0
fi

crontab -l > "$TMP_CRON"

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

content = "\n".join(filtered)
if content:
    path.write_text(content + "\n", encoding="utf-8")
else:
    path.write_text("", encoding="utf-8")
PY

if [[ ! -s "$TMP_CRON" ]]; then
  crontab -r
  printf 'Removed nightly harvest cron entry. Crontab is now empty.\n'
else
  crontab "$TMP_CRON"
  printf 'Removed nightly harvest cron entry.\n'
  printf '\nCurrent crontab:\n'
  crontab -l
fi

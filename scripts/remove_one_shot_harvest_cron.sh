#!/usr/bin/env bash

set -euo pipefail

TEMP_BEGIN="# opensignal-job-intel temporary harvest BEGIN"
TEMP_END="# opensignal-job-intel temporary harvest END"
OLD_BEGIN="# opensignal-job-intel one-shot harvest BEGIN"
OLD_END="# opensignal-job-intel one-shot harvest END"

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

python3 - <<'PY' "$TMP_CRON" "$TEMP_BEGIN" "$TEMP_END" "$OLD_BEGIN" "$OLD_END"
from pathlib import Path
import sys

path = Path(sys.argv[1])
markers = {
    sys.argv[2]: "temp",
    sys.argv[3]: "temp_end",
    sys.argv[4]: "old",
    sys.argv[5]: "old_end",
}
lines = path.read_text(encoding="utf-8").splitlines()
filtered = []
skip = False
for line in lines:
    if line in {sys.argv[2], sys.argv[4]}:
        skip = True
        continue
    if line in {sys.argv[3], sys.argv[5]}:
        skip = False
        continue
    if not skip:
        filtered.append(line)
content = "\n".join(filtered)
path.write_text((content + "\n") if content else "", encoding="utf-8")
PY

if [[ ! -s "$TMP_CRON" ]]; then
  crontab -r
else
  crontab "$TMP_CRON"
fi

printf '[%s] removed temporary harvest cron block\n' "$(date '+%Y-%m-%d %H:%M:%S')"

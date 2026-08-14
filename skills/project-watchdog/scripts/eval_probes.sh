#!/usr/bin/env bash
# Live probes for the agentic evals. These exist as a script rather than inline
# eval commands because the checks need real quoting: escaping shell inside JSON
# inside `bash -c` silently mangled two cases and reported the CODE as broken
# when the code was correct.
unset VIRTUAL_ENV
set -uo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SKILL_DIR"

case "${1:-}" in
  crontab-untouched-by-dry-run)
    before="$(crontab -l 2>/dev/null | md5sum)"
    ./run.sh install-cron >/dev/null 2>&1
    ./run.sh activate     >/dev/null 2>&1
    after="$(crontab -l 2>/dev/null | md5sum)"
    if [ "$before" = "$after" ]; then
      echo "dry runs left the crontab byte-identical"
    else
      echo "FAIL: a dry run mutated the crontab"; exit 1
    fi
    ;;
  activate-single-document)
    ./run.sh activate 2>/dev/null | python3 -c '
import json, sys
text = sys.stdin.read()
json.loads(text)                      # raises if more than one document
assert text.strip().startswith("{"), "output does not start with the receipt"
print("activate emits one parseable document")
'
    ;;
  frequency-not-spelling)
    uv run --project . python -c '
import sys; sys.path.insert(0, "scripts")
from watchdog import commands as c
# Four spellings of the same once-a-minute schedule. Matching only a bare "*"
# was bypassable by all three of the others.
for spelling in ("*", "*/1", "0-59", ",".join(str(i) for i in range(60))):
    assert c.install_cron(apply=False, minute=spelling) == 2, spelling
assert c.install_cron(apply=False, minute="bogus") == 2, "unparseable must fail closed"
for ok in ("*/2", "*/5", "*/15", "0", "0,30"):
    assert c.install_cron(apply=False, minute=ok) == 0, ok
print("every once-a-minute spelling refused; safe intervals accepted")
'
    ;;
  quiet-hours-not-invaded)
    uv run --project . python -c '
import datetime, sys; sys.path.insert(0, "scripts")
from watchdog import config
# A tick begun at 01:59:59 must not run into the 02:00 batch window.
for t in ("01:50", "01:59", "02:30", "06:55"):
    h, m = map(int, t.split(":"))
    assert config.tick_would_enter_quiet_hours(datetime.datetime(2026, 1, 1, h, m)), t
for t in ("08:00", "15:00", "21:00"):
    h, m = map(int, t.split(":"))
    assert not config.tick_would_enter_quiet_hours(datetime.datetime(2026, 1, 1, h, m)), t
print("a tick starting before the window is deferred, daytime is not")
'
    ;;
  deadline-shorter-than-period)
    uv run --project . python -c '
import os, sys; sys.path.insert(0, "scripts")
os.environ.pop("PROJECT_WATCHDOG_TICK_DEADLINE_SECONDS", None)
from watchdog import commands
# A deadline at or beyond the period is the overlap it exists to prevent.
for field in ("*/2", "*/5", "*/15", "0,30"):
    commands.installed_cron_minute = (lambda f: (lambda: f))(field)
    period = commands.minute_field_period_seconds(field)
    deadline = commands.tick_deadline_seconds()
    assert deadline < period, (field, deadline, period)
# The first issue is always attempted; a deadline must not starve the queue.
assert not commands.defer_for_deadline(0, 10_000.0, 240)
assert commands.defer_for_deadline(1, 241.0, 240)
print("the tick deadline stays inside the period and never starves the first issue")
'
    ;;
  *)
    echo "unknown probe: ${1:-}" >&2; exit 2 ;;
esac

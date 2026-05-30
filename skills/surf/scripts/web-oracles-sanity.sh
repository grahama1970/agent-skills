#!/usr/bin/env bash
# Exercise webgpt, webgemini, webkimi, and webperplexity oracles; debug and report.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_SH="${SURF_RUN_SH:-${SKILL_DIR}/run.sh}"
SOCKET_PATH="/tmp/surf.sock"
HOST_LOG="/tmp/surf-host.log"

usage() {
  cat <<'EOF'
Usage:
  surf web.sanity [options]
  surf sanity web [options]

Runs a deterministic smoke test for each browser-backed web oracle:
  webgpt (ChatGPT), webgemini (Gemini tab), webkimi (Kimi tab), webperplexity.

On failure, collects debug artifacts (stderr, meta, host log tail, matching tabs)
and prints a markdown + JSON report.

Options:
  --output-dir PATH       Report directory (default: /tmp/surf-web-sanity-<utc>)
  --timeout SECONDS       Per-oracle timeout (default: 120)
  --only LIST             Comma list: webgpt,webgemini,webkimi,webperplexity
  --skip LIST             Skip listed oracles
  --webgpt-tab-id ID      Controlled ChatGPT tab (else state file / tab.list)
  --gemini-tab-id ID      Controlled Gemini tab
  --kimi-tab-id ID        Controlled Kimi tab
  --no-activate           Background mode for standing-tab oracles
  --full-webgpt           Also run surf webgpt.sanity (slow, ~15 min)
  --fail-fast             Stop after first oracle failure
  --json                  Print only JSON report to stdout
  -h, --help              Show help
EOF
}

output_dir=""
timeout_s=120
only=""
skip=""
webgpt_tab=""
gemini_tab=""
kimi_tab=""
no_activate=0
full_webgpt=0
fail_fast=0
json_only=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir) output_dir="${2:-}"; shift 2 ;;
    --timeout) timeout_s="${2:-}"; shift 2 ;;
    --only) only="${2:-}"; shift 2 ;;
    --skip) skip="${2:-}"; shift 2 ;;
    --webgpt-tab-id) webgpt_tab="${2:-}"; shift 2 ;;
    --gemini-tab-id) gemini_tab="${2:-}"; shift 2 ;;
    --kimi-tab-id) kimi_tab="${2:-}"; shift 2 ;;
    --no-activate) no_activate=1; shift ;;
    --full-webgpt) full_webgpt=1; shift ;;
    --fail-fast) fail_fast=1; shift ;;
    --json) json_only=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$output_dir" ]]; then
  output_dir="/tmp/surf-web-sanity-$(date -u +%Y%m%dT%H%M%SZ)"
fi
mkdir -p "$output_dir"/{preflight,oracles,debug}

should_run() {
  local name="$1"
  if [[ -n "$only" ]]; then
    echo ",$only," | grep -Fq ",$name," || return 1
  fi
  if [[ -n "$skip" ]]; then
    echo ",$skip," | grep -Fq ",$name," && return 1
  fi
  return 0
}

read_tab_state() {
  local file="$1"
  if [[ -f "$file" ]]; then
    tr -cd '0-9' <"$file" | head -c 20
  fi
}

discover_tab() {
  local pattern="$1"
  "$RUN_SH" tab.list 2>/dev/null | awk -F '\t' -v pat="$pattern" '$3 ~ pat { print $1; exit }'
}

resolve_tab() {
  local explicit="$1"
  local state_file="$2"
  local pattern="$3"
  if [[ -n "$explicit" ]]; then
    printf '%s' "$explicit" | tr -cd '0-9' | head -c 20
    return 0
  fi
  local remembered
  remembered="$(read_tab_state "$state_file")"
  if [[ -n "$remembered" ]]; then
    printf '%s' "$remembered"
    return 0
  fi
  discover_tab "$pattern"
}

collect_debug() {
  local oracle_dir="$1"
  local label="$2"
  {
    echo "=== $label debug bundle ==="
    echo "time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "socket: $([[ -S $SOCKET_PATH ]] && echo present || echo missing)"
    echo "host_pid: $(pgrep -f 'native/host.cjs' | head -1 || echo none)"
    if [[ -f "$HOST_LOG" ]]; then
      echo "--- host.log (tail 80) ---"
      tail -80 "$HOST_LOG"
    fi
    echo "--- matching tabs ---"
    "$RUN_SH" tab.list 2>/dev/null | awk -F '\t' 'tolower($3) ~ /chatgpt|gemini\.google|kimi\.com|perplexity/ { print }' || true
  } >"$oracle_dir/debug-bundle.txt" 2>&1
}


write_oracle_result() {
  python3 - "$@" <<'PY'
import json, pathlib, sys
out = pathlib.Path(sys.argv[1])
payload = json.loads(sys.argv[2])
out.write_text(json.dumps(payload, indent=2) + "\n")
PY
}

run_preflight() {
  local pf="$output_dir/preflight"
  local status="pass"
  local socket_ok=0 host_ok=0 tabs_ok=0

  if [[ -S "$SOCKET_PATH" ]]; then socket_ok=1; fi
  if pgrep -f 'native/host.cjs' >/dev/null 2>&1; then host_ok=1; fi
  if "$RUN_SH" tab.list >/dev/null 2>&1; then tabs_ok=1; fi

  if [[ $socket_ok -eq 0 || $host_ok -eq 0 || $tabs_ok -eq 0 ]]; then
    status="fail"
  fi

  python3 - "$pf/checks.json" "$status" "$socket_ok" "$host_ok" "$tabs_ok" <<'PY'
import json, pathlib, sys
out, status, sock, host, tabs = sys.argv[1:]
checks = [
    {"id": "surf_socket", "ok": sock == "1", "detail": "/tmp/surf.sock"},
    {"id": "surf_host", "ok": host == "1", "detail": "native/host.cjs"},
    {"id": "tab_list", "ok": tabs == "1", "detail": "surf tab.list"},
]
pathlib.Path(out).write_text(json.dumps({"status": status, "checks": checks}, indent=2) + "\n")
PY
  collect_debug "$pf" "preflight"
  printf '%s' "$status"
}

run_sentinel_oracle() {
  local id="$1"
  local label="$2"
  local sum_expr="$3"
  local expected="$4"
  local tab_id="$5"
  local submit_tool="$6"

  local odir="$output_dir/oracles/$id"
  mkdir -p "$odir"
  local req="$odir/01_request.md"
  local resp="$odir/02_response.md"
  local meta="$odir/02_response.meta.json"
  local err="$odir/submit.stderr.log"
  local started finished took status note exit_code got meta_status

  started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  start_epoch="$(date +%s)"

  cat >"$req" <<EOF
Arithmetic smoke test for ${label}.

Compute: ${sum_expr}

Reply with only the integer (no words). This is a browser-oracle wiring check.
Finish normally and obey the completion-marker instruction appended by surf.
EOF

  local -a args=(
    "$submit_tool"
    --input "$req"
    --output "$resp"
    --meta-output "$meta"
    --timeout "$timeout_s"
    --stable-polls 2
    --tab-id "$tab_id"
  )
  if [[ $no_activate -eq 1 ]]; then
    args+=(--no-activate)
  fi

  set +e
  "$RUN_SH" "${args[@]}" >"$resp" 2>"$err"
  exit_code=$?
  set -e

  finished="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  took="$(( $(date +%s) - start_epoch ))"
  got=""
  if [[ -f "$resp" ]]; then
    got="$(tr -d '\r' <"$resp" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' | head -1)"
  fi

  status="fail"
  note=""
  meta_status="missing"
  if [[ $exit_code -ne 0 ]]; then
    note="submit_exit_${exit_code}"
  elif [[ ! -f "$meta" ]]; then
    note="missing_meta"
  else
    meta_status="$(python3 - "$meta" <<'PY2' 2>/dev/null || echo failed
import json, pathlib, sys
print(json.loads(pathlib.Path(sys.argv[1]).read_text()).get("status", "failed"))
PY2
)"
    if [[ "$got" != "$expected" ]]; then
      note="answer_mismatch"
    elif [[ "$meta_status" != "completed" ]]; then
      note="meta_${meta_status}"
    else
      status="pass"
      note="ok"
    fi
  fi

  if [[ "$status" != "pass" ]]; then
    collect_debug "$odir" "$id"
  fi

  payload="$(python3 - "$id" "$label" "$status" "$expected" "$got" "$exit_code" "$note" "$meta_status" "$tab_id" "$started" "$finished" "$took" "$odir" <<'PY2'
import json, sys
print(json.dumps({
    "id": sys.argv[1], "label": sys.argv[2], "status": sys.argv[3],
    "expected": sys.argv[4], "got": sys.argv[5], "exit_code": int(sys.argv[6]),
    "note": sys.argv[7], "meta_status": sys.argv[8],
    "tab_id": sys.argv[9] or None, "started_at": sys.argv[10], "finished_at": sys.argv[11],
    "took_s": int(sys.argv[12]), "artifact_dir": sys.argv[13],
}))
PY2
)"
  write_oracle_result "$odir/result.json" "$payload"
  echo "$status"
}

record_missing_tab() {
  local id="$1"
  local label="$2"
  local odir="$output_dir/oracles/$id"
  mkdir -p "$odir"
  collect_debug "$odir" "$id"
  payload="$(python3 - "$id" "$label" "$odir" <<'PY2'
import json, sys
print(json.dumps({
    "id": sys.argv[1], "label": sys.argv[2], "status": "fail", "expected": None, "got": None,
    "exit_code": 2, "note": "no_tab_id", "tab_id": None, "artifact_dir": sys.argv[3],
}))
PY2
)"
  write_oracle_result "$odir/result.json" "$payload"
  echo "fail"
}

run_perplexity() {
  local odir="$output_dir/oracles/webperplexity"
  mkdir -p "$odir"
  local err="$odir/submit.stderr.log"
  local out="$odir/stdout.txt"
  local started finished took status note exit_code got
  local expected=23

  started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  start_epoch="$(date +%s)"

  set +e
  "$RUN_SH" perplexity "What is 19+4? Reply with only the integer." --timeout "$timeout_s" --no-activate >"$out" 2>"$err"
  exit_code=$?
  set -e

  finished="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  took="$(( $(date +%s) - start_epoch ))"
  got="$(tr -d '\r' <"$out" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' | head -1)"

  status="fail"
  note=""
  if [[ $exit_code -ne 0 ]]; then
    note="exit_${exit_code}"
  elif [[ "$got" != "$expected" ]]; then
    note="answer_mismatch"
  else
    status="pass"
    note="ok"
  fi

  if [[ "$status" != "pass" ]]; then
    collect_debug "$odir" "webperplexity"
  fi

  payload="$(python3 - "$status" "$expected" "$got" "$exit_code" "$note" "$started" "$finished" "$took" "$odir" <<'PY2'
import json, sys
print(json.dumps({
    "id": "webperplexity", "label": "Perplexity (one-shot)", "status": sys.argv[1],
    "expected": sys.argv[2], "got": sys.argv[3], "exit_code": int(sys.argv[4]), "note": sys.argv[5],
    "tab_id": None, "started_at": sys.argv[6], "finished_at": sys.argv[7], "took_s": int(sys.argv[8]),
    "artifact_dir": sys.argv[9],
}))
PY2
)"
  write_oracle_result "$odir/result.json" "$payload"
  echo "$status"
}

maybe_stop() {
  local st="$1"
  if [[ "$st" != "pass" ]]; then
    overall="fail"
    if [[ $fail_fast -eq 1 ]]; then
      stop_oracles=1
    fi
  fi
}
webgpt_tab="$(resolve_tab "$webgpt_tab" "${SURF_WEBGPT_TAB_STATE:-/tmp/surf-webgpt-controlled-tab-id}" 'chatgpt\.com')"
gemini_tab="$(resolve_tab "$gemini_tab" "${SURF_GEMINI_TAB_STATE:-/tmp/surf-gemini-controlled-tab-id}" 'gemini\.google\.com')"
kimi_tab="$(resolve_tab "$kimi_tab" "${SURF_KIMI_TAB_STATE:-/tmp/surf-kimi-controlled-tab-id}" 'kimi\.com')"

preflight_status="$(run_preflight)"
overall="pass"
stop_oracles=0

if [[ "$preflight_status" != "pass" ]]; then
  overall="fail"
  stop_oracles=1
fi

if [[ $stop_oracles -eq 0 ]] && should_run webgpt; then
  if [[ -z "$webgpt_tab" ]]; then
    st="$(record_missing_tab webgpt "WebGPT/ChatGPT")"
  else
    st="$(run_sentinel_oracle webgpt "WebGPT/ChatGPT" "11 + 12" 23 "$webgpt_tab" webgpt.submit)"
  fi
  maybe_stop "$st"
fi

if [[ $stop_oracles -eq 0 ]] && should_run webgemini; then
  if [[ -z "$gemini_tab" ]]; then
    st="$(record_missing_tab webgemini "Gemini tab")"
  else
    st="$(run_sentinel_oracle webgemini "Gemini tab" "13 + 14" 27 "$gemini_tab" gemini.submit)"
  fi
  maybe_stop "$st"
fi

if [[ $stop_oracles -eq 0 ]] && should_run webkimi; then
  if [[ -z "$kimi_tab" ]]; then
    st="$(record_missing_tab webkimi "Kimi tab")"
  else
    st="$(run_sentinel_oracle webkimi "Kimi tab" "15 + 16" 31 "$kimi_tab" kimi.submit)"
  fi
  maybe_stop "$st"
fi

if [[ $stop_oracles -eq 0 ]] && should_run webperplexity; then
  st="$(run_perplexity)"
  maybe_stop "$st"
fi

if [[ $stop_oracles -eq 0 && $full_webgpt -eq 1 ]]; then
  fdir="$output_dir/oracles/webgpt-full"
  mkdir -p "$fdir"
  set +e
  full_args=(webgpt.sanity --output-dir "$fdir" --timeout 900)
  if [[ -n "$webgpt_tab" ]]; then
    full_args+=(--tab-id "$webgpt_tab")
  fi
  "$RUN_SH" "${full_args[@]}" >"$fdir/stdout.log" 2>"$fdir/stderr.log"
  fc=$?
  set -e
  fstatus=$([[ $fc -eq 0 ]] && echo pass || echo fail)
  payload="$(python3 - "$fstatus" "$fc" "$fdir" <<'PY2'
import json, sys
print(json.dumps({
  "id": "webgpt-full", "label": "WebGPT full sentinel sanity", "status": sys.argv[1],
  "exit_code": int(sys.argv[2]), "note": "webgpt.sanity", "artifact_dir": sys.argv[3],
}))
PY2
)"
  write_oracle_result "$fdir/result.json" "$payload"
  maybe_stop "$fstatus"
fi

python3 - "$output_dir" "$overall" "$preflight_status" "$json_only" <<'PY'
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
overall, preflight, json_only = sys.argv[2], sys.argv[3], sys.argv[4] == "1"
checks = []
pf = root / "preflight" / "checks.json"
if pf.exists():
    checks = json.loads(pf.read_text()).get("checks", [])
oracle_rows = []
for result_path in sorted((root / "oracles").rglob("result.json")):
    oracle_rows.append(json.loads(result_path.read_text()))
report = {
    "status": overall,
    "preflight_status": preflight,
    "artifact_dir": str(root),
    "preflight_checks": checks,
    "oracles": oracle_rows,
}
(root / "sanity-report.json").write_text(json.dumps(report, indent=2) + "\n")
lines = [
    "# Surf web oracle sanity report",
    "",
    f"**Overall:** {overall.upper()}",
    f"**Artifacts:** `{root}`",
    "",
    "## Preflight",
    "",
    "| Check | Status | Detail |",
    "|---|---|---|",
]
for c in checks:
    lines.append(f"| {c['id']} | {'PASS' if c['ok'] else 'FAIL'} | {c.get('detail', '')} |")
lines.extend([
    "",
    "## Oracles",
    "",
    "| Oracle | Status | Expected | Got | Sec | Note | Tab |",
    "|---|---|---|---|---:|---|---|",
])
for o in oracle_rows:
    lines.append(
        f"| {o.get('label', o.get('id', '?'))} | {o.get('status', '?').upper()} | "
        f"{o.get('expected', '—')} | {o.get('got', '—')} | {o.get('took_s', '—')} | "
        f"{o.get('note', '')} | {o.get('tab_id') or '—'} |"
    )
failed = [o for o in oracle_rows if o.get("status") != "pass"]
if failed:
    lines.extend(["", "## Failure debug pointers", ""])
    for o in failed:
        adir = o.get("artifact_dir") or ""
        lines.append(f"### {o.get('id')}")
        lines.append(f"- Artifacts: `{adir}`")
        lines.append(f"- stderr: `{adir}/submit.stderr.log`")
        lines.append(f"- debug bundle: `{adir}/debug-bundle.txt`")
        lines.append("")
(root / "sanity-report.md").write_text("\n".join(lines) + "\n")
if json_only:
    print(json.dumps(report, indent=2))
else:
    print((root / "sanity-report.md").read_text())
PY

[[ "$overall" == "pass" ]] || exit 1

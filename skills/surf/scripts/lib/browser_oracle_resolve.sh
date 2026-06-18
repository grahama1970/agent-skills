#!/usr/bin/env bash
# Resolve browser-oracle project/tab/url via sibling skill (JSON on stdout).
# shellcheck disable=SC2034

browser_oracle_resolve_json() {
  local from_path="${1:-.}"
  local backend="${2:-webgpt}"
  local project="${3:-}"
  local lane="${4:-}"

  local skill_dir
  skill_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  local bo_run="${BROWSER_ORACLE_RUN:-${skill_dir}/../browser-oracle/run.sh}"

  if [[ ! -x "$bo_run" ]]; then
    echo '{"status":"skipped","reason":"browser_oracle_missing"}'
    return 1
  fi

  local -a cmd=("$bo_run" resolve --from "$from_path" --backend "$backend" --json)
  if [[ -n "$project" ]]; then
    cmd+=(--project "$project")
  fi
  if [[ -n "$lane" ]]; then
    cmd+=(--lane "$lane")
  fi

  local out
  if ! out="$("${cmd[@]}" 2>/dev/null)"; then
    echo "$out"
    return 2
  fi
  printf '%s' "$out"
}

browser_oracle_reconcile_json() {
  local backend="${1:-webgpt}"
  local project="${2:-}"
  local prune_missing="${3:-0}"

  local skill_dir
  skill_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  local bo_run="${BROWSER_ORACLE_RUN:-${skill_dir}/../browser-oracle/run.sh}"

  if [[ ! -x "$bo_run" ]]; then
    echo '{"status":"skipped","reason":"browser_oracle_missing","rows":[]}'
    return 1
  fi

  local -a cmd=("$bo_run" reconcile --backend "$backend" --json)
  if [[ -n "$project" ]]; then
    cmd+=(--project "$project")
  fi
  if [[ "$prune_missing" == "1" || "$prune_missing" == "true" ]]; then
    cmd+=(--prune-missing)
  fi

  local out
  if ! out="$("${cmd[@]}" 2>/dev/null)"; then
    # reconcile exits non-zero for stale rows, but still prints the useful JSON.
    if [[ -n "$out" ]]; then
      printf '%s' "$out"
      return 0
    fi
    echo '{"status":"failed","reason":"browser_oracle_reconcile_failed","rows":[]}'
    return 2
  fi
  printf '%s' "$out"
}

browser_oracle_open_bind_json() {
  local project="$1"
  local backend="${2:-webgpt}"
  local url="$3"

  local skill_dir
  skill_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  local bo_run="${BROWSER_ORACLE_RUN:-${skill_dir}/../browser-oracle/run.sh}"

  if [[ ! -x "$bo_run" ]]; then
    echo '{"status":"skipped","reason":"browser_oracle_missing"}'
    return 1
  fi
  "$bo_run" open-bind "$project" --backend "$backend" --url "$url" --manual --json
}

# Apply resolved tab/url to caller variables: tab_id_var expect_url_var project_var
browser_oracle_apply_webgpt() {
  local from_path="${1:-.}"
  local project_in="${2:-}"
  local tab_id_in="${3:-}"
  local url_in="${4:-}"
  local create_tab="${5:-0}"

  if [[ -n "$tab_id_in" || -n "$url_in" || "$create_tab" -eq 1 ]]; then
    return 0
  fi

  local payload
  payload="$(browser_oracle_resolve_json "$from_path" webgpt "$project_in" "")" || return 0

  local resolved_project resolved_tab resolved_url
  resolved_project="$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("project") or "")' <<<"$payload")"
  resolved_tab="$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("tab_id") or "")' <<<"$payload")"
  resolved_url="$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("conversation_url") or "")' <<<"$payload")"

  if [[ -n "$resolved_project" && -n "$resolved_tab" ]]; then
    local reconcile_payload reconcile_status
    reconcile_payload="$(browser_oracle_reconcile_json webgpt "$resolved_project" "${SURF_BROWSER_ORACLE_PRUNE_MISSING:-0}" || true)"
    reconcile_status="$(python3 -c 'import json,sys; d=json.load(sys.stdin); rows=d.get("rows") or []; print((rows[0].get("status") if rows else ""))' <<<"$reconcile_payload" 2>/dev/null || true)"
    if [[ "$reconcile_status" != "ready" ]]; then
      resolved_tab=""
      resolved_url=""
    fi
  fi

  if [[ -z "$project_in" && -n "$resolved_project" ]]; then
    printf -v "$6" '%s' "$resolved_project"
  fi
  if [[ -z "$tab_id_in" && -n "$resolved_tab" ]]; then
    printf -v "$7" '%s' "$resolved_tab"
  fi
  if [[ -z "$url_in" && -n "$resolved_url" ]]; then
    printf -v "$8" '%s' "$resolved_url"
  fi
  return 0
}

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

  if [[ -z "$project" ]]; then
    echo '{"project":"","backend":"'"$backend"'","rows":[]}'
    return 2
  fi
  if [[ ! -x "$bo_run" ]]; then
    echo '{"project":"'"$project"'","backend":"'"$backend"'","rows":[{"status":"skipped","reason":"browser_oracle_missing"}]}'
    return 1
  fi

  local out
  if out="$("$bo_run" reconcile "$project" --backend "$backend" --json --prune-missing="$prune_missing" 2>/dev/null)"; then
    printf '%s' "$out"
    return 0
  fi

  if out="$("$bo_run" verify "$project" --backend "$backend" --json 2>/dev/null)"; then
    python3 -c 'import json,sys
backend = sys.argv[1]
project = sys.argv[2]
data = json.load(sys.stdin)
verified = bool(data.get("verified") or data.get("ok"))
status = "ready" if verified else "missing_live_tab"
row = dict(data)
row.setdefault("project", data.get("name") or project)
row.setdefault("backend", data.get("backend") or backend)
row["status"] = status
print(json.dumps({"project": row.get("project") or project, "backend": row.get("backend") or backend, "rows": [row]}, separators=(",", ":")))' "$backend" "$project" <<<"$out"
    return 0
  fi

  printf '%s' "$out"
  return 2
}

browser_oracle_open_bind_json() {
  local project="${1:-}"
  local backend="${2:-webgpt}"
  local url="${3:-}"

  local skill_dir
  skill_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  local bo_run="${BROWSER_ORACLE_RUN:-${skill_dir}/../browser-oracle/run.sh}"

  if [[ -z "$project" ]]; then
    echo '{"status":"failed","reason":"project_required"}'
    return 2
  fi
  if [[ ! -x "$bo_run" ]]; then
    echo '{"status":"failed","reason":"browser_oracle_missing"}'
    return 1
  fi

  local out
  if out="$("$bo_run" open-bind "$project" --backend "$backend" --url "$url" --json 2>/dev/null)"; then
    printf '%s' "$out"
    return 0
  fi
  if out="$("$bo_run" open-bind "$project" "$backend" "$url" 2>/dev/null)"; then
    printf '%s' "$out"
    return 0
  fi

  echo '{"status":"failed","reason":"browser_oracle_open_bind_unavailable"}'
  return 2
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

#!/usr/bin/env bash
# Shared helpers for resolving ChatGPT tabs. Source from other webgpt scripts.

webgpt_resolve_lib_dir() {
  if [[ -n "${WEBGPT_RESOLVE_LIB_DIR:-}" ]]; then
    printf '%s\n' "$WEBGPT_RESOLVE_LIB_DIR"
    return 0
  fi
  WEBGPT_RESOLVE_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  printf '%s\n' "$WEBGPT_RESOLVE_LIB_DIR"
}

webgpt_resolve_url_from_list() {
  local target_url="$1"
  local tab_list_text="$2"
  local lib_dir
  lib_dir="$(webgpt_resolve_lib_dir)"
  resolve_json="$(
    printf '%s\n' "$tab_list_text" \
      | python3 "${lib_dir}/resolve_webgpt_tab.py" resolve-url --url "$target_url"
  )"
  resolve_error="$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('error') or '')" "$resolve_json")"
  if python3 -c "import json,sys; raise SystemExit(0 if json.loads(sys.argv[1]).get('ok') else 1)" "$resolve_json"; then
    resolved_tab_id="$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['tab_id'])" "$resolve_json")"
    return 0
  fi
  resolved_tab_id=""
  return 1
}

webgpt_sanitize_tab_id() {
  printf '%s' "$1" | tr -cd '0-9' | head -c 20
}

webgpt_focus_active_tab_id() {
  local focus_json="${1:-\{\}}"
  python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('activeTabId') or '')" "$focus_json"
}

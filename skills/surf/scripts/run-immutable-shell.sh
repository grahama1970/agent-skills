#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: run-immutable-shell.sh SCRIPT [ARGS...]" >&2
  exit 2
fi

source_script="$1"
shift
script_dir="$(cd "$(dirname "$source_script")" && pwd)"
script_name="$(basename "$source_script")"
snapshot="$(mktemp "${script_dir}/.${script_name}.snapshot.XXXXXX")"

cleanup() {
  rm -f "$snapshot"
}
trap cleanup EXIT INT TERM

cp "$source_script" "$snapshot"
chmod --reference="$source_script" "$snapshot"
"$snapshot" "$@"

#!/usr/bin/env bash
# Conservative live red-team probes for /surf WebGPT transport.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUT="${SKILL_DIR}/.surf_artifacts/redteam/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT"
REPORT="$OUT/REPORT.md"
RUN_SH="${SKILL_DIR}/run.sh"
TAB_ID="${REDTEAM_TAB_ID:-}"
URL="${REDTEAM_URL:-}"
{
  echo "# Surf WebGPT red-team report"
  echo "- run_dir: \`$OUT\`"
  echo ""
  echo "| probe | result | detail |"
  echo "| --- | --- | --- |"
} >"$REPORT"
probe() {
  local name="$1"; shift
  local detail result=pass
  if detail="$("$@" 2>&1)"; then result=pass; else result=fail; fi
  detail="${detail//$'\n'/; }"; detail="${detail:0:200}"
  echo "| $name | $result | $detail |" >>"$REPORT"
}
probe_expect_fail preflight_fake_tab "$RUN_SH" webgpt.preflight --tab-id 999999999 --no-activate --json
echo "pong" > "$OUT/req.md"
probe_expect_fail no_activate_requires_target bash -c "$RUN_SH webgpt.submit --no-activate --input $OUT/req.md --output $OUT/out.md --timeout 5; test \$? -ne 0"
if [[ -n "$TAB_ID" ]]; then
  probe tab_id_background "$RUN_SH" webgpt.tab-id-background-sanity --json --output-dir "$OUT/tab-bg" --tab-id "$TAB_ID"
  if [[ "${REDTEAM_ALLOW_ROUNDTRIP:-0}" == "1" ]]; then
    probe roundtrip "$RUN_SH" webgpt.roundtrip-preflight --no-activate --json --timeout 60 --output-dir "$OUT/roundtrip" --tab-id "$TAB_ID" ${URL:+--expect-url "$URL"}
  else
    echo "| roundtrip | skipped | REDTEAM_ALLOW_ROUNDTRIP=1 |" >>"$REPORT"
  fi
else
  echo "| tab probes | skipped | set REDTEAM_TAB_ID |" >>"$REPORT"
fi
cat "$REPORT"

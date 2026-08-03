#!/usr/bin/env bash
# surf_cmds.sh — emit direct surf CLI commands for this agent's WebGPT work.
# Source this, then run the printed commands verbatim.
set -euo pipefail

BINDING="$HOME/.pi/webgpt-projects/sparta.json"
SURF="/home/graham/workspace/experiments/agent-skills/skills/surf/run.sh"
CLI="/home/graham/workspace/experiments/agent-skills/skills/surf/vendor/surf-cli/native/cli.cjs"

tab_id="$(python3 -c "import json; print(json.load(open('$BINDING')).get('tab_id',''))" 2>/dev/null)"
conv_url="$(python3 -c "import json; print(json.load(open('$BINDING')).get('conversation_url',''))" 2>/dev/null)"
kde="$(python3 -c "import json; print(json.load(open('$BINDING')).get('kde_desktop_index','2'))" 2>/dev/null)"

case "${1:-}" in
  submit)
    bundle="${2:-bundle.md}"
    cat <<CMDS
# === surf commands for: webgpt submit ===
# 1. Switch to KDE desktop ${kde} (tab lives there)
CURRENT_DESKTOP=\$(qdbus org.kde.KWin /KWin currentDesktop)
if [ "\$CURRENT_DESKTOP" != "${kde}" ]; then wmctrl -s ${kde}; sleep 1; fi

# 2. Submit via --create-tab (avoids stale CDP + composer drafts)
${SURF} webgpt.submit \\
  --input "${bundle}" \\
  --output "${bundle%.*}-response.md" \\
  --create-tab \\
  --timeout 900

# 3. After response: download any solution zip
NEW_TAB=\$(cat /tmp/surf-webgpt-controlled-tab-id)
${SURF} webgpt.download \\
  --match ".zip" \\
  --tab-id "\$NEW_TAB" \\
  --output "${bundle%.*}-solution.zip" \\
  --timeout 30
CMDS
    ;;

  download)
    cat <<CMDS
# === surf commands for: download zip ===
# Click download button by matching text
TAB=\$(cat /tmp/surf-webgpt-controlled-tab-id)
${SURF} click "${2:-.zip}" --tab-id "\$TAB"
sleep 3
ls -lt ~/Downloads/*.zip 2>/dev/null | head -3
CMDS
    ;;

  submit-direct)
    bundle="${2:-bundle.md}"
    cat <<CMDS
# === surf commands for: direct submit via CLI (no wrapper) ===
# Switch desktop
CURRENT_DESKTOP=\$(qdbus org.kde.KWin /KWin currentDesktop)
if [ "\$CURRENT_DESKTOP" != "${kde}" ]; then wmctrl -s ${kde}; sleep 1; fi

# Activate tab (release stale CDP)
${SURF} tab.activate ${tab_id}
sleep 2

# Clear composer + localStorage drafts
${SURF} js 'if(typeof localStorage!="undefined"){Object.keys(localStorage).filter(k=>k.includes("draft")||k.includes("composer")).forEach(k=>localStorage.removeItem(k))};const ta=document.querySelector("#prompt-textarea")||document.querySelector("[contenteditable]");if(ta){if(ta.tagName==="TEXTAREA"||ta.tagName==="INPUT")ta.value="";else{ta.innerHTML="<p></p>";ta.textContent=""};ta.dispatchEvent(new Event("input",{bubbles:true}))};return"ok"' --tab-id ${tab_id}

# Submit directly via compiled CLI (skips bash wrapper)
${CLI} chatgpt --query-file "${bundle}" \\
  --tab-id ${tab_id} \\
  --target-tab-id ${tab_id} \\
  --sentinel "\$(date +%Y%m%dT%H%M%SZ)" \\
  --timeout 900 \\
  --keep-tab \\
  --reasoning Pro
CMDS
    ;;

  *)
    echo "Usage: $0 {submit|download|submit-direct} [bundle.md]" >&2
    echo "Outputs exact surf CLI commands for this agent (sparta)." >&2
    exit 1
    ;;
esac

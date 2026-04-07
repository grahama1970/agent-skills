#!/usr/bin/env bash
# Audio diagnostics: PipeWire, ALSA, sinks, streams, XRUN detection.
# Catches silent failures like XRDP sink hijack, echo-cancel XRUNs, stale streams.
set -euo pipefail

OUTPUT="${OUTPUT:-markdown}"
FIX=false

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Audio system diagnostics — PipeWire, ALSA, sinks, streams, and error detection.

Options:
  --json           Output as JSON (single object) or set OUTPUT=json env
  --fix            Attempt automatic fixes for detected issues
  --help           Show this message

Checks:
  - PipeWire / WirePlumber service status
  - Default sink (detects virtual sink hijack: xrdp, null, dummy)
  - Sink volume and mute state
  - ALSA XRUN detection (buffer underruns — silent audio killer)
  - PipeWire node error counts (pw-top ERR column)
  - Active streams and their routing
  - Echo-cancel module health
  - USB audio device connectivity

Exit Codes:
  0 = Audio healthy
  1 = Warning (suboptimal but working)
  2 = Critical (audio broken or muted)
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --json) OUTPUT="json"; shift;;
    --fix) FIX=true; shift;;
    --help|-h) usage; exit 0;;
    *) echo "Unknown option: $1" >&2; usage; exit 1;;
  esac
done

status=0  # 0=ok, 1=warn, 2=critical
issues=()
fixes_applied=()

escalate() {
  local level="$1"
  if (( level > status )); then
    status=$level
  fi
}

issue() {
  local severity="$1" msg="$2"
  issues+=("${severity}|${msg}")
  if [[ "$severity" == "CRITICAL" ]]; then
    escalate 2
  else
    escalate 1
  fi
}

# ── Check 1: PipeWire services ──

pw_running=false
wp_running=false
pulse_running=false

if systemctl --user is-active pipewire >/dev/null 2>&1; then
  pw_running=true
fi
if systemctl --user is-active wireplumber >/dev/null 2>&1; then
  wp_running=true
fi
if systemctl --user is-active pipewire-pulse >/dev/null 2>&1; then
  pulse_running=true
fi

if ! $pw_running; then
  issue "CRITICAL" "PipeWire not running"
fi
if ! $wp_running; then
  issue "CRITICAL" "WirePlumber not running"
fi

pw_version=""
if command -v pipewire >/dev/null 2>&1; then
  pw_version=$(pipewire --version 2>/dev/null | grep -oP 'libpipewire \K[0-9.]+' | head -1 || echo "unknown")
fi

# ── Check 2: Default sink (virtual sink hijack detection) ──

default_sink_name=""
default_configured_sink=""
sink_hijacked=false

if command -v pw-metadata >/dev/null 2>&1 && $pw_running; then
  default_sink_name=$(pw-metadata -n default 2>/dev/null | grep "default.audio.sink" | grep -oP '"name":\s*"[^"]*"' | head -1 | cut -d'"' -f4 || echo "")
  default_configured_sink=$(pw-metadata -n default 2>/dev/null | grep "default.configured.audio.sink" | grep -oP '"name":\s*"[^"]*"' | head -1 | cut -d'"' -f4 || echo "")

  # Detect virtual/dummy sink hijack
  for bad_sink in "xrdp-sink" "null" "dummy" "auto_null"; do
    if [[ "$default_configured_sink" == *"$bad_sink"* ]]; then
      issue "CRITICAL" "Default configured sink hijacked by '$default_configured_sink' — audio routed to virtual device"
      sink_hijacked=true

      if $FIX; then
        # Find first real ALSA sink and set it as default
        real_sink_id=$(wpctl status 2>/dev/null | grep -E "^\s+\*?\s+\d+\." | grep -i "alsa\|analog\|speak\|headphone\|speaker" | head -1 | grep -oP '^\s*\*?\s*\K\d+' || echo "")
        if [[ -n "$real_sink_id" ]]; then
          wpctl set-default "$real_sink_id" 2>/dev/null
          fixes_applied+=("Set default sink to node $real_sink_id")
        fi
      fi
      break
    fi
  done
fi

# ── Check 3: Sink volume and mute ──

sink_volume=""
sink_muted=false

if command -v wpctl >/dev/null 2>&1 && $pw_running; then
  vol_output=$(wpctl get-volume @DEFAULT_AUDIO_SINK@ 2>/dev/null || echo "")
  if [[ "$vol_output" == *"MUTED"* ]]; then
    sink_muted=true
    issue "CRITICAL" "Default audio sink is MUTED"
    if $FIX; then
      wpctl set-mute @DEFAULT_AUDIO_SINK@ 0 2>/dev/null
      fixes_applied+=("Unmuted default audio sink")
    fi
  fi
  sink_volume=$(echo "$vol_output" | grep -oP 'Volume: \K[0-9.]+' || echo "")

  if [[ -n "$sink_volume" ]] && (( $(echo "$sink_volume < 0.1" | bc -l 2>/dev/null || echo 0) )); then
    issue "WARNING" "Default sink volume very low: ${sink_volume}"
  fi
fi

# ── Check 4: ALSA XRUN detection ──

xrun_detected=false
xrun_cards=()

if $pw_running; then
  for status_file in /proc/asound/card*/pcm*p/sub*/status; do
    [[ -f "$status_file" ]] || continue
    state=$(grep "^state:" "$status_file" 2>/dev/null | awk '{print $2}' || echo "")
    if [[ "$state" == "XRUN" ]]; then
      xrun_detected=true
      card=$(echo "$status_file" | grep -oP 'card\K\d+')
      card_name=$(cat "/proc/asound/card${card}/id" 2>/dev/null || echo "card${card}")
      xrun_cards+=("${card_name}")
      issue "CRITICAL" "ALSA XRUN on ${card_name} (card ${card}) — audio buffer underrun, no sound output"
    fi
  done
fi

# ── Check 5: PipeWire node errors (pw-top) ──

pw_errors=()

if command -v pw-top >/dev/null 2>&1 && $pw_running; then
  # pw-top -b gives one snapshot
  while IFS= read -r line; do
    # Parse: S ID QUANT RATE WAIT BUSY W/Q B/Q ERR FORMAT NAME
    err=$(echo "$line" | awk '{print $9}')
    name=$(echo "$line" | awk '{for(i=11;i<=NF;i++) printf "%s ", $i; print ""}' | sed 's/ *$//')
    if [[ "$err" =~ ^[0-9]+$ ]] && (( err > 10 )); then
      pw_errors+=("${name}|${err}")
      if (( err > 100 )); then
        issue "CRITICAL" "PipeWire node '${name}' has ${err} errors — audio processing failing"
      else
        issue "WARNING" "PipeWire node '${name}' has ${err} errors"
      fi
    fi
  done < <(timeout 2 pw-top -b 2>/dev/null | tail -n +2 || true)
fi

# ── Check 6: Echo-cancel module ──

aec_enabled=false
aec_config=""
aec_xrun=false

for conf in "$HOME/.config/pipewire/pipewire.conf.d"/*echo*cancel* "$HOME/.config/pipewire/pipewire.conf.d"/*aec* /etc/pipewire/pipewire.conf.d/*echo*cancel*; do
  if [[ -f "$conf" ]] && [[ "$conf" != *.disabled ]]; then
    aec_enabled=true
    aec_config="$conf"
    break
  fi
done

if $aec_enabled && $xrun_detected; then
  aec_xrun=true
  issue "CRITICAL" "Echo-cancel module active (${aec_config}) AND ALSA XRUN detected — AEC likely causing buffer underruns"
  if $FIX; then
    mv "$aec_config" "${aec_config}.disabled" 2>/dev/null
    fixes_applied+=("Disabled echo-cancel config: ${aec_config}")
    systemctl --user restart pipewire pipewire-pulse wireplumber 2>/dev/null || true
    fixes_applied+=("Restarted PipeWire")
  fi
fi

# ── Check 7: Active streams ──

streams=()

if command -v wpctl >/dev/null 2>&1 && $pw_running; then
  while IFS= read -r line; do
    # Match stream lines like: "  107. Google Chrome  [active]"
    if [[ "$line" =~ ^[[:space:]]+([0-9]+)\.[[:space:]]+(.+)[[:space:]]+$ ]]; then
      streams+=("${BASH_REMATCH[1]}|${BASH_REMATCH[2]}")
    fi
  done < <(wpctl status 2>/dev/null | sed -n '/Streams:/,/^$/p' || true)
fi

# ── Check 8: USB audio devices ──

usb_audio_devices=()

if [[ -d /proc/asound ]]; then
  for card_dir in /proc/asound/card*/; do
    [[ -d "$card_dir" ]] || continue
    card_num=$(basename "$card_dir" | sed 's/card//')
    card_id=$(cat "${card_dir}id" 2>/dev/null || echo "unknown")

    stream_file="${card_dir}stream0"
    if [[ -f "$stream_file" ]] && grep -q "USB Audio" "$stream_file" 2>/dev/null; then
      usb_speed=""
      # Check USB topology for speed
      product=$(head -1 "$stream_file" 2>/dev/null || echo "")
      if echo "$product" | grep -q "full speed"; then
        usb_speed="full-speed (12M)"
      elif echo "$product" | grep -q "high speed"; then
        usb_speed="high-speed (480M)"
      elif echo "$product" | grep -q "super speed"; then
        usb_speed="super-speed (5G+)"
      fi

      playback_state="none"
      pcm_status="${card_dir}pcm0p/sub0/status"
      if [[ -f "$pcm_status" ]]; then
        playback_state=$(grep "^state:" "$pcm_status" 2>/dev/null | awk '{print $2}' || echo "closed")
      fi

      usb_audio_devices+=("${card_num}|${card_id}|${usb_speed}|${playback_state}|${product}")
    fi
  done
fi

# ── Check 9: Sink list ──

sinks=()

if command -v wpctl >/dev/null 2>&1 && $pw_running; then
  while IFS= read -r line; do
    if [[ "$line" =~ ^[[:space:]]*(\*?)[[:space:]]*([0-9]+)\.[[:space:]]+(.+)[[:space:]]+\[vol:[[:space:]]*([0-9.]+)\] ]]; then
      is_default="false"
      [[ -n "${BASH_REMATCH[1]}" ]] && is_default="true"
      sinks+=("${BASH_REMATCH[2]}|${BASH_REMATCH[3]}|${BASH_REMATCH[4]}|${is_default}")
    fi
  done < <(wpctl status 2>/dev/null | sed -n '/Audio/,/Video/p' | sed -n '/Sinks:/,/Sink endpoints/p' || true)
fi

# ── Output ──

json_escape() {
  echo -n "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\t/ /g'
}

if [[ "$OUTPUT" == "json" ]]; then
  echo "{"
  echo "  \"timestamp\": \"$(date -Iseconds)\","
  echo "  \"status\": $status,"
  echo "  \"status_text\": \"$(if (( status == 0 )); then echo "healthy"; elif (( status == 1 )); then echo "warning"; else echo "critical"; fi)\","
  echo "  \"pipewire\": {\"running\": $pw_running, \"version\": \"$(json_escape "$pw_version")\", \"wireplumber\": $wp_running, \"pulse\": $pulse_running},"
  echo "  \"default_sink\": {\"name\": \"$(json_escape "$default_sink_name")\", \"configured\": \"$(json_escape "$default_configured_sink")\", \"volume\": \"$sink_volume\", \"muted\": $sink_muted, \"hijacked\": $sink_hijacked},"
  echo "  \"xrun_detected\": $xrun_detected,"
  echo "  \"aec\": {\"enabled\": $aec_enabled, \"config\": \"$(json_escape "$aec_config")\", \"causing_xrun\": $aec_xrun},"

  # Issues
  echo "  \"issues\": ["
  first=true
  for i in "${issues[@]+"${issues[@]}"}"; do
    $first || echo ","
    first=false
    sev=$(echo "$i" | cut -d'|' -f1)
    msg=$(echo "$i" | cut -d'|' -f2-)
    echo -n "    {\"severity\": \"$sev\", \"message\": \"$(json_escape "$msg")\"}"
  done
  echo ""
  echo "  ],"

  # Sinks
  echo "  \"sinks\": ["
  first=true
  for s in "${sinks[@]+"${sinks[@]}"}"; do
    $first || echo ","
    first=false
    IFS='|' read -r id name vol def <<< "$s"
    echo -n "    {\"id\": $id, \"name\": \"$(json_escape "$name")\", \"volume\": $vol, \"default\": $def}"
  done
  echo ""
  echo "  ],"

  # USB devices
  echo "  \"usb_audio\": ["
  first=true
  for d in "${usb_audio_devices[@]+"${usb_audio_devices[@]}"}"; do
    $first || echo ","
    first=false
    IFS='|' read -r num cid speed pstate product <<< "$d"
    echo -n "    {\"card\": $num, \"id\": \"$(json_escape "$cid")\", \"usb_speed\": \"$(json_escape "$speed")\", \"playback_state\": \"$(json_escape "$pstate")\", \"product\": \"$(json_escape "$product")\"}"
  done
  echo ""
  echo "  ],"

  # PW errors
  echo "  \"pw_node_errors\": ["
  first=true
  for e in "${pw_errors[@]+"${pw_errors[@]}"}"; do
    $first || echo ","
    first=false
    name=$(echo "$e" | cut -d'|' -f1)
    err=$(echo "$e" | cut -d'|' -f2)
    echo -n "    {\"node\": \"$(json_escape "$name")\", \"errors\": $err}"
  done
  echo ""
  echo "  ],"

  # Fixes
  echo "  \"fixes_applied\": ["
  first=true
  for f in "${fixes_applied[@]+"${fixes_applied[@]}"}"; do
    $first || echo ","
    first=false
    echo -n "    \"$(json_escape "$f")\""
  done
  echo ""
  echo "  ]"
  echo "}"
else
  echo "## Audio Diagnostics"
  echo ""
  echo "**Generated:** $(date '+%Y-%m-%d %H:%M:%S')"
  echo ""

  # Status banner
  if (( status == 0 )); then
    echo "**Status: HEALTHY**"
  elif (( status == 1 )); then
    echo "**Status: WARNING**"
  else
    echo "**Status: CRITICAL**"
  fi
  echo ""

  # Issues
  if [[ ${#issues[@]} -gt 0 ]]; then
    echo "### Issues Detected"
    echo ""
    for i in "${issues[@]}"; do
      sev=$(echo "$i" | cut -d'|' -f1)
      msg=$(echo "$i" | cut -d'|' -f2-)
      if [[ "$sev" == "CRITICAL" ]]; then
        echo "- **$sev:** $msg"
      else
        echo "- $sev: $msg"
      fi
    done
    echo ""
  fi

  # Fixes applied
  if [[ ${#fixes_applied[@]} -gt 0 ]]; then
    echo "### Fixes Applied"
    echo ""
    for f in "${fixes_applied[@]}"; do
      echo "- $f"
    done
    echo ""
  fi

  # Services
  echo "### PipeWire Services"
  echo ""
  echo "| Service | Status |"
  echo "|---------|--------|"
  echo "| PipeWire | $($pw_running && echo "running" || echo "**STOPPED**") |"
  echo "| WirePlumber | $($wp_running && echo "running" || echo "**STOPPED**") |"
  echo "| PipeWire-Pulse | $($pulse_running && echo "running" || echo "**STOPPED**") |"
  if [[ -n "$pw_version" ]]; then
    echo "| Version | $pw_version |"
  fi
  echo ""

  # Default sink
  echo "### Default Sink"
  echo ""
  echo "| Property | Value |"
  echo "|----------|-------|"
  echo "| Active sink | ${default_sink_name:-unknown} |"
  echo "| Configured sink | ${default_configured_sink:-unknown} |"
  echo "| Volume | ${sink_volume:-unknown} |"
  echo "| Muted | $sink_muted |"
  if $sink_hijacked; then
    echo "| **HIJACKED** | Default routed to virtual device |"
  fi
  echo ""

  # Sinks
  if [[ ${#sinks[@]} -gt 0 ]]; then
    echo "### Audio Sinks"
    echo ""
    echo "| ID | Name | Volume | Default |"
    echo "|----|------|--------|---------|"
    for s in "${sinks[@]}"; do
      IFS='|' read -r id name vol def <<< "$s"
      def_mark=""
      [[ "$def" == "true" ]] && def_mark="*"
      echo "| $id | $name | $vol | $def_mark |"
    done
    echo ""
  fi

  # USB audio
  if [[ ${#usb_audio_devices[@]} -gt 0 ]]; then
    echo "### USB Audio Devices"
    echo ""
    echo "| Card | ID | USB Speed | Playback State |"
    echo "|------|----|-----------|----------------|"
    for d in "${usb_audio_devices[@]}"; do
      IFS='|' read -r num cid speed pstate product <<< "$d"
      state_fmt="$pstate"
      [[ "$pstate" == "XRUN" ]] && state_fmt="**XRUN**"
      echo "| $num | $cid | $speed | $state_fmt |"
    done
    echo ""
  fi

  # Echo-cancel
  echo "### Echo Cancellation"
  echo ""
  if $aec_enabled; then
    echo "- Module: **enabled** ($aec_config)"
    if $aec_xrun; then
      echo "- **AEC is likely causing XRUN** — disable with: \`mv $aec_config ${aec_config}.disabled\`"
    fi
  else
    echo "- Module: disabled"
  fi
  echo ""

  # PW node errors
  if [[ ${#pw_errors[@]} -gt 0 ]]; then
    echo "### PipeWire Node Errors"
    echo ""
    echo "| Node | Errors |"
    echo "|------|--------|"
    for e in "${pw_errors[@]}"; do
      name=$(echo "$e" | cut -d'|' -f1)
      err=$(echo "$e" | cut -d'|' -f2)
      echo "| $name | **$err** |"
    done
    echo ""
  fi

  # Troubleshooting tips
  if (( status > 0 )); then
    echo "### Troubleshooting"
    echo ""
    if $sink_hijacked; then
      echo "**Virtual sink hijack:** An XRDP or virtual session set itself as the default audio device."
      echo "Fix: \`wpctl set-default <real-sink-id>\` or run with \`--fix\`"
      echo ""
    fi
    if $xrun_detected; then
      echo "**ALSA XRUN:** Audio buffer underruns — the audio device cannot process data fast enough."
      echo "Common causes:"
      echo "- Echo-cancel module incompatible with USB device timing"
      echo "- USB full-speed (12M) device needs larger buffer headroom"
      echo "- PipeWire ALSA driver misconfiguration"
      echo ""
      echo "Quick fix: \`systemctl --user restart pipewire pipewire-pulse wireplumber\`"
      echo "If echo-cancel is the cause: \`mv ~/.config/pipewire/pipewire.conf.d/*aec* ~/.config/pipewire/pipewire.conf.d/disabled/\`"
      echo ""
    fi
    if $sink_muted; then
      echo "**Sink muted:** \`wpctl set-mute @DEFAULT_AUDIO_SINK@ 0\`"
      echo ""
    fi
  fi
fi

exit $status

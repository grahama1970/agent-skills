#!/usr/bin/env bash
set -euo pipefail

OUTPUT="${OUTPUT:-markdown}"
ACTION="${1:-status}"
[[ $# -gt 0 ]] && shift || true
TARGET=""

SINK_VOL="${OPS_WORKSTATION_MEETING_SINK_VOL:-0.85}"
SOURCE_VOL="${OPS_WORKSTATION_MEETING_SOURCE_VOL:-0.60}"
JABRA_MATCH="${OPS_WORKSTATION_JABRA_MATCH:-Jabra|SPEAK_510|SPEAK 510}"
EARBUD_MATCH="${OPS_WORKSTATION_EARBUD_BT_MATCH:-earbud|buds|airpods|galaxy|sony|bose|beats|BTunes|SB1PA59D}"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/ops-workstation"
RECEIPT="$STATE_DIR/audio-switch-receipt.json"
mkdir -p "$STATE_DIR"

usage() {
  cat <<USAGE
Usage: $(basename "$0") [status|set TARGET|fallback|next] [TARGET] [--json]

Targets: jabra-usb, jabra-bt, earbuds-bt, wired
fallback order: jabra-bt -> earbuds-bt -> wired -> jabra-usb
USAGE
}

for arg in "$@"; do
  case "$arg" in
    --json) OUTPUT=json ;;
    --help|-h) usage; exit 0 ;;
    *) [[ -z "$TARGET" ]] && TARGET="$arg" ;;
  esac
done

case "$ACTION" in
  status|set|fallback|next) ;;
  --json) OUTPUT=json; ACTION=status ;;
  --help|-h) usage; exit 0 ;;
  *) echo "Unknown action: $ACTION" >&2; usage; exit 2 ;;
esac

python3 - "$OUTPUT" "$ACTION" "$TARGET" "$SINK_VOL" "$SOURCE_VOL" "$JABRA_MATCH" "$EARBUD_MATCH" "$RECEIPT" <<'PY'
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

output, action, requested, sink_vol, source_vol, jabra_rx, earbud_rx, receipt_path = sys.argv[1:]
TARGETS = ["jabra-usb", "jabra-bt", "earbuds-bt", "wired"]
FALLBACK = ["jabra-bt", "earbuds-bt", "wired", "jabra-usb"]


def run(cmd: list[str], timeout: int = 8) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, check=False)
        return p.returncode, p.stdout, p.stderr
    except Exception as exc:
        return 124, "", str(exc)


def pulse(kind: str) -> list[dict[str, str]]:
    rc, out, _ = run(["pactl", "list", "short", kind])
    rows = []
    if rc != 0:
        return rows
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            rows.append({"id": parts[0], "name": parts[1], "raw": line})
    return rows


def info() -> dict[str, str]:
    rc, out, _ = run(["pactl", "info"])
    data = {}
    if rc == 0:
        for line in out.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                data[k.strip()] = v.strip()
    return data


def match(rows: list[dict[str, str]], target: str) -> dict[str, str] | None:
    def has(row: dict[str, str], rx: str) -> bool:
        return re.search(rx, row["name"], re.I) is not None

    if target == "wired":
        choices = []
        for row in rows:
            name = row["name"]
            lower = name.lower()
            is_bt = "bluez" in lower
            is_jabra = has(row, jabra_rx)
            if is_bt or is_jabra or "webcam" in lower or "c920" in lower:
                continue
            if not re.search(r"headphone|headset|microphone|mic|HiFi|usb-Generic_USB_Audio", name, re.I):
                continue
            score = 0
            if "_1__sink" in name or "headphone" in lower or "headset" in lower:
                score += 100
            if "_2__source" in name or "microphone" in lower or "mic" in lower:
                score += 100
            if "spdif" in lower or "_2__sink" in name or "line" in lower:
                score -= 50
            choices.append((score, row))
        return max(choices, key=lambda item: item[0])[1] if choices else None

    for row in rows:
        name = row["name"]
        is_bt = "bluez" in name.lower()
        is_jabra = has(row, jabra_rx)
        if target == "jabra-usb" and is_jabra and not is_bt:
            return row
        if target == "jabra-bt" and is_jabra and is_bt:
            return row
        if target == "earbuds-bt" and is_bt and not is_jabra and has(row, earbud_rx):
            return row
    return None


def wpctl_id(node_name: str) -> str | None:
    rc, out, _ = run(["wpctl", "status"])
    if rc != 0:
        return None
    ids = re.findall(r"\b(\d+)\.", out)
    for node_id in ids:
        irc, inspect, _ = run(["wpctl", "inspect", node_id])
        if irc == 0 and f'node.name = "{node_name}"' in inspect:
            return node_id
    return None


def set_default(kind: str, name: str, commands: list[str], errors: list[str]) -> None:
    value = json.dumps({"name": name})
    for key in (f"default.audio.{kind}", f"default.configured.audio.{kind}"):
        cmd = ["pw-metadata", "-n", "default", "0", key, value, "Spa:String:JSON"]
        commands.append(" ".join(cmd))
        rc, _, err = run(cmd)
        if rc != 0:
            errors.append(err.strip() or " ".join(cmd))
    node_id = wpctl_id(name)
    if node_id:
        cmd = ["wpctl", "set-default", node_id]
        commands.append(" ".join(cmd))
        rc, _, err = run(cmd)
        if rc != 0:
            errors.append(err.strip() or " ".join(cmd))
    cmd = ["pactl", f"set-default-{kind}", name]
    commands.append(" ".join(cmd))
    rc, _, err = run(cmd)
    if rc != 0:
        errors.append(err.strip() or " ".join(cmd))


def chrome_stream_ids(kind: str) -> list[str]:
    rc, out, _ = run(["pactl", "list", kind])
    ids, current, chrome = [], None, False
    header = "Sink Input #" if kind == "sink-inputs" else "Source Output #"
    for line in out.splitlines() + [""]:
        if line.startswith(header):
            if current and chrome:
                ids.append(current)
            current = line.rsplit("#", 1)[1].strip()
            chrome = False
        elif 'application.name = "Google Chrome"' in line or 'application.process.binary = "chrome"' in line or 'application.process.binary = "google-chrome"' in line:
            chrome = True
        elif not line.strip() and current:
            if chrome:
                ids.append(current)
            current, chrome = None, False
    return ids


def write_override_marker(target: str) -> None:
    if target == "jabra-usb":
        return
    Path(receipt_path).write_text(json.dumps({
        "schema": "ops_workstation.audio_switch.v1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "override-marker",
        "selected_target": target,
        "status": "OK",
    }, indent=2) + "\n")


def set_target(target: str) -> tuple[bool, list[str], list[str], dict[str, str | None]]:
    write_override_marker(target)
    sinks, sources = pulse("sinks"), pulse("sources")
    sink = match(sinks, target)
    source = match([s for s in sources if not s["name"].endswith(".monitor")], target)
    commands, errors = [], []
    if not sink:
        return False, commands, [f"no sink for {target}"], {"sink": None, "source": source["name"] if source else None}
    set_default("sink", sink["name"], commands, errors)
    for cmd in (["pactl", "set-sink-mute", sink["name"], "0"], ["pactl", "set-sink-volume", sink["name"], sink_vol]):
        commands.append(" ".join(cmd))
        rc, _, err = run(cmd)
        if rc != 0:
            errors.append(err.strip() or " ".join(cmd))
    if source:
        set_default("source", source["name"], commands, errors)
        for cmd in (["pactl", "set-source-mute", source["name"], "0"], ["pactl", "set-source-volume", source["name"], source_vol]):
            commands.append(" ".join(cmd))
            rc, _, err = run(cmd)
            if rc != 0:
                errors.append(err.strip() or " ".join(cmd))
    else:
        errors.append(f"no source for {target}")
    for sid in chrome_stream_ids("sink-inputs"):
        cmd = ["pactl", "move-sink-input", sid, sink["name"]]
        commands.append(" ".join(cmd))
        run(cmd)
    if source:
        for sid in chrome_stream_ids("source-outputs"):
            cmd = ["pactl", "move-source-output", sid, source["name"]]
            commands.append(" ".join(cmd))
            run(cmd)
    return not errors, commands, errors, {"sink": sink["name"], "source": source["name"] if source else None}


def target_availability() -> dict[str, dict[str, object]]:
    sinks, sources = pulse("sinks"), [s for s in pulse("sources") if not s["name"].endswith(".monitor")]
    return {t: {"sink": (match(sinks, t) or {}).get("name"), "source": (match(sources, t) or {}).get("name")} for t in TARGETS}

availability = target_availability()
inf = info()
commands: list[str] = []
errors: list[str] = []
selected = None
ok = True

if action == "set":
    if requested not in TARGETS:
        ok = False
        errors.append(f"unknown target {requested!r}")
    else:
        selected = requested
        ok, commands, errors, _ = set_target(requested)
elif action == "fallback":
    ok = False
    for target in FALLBACK:
        if availability[target]["sink"] and availability[target]["source"]:
            selected = target
            ok, commands, errors, _ = set_target(target)
            break
    if not selected:
        errors.append("no fallback audio sink available")
elif action == "next":
    current = inf.get("Default Sink", "")
    current_target = next((t for t in TARGETS if availability[t]["sink"] == current), None)
    order = TARGETS
    start = (order.index(current_target) + 1) if current_target in order else 0
    ok = False
    for target in order[start:] + order[:start]:
        if availability[target]["sink"] and availability[target]["source"]:
            selected = target
            ok, commands, errors, _ = set_target(target)
            break
    if not selected:
        errors.append("no audio sink available")

inf = info()
availability = target_availability()
receipt = {
    "schema": "ops_workstation.audio_switch.v1",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "action": action,
    "requested_target": requested,
    "selected_target": selected,
    "status": "OK" if ok else "FAILED",
    "default_sink": inf.get("Default Sink", ""),
    "default_source": inf.get("Default Source", ""),
    "targets": availability,
    "commands": commands,
    "errors": errors,
    "receipt": receipt_path,
}
Path(receipt_path).write_text(json.dumps(receipt, indent=2) + "\n")

if output == "json":
    print(json.dumps(receipt, indent=2))
else:
    print("## Audio Switch")
    print(f"Status: {receipt['status']}")
    print(f"Default sink: {receipt['default_sink']}")
    print(f"Default source: {receipt['default_source']}")
    print("\nTargets:")
    for target, devices in availability.items():
        print(f"- {target}: sink={devices['sink'] or 'missing'} source={devices['source'] or 'missing'}")
    if selected:
        print(f"\nSelected: {selected}")
    if errors:
        print("\nErrors:")
        for error in errors:
            print(f"- {error}")
    print(f"\nReceipt: {receipt_path}")

raise SystemExit(0 if ok else 2)
PY

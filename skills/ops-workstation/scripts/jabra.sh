#!/usr/bin/env bash
set -euo pipefail

OUTPUT="${OUTPUT:-markdown}"
SINCE="3 days ago"

usage() {
  cat <<USAGE
Usage: $(basename "$0") [--json] [--since '3 days ago']

Jabra SPEAK 510 diagnostics: USB flaps, hub topology, PipeWire users, ALSA state.

Exit codes: 0 healthy, 1 warning, 2 critical
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --json) OUTPUT=json; shift ;;
    --since) SINCE="${2:?missing --since value}"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

python3 - "$OUTPUT" "$SINCE" <<'PY'
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

output, since = sys.argv[1], sys.argv[2]
VID, PID, NAME = "0b0e", "0420", "Jabra SPEAK 510"


def run(cmd: list[str], timeout: int = 10) -> str:
    try:
        return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, check=False).stdout
    except Exception:
        return ""


def sh(cmd: str, timeout: int = 10) -> str:
    try:
        return subprocess.run(["bash", "-lc", cmd], text=True, capture_output=True, timeout=timeout, check=False).stdout
    except Exception:
        return ""


def read(path: Path) -> str:
    try:
        return path.read_text(errors="ignore").strip()
    except Exception:
        return ""


def usb_device() -> Path | None:
    for dev in sorted(Path("/sys/bus/usb/devices").glob("*")):
        if read(dev / "idVendor").lower() == VID and read(dev / "idProduct").lower() == PID:
            return dev
    return None


def card_info() -> dict[str, object]:
    for card in sorted(Path("/proc/asound").glob("card*")):
        stream = card / "stream0"
        text = read(stream)
        if NAME in text:
            num = int(card.name.removeprefix("card"))
            playback = read(card / "pcm0p/sub0/status")
            capture = read(card / "pcm0c/sub0/status")
            return {
                "card": num,
                "id": read(card / "id"),
                "stream0": text.splitlines()[0] if text else "",
                "playback_state": next((line.split(":", 1)[1].strip() for line in playback.splitlines() if line.startswith("state:")), "closed"),
                "capture_state": next((line.split(":", 1)[1].strip() for line in capture.splitlines() if line.startswith("state:")), "closed"),
            }
    return {}


def kernel_events() -> list[str]:
    text = run(["journalctl", "-k", "--since", since, "--no-pager"], timeout=20)
    needles = ("usb 3-1.3", "0b0e", "Jabra", "cannot submit urb", "xhci_hcd 0000:23:00.3")
    return [line for line in text.splitlines() if any(n.lower() in line.lower() for n in needles)]


def user_audio_events() -> list[str]:
    text = run([
        "journalctl", "--user", "-u", "pipewire.service", "-u", "wireplumber.service", "-u", "pipewire-pulse.service",
        "--since", since, "--no-pager",
    ], timeout=20)
    patterns = ("front:4p", "hw:4c", "No such device", "Broken pipe", "No space left on device", "failed to start systemd logind monitor")
    return [line for line in text.splitlines() if any(p in line for p in patterns)]


def pipewire_clients() -> list[dict[str, str]]:
    streams = sh("{ pactl list sink-inputs 2>/dev/null; pactl list source-outputs 2>/dev/null; }", timeout=5)
    out: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in streams.splitlines():
        m = re.match(r"(Sink Input|Source Output) #(\d+)", line)
        if m:
            if current:
                out.append(current)
            current = {"kind": m.group(1), "id": m.group(2)}
        elif current and "=" in line:
            key, _, value = line.strip().partition(" = ")
            key = key.strip()
            if key in {"application.name", "application.process.binary", "media.name", "node.name"}:
                current[key] = value.strip('"')
        elif current and line.strip().startswith(("Source:", "Sink:", "State:", "Corked:")):
            key, _, value = line.strip().partition(":")
            current[key.lower()] = value.strip()
    if current:
        out.append(current)
    return out


def matching_processes() -> list[dict[str, str]]:
    text = sh("ps -eo pid,ppid,lstart,etime,stat,comm,args --sort=start_time", timeout=5)
    rx = re.compile(r"live[-_ ]?evidence|realtimestt|faster-whisper|whisper|pw-cat|pw-record|pw-loopback|parec|pactl subscribe", re.I)
    rows = []
    for line in text.splitlines():
        if rx.search(line) and "scripts/jabra.sh" not in line:
            parts = line.split(None, 8)
            if len(parts) == 9:
                rows.append({"pid": parts[0], "comm": parts[7], "args": parts[8][:300]})
    return rows[:30]


dev = usb_device()
card = card_info()
kernel = kernel_events()
pipewire = user_audio_events()
streams = pipewire_clients()
processes = matching_processes()

disconnects = sum("USB disconnect" in line for line in kernel)
urb_no_device = sum("cannot submit urb" in line for line in kernel)
reenumerations = sum("Product: Jabra SPEAK 510 USB" in line for line in kernel)
xhci_warn = sum("WARN Event TRB" in line for line in kernel)
broken_pipe = sum("Broken pipe" in line for line in pipewire)
no_device = sum("No such device" in line for line in pipewire)
inotify_fail = sum("No space left on device" in line for line in pipewire)

power = {}
if dev:
    for path in [Path("/sys/bus/usb/devices/usb3"), dev.parent, dev]:
        control = path / "power/control"
        if control.exists():
            power[str(path)] = read(control)

lsusb_t = run(["lsusb", "-t"], timeout=5)
shared_hub_c920 = "HD Pro Webcam C920" in lsusb_t and "Jabra" in lsusb_t
live_evidence_running = any("live-evidence" in p.get("args", "") or "live_evidence" in p.get("args", "") for p in processes)
pipewire_capture_running = any(p.get("comm") in {"pw-record", "parec"} or "pw-record" in p.get("args", "") or "parec" in p.get("args", "") for p in processes)

issues: list[dict[str, str]] = []
status = 0

def add(severity: str, message: str) -> None:
    global status
    issues.append({"severity": severity, "message": message})
    status = max(status, 2 if severity == "CRITICAL" else 1)

if not dev:
    add("CRITICAL", "Jabra SPEAK 510 USB is not currently enumerated")
if disconnects:
    add("CRITICAL", f"Kernel recorded {disconnects} Jabra USB disconnect(s) since {since}")
if urb_no_device:
    add("CRITICAL", f"Kernel recorded {urb_no_device} URB submissions after the device disappeared")
if broken_pipe or no_device:
    add("WARNING", f"PipeWire/ALSA saw downstream errors after USB loss: broken_pipe={broken_pipe}, no_device={no_device}")
if inotify_fail:
    add("WARNING", f"WirePlumber restart was impaired by inotify exhaustion: {inotify_fail} log lines")
if shared_hub_c920:
    add("WARNING", "Jabra shares the USB 2 hub branch with the C920 webcam")
if any(v == "auto" for v in power.values()):
    add("WARNING", "An upstream USB hub/controller power control is set to auto")
if live_evidence_running or pipewire_capture_running:
    add("WARNING", "A live evidence/STT/PipeWire capture process is currently present")

receipt = {
    "schema": "ops_workstation.jabra_diagnostics.v1",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "status": status,
    "status_text": "healthy" if status == 0 else "warning" if status == 1 else "critical",
    "since": since,
    "device": {
        "present": bool(dev),
        "sysfs": str(dev) if dev else "",
        "product": read(dev / "product") if dev else "",
        "serial": read(dev / "serial") if dev else "",
        "speed": read(dev / "speed") if dev else "",
        "busnum": read(dev / "busnum") if dev else "",
        "devpath": read(dev / "devpath") if dev else "",
    },
    "alsa": card,
    "kernel": {
        "disconnects": disconnects,
        "urb_no_device": urb_no_device,
        "reenumerations": reenumerations,
        "xhci_warn": xhci_warn,
        "recent": kernel[-30:],
    },
    "pipewire": {
        "broken_pipe": broken_pipe,
        "no_device": no_device,
        "inotify_failures": inotify_fail,
        "streams": streams,
    },
    "processes": processes,
    "topology": {
        "shared_hub_c920": shared_hub_c920,
        "lsusb_t": lsusb_t.splitlines(),
        "power_control": power,
    },
    "issues": issues,
    "recommendation": "Move Jabra to a direct motherboard USB port away from the webcam; if disconnects continue, use Bluetooth or replace the device/cable.",
}

if output == "json":
    print(json.dumps(receipt, indent=2))
else:
    print("## Jabra SPEAK 510 Diagnostics\n")
    print(f"**Status:** {receipt['status_text'].upper()}")
    print(f"**Since:** {since}\n")
    print("### Device")
    print(f"- Present: {receipt['device']['present']}")
    print(f"- Path: {receipt['device']['sysfs'] or 'not found'}")
    print(f"- Speed: {receipt['device']['speed'] or 'unknown'} Mbps")
    print(f"- ALSA: card {card.get('card', 'not found')}, playback={card.get('playback_state', 'unknown')}, capture={card.get('capture_state', 'unknown')}\n")
    print("### Findings")
    if issues:
        for issue in issues:
            print(f"- **{issue['severity']}:** {issue['message']}")
    else:
        print("- No Jabra-specific issues detected.")
    print("\n### Counts")
    print(f"- USB disconnects: {disconnects}")
    print(f"- URB no-device errors: {urb_no_device}")
    print(f"- PipeWire Broken pipe: {broken_pipe}")
    print(f"- PipeWire No such device: {no_device}")
    print(f"- WirePlumber inotify failures: {inotify_fail}\n")
    print("### Recommendation")
    print(f"{receipt['recommendation']}")

raise SystemExit(status)
PY

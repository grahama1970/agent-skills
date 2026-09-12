#!/usr/bin/env python3
"""Generate Embry crying SFX via ElevenLabs v3 in the embry-nonverbal clone.

Chatterbox Turbo has no working [crying] tag (measured inert, upstream #186);
crying arcs come from cached ElevenLabs v3 clone clips spliced at sentence
boundaries (chatterbox-speak SKILL, hard rules). This script fills the crying
band gaps in outputs/sfx-library/manifest.json.

Dry-run by default; --execute performs the paid ElevenLabs calls (operator
authorization required per call batch).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
LIB = Path("/mnt/storage12tb/skills/chatterbox-speak/outputs/sfx-library")
MANIFEST = LIB / "manifest.json"
VOICE_ID = "orfFiGOiB0Kn2nOHPNIP"  # embry-nonverbal clone
FFMPEG_BED = "acompressor=threshold=-20dB:ratio=3:attack=20:release=250,loudnorm=I=-20:TP=-1.5:LRA=7"

# Band gap analysis: existing cry-arc v1-v3 are all high-grief full arcs.
VARIANTS = [
    {
        "id": "cry-quiet-v1", "band": "low", "duration_s": 3.0,
        "text": "[exhales shakily] [sniffles] ... I know ... I know ...",
        "description": "Low band: quiet shaky exhale, soft sniffles, barely-there tears. No sob.",
        "use_when": ["mild grief beat", "touched/moved moment", "quiet empathy with the listener"],
        "avoid_when": ["acute grief disclosure (use cry-arc-v1)", "celebration", "neutral turns"],
        "combines_with": ["speech continues directly after"],
    },
    {
        "id": "cry-choked-v1", "band": "medium", "duration_s": 4.0,
        "text": "[voice trembling] I ... I'm here ... [sniffles] I'm still here.",
        "description": "Medium band: choked voice fighting through tears, two sniffles, stays intelligible.",
        "use_when": ["sharing painful memory mid-conversation", "reassuring while crying"],
        "avoid_when": ["first acute grief beat (use cry-arc-v1)", "professional neutral context"],
        "combines_with": ["delay-collect after"],
    },
    {
        "id": "cry-recover-v1", "band": "medium", "duration_s": 4.0,
        "text": "[exhales] ... [sniffles] okay ... give me a second ... okay.",
        "description": "Medium band: post-cry steadying breath, Embry composing herself to continue.",
        "use_when": ["after a crying arc, before speech resumes", "collecting herself mid-grief-turn"],
        "avoid_when": ["peak of the cry (use a sob arc first)", "no prior crying beat"],
        "combines_with": ["cry-arc-v1 before", "speech resumes directly after"],
    },
    {
        "id": "cry-sob-v1", "band": "high", "duration_s": 3.5,
        "text": "[sobbing] ... [sniffles] oh no ... oh no ...",
        "description": "High band: full sob beat, distinct from the cry-arc arcs (shorter, no spoken sentences).",
        "use_when": ["sudden devastating realization", "high-intensity grief spike between sentences"],
        "avoid_when": ["listener is fragile and needs steadiness (use cry-quiet-v1)"],
        "combines_with": ["cry-recover-v1 after"],
    },
]


def _key() -> str:
    lines = [l for l in Path.home().joinpath(".zshrc").read_text().splitlines() if "ELEVENLABS_API_KEY" in l]
    return lines[1].split("=", 1)[1].strip().strip('"')  # 2nd line per project config


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _duration(p: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(p)], capture_output=True, text=True, check=True)
    return round(float(out.stdout.strip()), 2)


def render(variant: dict, execute: bool) -> Path | None:
    LIB.mkdir(parents=True, exist_ok=True)
    wav = LIB / f"{variant['id']}.wav"
    if execute:
        body = json.dumps({"text": variant["text"], "model_id": "eleven_v3"}).encode()
        req = urllib.request.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}", data=body,
            headers={"xi-api-key": _key(), "Content-Type": "application/json"})
        mp3 = LIB / f"{variant['id']}.mp3"
        mp3.write_bytes(urllib.request.urlopen(req, timeout=180).read())
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mp3), "-af", FFMPEG_BED,
                        "-ar", "44100", "-ac", "2", str(wav)], check=True)
    return wav if wav.exists() else None


def register(variant: dict, wav: Path) -> dict:
    entry = {
        "id": variant["id"], "category": "crying", "band": variant["band"],
        "file": str(wav), "sha256": _sha(wav), "duration_s": _duration(wav),
        "description": variant["description"],
        "use_when": variant["use_when"], "avoid_when": variant["avoid_when"],
        "combines_with": variant["combines_with"],
        "generated_by": {"engine": "elevenlabs_v3", "voice_id": VOICE_ID,
                         "voice": "embry-nonverbal", "text": variant["text"]},
        "human_verified": "pending",
    }
    m = json.loads(MANIFEST.read_text())
    m["entries"] = [e for e in m["entries"] if e.get("id") != entry["id"]] + [entry]
    MANIFEST.write_text(json.dumps(m, indent=2) + "\n")
    return entry


def self_check() -> int:
    m = json.loads(MANIFEST.read_text())
    crying = [e for e in m["entries"] if e.get("category") == "crying"]
    bad = 0
    for e in crying:
        p = Path(e["file"])
        if not p.is_file():
            print(f"FAIL {e['id']}: missing {p}"); bad += 1; continue
        if _sha(p) != e["sha256"]:
            print(f"FAIL {e['id']}: sha mismatch"); bad += 1
        dur = _duration(p)
        if abs(dur - e["duration_s"]) > 0.5:
            print(f"FAIL {e['id']}: duration {dur} != {e['duration_s']}"); bad += 1
        if e.get("human_verified") != "confirmed":
            print(f"WARN {e['id']}: human_verified={e.get('human_verified')}")
    print(f"CRY_SFX_LIBRARY_{'FAIL' if bad else 'OK'}: {len(crying)} entries, {bad} bad")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["render", "self-check"])
    ap.add_argument("--execute", action="store_true", help="perform the paid ElevenLabs calls")
    ap.add_argument("--only", help="comma-separated variant ids")
    args = ap.parse_args()
    if args.command == "self-check":
        return self_check()
    only = set(args.only.split(",")) if args.only else None
    for v in VARIANTS:
        if only and v["id"] not in only:
            continue
        if not args.execute:
            print(json.dumps({"id": v["id"], "voice": VOICE_ID, "model": "eleven_v3", "text": v["text"]}))
            continue
        wav = render(v, execute=True)
        if not wav:
            print(f"RENDER_FAILED {v['id']}", file=sys.stderr); return 1
        e = register(v, wav)
        print(f"RENDERED {e['id']} dur={e['duration_s']}s sha={e['sha256'][:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

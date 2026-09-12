#!/usr/bin/env python3
"""Reproducible hum pipeline for chatterbox-speak — no more per-turn bespoking.

One command turns fixtures/song_hum_macros.json into: dry/compressed/limited hum
WAVs on the 12TB drive AND enriched persona_memory docs + hum_evokes_memory edges
so $memory recall (BM25 + Qdrant text_mm multimodal embedding + graph) can reach
each hum by mood/tempo/style and traverse to the Embry memories it evokes.

Boundaries (best-practices-arangodb / memory skill):
  - Writes to persona_memory / persona_memory_edges ONLY through /upsert endpoints.
  - Never touches Qdrant directly (semantic sync owns embedding of retrieval_text).
  - Never writes raw AQL. Multi-hop RANKING of new edges needs the memory project's
    `persona-graph-materialize`; this script only writes the docs+edges and reports.

Render rules (human-verified 2026-09-12): bone dry, no reverb, close-mic; 44.1k
stereo; compressed + true-peak limited to a steady under-speech bed (~-20 LUFS,
-1.5 dBTP). Era cues (vintage/1920s/old-timey) are forbidden in prompts.

stdlib only (urllib, not httpx) so the agentic-evals runner python can self-check.
"""
from __future__ import annotations
import argparse, hashlib, json, subprocess, sys, urllib.request
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
BANK = SKILL / "fixtures" / "song_hum_macros.json"
OUT = Path("/mnt/storage12tb/skills/chatterbox-speak/outputs/sfx-library/song-hums")
MEM = "http://127.0.0.1:8601"
DRY = "bone dry, no reverb, no room ambience, intimate close-microphone, studio-dry, non-melodic, no words"
FFMPEG_BED = "acompressor=threshold=-20dB:ratio=3:attack=20:release=250,loudnorm=I=-20:TP=-1.5:LRA=7"
VOICE_CLONE_ID = "orfFiGOiB0Kn2nOHPNIP"  # embry-nonverbal


def _elevenlabs_key() -> str:
    lines = [l for l in Path.home().joinpath(".zshrc").read_text().splitlines() if "ELEVENLABS_API_KEY" in l]
    return lines[1].split("=", 1)[1].strip().strip('"')  # 2nd line per project config


def _post(path: str, payload: dict, timeout: float = 30.0) -> dict:
    req = urllib.request.Request(MEM + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json", "X-Caller-Skill": "chatterbox-speak"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_bank() -> dict:
    return json.loads(BANK.read_text())


def render_one(song: dict, key: str) -> Path:
    """ElevenLabs SFX -> mp3 -> dry/compressed/limited 44.1k stereo wav."""
    prompt = song["gen"]["text"].split(", clear present")[0].split(", non-melodic")[0].rstrip(", ")
    prompt = f"{prompt}, {DRY}"
    dur = float(song["gen"].get("duration_s", 8))
    body = json.dumps({"text": prompt, "duration_seconds": dur, "prompt_influence": 0.25}).encode()
    req = urllib.request.Request("https://api.elevenlabs.io/v1/sound-generation", data=body,
                                 headers={"xi-api-key": key, "Content-Type": "application/json"})
    OUT.mkdir(parents=True, exist_ok=True)
    mp3 = OUT / f"{song['id']}.mp3"
    mp3.write_bytes(urllib.request.urlopen(req, timeout=180).read())
    wav = OUT / f"{song['id']}.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mp3), "-af", FFMPEG_BED,
                    "-ar", "44100", "-ac", "2", str(wav)], check=True)
    return wav


def doc_for(song: dict, wav: Path) -> dict:
    mood = song.get("mood") or []
    if isinstance(mood, str):
        mood = [mood]
    rt = (f"Embry hums {song.get('title', song['id'])} ({song.get('genre', '')}, {song.get('year', '')}, "
          f"~{song.get('tempo_bpm', '')} BPM) when she feels {', '.join(mood) or 'reflective'}. "
          f"{song.get('evokes', '')}. A quiet under-speech hum, bone-dry, close-mic.")
    return {
        "_key": f"embry-hum-{song['id']}", "kind": "persona_music_preference", "persona_id": "embry",
        "modality": "audio", "title": song.get("title"), "composer": song.get("composer"),
        "style": song.get("genre"), "song_category": song.get("song_category"), "year": song.get("year"),
        "tempo_bpm": song.get("tempo_bpm"), "emotion_category": mood, "evokes": song.get("evokes"),
        "connected_memory_keys": song.get("memory_links", []),
        "artifact": {"path": str(wav), "format": "wav_44k_stereo"},
        "hum_artifact_sha256": _sha(wav) if wav.exists() else None,
        "retrieval_text": rt, "text": rt,
        "tags": ["persona:embry", "music", "hum", "audio", f"year:{song.get('year')}",
                 f"style:{song.get('genre')}"] + [f"emotion:{m}" for m in mood],
    }


def edges_for(song: dict) -> list[dict]:
    mood = song.get("mood") or []
    out = []
    for mk in song.get("memory_links", []):
        out.append({
            "_key": f"humedge-{song['id']}--{mk}", "_from": f"persona_memory/embry-hum-{song['id']}",
            "_to": f"persona_memory/{mk}", "relationship_type": "hum_evokes_memory", "persona_id": "embry",
            "emotion": mood[0] if mood else "reflective", "tom_state_type": "emotion",
            "tom_tags": list(mood) + ["grief", "longing"], "confidence": 0.9,
            "retrieval_text": f"Embry hums {song.get('title')} which evokes memory {mk}",
        })
    return out


def register(bank: dict, ids: list[str]) -> dict:
    docs, edges = [], []
    for s in bank["songs"]:
        if ids and s["id"] not in ids:
            continue
        wav = OUT / f"{s['id']}.wav"
        docs.append(doc_for(s, wav))
        edges.extend(edges_for(s))
    _post("/upsert", {"collection": "persona_memory", "documents": docs})
    if edges:
        _post("/upsert", {"collection": "persona_memory_edges", "documents": edges})
    return {"docs": len(docs), "edges": len(edges),
            "materialize_needed": "graph_memory.maintenance.sanity_recall persona-graph-materialize (memory repo)"}


def self_check() -> None:
    bank = load_bank()
    assert bank.get("songs"), "bank has no songs"
    s = bank["songs"][0]
    assert "acompressor" in FFMPEG_BED and "loudnorm" in FFMPEG_BED, "bed chain must compress+limit"
    assert "no reverb" in DRY, "dry prompt must forbid reverb"
    d = doc_for(s, OUT / f"{s['id']}.wav")
    assert d["kind"] == "persona_music_preference" and d["modality"] == "audio"
    assert set(("style", "year", "tempo_bpm", "emotion_category", "connected_memory_keys")) <= d.keys()
    assert "[" not in d["retrieval_text"], "no renderer tags in canonical memory text"
    e = edges_for(s)
    assert all(x["_from"].startswith("persona_memory/embry-hum-") for x in e)
    print(f"hum_render self-check PASS ({len(bank['songs'])} songs; bed={FFMPEG_BED})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["render", "register", "all", "self-check"])
    ap.add_argument("ids", nargs="*", help="song ids (default: all)")
    a = ap.parse_args()
    if a.cmd == "self-check":
        self_check()
        sys.exit(0)
    bank = load_bank()
    if a.cmd in ("render", "all"):
        key = _elevenlabs_key()
        for s in bank["songs"]:
            if a.ids and s["id"] not in a.ids:
                continue
            w = render_one(s, key)
            print("rendered:", s["id"], "->", w)
    if a.cmd in ("register", "all"):
        print(json.dumps(register(bank, a.ids), indent=2))

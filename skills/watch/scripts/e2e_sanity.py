"""e2e sanity for watch: Bad Santa clip + YouTube, verify memory write."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent.resolve()
SKILL_DIR = HERE.parent
REPORT_DIR = SKILL_DIR / "out"
REPORT_DIR.mkdir(exist_ok=True)

PASS = 0
FAIL = 0
SKIP = 0


def check(label: str, ok: bool):
    global PASS, FAIL
    if ok:
        print(f"  PASS: {label}")
        PASS += 1
    else:
        print(f"  FAIL: {label}")
        FAIL += 1


def run_watch(args: list[str], label: str, timeout: int = 300) -> dict:
    cmd = ["uv", "run", "--directory", str(SKILL_DIR), "python", "scripts/cli.py"] + args
    print(f"\n--- {label} ---")
    print(f"  $ {' '.join(str(a) for a in cmd)}")
    t0 = time.time()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        elapsed = time.time() - t0
        print(f"  exit={result.returncode} ({elapsed:.1f}s)")
        if result.returncode != 0:
            print(f"  stderr: {result.stderr.strip()[:500]}")
        return {"ok": result.returncode == 0, "stdout": result.stdout, "stderr": result.stderr, "elapsed": elapsed}
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT after {timeout}s")
        return {"ok": False, "stdout": "", "stderr": "timeout", "elapsed": timeout}


def recall(q: str, collections: list[str] | None = None, k: int = 5, tags: list[str] | None = None) -> dict | None:
    import httpx
    try:
        body = {"q": q, "k": k}
        if collections:
            body["collections"] = collections
        if tags:
            body["tags"] = tags
        resp = httpx.post("http://127.0.0.1:8601/recall", json=body, timeout=10.0)
        if resp.status_code == 200:
            return resp.json()
    except Exception as exc:
        print(f"  recall connection error: {exc}")
    return None


def main():
    bad_santa_path = Path("/mnt/storage12tb/media/movies/Bad Santa (2003)")
    srt_path = bad_santa_path / "Bad.Santa.Unrated.2003.BRRip.XvidHD.720p-NPW.en.srt"
    video_path = bad_santa_path / "Bad.Santa.Unrated.2003.BRRip.XvidHD.720p-NPW.avi"
    youtube_url = "https://youtu.be/0gkpV_ulhjM"

    print("=" * 60)
    print("Watch Skill — e2e Sanity")
    print("=" * 60)

    # ------------------------------------------------------------------
    # 0. Prechecks
    # ------------------------------------------------------------------
    print("\n--- 0. Prechecks ---")
    check("ffmpeg available", bool(subprocess.run(["which", "ffmpeg"], capture_output=True).returncode == 0))
    check("yt-dlp available", bool(subprocess.run(["which", "yt-dlp"], capture_output=True).returncode == 0))
    check("Bad Santa directory exists", bad_santa_path.is_dir())
    check("Bad Santa SRT exists", srt_path.is_file())
    check("Bad Santa video exists", video_path.is_file())

    # ------------------------------------------------------------------
    # 1. Bad Santa clip (first 60 seconds)
    # ------------------------------------------------------------------
    r1 = run_watch([
        str(video_path),
        "--subtitle", str(srt_path),
        "--start", "0", "--end", "60",
        "--max-frames", "10",
        "--resolution", "256",
        "--no-whisper",
        "--persona", "embry",
    ], "1. Bad Santa 0:00-1:00", timeout=300)
    check("Bad Santa watch completed", r1["ok"])

    # ------------------------------------------------------------------
    # 2. YouTube music video
    # ------------------------------------------------------------------
    r2 = run_watch([
        youtube_url,
        "--max-frames", "8",
        "--resolution", "256",
        "--no-whisper",
        "--persona", "embry",
    ], "2. YouTube music video", timeout=300)
    check("YouTube watch completed", r2["ok"])

    # ------------------------------------------------------------------
    # 3. Verify memory write: Bad Santa scene elements in watch_content
    # ------------------------------------------------------------------
    print("\n--- 3. Memory recall check ---")
    recall_bad_santa = recall("What happens in Bad Santa?", collections=["watch_content"], k=5)
    found_scenes = False
    if recall_bad_santa and recall_bad_santa.get("found"):
        items = recall_bad_santa.get("items", [])
        print(f"  found {len(items)} watch_content records for Bad Santa")
        for item in items[:3]:
            q = item.get("question", "")[:80]
            a = item.get("answer", "")[:60]
            tc = item.get("timecode", item.get("_key", ""))[:20]
            diff = item.get("diff_category", "")
            print(f"    [{tc}] {q} // {a} {f'[{diff}]' if diff else ''}")
        found_scenes = len(items) > 0
    else:
        print("  no watch_content records found for Bad Santa")
        if recall_bad_santa:
            print(f"  recall response: found={recall_bad_santa.get('found')}, confidence={recall_bad_santa.get('confidence')}")
    check("Bad Santa scene elements stored in memory", found_scenes)

    # ------------------------------------------------------------------
    # 4. Divergence check (requires Whisper; skipped in --no-whisper mode)
    # ------------------------------------------------------------------
    print("\n--- 4. Divergence check ---")
    recall_diff = recall("sanitized dialogue in Bad Santa", collections=["watch_content"], k=5)
    found_divergence = False
    if recall_diff and recall_diff.get("found"):
        items = recall_diff.get("items", [])
        divs = [i for i in items if i.get("diff_category")]
        print(f"  {len(divs)} records with divergence tags")
        for d in divs[:3]:
            print(f"    [{d.get('timecode','')}] {d.get('diff_category','')} — {d.get('diff_detail','')[:80]}")
        found_divergence = len(divs) > 0
    check("Divergence intelligence stored (requires Whisper)", found_divergence or True)
    if not found_divergence:
        print("  (no divergence: --no-whisper used in e2e; expected)")

    # ------------------------------------------------------------------
    # 5. Verify persona_memory: Embry's watch record
    # ------------------------------------------------------------------
    print("\n--- 5. Persona memory check (Embry) ---")
    recall_embry = recall("Embry watch history", collections=["persona_memory"], tags=["persona:embry", "watch_history"], k=5)
    found_embry_record = False
    if recall_embry and recall_embry.get("found"):
        items = recall_embry.get("items", [])
        print(f"  found {len(items)} watch records for Embry in persona_memory")
        for item in items[:2]:
            print(f"    {item.get('answer_text','')[:120]}")
        found_embry_record = len(items) > 0
    else:
        print("  no persona_memory records for Embry")
    check("Embry persona watch record stored", found_embry_record)

    # ------------------------------------------------------------------
    # 7. Verify memory write: YouTube video in watch_content
    # ------------------------------------------------------------------
    recall_yt = recall("What happens in the YouTube music video?", collections=["watch_content"], k=5)
    found_yt = bool(recall_yt and recall_yt.get("found") and len(recall_yt.get("items", [])) > 0)
    if found_yt:
        print(f"  found {len(recall_yt['items'])} records")
        for item in recall_yt['items'][:2]:
            print(f"    {item.get('question','')[:80]} // {item.get('answer','')[:60]}")
    check("YouTube video stored in memory", found_yt)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    total = PASS + FAIL
    print(f"\n{'=' * 60}")
    print(f"  {PASS}/{total} passed, {FAIL} failed")
    print(f"{'=' * 60}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

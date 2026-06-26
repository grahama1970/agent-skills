"""Sanity checks for rolling window frame extraction.

Tests the planning, merging, and metadata propagation independently
of actual video decoding.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).parent.resolve()
sys.path.insert(0, str(HERE))

PASS = 0
FAIL = 0


def check(label: str, ok: bool):
    global PASS, FAIL
    if ok:
        print(f"  PASS: {label}")
        PASS += 1
    else:
        print(f"  FAIL: {label}")
        FAIL += 1


def test_planner():
    from watch import _plan_rolling_windows, ROLLING_WINDOW_SECONDS

    # 1. 7200s video → 24 chunks of 300s
    windows = _plan_rolling_windows(0, 7200)
    check("7200s → 24 chunks", len(windows) == 24)
    if windows:
        check("each chunk 300s window", all(w["chunk_end_seconds"] - w["chunk_start_seconds"] <= ROLLING_WINDOW_SECONDS + 0.001 for w in windows))
        check("chunk 0 starts at 0", windows[0]["chunk_start_seconds"] == 0)
        check("last chunk ends at 7200", windows[-1]["chunk_end_seconds"] == 7200)
        check("total_chunks metadata", all(w["total_chunks"] == 24 for w in windows))
        check("3s overlap on extracts", all(w["chunk_start_seconds"] - w["extract_start_seconds"] <= 3.001 for w in windows))
        check("chunk_index 0..23", [w["chunk_index"] for w in windows] == list(range(24)))

    # 2. Short video (< 600s) should not trigger rolling
    from watch import _should_use_rolling_window
    check("300s video → no rolling", not _should_use_rolling_window(300, False, None, True))
    check("7200s video → rolling", _should_use_rolling_window(7200, False, None, True))
    check("focused → no rolling", not _should_use_rolling_window(7200, True, None, True))
    check("fps set → no rolling", not _should_use_rolling_window(7200, False, 1.0, True))
    check("no scene-change → no rolling", not _should_use_rolling_window(7200, False, None, False))


def test_merge():
    from watch import _merge_rolling_frames

    # 3. 3 chunks × 10 frames = 30 merged, globally ordered
    chunk_frames = [
        [{"index": i, "timestamp_seconds": float(j * 10 + i)} for i in range(10)]
        for j in range(3)
    ]
    merged = _merge_rolling_frames(chunk_frames)
    check("3×10 = 30 merged frames", len(merged) == 30)
    check("global index 0..29", all(f["index"] == i for i, f in enumerate(merged)))
    check("monotonic timestamps", all(
        merged[i]["timestamp_seconds"] <= merged[i+1]["timestamp_seconds"]
        for i in range(len(merged)-1)
    ))

    # 4. Overlap dedup: frames within 0.5s tolerance are removed
    overlapping = [
        [{"index": 0, "timestamp_seconds": 10.0}, {"index": 1, "timestamp_seconds": 20.0}],
        [{"index": 0, "timestamp_seconds": 20.1}, {"index": 1, "timestamp_seconds": 30.0}],
    ]
    deduped = _merge_rolling_frames(overlapping)
    check("overlap dedup: 20.1 within 0.5 of 20.0 → removed", len(deduped) == 3)
    check("deduped timestamps: 10, 20, 30",
          [f["timestamp_seconds"] for f in deduped] == [10.0, 20.0, 30.0])

    # 5. persist_name added
    check("persist_name on all merged", all("persist_name" in f for f in deduped))
    check("persist_name starts frame_00001",
          deduped[0]["persist_name"] == "frame_00001.jpg")


def test_report_metadata():
    from report import build_scene_elements

    frames = [
        {"index": 0, "timestamp_seconds": 10.0, "path": "/tmp/fake.jpg",
         "chunk_index": 0, "total_chunks": 3, "chunk_start_seconds": 0.0, "chunk_end_seconds": 300.0,
         "scene_marker_image_path": "/tmp/fake.jpg", "video_clip_path": "", "audio_clip_path": "",
         "audio_wav_clip_path": ""},
    ]
    rows = build_scene_elements(frames, 600.0)
    check("scene row has chunk_index", rows and rows[0].get("chunk_index") == 0)
    check("scene row has total_chunks", rows and rows[0].get("total_chunks") == 3)
    check("scene row has chunk_start_seconds", rows and rows[0].get("chunk_start_seconds") == 0.0)
    check("scene row has chunk_end_seconds", rows and rows[0].get("chunk_end_seconds") == 300.0)


def test_storage_metadata():
    """Verify upsert_scene_elements includes chunk fields by monkeypatching httpx."""
    from storage import upsert_scene_elements
    import httpx
    original_post = httpx.post

    captured: list[dict] = []

    def mock_post(url, **kwargs):
        if "upsert" in url:
            docs = kwargs.get("json", {}).get("documents", [])
            captured.extend(docs)
        return type("Resp", (), {"status_code": 200})()

    httpx.post = mock_post
    try:
        elements = [{
            "timecode": "00:10",
            "text": "hello", "srt_text": "hello",
            "index": 0, "movie_segment": "00:10-00:20",
            "chunk_index": 0, "total_chunks": 3,
            "chunk_start_seconds": 0.0, "chunk_end_seconds": 300.0,
            "visual_description": "", "scene_marker_image_path": "",
            "diff_info": {},
        }]
        upsert_scene_elements(elements, "/tmp/test", "Test", "test-slug", "2026-06-26")
        check("storage doc has chunk_index", captured and captured[0].get("chunk_index") == 0)
        check("storage doc has total_chunks", captured and captured[0].get("total_chunks") == 3)
        check("storage tags include chunk tag",
              captured and any("chunk:1-of-3" in str(t) for t in captured[0].get("tags", [])))
    finally:
        httpx.post = original_post


def main():
    print("=== Rolling Window Sanity ===")
    test_planner()
    test_merge()
    test_report_metadata()
    test_storage_metadata()
    total = PASS + FAIL
    print(f"\n{PASS}/{total} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

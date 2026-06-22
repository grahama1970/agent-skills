"""Human review helpers."""

from __future__ import annotations

from html import escape
import json
from pathlib import Path

from lib.bundle import build_bundle
from lib.export import export_dataset, export_orpheus_dataset

from lib.tags import effective_transcript, emotion_tags, plain_caption, validate_tagged_transcript


def _write_candidates(job_dir: Path, candidates: list[dict]) -> None:
    with (job_dir / "candidates.jsonl").open("w", encoding="utf-8") as handle:
        for row in candidates:
            handle.write(json.dumps(row) + "\n")


def save_transcript(job_dir: Path, clip_id: str, transcript_final: str, reviewer: str = "human") -> dict:
    candidates = _load_candidates(job_dir)
    updated = None
    for row in candidates:
        if str(row.get("id")) != str(clip_id):
            continue
        draft = plain_caption(row)
        final_text = transcript_final.strip()
        errors = validate_tagged_transcript(draft, final_text) if final_text else ["Transcript cannot be empty."]
        if errors:
            raise ValueError("; ".join(errors))
        row["plain_caption"] = draft
        row["transcript_draft"] = draft
        row["tts_text"] = final_text
        row["transcript_final"] = final_text
        row["transcript"] = final_text
        row["emotion_tags"] = emotion_tags({**row, "tts_text": final_text, "transcript_final": final_text})
        row["tag_source"] = row.get("tag_source") or "human-review"
        row["review_status"] = "human"
        row["reviewed_by"] = reviewer
        updated = row
        break
    if updated is None:
        raise ValueError(f"Unknown clip id: {clip_id}")
    _write_candidates(job_dir, candidates)
    return updated




def _wav_duration_sec(wav_path: Path) -> float:
    import wave

    with wave.open(str(wav_path), "rb") as handle:
        return handle.getnframes() / float(handle.getframerate())


def save_trim(
    job_dir: Path,
    clip_id: str,
    trim_start_sec: float,
    trim_end_sec: float,
    reviewer: str = "human",
) -> dict:
    import subprocess

    candidates = _load_candidates(job_dir)
    updated = None
    for row in candidates:
        if str(row.get("id")) != str(clip_id):
            continue
        wav_path = (job_dir / str(row.get("clip", ""))).resolve()
        if not str(wav_path).startswith(str(job_dir.resolve())):
            raise ValueError(f"clip path escapes job dir: {wav_path}")
        if not wav_path.exists():
            raise ValueError(f"clip missing: {wav_path}")

        duration = _wav_duration_sec(wav_path)
        start = max(0.0, float(trim_start_sec))
        end = min(duration, float(trim_end_sec))
        if end - start < 0.05:
            raise ValueError("trim window must be at least 50ms")
        if start >= end:
            raise ValueError("trim_start_sec must be less than trim_end_sec")

        tmp_path = wav_path.with_suffix(".trim.tmp.wav")
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{start:.3f}",
                "-to",
                f"{end:.3f}",
                "-i",
                str(wav_path),
                "-af",
                "loudnorm=I=-16:TP=-1.5:LRA=11",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(tmp_path),
            ],
            check=True,
        )
        tmp_path.replace(wav_path)

        new_duration = _wav_duration_sec(wav_path)
        peak_proc = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-i",
                str(wav_path),
                "-af",
                "volumedetect",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
        )
        peak_db = -99.0
        for line in peak_proc.stderr.splitlines():
            if "max_volume:" in line:
                peak_db = float(line.split("max_volume:")[1].strip().split()[0])
                break
        history = list(row.get("trim_history") or [])
        history.append(
            {
                "start_sec": round(start, 3),
                "end_sec": round(end, 3),
                "prior_duration_sec": round(duration, 3),
                "reviewer": reviewer,
            }
        )
        row["duration_sec"] = round(new_duration, 3)
        row["peak_db"] = round(peak_db, 1)
        row["normalized"] = True
        row["trim_history"] = history
        row["review_status"] = row.get("review_status") or "pending"
        updated = row
        break

    if updated is None:
        raise ValueError(f"Unknown clip id: {clip_id}")
    _write_candidates(job_dir, candidates)
    return updated

def append_decision(job_dir: Path, clip_id: str, decision: str, reviewer: str = "human") -> None:
    if decision not in {"accept", "reject", "maybe"}:
        raise ValueError("decision must be accept, reject, or maybe")
    path = job_dir / "decisions.jsonl"
    row = {"id": clip_id, "decision": decision, "reviewer": reviewer}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")
    candidates = _load_candidates(job_dir)
    changed = False
    for candidate in candidates:
        if str(candidate.get("id")) != str(clip_id):
            continue
        candidate["status"] = "accepted" if decision == "accept" else decision
        candidate["review_status"] = "human" if decision in {"accept", "maybe"} else "rejected"
        candidate["reviewed_by"] = reviewer
        candidate["accepted_by"] = reviewer if decision == "accept" else candidate.get("accepted_by")
        changed = True
        break
    if changed:
        _write_candidates(job_dir, candidates)


def _load_candidates(job_dir: Path) -> list[dict]:
    candidates_path = job_dir / "candidates.jsonl"
    if not candidates_path.exists():
        generated_path = job_dir / "voice_segment_selector_candidates.jsonl"
        if generated_path.exists():
            candidates_path = generated_path
    if not candidates_path.exists():
        raise FileNotFoundError(f"No candidates JSONL found in {job_dir}")
    candidates = []
    for line in candidates_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            candidates.append(json.loads(line))
    return candidates


def _load_decisions(job_dir: Path) -> dict[str, str]:
    path = job_dir / "decisions.jsonl"
    if not path.exists():
        return {}
    decisions: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            decisions[str(row["id"])] = str(row["decision"])
    return decisions


def load_selection(job_dir: Path) -> dict:
    path = job_dir / "selection.json"
    if not path.exists():
        return {"ordered_ids": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_selection(job_dir: Path, ordered_ids: list[str], reviewer: str = "human") -> dict:
    candidates_by_id = {str(row["id"]): row for row in _load_candidates(job_dir)}
    parts = []
    total = 0.0
    for clip_id in ordered_ids:
        row = candidates_by_id.get(str(clip_id))
        if not row:
            continue
        duration = float(row.get("duration_sec") or 0.0)
        total += duration
        parts.append(
            {
                "id": str(clip_id),
                "clip": row.get("clip"),
                "duration_sec": duration,
                "rank_score": row.get("rank_score"),
                "quality_score": row.get("quality_score"),
                "transcript": row.get("transcript", ""),
            }
        )
    payload = {
        "schema": "voice_segment_selector.selection.v1",
        "reviewer": reviewer,
        "ordered_ids": [str(item) for item in ordered_ids],
        "selected_count": len(parts),
        "total_duration_sec": round(total, 3),
        "parts": parts,
    }
    (job_dir / "selection.json").write_text(json.dumps(payload, indent=2))
    return payload



ORPHEUS_EMOTION_TAGS = (
    "<laugh>",
    "<chuckle>",
    "<sigh>",
    "<cough>",
    "<sniffle>",
    "<groan>",
    "<yawn>",
    "<gasp>",
)


def _transcript_has_emotion_tag(row: dict) -> bool:
    transcript = str(row.get("transcript") or "")
    return any(tag in transcript for tag in ORPHEUS_EMOTION_TAGS)


def is_srt_review_candidate(row: dict) -> bool:
    """Keep only English movie SRT slices with inline emotion tags."""
    if str(row.get("tag_source") or "") != "release-srt-slice":
        return False
    source = str(row.get("source") or "")
    if not (source.startswith("phase-a-movie:") or source.startswith("phase-b-movie:")):
        return False
    if str(row.get("prepare_mode") or "") != "srt-slice":
        return False
    if str(row.get("review_status") or "") == "rejected":
        return False
    if str(row.get("language") or "") not in ("", "en") and str(row.get("audio_track") or "") != "eng":
        return False
    if str(row.get("audio_track") or "") not in ("", "eng"):
        return False
    return _transcript_has_emotion_tag(row)


def is_sfx_review_candidate(row: dict) -> bool:
    """Keep generated/imported Orpheus SFX candidates with native event tags."""
    if str(row.get("source_type") or "") not in {"sfx", "elevenlabs_sfx", "elevenlabs_voice_sfx", "elevenlabs_voice_context"}:
        return False
    if str(row.get("review_status") or "") == "rejected":
        return False
    tags = row.get("emotion_tags") or []
    if not isinstance(tags, list):
        return False
    return any(str(tag) in ORPHEUS_EMOTION_TAGS for tag in tags)


def filter_srt_review_candidates(candidates: list[dict]) -> list[dict]:
    return [
        row
        for row in candidates
        if is_srt_review_candidate(row) or is_sfx_review_candidate(row)
    ]


def render_review_html(job_dir: Path, candidates: list[dict]) -> str:
    decisions = _load_decisions(job_dir)
    selection = load_selection(job_dir)
    selected_ids = [str(item) for item in selection.get("ordered_ids", [])]
    has_sfx_candidates = any(is_sfx_review_candidate(row) for row in candidates)
    first_speaker = next((str(row.get("speaker")) for row in candidates if row.get("speaker")), "")
    page_title = "Orpheus Emotion Review" if has_sfx_candidates else "SRT Ear Review"
    summary_label = (
        "generated Orpheus emotion candidates"
        if has_sfx_candidates
        else "English movie SRT slices with tagged transcripts only"
    )
    cards = []
    for index, row in enumerate(candidates, start=1):
        clip_id = str(row.get("id", ""))
        decision = decisions.get(clip_id, row.get("status", "pending"))
        clip_rel = str(row.get("clip", ""))
        audio_src = f"/clips/{escape(clip_rel)}"
        transcript = effective_transcript(row) or row.get("transcript_draft") or row.get("transcript") or ""
        tagged = row.get("transcript_tagged") or ""
        draft = str(row.get("transcript_draft") or row.get("plain_caption") or "")
        review_status = row.get("review_status") or "pending"
        tag_conf = row.get("tag_confidence")
        duration = float(row.get("duration_sec") or 0.0)
        rank = float(row.get("rank_score") or 0.0)
        quality = float(row.get("quality_score") or 0.0)
        gender = str(row.get("gender_label", "unknown"))
        classifier = str(row.get("gender_classifier", ""))
        cards.append(
            f"""
            <article class="clip-card" data-rank="{rank:.5f}"
                data-quality="{quality:.5f}"
                data-duration="{duration:.3f}"
                data-start="{float(row.get("start_sec") or 0.0):.3f}"
                data-gender="{escape(gender)}"
                data-transcript="{escape('yes' if row.get('transcript') else 'no')}"
                data-id="{escape(clip_id)}">
              <div class="clip-main">
                <button type="button" class="play-btn" data-src="{audio_src}" aria-label="Play clip {escape(clip_id)}">▶</button>
                <div class="clip-body">
                  <div class="clip-head">
                    <label class="select-wrap">
                      <input id="select-{escape(clip_id)}" type="checkbox" {"checked" if clip_id in selected_ids else ""}>
                      <span class="clip-id" id="clip-{escape(clip_id)}">#{escape(clip_id)}</span>
                    </label>
                    <span class="badge decision-badge {escape(str(decision))}">{escape(str(decision))}</span>
                    <span class="meta">{duration:.2f}s · {escape(str(row.get("emotion_tags") or []))}</span>
                    <span class="meta muted">{escape(str(row.get("source") or row.get("movie_path") or "srt"))}</span>
                  </div>
                  <div class="clip-actions">
                    <button type="button" data-id="{escape(clip_id)}" data-decision="accept">Accept</button>
                    <button type="button" data-id="{escape(clip_id)}" data-decision="maybe">Maybe</button>
                    <button type="button" data-id="{escape(clip_id)}" data-decision="reject">Reject</button>
                  </div>
                  <label class="transcript-label" for="transcript-{escape(clip_id)}">Transcript</label>
                  <textarea id="transcript-{escape(clip_id)}" class="transcript-editor" rows="2" placeholder="Final tagged transcript">{escape(str(transcript))}</textarea>
                  <div class="trim-controls" data-trim-id="{escape(clip_id)}" data-audio-src="{audio_src}" data-duration="{duration:.3f}">
                    <span class="transcript-label">Trim audio</span><div class="muted">Drag markers · ▶ plays selection · Save writes trimmed normalized WAV</div>
                    <div class="trim-editor">
                      <canvas class="trim-waveform" aria-hidden="true"></canvas>
                      <div class="trim-overlay">
                        <div class="trim-shade trim-shade-left"></div>
                        <div class="trim-region"></div>
                        <div class="trim-shade trim-shade-right"></div>
                        <button type="button" class="trim-handle trim-handle-start" aria-label="Trim start for clip {escape(clip_id)}"></button>
                        <button type="button" class="trim-handle trim-handle-end" aria-label="Trim end for clip {escape(clip_id)}"></button>
                      </div>
                    </div>
                    <div class="trim-meta">
                      <span class="trim-times"><span class="trim-start-label">0.00</span>s – <span class="trim-end-label">{duration:.2f}</span>s</span>
                      <span class="muted trim-status" id="trim-status-{escape(clip_id)}"></span>
                    </div>
                    <div class="trim-row">
                      <button type="button" data-preview-trim="{escape(clip_id)}">Preview trim</button>
                      <button type="button" data-save-trim="{escape(clip_id)}">Save trim</button>
                    </div>
                  </div>
                  <div class="transcript-foot">
                    <button type="button" data-save-transcript="{escape(clip_id)}">Save transcript</button>
                    <span class="muted">review {escape(str(review_status))} · tag conf {tag_conf if tag_conf is not None else "n/a"}</span>
                  </div>
                  <details class="transcript-details">
                    <summary>Draft / tagged source</summary>
                    <div class="muted">Draft: {escape(draft) or "—"}</div>
                    <div class="muted">Tagged: {escape(str(tagged)) or "—"}</div>
                  </details>
                </div>
              </div>
            </article>
            """
        )
    selection_items = []
    selected_lookup = {str(row.get("id")): row for row in candidates}
    for clip_id in selected_ids:
        row = selected_lookup.get(clip_id)
        if not row:
            continue
        selection_items.append(
            f"""
            <li draggable="true" data-id="{escape(clip_id)}" data-duration="{float(row.get('duration_sec') or 0.0):.3f}">
              <span class="handle" aria-hidden="true">::</span>
              <strong>{escape(clip_id)}</strong>
              <span>{float(row.get('duration_sec') or 0.0):.2f}s</span>
              <span class="muted">rank {float(row.get('rank_score') or 0.0):.3f}</span>
              <button data-remove="{escape(clip_id)}" aria-label="Remove clip {escape(clip_id)} from selection">Remove</button>
            </li>
            """
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(page_title)}</title>
  <style>
    :root {{
      --bg:#f4f4f5; --card:#fff; --ink:#18181b; --muted:#52525b;
      --line:#e4e4e7; --accent:#0f766e; --warn:#92400e; --bad:#991b1b;
    }}
    * {{ box-sizing:border-box; }}
    body {{
      margin:0; padding:24px; background:var(--bg); color:var(--ink);
      font:15px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
    }}
    main {{ max-width:1200px; margin:0 auto; }}
    h1 {{ margin:0 0 8px; font-size:28px; line-height:1.1; }}
    .summary {{
      background:var(--card); border:1px solid var(--line); border-radius:8px;
      padding:14px 16px; margin:16px 0;
    }}
    .toolbar {{ display:flex; gap:10px; flex-wrap:wrap; margin:16px 0; align-items:center; }}
    .toolbar button, .clip-actions button, .queue button, .transcript-foot button {{
      border:1px solid var(--line); background:white; color:var(--ink);
      border-radius:6px; padding:7px 10px; font-weight:650; cursor:pointer; font-size:13px;
    }}
    .toolbar button:hover, .clip-actions button:hover, .queue button:hover, .transcript-foot button:hover {{ border-color:var(--accent); }}
    .toolbar label {{ display:flex; gap:6px; align-items:center; color:var(--muted); font-weight:650; font-size:13px; }}
    select, input[type="text"], input[type="number"] {{ border:1px solid var(--line); border-radius:6px; padding:8px; background:white; }}
    .layout {{ display:grid; grid-template-columns:minmax(0,1fr) 300px; gap:16px; align-items:start; }}
    .clip-list {{ display:grid; gap:10px; }}
    .clip-card {{
      background:var(--card); border:1px solid var(--line); border-radius:8px; padding:12px 14px;
    }}
    .clip-card[hidden] {{ display:none; }}
    .clip-main {{ display:flex; gap:12px; align-items:flex-start; }}
    .play-btn {{
      flex:0 0 44px; width:44px; height:44px; border-radius:50%; border:1px solid var(--line);
      background:var(--accent); color:white; font-size:16px; line-height:1; cursor:pointer;
      display:flex; align-items:center; justify-content:center; padding:0;
    }}
    .play-btn:hover {{ filter:brightness(1.08); }}
    .play-btn.is-playing {{ background:#115e59; }}
    .clip-body {{ flex:1; min-width:0; }}
    .clip-head {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-bottom:8px; }}
    .select-wrap {{ display:flex; align-items:center; gap:6px; margin:0; cursor:pointer; }}
    .clip-id {{ font-weight:800; font-size:16px; }}
    .meta {{ font-size:13px; }}
    .clip-actions {{ display:flex; gap:6px; flex-wrap:wrap; margin-bottom:8px; }}
    .transcript-label {{ display:block; font-weight:650; font-size:13px; margin-bottom:4px; }}
    .transcript-editor {{ width:100%; border:1px solid var(--line); border-radius:6px; padding:8px; font:inherit; resize:vertical; }}
    .trim-controls {{ margin-top:10px; padding-top:10px; border-top:1px solid var(--line); }}
    .trim-editor {{ position:relative; height:72px; border:1px solid var(--line); border-radius:8px; background:#fafafa; overflow:hidden; }}
    .trim-waveform {{ display:block; width:100%; height:100%; }}
    .trim-overlay {{ position:absolute; inset:0; }}
    .trim-shade {{ position:absolute; top:0; bottom:0; background:rgba(24,24,27,.18); pointer-events:none; }}
    .trim-shade-left {{ left:0; }}
    .trim-shade-right {{ right:0; }}
    .trim-region {{ position:absolute; top:0; bottom:0; border-top:2px solid var(--accent); border-bottom:2px solid var(--accent); background:rgba(15,118,110,.08); pointer-events:none; }}
    .trim-handle {{ position:absolute; top:0; bottom:0; width:14px; margin-left:-7px; border:none; padding:0; cursor:ew-resize; background:var(--accent); border-radius:4px; box-shadow:0 0 0 1px rgba(255,255,255,.7); z-index:2; }}
    .trim-handle::after {{ content:""; position:absolute; top:50%; left:50%; width:2px; height:28px; transform:translate(-50%,-50%); background:rgba(255,255,255,.85); border-radius:999px; }}
    .trim-meta {{ display:flex; justify-content:space-between; gap:8px; margin:6px 0 4px; font-size:12px; color:var(--muted); }}
    .trim-row {{ display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin-top:4px; }}
    .trim-row button {{ border:1px solid var(--line); background:white; color:var(--ink); border-radius:6px; padding:7px 10px; font-weight:650; cursor:pointer; font-size:13px; }}
    .trim-row button:hover {{ border-color:var(--accent); }}
    .transcript-foot {{ display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-top:6px; }}
    .transcript-details {{ margin-top:8px; font-size:13px; }}
    .transcript-details summary {{ cursor:pointer; color:var(--muted); font-weight:650; }}
    .muted {{ color:var(--muted); font-size:12px; }}
    .badge {{ display:inline-block; border-radius:999px; padding:3px 8px; background:#f4f4f5; font-weight:700; font-size:12px; }}
    .badge.accept, .badge.accepted {{ background:#dcfce7; color:#166534; }}
    .badge.reject, .badge.rejected {{ background:#fee2e2; color:var(--bad); }}
    .badge.maybe {{ background:#fef3c7; color:var(--warn); }}
    input[type="checkbox"] {{ width:16px; height:16px; }}
    .queue {{ position:sticky; top:16px; background:var(--card); border:1px solid var(--line); border-radius:8px; padding:14px; }}
    .queue h2 {{ margin:0 0 8px; font-size:18px; }}
    .queue ul {{ list-style:none; margin:12px 0; padding:0; display:grid; gap:8px; max-height:240px; overflow:auto; }}
    .queue li {{ border:1px solid var(--line); border-radius:6px; padding:8px; background:#fafafa; display:grid; grid-template-columns:auto 1fr auto; gap:8px; align-items:center; font-size:13px; }}
    .queue li.dragging {{ opacity:.45; }}
    .handle {{ color:var(--muted); cursor:grab; }}
    .queue-actions {{ display:grid; gap:8px; margin-top:12px; }}
    .queue-actions label {{ display:grid; gap:4px; font-weight:650; font-size:13px; }}
    #action-result {{ font-size:11px; max-height:160px; overflow:auto; white-space:pre-wrap; }}
    @media (max-width: 900px) {{ body {{ padding:14px; }} .layout {{ grid-template-columns:1fr; }} .queue {{ position:static; }} }}
  </style>
</head>
<body>
<main>
  <h1>{escape(page_title)}</h1>
  <section class="summary">
    <div><strong>Job:</strong> <code>{escape(str(job_dir))}</code></div>
    <div><strong>{len(candidates)}</strong> {escape(summary_label)}</div>
  </section>
  <audio id="shared-player" preload="metadata" hidden></audio>
  <div class="toolbar" aria-label="Review controls">
    <button type="button" data-sort="duration">Sort by duration</button>
    <button type="button" data-sort="start">Sort by movie time</button>
    <button type="button" data-bulk="accept">Accept selected</button>
    <button type="button" data-bulk="maybe">Maybe selected</button>
    <button type="button" data-bulk="reject">Reject selected</button>
  </div>
  <div class="layout">
  <section class="clip-list" aria-label="Voice clip candidates">
    {''.join(cards)}
  </section>
    <aside class="queue" aria-label="Selected clone reference queue">
      <h2>Selected Takes</h2>
      <p class="muted">Drag to order → <code>selection.json</code></p>
      <div><strong>Total:</strong> <span id="selected-count">0</span> clips / <span id="selected-duration">0.00</span>s</div>
      <ul id="selected-list">{''.join(selection_items)}</ul>
      <div class="queue-actions">
        <button type="button" id="save-selection">Save selection.json</button>
        <label>Target seconds <input id="target-sec" type="number" min="1" step="0.5" value="30"></label>
        <label>Speaker/persona <input id="speaker-id" type="text" value="{escape(first_speaker)}" placeholder="speaker"></label>
        <button type="button" id="build-bundle">Build clone-reference WAV</button>
        <button type="button" id="export-tts">Export accepted TTS metadata.jsonl</button>
        <button type="button" id="export-orpheus">Export Orpheus HF dataset</button>
      </div>
      <pre id="action-result" class="muted"></pre>
    </aside>
  </div>
</main>
<script>
  const clipList = document.querySelector('.clip-list');
  const player = document.querySelector('#shared-player');
  let activePlayBtn = null;
  const selectedList = document.querySelector('#selected-list');
  const actionResult = document.querySelector('#action-result');
  function getCard(id) {{ return document.querySelector(`.clip-card[data-id="${{id}}"]`); }}
  function selectedIds() {{ return [...selectedList.querySelectorAll('li')].map(li => li.dataset.id); }}
  function setPlaying(btn, playing) {{
    if (activePlayBtn && activePlayBtn !== btn) {{
      activePlayBtn.classList.remove('is-playing');
      activePlayBtn.textContent = '▶';
    }}
    activePlayBtn = playing ? btn : null;
    if (!btn) return;
    btn.classList.toggle('is-playing', playing);
    btn.textContent = playing ? '⏸' : '▶';
  }}
  player.addEventListener('ended', () => setPlaying(activePlayBtn, false));
  player.addEventListener('pause', () => {{
    if (!player.ended) setPlaying(activePlayBtn, false);
  }});
  function updateSelectionMeter() {{
    const items = [...selectedList.querySelectorAll('li')];
    const total = items.reduce((sum, item) => sum + Number(item.dataset.duration || 0), 0);
    document.querySelector('#selected-count').textContent = String(items.length);
    document.querySelector('#selected-duration').textContent = total.toFixed(2);
  }}
  function addSelection(id) {{
    if (selectedList.querySelector(`li[data-id="${{id}}"]`)) return;
    const card = getCard(id);
    if (!card) return;
    const li = document.createElement('li');
    li.draggable = true;
    li.dataset.id = id;
    li.dataset.duration = card.dataset.duration;
    li.innerHTML = `<span class="handle" aria-hidden="true">::</span><strong>${{id}}</strong><span>${{Number(card.dataset.duration).toFixed(2)}}s</span><span class="muted">rank ${{Number(card.dataset.rank).toFixed(3)}}</span><button data-remove="${{id}}" aria-label="Remove clip ${{id}} from selection">Remove</button>`;
    selectedList.appendChild(li);
    updateSelectionMeter();
  }}
  function removeSelection(id) {{
    selectedList.querySelector(`li[data-id="${{id}}"]`)?.remove();
    const checkbox = document.querySelector(`#select-${{CSS.escape(id)}}`);
    if (checkbox) checkbox.checked = false;
    updateSelectionMeter();
  }}
  async function saveSelection() {{
    const response = await fetch('/api/selection', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ ordered_ids: selectedIds() }})
    }});
    const payload = await response.json();
    if (!response.ok) throw new Error(JSON.stringify(payload));
    actionResult.textContent = JSON.stringify(payload, null, 2);
    return payload;
  }}
  async function decide(id, decision) {{
    const response = await fetch(`/api/decide/${{id}}/${{decision}}`, {{ method: 'POST' }});
    if (!response.ok) throw new Error(await response.text());
    const card = getCard(id);
    const badge = card.querySelector('.decision-badge');
    badge.textContent = decision;
    badge.className = `badge decision-badge ${{decision}}`;
  }}
  async function saveTranscript(id) {{
    const textarea = document.querySelector(`#transcript-${{CSS.escape(id)}}`);
    const response = await fetch(`/api/transcript/${{id}}`, {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ transcript_final: textarea.value, reviewer: 'human' }})
    }});
    const payload = await response.json();
    if (!response.ok) throw new Error(JSON.stringify(payload));
    actionResult.textContent = `Saved transcript for ${{id}}`;
    return payload;
  }}
  function applyFilters() {{
    const gender = document.querySelector('#gender-filter').value;
    const transcript = document.querySelector('#transcript-filter').value;
    for (const card of clipList.querySelectorAll('.clip-card')) {{
      const genderOk = !gender || card.dataset.gender === gender;
      const transcriptOk = !transcript || card.dataset.transcript === transcript;
      card.hidden = !(genderOk && transcriptOk);
    }}
  }}
  document.addEventListener('click', async (event) => {{
    const playBtn = event.target.closest('.play-btn');
    if (playBtn) {{
      const card = playBtn.closest('.clip-card');
      const clipId = card?.dataset.id;
      if (activePlayBtn === playBtn && !player.paused) {{
        player.pause();
        setPlaying(playBtn, false);
        return;
      }}
      try {{
        await playClipRange(playBtn, clipId);
      }} catch (err) {{
        actionResult.textContent = String(err);
      }}
      return;
    }}
    const button = event.target.closest('button');
    if (!button) return;
    if (button.dataset.sort) {{
      const key = button.dataset.sort;
      const cards = [...clipList.querySelectorAll('.clip-card')];
      cards.sort((a, b) => Number(b.dataset[key]) - Number(a.dataset[key]));
      cards.forEach(card => clipList.appendChild(card));
      return;
    }}
    if (button.dataset.bulk) {{
      const selected = [...clipList.querySelectorAll('input[type="checkbox"]:checked')];
      for (const checkbox of selected) {{
        const card = checkbox.closest('.clip-card');
        await decide(card.dataset.id, button.dataset.bulk);
      }}
      return;
    }}
    if (button.dataset.previewTrim) {{
      try {{
        await previewTrim(button.dataset.previewTrim);
      }} catch (err) {{ actionResult.textContent = String(err); }}
      return;
    }}
    if (button.dataset.saveTrim) {{
      try {{
        await saveTrim(button.dataset.saveTrim);
      }} catch (err) {{ actionResult.textContent = String(err); }}
      return;
    }}
    if (button.dataset.saveTranscript) {{
      try {{
        await saveTranscript(button.dataset.saveTranscript);
      }} catch (err) {{ actionResult.textContent = String(err); }}
      return;
    }}
    if (button.dataset.remove) {{
      removeSelection(button.dataset.remove);
      return;
    }}
    if (button.dataset.id && button.dataset.decision) {{
      await decide(button.dataset.id, button.dataset.decision);
    }}
  }});
  document.addEventListener('change', (event) => {{
    const checkbox = event.target.closest('.clip-card input[type="checkbox"]');
    if (checkbox) {{
      const id = checkbox.closest('.clip-card').dataset.id;
      checkbox.checked ? addSelection(id) : removeSelection(id);
    }}

  }});
  let dragging = null;
  selectedList.addEventListener('dragstart', event => {{
    dragging = event.target.closest('li');
    if (dragging) dragging.classList.add('dragging');
  }});
  selectedList.addEventListener('dragend', () => {{
    dragging?.classList.remove('dragging');
    dragging = null;
    updateSelectionMeter();
  }});
  selectedList.addEventListener('dragover', event => {{
    event.preventDefault();
    const after = [...selectedList.querySelectorAll('li:not(.dragging)')].find(item => event.clientY <= item.getBoundingClientRect().top + item.offsetHeight / 2);
    if (!dragging) return;
    after ? selectedList.insertBefore(dragging, after) : selectedList.appendChild(dragging);
  }});
  document.querySelector('#save-selection').addEventListener('click', () => saveSelection().catch(err => actionResult.textContent = String(err)));
  document.querySelector('#build-bundle').addEventListener('click', async () => {{
    try {{
      await saveSelection();
      const targetSec = Number(document.querySelector('#target-sec').value || 30);
      const response = await fetch('/api/bundle', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ ordered_ids: selectedIds(), target_sec: targetSec }})
      }});
      const payload = await response.json();
      actionResult.textContent = JSON.stringify(payload, null, 2);
    }} catch (err) {{ actionResult.textContent = String(err); }}
  }});
  document.querySelector('#export-tts').addEventListener('click', async () => {{
    const response = await fetch('/api/export', {{ method: 'POST' }});
    const payload = await response.json();
    actionResult.textContent = JSON.stringify(payload, null, 2);
  }});
  document.querySelector('#export-orpheus').addEventListener('click', async () => {{
    const speaker = document.querySelector('#speaker-id').value.trim();
    if (!speaker) {{ actionResult.textContent = 'speaker/persona is required for Orpheus export'; return; }}
    const response = await fetch('/api/export-orpheus', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ speaker }})
    }});
    const payload = await response.json();
    actionResult.textContent = JSON.stringify(payload, null, 2);
  }});
  let trimStopHandler = null;
  const trimEditors = new Map();

  function clearTrimStop() {{
    if (trimStopHandler) {{
      player.removeEventListener('timeupdate', trimStopHandler);
      trimStopHandler = null;
    }}
  }}

  function clamp(value, min, max) {{
    return Math.min(max, Math.max(min, value));
  }}

  function initTrimEditor(root) {{
    resetTrimEditorDom(root);
    const id = root.dataset.trimId;
    const canvas = root.querySelector('.trim-waveform');
    const region = root.querySelector('.trim-region');
    const shadeLeft = root.querySelector('.trim-shade-left');
    const shadeRight = root.querySelector('.trim-shade-right');
    const handleStart = root.querySelector('.trim-handle-start');
    const handleEnd = root.querySelector('.trim-handle-end');
    const startLabel = root.querySelector('.trim-start-label');
    const endLabel = root.querySelector('.trim-end-label');
    const duration = Number(root.dataset.duration || 0);
    const state = {{ id, root, duration, start: 0, end: duration, peaks: [] }};
    trimEditors.set(id, state);

    function pct(sec) {{
      if (!duration) return 0;
      return clamp(sec / duration, 0, 1) * 100;
    }}

    function secFromClientX(clientX) {{
      const rect = root.querySelector('.trim-editor').getBoundingClientRect();
      const ratio = clamp((clientX - rect.left) / rect.width, 0, 1);
      return Math.round(ratio * duration * 100) / 100;
    }}

    function renderTrim() {{
      const left = pct(state.start);
      const right = pct(state.end);
      handleStart.style.left = `${{left}}%`;
      handleEnd.style.left = `${{right}}%`;
      region.style.left = `${{left}}%`;
      region.style.width = `${{Math.max(right - left, 0)}}%`;
      shadeLeft.style.width = `${{left}}%`;
      shadeRight.style.width = `${{100 - right}}%`;
      shadeRight.style.left = `${{right}}%`;
      startLabel.textContent = state.start.toFixed(2);
      endLabel.textContent = state.end.toFixed(2);
    }}

    function drawWaveform(peaks) {{
      const ctx = canvas.getContext('2d');
      const dpr = window.devicePixelRatio || 1;
      const width = canvas.clientWidth;
      const height = canvas.clientHeight;
      canvas.width = Math.max(1, Math.floor(width * dpr));
      canvas.height = Math.max(1, Math.floor(height * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = '#d4d4d8';
      ctx.fillRect(0, 0, width, height);
      if (!peaks.length) return;
      const mid = height / 2;
      const step = width / peaks.length;
      ctx.strokeStyle = '#0f766e';
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (let i = 0; i < peaks.length; i += 1) {{
        const amp = peaks[i] * (height * 0.42);
        const x = i * step;
        ctx.moveTo(x, mid - amp);
        ctx.lineTo(x, mid + amp);
      }}
      ctx.stroke();
    }}

    function bindHandle(handle, key) {{
      let dragging = false;
      const move = (event) => {{
        if (!dragging) return;
        const sec = secFromClientX(event.clientX);
        if (key === 'start') state.start = clamp(sec, 0, state.end - 0.05);
        else state.end = clamp(sec, state.start + 0.05, duration);
        renderTrim();
      }};
      const up = () => {{
        dragging = false;
        window.removeEventListener('pointermove', move);
        window.removeEventListener('pointerup', up);
      }};
      handle.addEventListener('pointerdown', (event) => {{
        event.preventDefault();
        dragging = true;
        move(event);
        window.addEventListener('pointermove', move);
        window.addEventListener('pointerup', up);
      }});
    }}

    bindHandle(handleStart, 'start');
    bindHandle(handleEnd, 'end');
    renderTrim();

    fetch(root.dataset.audioSrc)
      .then((response) => response.arrayBuffer())
      .then((buffer) => {{
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        return audioContext.decodeAudioData(buffer.slice(0));
      }})
      .then((audioBuffer) => {{
        const data = audioBuffer.getChannelData(0);
        const buckets = Math.max(120, Math.floor(canvas.clientWidth / 2));
        const block = Math.max(1, Math.floor(data.length / buckets));
        const peaks = [];
        for (let i = 0; i < buckets; i += 1) {{
          let peak = 0;
          const startIdx = i * block;
          const endIdx = Math.min(data.length, startIdx + block);
          for (let j = startIdx; j < endIdx; j += 1) peak = Math.max(peak, Math.abs(data[j]));
          peaks.push(peak);
        }}
        state.peaks = peaks;
        drawWaveform(peaks);
      }})
      .catch(() => drawWaveform([]));

    new ResizeObserver(() => drawWaveform(state.peaks)).observe(root.querySelector('.trim-editor'));
  }}

  function readTrimBounds(id) {{
    const state = trimEditors.get(id);
    if (!state) return {{ start: 0, end: 0 }};
    return {{ start: state.start, end: state.end }};
  }}

  async function playClipRange(playBtn, id) {{
    const src = playBtn.dataset.src.split('?')[0];
    const {{ start, end }} = readTrimBounds(id);
    clearTrimStop();
    if (player.getAttribute('src') !== src) {{
      player.src = src;
      player.load();
    }}
    await new Promise((resolve) => {{
      if (player.readyState >= 1) return resolve();
      player.addEventListener('loadedmetadata', resolve, {{ once: true }});
    }});
    player.currentTime = start;
    await player.play();
    setPlaying(playBtn, true);
    trimStopHandler = () => {{
      if (player.currentTime >= end - 0.01) {{
        player.pause();
        clearTrimStop();
        setPlaying(playBtn, false);
      }}
    }};
    player.addEventListener('timeupdate', trimStopHandler);
  }}

  function resetTrimEditorDom(root) {{
    const editor = root.querySelector('.trim-editor');
    if (!editor) return;
    editor.replaceWith(editor.cloneNode(true));
  }}

  async function previewTrim(id) {{
    const {{ start, end }} = readTrimBounds(id);
    if (!(end > start)) {{
      actionResult.textContent = `Invalid trim window for ${{id}}`;
      return;
    }}
    const playBtn = getCard(id)?.querySelector('.play-btn');
    await playClipRange(playBtn, id);
    document.querySelector(`#trim-status-${{id}}`).textContent = `Previewing ${{start.toFixed(2)}}s – ${{end.toFixed(2)}}s (normalized on save)`;
  }}

  async function saveTrim(id) {{
    const {{ start, end }} = readTrimBounds(id);
    const response = await fetch(`/api/trim/${{id}}`, {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ trim_start_sec: start, trim_end_sec: end, reviewer: 'human' }})
    }});
    const payload = await response.json();
    if (!response.ok) throw new Error(JSON.stringify(payload));
    const card = getCard(id);
    const duration = Number(payload.duration_sec || 0);
    card.dataset.duration = String(duration);
    const meta = card.querySelector('.meta');
    const tail = meta.textContent.split('·').slice(1).join('·').trim();
    meta.textContent = `${{duration.toFixed(2)}}s · ${{tail}}`;
    const root = card.querySelector('.trim-controls');
    root.dataset.duration = String(duration);
    const bust = `?t=${{Date.now()}}`;
    root.dataset.audioSrc = root.dataset.audioSrc.split('?')[0] + bust;
    card.querySelector('.play-btn').dataset.src = card.querySelector('.play-btn').dataset.src.split('?')[0] + bust;
    initTrimEditor(root);
    document.querySelector(`#trim-status-${{id}}`).textContent = `Saved trimmed + normalized · ${{duration.toFixed(2)}}s`;
    actionResult.textContent = JSON.stringify(payload, null, 2);
    updateSelectionMeter();
  }}

  document.querySelectorAll('.trim-controls').forEach(initTrimEditor);

  updateSelectionMeter();
</script>
</body>
</html>"""


def serve_review(job_dir: Path, host: str = "127.0.0.1", port: int = 8791) -> None:
    try:
        from fastapi import FastAPI
        from fastapi.responses import FileResponse, HTMLResponse
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("Install review extras: uv sync --extra review") from exc

    candidates = filter_srt_review_candidates(_load_candidates(job_dir))

    def refresh_candidates():
        nonlocal candidates
        candidates = filter_srt_review_candidates(_load_candidates(job_dir))
        return candidates

    app = FastAPI(title="voice-segment-selector review")

    @app.get("/api/candidates")
    def list_candidates():
        return candidates

    @app.post("/api/decide/{clip_id}/{decision}")
    def decide(clip_id: str, decision: str):
        append_decision(job_dir, clip_id, decision)
        return {"ok": True, "id": clip_id, "decision": decision}

    @app.post("/api/transcript/{clip_id}")
    def post_transcript(clip_id: str, payload: dict):
        updated = save_transcript(job_dir, clip_id, str(payload.get("transcript_final", "")), reviewer=str(payload.get("reviewer") or "human"))
        refresh_candidates()
        return {"ok": True, "id": clip_id, "transcript_final": updated.get("transcript_final"), "review_status": updated.get("review_status")}

    @app.post("/api/trim/{clip_id}")
    def post_trim(clip_id: str, payload: dict):
        updated = save_trim(
            job_dir,
            clip_id,
            float(payload.get("trim_start_sec", 0.0)),
            float(payload.get("trim_end_sec", 0.0)),
            reviewer=str(payload.get("reviewer") or "human"),
        )
        refresh_candidates()
        return {
            "ok": True,
            "id": clip_id,
            "duration_sec": updated.get("duration_sec"),
            "clip": updated.get("clip"),
            "trim_history": updated.get("trim_history"),
        }

    @app.get("/api/selection")
    def get_selection():
        return load_selection(job_dir)

    @app.post("/api/selection")
    def post_selection(payload: dict):
        return save_selection(job_dir, [str(item) for item in payload.get("ordered_ids", [])])

    @app.post("/api/export")
    def post_export():
        return export_dataset(job_dir=job_dir, out_dir=job_dir / "voice-dataset")

    @app.post("/api/export-orpheus")
    def post_export_orpheus(payload: dict):
        return export_orpheus_dataset(
            job_dir=job_dir,
            out_dir=job_dir / "orpheus-dataset",
            speaker=str(payload["speaker"]),
        )

    @app.post("/api/bundle")
    def post_bundle(payload: dict):
        ordered_ids = [str(item) for item in payload.get("ordered_ids", [])]
        if ordered_ids:
            save_selection(job_dir, ordered_ids)
        target_sec = float(payload.get("target_sec", 30.0))
        output = job_dir / f"selected_best_{int(target_sec)}s.wav"
        return build_bundle(job_dir=job_dir, out_path=output, gender=str(payload.get("gender") or ""), target_sec=target_sec)

    @app.get("/clips/{clip_path:path}")
    def clip(clip_path: str):
        path = (job_dir / clip_path).resolve()
        if not str(path).startswith(str(job_dir.resolve())) or not path.exists():
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail=f"clip not found: {clip_path}")
        return FileResponse(path, headers={"Cache-Control": "no-store"})

    @app.get("/")
    def index():
        return HTMLResponse(render_review_html(job_dir, candidates))

    uvicorn.run(app, host=host, port=port, log_level="info")

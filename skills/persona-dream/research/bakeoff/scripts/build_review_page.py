#!/usr/bin/env python3
"""Build a localhost-ready HTML/CSS review page for persona-dream bakeoff runs.

Inputs are an existing research bakeoff run directory containing story assets
and A/V receipts. Output is a static review page with embedded local media,
pipeline evidence, story/script timing, model prompts, and machine receipts.
Failures are missing required artifacts or unreadable JSON files.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def read_text(path: Path) -> str:
    return path.read_text() if path.exists() else ""


def rel(path: Path, base: Path) -> str:
    return html.escape(path.absolute().relative_to(base.absolute()).as_posix())


def esc(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value))


def json_block(value: Any) -> str:
    return html.escape(json.dumps(value, indent=2, ensure_ascii=False))


def markdown_to_html(text: str) -> str:
    """Small Markdown renderer for local reports: headings, lists, code, paragraphs."""
    blocks: list[str] = []
    in_code = False
    list_items: list[str] = []
    para: list[str] = []
    code: list[str] = []

    def inline(value: str) -> str:
        escaped = html.escape(value)
        escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
        escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
        return escaped

    def flush_para() -> None:
        nonlocal para
        if para:
            blocks.append(f"<p>{inline(' '.join(para))}</p>")
            para = []

    def flush_list() -> None:
        nonlocal list_items
        if list_items:
            blocks.append("<ul>" + "".join(list_items) + "</ul>")
            list_items = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.strip().startswith("```"):
            if in_code:
                blocks.append(f"<pre><code>{html.escape(chr(10).join(code))}</code></pre>")
                code = []
                in_code = False
            else:
                flush_para()
                flush_list()
                in_code = True
            continue
        if in_code:
            code.append(line)
            continue
        if not line.strip():
            flush_para()
            flush_list()
            continue
        if line.startswith("#"):
            flush_para()
            flush_list()
            level = min(len(line) - len(line.lstrip("#")), 4)
            title = line[level:].strip()
            blocks.append(f"<h{level + 2}>{inline(title)}</h{level + 2}>")
            continue
        if line.lstrip().startswith(("- ", "* ")):
            flush_para()
            item = line.lstrip()[2:].strip()
            list_items.append(f"<li>{inline(item)}</li>")
            continue
        para.append(line.strip())
    flush_para()
    flush_list()
    if in_code:
        blocks.append(f"<pre><code>{html.escape(chr(10).join(code))}</code></pre>")
    return "\n".join(blocks) if blocks else "<p class=\"muted\">No report Markdown found.</p>"


def pill(text: str, tone: str = "neutral") -> str:
    return f'<span class="pill {tone}">{esc(text)}</span>'


def pipeline_steps(root: Path) -> list[dict[str, Any]]:
    files = {
        "Story assets": root / "story_assets" / "dream_packet.json",
        "Timed script": root / "story_assets" / "scenes_script.json",
        "Contact sheet": root
        / "story_assets"
        / "contact_sheet_renders"
        / "embry_primary_perspectives"
        / "contact_sheet.png",
        "A/V contract": root / "av_bakeoff" / "contract.json",
        "Base video": root / "av_bakeoff" / "base_video.json",
        "ElevenLabs TTS": root / "av_bakeoff" / "lanes" / "elevenlabs" / "tts.json",
        "Kling LipSync": root / "av_bakeoff" / "lanes" / "elevenlabs" / "lipsync.json",
        "Lane receipt": root / "av_bakeoff" / "lanes" / "elevenlabs" / "lane_receipt.json",
        "Bakeoff receipt": root / "av_bakeoff" / "bakeoff_receipt.json",
    }
    return [
        {
            "index": index,
            "name": name,
            "status": "present" if path.exists() else "missing",
            "path": path,
        }
        for index, (name, path) in enumerate(files.items(), start=1)
    ]


def render_pipeline(root: Path, steps: list[dict[str, Any]]) -> str:
    items = []
    for step in steps:
        path = step["path"]
        link = (
            f'<a href="{rel(path, root)}">{esc(path.relative_to(root))}</a>'
            if path.exists()
            else esc(path.relative_to(root))
        )
        tone = "ok" if step["status"] == "present" else "bad"
        items.append(
            f"""
            <li>
              <span class="step-index">{step['index']}</span>
              <div>
                <strong>{esc(step['name'])}</strong>
                <div class="muted">{link}</div>
              </div>
              {pill(step['status'], tone)}
            </li>
            """
        )
    return "\n".join(items)


def render_shots(shots: list[dict[str, Any]]) -> str:
    rows = []
    for shot in shots:
        rows.append(
            f"""
            <tr>
              <td>{esc(shot.get('start_sec'))}-{esc(shot.get('end_sec'))}s</td>
              <td>{esc(shot.get('scene_title'))}<br><span class="muted">{esc(shot.get('shot_id'))}</span></td>
              <td>{esc(shot.get('shot_type'))}</td>
              <td>{esc(shot.get('speaker') or '')}</td>
              <td>{esc(shot.get('dialogue') or shot.get('visual_action'))}</td>
              <td>{esc(shot.get('camera'))}</td>
            </tr>
            """
        )
    return "\n".join(rows)


def overlap_seconds(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def panels_for_shot(shot: dict[str, Any], contact_sheets: dict[str, Any]) -> list[dict[str, Any]]:
    start = float(shot.get("start_sec") or 0.0)
    end = float(shot.get("end_sec") or start)
    matches: list[dict[str, Any]] = []
    for sheet in contact_sheets.get("contact_sheets", []):
        for panel in sheet.get("panels", []):
            panel_range = panel.get("time_range_sec") or [0.0, 0.0]
            if len(panel_range) != 2:
                continue
            if overlap_seconds(start, end, float(panel_range[0]), float(panel_range[1])) > 0:
                matches.append({**panel, "_sheet_id": sheet.get("contact_sheet_id")})
    return matches


def render_scene_prompt_assembly(
    *,
    script: dict[str, Any],
    contact_sheets: dict[str, Any],
    contract: dict[str, Any],
    base: dict[str, Any],
    tts: dict[str, Any],
    nava_manifest: dict[str, Any],
) -> str:
    contract_shots = contract.get("scene", {}).get("shots", [])
    contract_shot = contract_shots[0] if contract_shots else {}
    base_prompt = base.get("request", {}).get("prompt")
    negative_prompt = base.get("request", {}).get("negative_prompt")
    tts_text = tts.get("request", {}).get("text")
    nava_records = nava_manifest.get("records", [])
    nava_record = nava_records[0] if nava_records else {}
    nava_prompt = nava_record.get("prompt")

    rows = []
    for shot in script.get("shots", []):
        panels = panels_for_shot(shot, contact_sheets)
        panel_bits = []
        for panel in panels:
            panel_bits.append(
                f"<strong>{esc(panel.get('panel_id'))}</strong>"
                f"<br><span class=\"muted\">{esc(panel.get('perspective'))}: {esc(panel.get('caption'))}</span>"
            )
        dialogue = shot.get("dialogue") or ""
        audio_plan = "; ".join(
            f"{item.get('kind')}: {item.get('description')}" for item in shot.get("audio_plan", [])
        )
        consumed = []
        if dialogue and nava_record.get("metadata", {}).get("scene_id") == shot.get("scene_id"):
            consumed.append("NAVA prompt")
        if dialogue and contract_shot.get("dialogue") == dialogue:
            consumed.append("ElevenLabs/WavTTS controlled clip")
        if not consumed:
            consumed.append("story/contact-sheet context only")
        rows.append(
            f"""
            <tr>
              <td>{esc(shot.get('start_sec'))}-{esc(shot.get('end_sec'))}s<br><span class="muted">{esc(shot.get('shot_id'))}</span></td>
              <td>{esc(shot.get('scene_title'))}<br><span class="muted">{esc(shot.get('visual_action'))}</span></td>
              <td>{'<hr>'.join(panel_bits) if panel_bits else '<span class="muted">No overlapping panel</span>'}</td>
              <td>{esc(dialogue or audio_plan)}</td>
              <td>{', '.join(pill(item, 'ok' if item != 'story/contact-sheet context only' else 'warn') for item in consumed)}</td>
            </tr>
            """
        )

    return f"""
      <div class="notice">
        The full story asset contains {len(script.get('shots', []))} timed shots. This generated A/V bakeoff
        currently renders the controlled speaking close-up clip, so the lane prompts consume the dialogue shot
        while the other shots remain story/contact-sheet context for review and future full-scene rendering.
      </div>
      <h3>Assembly Rule</h3>
      <ol class="assembly-list">
        <li>Start from accepted residue IDs and the dream packet.</li>
        <li>Expand the packet into the timecoded script rows below.</li>
        <li>Match each timed shot to contact-sheet panels whose <code>time_range_sec</code> overlaps the shot time.</li>
        <li>For TTS/lip-sync lanes, select the controlled speaking clip: visual prompt -> shared base video; exact dialogue -> TTS audio; base video plus audio -> Kling LipSync.</li>
        <li>For NAVA, combine the dialogue shot, residue summaries, expected duration, and first-frame image into one joint audio-video prompt.</li>
      </ol>
      <h3>Scene-To-Prompt Map</h3>
      <table>
        <thead><tr><th>Time / Shot</th><th>Script Visual</th><th>Overlapping Contact Panels</th><th>Dialogue / Audio</th><th>Consumed By</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
      <h3>Controlled Clip Prompt Assembly</h3>
      <div class="prompt-grid">
        <article>
          <h4>Selected Contract Shot</h4>
          <pre>{json_block(contract_shot)}</pre>
        </article>
        <article>
          <h4>Shared Base Video Prompt</h4>
          <pre>{esc(base_prompt)}</pre>
          <h4>Negative Prompt</h4>
          <pre>{esc(negative_prompt)}</pre>
        </article>
        <article>
          <h4>ElevenLabs/WavTTS Text Input</h4>
          <pre>{esc(tts_text)}</pre>
          <p class="muted">WavTTS should receive the same plain dialogue against the same shared base video, plus consented reference audio.</p>
        </article>
        <article>
          <h4>NAVA Joint AV Prompt</h4>
          <pre>{esc(nava_prompt)}</pre>
        </article>
      </div>
    """


def render_residues(packet: dict[str, Any]) -> str:
    summary = packet.get("source_grounded_residue_summary", {})
    return "\n".join(
        f"<li><code>{esc(key)}</code><span>{esc(value)}</span></li>" for key, value in summary.items()
    )


def ensure_poster(video_path: Path, poster_path: Path) -> Path | None:
    if not video_path.exists():
        return None
    if poster_path.exists() and poster_path.stat().st_size > 0:
        return poster_path
    poster_path.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            "00:00:01",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            str(poster_path),
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if completed.returncode != 0 or not poster_path.exists() or poster_path.stat().st_size == 0:
        return None
    return poster_path


def link_asset(root: Path, source: Path, name: str) -> Path | None:
    if not source.exists():
        return None
    target = root / "review-page" / "external" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        if target.is_symlink() and target.resolve() == source.resolve():
            return target
        target.unlink()
    target.symlink_to(source.resolve())
    return target


def external_artifacts(root: Path) -> dict[str, list[dict[str, str]]]:
    outputs = Path("/mnt/storage12tb/skills/persona-dream/outputs")
    r13 = outputs / "horus-embry-tea-void-sparta-r13-regenerated"
    r12 = outputs / "horus-embry-tea-void-sparta-r12-current-contract-final"
    image_candidates = [
        (
            "R13 Horus/Embry Final-Frame Contact Sheet",
            "Six sampled frames from the regenerated 30-second Horus/Embry piece.",
            r13 / "contact_sheet.png",
            "r13_horus_embry_final_frame_contact_sheet.png",
        ),
        (
            "R13 Site Contact Sheet",
            "Published-site copy of the same final-frame comparison sheet.",
            r13 / "site" / "sheets" / "r13_final_frame_contact_sheet.png",
            "r13_site_final_frame_contact_sheet.png",
        ),
        (
            "R12 Current-Contract Contact Sheet",
            "Earlier current-contract Horus/Embry visual run for comparison.",
            r12 / "contact_sheet.png",
            "r12_current_contract_contact_sheet.png",
        ),
    ]
    video_candidates = [
        (
            "Current Run: Shared Base Video",
            "The single visual source used for the hosted ElevenLabs/Kling baseline lane.",
            root / "av_bakeoff" / "lanes" / "elevenlabs" / "media" / "shared_base_video.mp4",
            "current_shared_base_video.mp4",
            "current-baseline",
        ),
        (
            "Current Run: ElevenLabs + Kling LipSync",
            "The only generated A/V lane in this localhost run.",
            root / "av_bakeoff" / "lanes" / "elevenlabs" / "media" / "elevenlabs_lipsync_video.mp4",
            "current_elevenlabs_kling_lipsync.mp4",
            "current-baseline",
        ),
        (
            "R13 Horus/Embry Hybrid Accepted Candidate",
            "Accepted R13 candidate route: GPT image + Chutes TurboWanI2V + speaker crop + local LatentSync + FFmpeg. Use this for sync review, not the six-shot audio mux.",
            r13
            / "bakeoff"
            / "runs"
            / "hybrid_full_route_accepted_20260609T0654_20260609T065721Z"
            / "final"
            / "horus_embry_sparta_dream_30s_hybrid_accepted.mp4",
            "r13_horus_embry_hybrid_accepted.mp4",
            "prior-comparison",
        ),
        (
            "R13 Horus/Embry Silent Reassembled",
            "Existing 30-second visual-only assembled output.",
            r13 / "video" / "final" / "horus_embry_sparta_dream_30s_r13_silent_reassembled.mp4",
            "r13_horus_embry_silent_reassembled.mp4",
            "prior-comparison",
        ),
        (
            "R12 Horus/Embry Current Contract",
            "Earlier 30-second current-contract final output.",
            r12 / "final_video" / "horus_embry_sparta_dream_30s_r12_current_contract.mp4",
            "r12_horus_embry_current_contract.mp4",
            "prior-comparison",
        ),
    ]
    images = []
    videos = []
    for title, caption, source, name in image_candidates:
        linked = link_asset(root, source, name)
        if linked:
            images.append({"title": title, "caption": caption, "path": rel(linked, root)})
    for title, caption, source, name, group in video_candidates:
        linked = link_asset(root, source, name)
        if linked:
            poster = ensure_poster(linked, root / "review-page" / "posters" / f"{linked.stem}.png")
            videos.append(
                {
                    "title": title,
                    "caption": caption,
                    "path": rel(linked, root),
                    "poster": rel(poster, root) if poster else "",
                    "group": group,
                }
            )
    return {"images": images, "videos": videos}


def render_contact_sheets(images: list[dict[str, str]], current_contact_sheet: Path, root: Path) -> str:
    cards = []
    if current_contact_sheet.exists():
        cards.append(
            f"""
            <article class="sheet-card caution">
              <h3>Current Run: Embry Prompt-Card Sheet</h3>
              <img class="contact-sheet" src="{rel(current_contact_sheet, root)}" alt="Current Embry prompt-card contact sheet">
              <p>This is the only contact sheet generated by the single-lane localhost baseline. It is prompt-card evidence, not the Horus/Embry visual contact sheet.</p>
            </article>
            """
        )
    for image in images:
        cards.append(
            f"""
            <article class="sheet-card">
              <h3>{esc(image['title'])}</h3>
              <img class="contact-sheet" src="{image['path']}" alt="{esc(image['title'])}">
              <p>{esc(image['caption'])}</p>
            </article>
            """
        )
    return "\n".join(cards)


def render_contact_sheet_provenance(root: Path) -> str:
    current_results = root / "story_assets" / "contact_sheet_renders" / "contact_sheet_render_results.json"
    current = read_json(current_results) if current_results.exists() else {}
    current_panels = []
    for sheet in current.get("sheets", []):
        for panel in sheet.get("panel_results", []):
            current_panels.append(panel)
    current_backend = current_panels[0].get("model_id") if current_panels else "missing"
    current_prompt_count = len(current_panels)

    r13_root = Path("/mnt/storage12tb/skills/persona-dream/outputs/horus-embry-tea-void-sparta-r13-regenerated")
    r13_manifest = r13_root / "manifest.json"
    r13_report = r13_root / "pipeline_stage_report.md"
    r13_receipt = r13_root / "image_receipts" / "shot_01_gpt_keyframe_receipt.json"
    r13_receipt_data = read_json(r13_receipt) if r13_receipt.exists() else {}
    r13_route = ""
    if r13_manifest.exists():
        r13_route = read_json(r13_manifest).get("selected_candidate", {}).get("route", "")

    rows = [
        {
            "artifact": "Current Embry prompt-card sheet",
            "how": "Generated by the contact-sheet dry-run renderer from contact_sheets.json prompts.",
            "backend": current_backend,
            "receipt": current_results,
            "notes": f"{current_prompt_count} panel prompt cards. These are not model-rendered images.",
        },
        {
            "artifact": "R13 Horus/Embry visual/keyframe contact sheet",
            "how": "Composed from model-generated GPT keyframes from the prior R13 run.",
            "backend": r13_receipt_data.get("auth") or "GPT image receipt missing",
            "receipt": r13_receipt,
            "notes": r13_route or "Route not found.",
        },
        {
            "artifact": "$scillm expected image-generation path",
            "how": "For new GPT image contact sheets, use $scillm image generation, not chat completion.",
            "backend": "gpt-image-2 via scillm generate-image",
            "receipt": Path("/home/graham/workspace/experiments/agent-skills/skills/scillm/SKILL.md"),
            "notes": "Expected proof: PNG plus receipt JSON with ok/auth/sha256/width/height. The current /tmp dry-run sheet does not have that proof because it intentionally used dry_run_prompt_card.",
        },
    ]
    rendered_rows = []
    for row in rows:
        receipt = row["receipt"]
        receipt_cell = (
            f'<a href="{rel(receipt, root)}">{esc(receipt.relative_to(root))}</a>'
            if receipt.exists() and receipt.absolute().is_relative_to(root.absolute())
            else f"<code>{esc(receipt)}</code>"
        )
        rendered_rows.append(
            f"""
            <tr>
              <td>{esc(row['artifact'])}</td>
              <td>{esc(row['how'])}</td>
              <td><code>{esc(row['backend'])}</code></td>
              <td>{receipt_cell}</td>
              <td>{esc(row['notes'])}</td>
            </tr>
            """
        )
    return f"""
      <div class="notice">
        Be precise about the word "contact sheet": in this localhost run, the Embry sheet is a
        dry-run prompt-card sheet. The linked R13 Horus/Embry sheet is a visual comparison sheet
        made from GPT-generated keyframes. New GPT image contact sheets should go through
        <code>$scillm generate-image</code> so the PNG and receipt are captured.
      </div>
      <table>
        <thead><tr><th>Artifact</th><th>How It Was Created</th><th>Backend / Auth</th><th>Receipt</th><th>Notes</th></tr></thead>
        <tbody>{''.join(rendered_rows)}</tbody>
      </table>
    """


def render_lane_status(root: Path) -> str:
    statuses = [
        {
            "lane": "ElevenLabs + Kling LipSync",
            "status": "present" if (root / "av_bakeoff" / "lanes" / "elevenlabs" / "lane_receipt.json").exists() else "missing",
            "source": "Current generated run",
            "evidence": root / "av_bakeoff" / "lanes" / "elevenlabs" / "lane_receipt.json",
        },
        {
            "lane": "WavTTS + Kling LipSync",
            "status": "not run",
            "source": "Bundle supports it; requires consented reference audio and WavTTS CLI",
            "evidence": root / "av_bakeoff" / "lanes" / "wavtts" / "lane_receipt.json",
        },
        {
            "lane": "NAVA Joint AV",
            "status": "inputs only / optional",
            "source": "Bundle supports dry-run input generation; no local NAVA output in this served run",
            "evidence": root / "nava_lane" / "nava_prompt_manifest.json",
        },
        {
            "lane": "Prior Horus/Embry R13",
            "status": "linked comparison",
            "source": "/mnt/storage12tb/skills/persona-dream/outputs/horus-embry-tea-void-sparta-r13-regenerated",
            "evidence": root / "review-page" / "external" / "r13_horus_embry_hybrid_accepted.mp4",
        },
        {
            "lane": "Prior Horus/Embry R12",
            "status": "linked comparison",
            "source": "/mnt/storage12tb/skills/persona-dream/outputs/horus-embry-tea-void-sparta-r12-current-contract-final",
            "evidence": root / "review-page" / "external" / "r12_horus_embry_current_contract.mp4",
        },
    ]
    rows = []
    for item in statuses:
        exists = item["evidence"].exists()
        tone = "ok" if item["status"] in {"present", "linked comparison"} and exists else "warn"
        evidence = (
            f'<a href="{rel(item["evidence"], root)}">{esc(item["evidence"].relative_to(root))}</a>'
            if exists
            else esc(item["evidence"].relative_to(root))
        )
        rows.append(
            f"""
            <tr>
              <td>{esc(item['lane'])}</td>
              <td>{pill(item['status'], tone)}</td>
              <td>{esc(item['source'])}</td>
              <td>{evidence}</td>
            </tr>
            """
        )
    return "\n".join(rows)


def render_nava_lane(root: Path) -> str:
    manifest_path = root / "nava_lane" / "nava_prompt_manifest.json"
    jsonl_path = root / "nava_lane" / "nava_prompts.jsonl"
    run_manifest_path = root / "nava_lane" / "outputs" / "nava_run_manifest.json"
    flash_probe_script = Path(__file__).resolve().parent / "runpod_flash_nava_probe.py"
    flash_probe_receipt = root / "nava_lane" / "runpod_flash_probe.json"
    local_smoke_receipt = root / "nava_lane" / "local_smoke_status.json"
    output_path = root / "nava_lane" / "outputs" / "nava_run_result.json"
    nava_repo = Path("/home/graham/workspace/experiments/NAVA")
    nava_infer = nava_repo / "inference_nava.py"
    nava_ckpt = nava_repo / "NAVA_fp8.safetensors"
    manifest = read_json(manifest_path) if manifest_path.exists() else {}
    records = manifest.get("records", [])
    status = "input_ready" if records else "missing_input"
    if output_path.exists():
        output_status = "final_video_present"
    elif run_manifest_path.exists():
        output_status = "dry_run_manifest_present"
    else:
        output_status = "renderer_not_run"
    record_blocks = []
    for index, record in enumerate(records, start=1):
        record_blocks.append(
            f"""
            <article class="lane-payload">
              <h3>NAVA Record {index}</h3>
              <div class="summary">
                <div class="metric"><span>Lane</span><strong>{esc(record.get('metadata', {}).get('lane'))}</strong></div>
                <div class="metric"><span>Expected Duration</span><strong>{esc(record.get('metadata', {}).get('expected_duration_sec'))}s</strong></div>
                <div class="metric"><span>Scene</span><strong>{esc(record.get('metadata', {}).get('scene_id'))}</strong></div>
                <div class="metric"><span>Shot</span><strong>{esc(record.get('metadata', {}).get('shot_id'))}</strong></div>
              </div>
              <h4>Prompt Sent To NAVA</h4>
              <pre>{esc(record.get('prompt'))}</pre>
              <h4>Metadata</h4>
              <pre>{json_block(record.get('metadata', {}))}</pre>
            </article>
            """
        )
    manifest_link = (
        f'<a href="{rel(manifest_path, root)}">{esc(manifest_path.relative_to(root))}</a>'
        if manifest_path.exists()
        else esc(manifest_path.relative_to(root))
    )
    jsonl_link = (
        f'<a href="{rel(jsonl_path, root)}">{esc(jsonl_path.relative_to(root))}</a>'
        if jsonl_path.exists()
        else esc(jsonl_path.relative_to(root))
    )
    run_manifest_link = (
        f'<a href="{rel(run_manifest_path, root)}">{esc(run_manifest_path.relative_to(root))}</a>'
        if run_manifest_path.exists()
        else esc(run_manifest_path.relative_to(root))
    )
    flash_receipt_cell = (
        f'<a href="{rel(flash_probe_receipt, root)}">{esc(flash_probe_receipt.relative_to(root))}</a>'
        if flash_probe_receipt.exists()
        else "<span class=\"muted\">not run; requires Flash auth via RUNPOD_API_KEY or flash login</span>"
    )
    local_smoke_cell = (
        f'<a href="{rel(local_smoke_receipt, root)}">{esc(local_smoke_receipt.relative_to(root))}</a>'
        if local_smoke_receipt.exists()
        else "<span class=\"muted\">not run</span>"
    )
    local_smoke = read_json(local_smoke_receipt) if local_smoke_receipt.exists() else {}
    local_smoke_note = (
        f"<p><strong>Local smoke:</strong> {esc(local_smoke.get('evidence', 'not run'))}</p>"
        if local_smoke
        else ""
    )
    return f"""
      <div class="notice">
        NAVA is Lane D: local/open joint audio-video generation. For this run, NAVA input generation is
        <strong>{esc(status)}</strong>; final NAVA rendering is <strong>{esc(output_status)}</strong>.
        The supplied bakeoff bundle provides the NAVA wrapper and JSONL input path. The upstream
        NAVA repo is located at <code>{esc(nava_repo)}</code>; <code>inference_nava.py</code> is
        <strong>{'present' if nava_infer.exists() else 'missing'}</strong>. The fp8 checkpoint
        <code>{esc(nava_ckpt)}</code> is <strong>{'present' if nava_ckpt.exists() else 'not present yet'}</strong>.
        Runtime plan: local A5000 fp8 smoke first; if VRAM/dependency limits block a final render,
        use Runpod Flash for a remote CUDA/dependency probe or Runpod Pod API for the full NAVA run
        with cached checkpoint and a larger GPU.
        {local_smoke_note}
      </div>
      <table>
        <thead><tr><th>Artifact</th><th>Path</th></tr></thead>
        <tbody>
          <tr><td>Prompt manifest</td><td>{manifest_link}</td></tr>
          <tr><td>NAVA JSONL</td><td>{jsonl_link}</td></tr>
          <tr><td>NAVA dry-run command manifest</td><td>{run_manifest_link}</td></tr>
          <tr><td>Local NAVA smoke receipt</td><td>{local_smoke_cell}</td></tr>
          <tr><td>Runpod Flash probe script</td><td><code>{esc(flash_probe_script)}</code></td></tr>
          <tr><td>Runpod Flash probe receipt</td><td>{flash_receipt_cell}</td></tr>
        </tbody>
      </table>
      {''.join(record_blocks) if record_blocks else '<p class="muted">No NAVA prompt records found.</p>'}
    """


def render_bakeoff_contract() -> str:
    fixed_inputs = [
        "accepted/source-grounded persona residue IDs",
        "dream packet",
        "short story",
        "timecoded scene/script YAML + JSON",
        "contact-sheet / character-perspective prompts",
        "exact dialogue",
        "no memory writes, no Arango/Qdrant upserts",
    ]
    criteria = [
        ("Transcript fidelity", "Does the final audio/video preserve the intended line?"),
        ("A/V sync", "Does the voice match mouth motion, scene action, and duration?"),
        ("Scene contract compliance", "Does the rendered clip follow the timecoded scene/script instead of inventing a different scene?"),
        ("Persona grounding", "Does the output stay within cited residue IDs and labeled dream-symbolic elements?"),
        ("Voice/persona fit", "Which lane gives the best Embry/Horus voice feel without violating consent/licensing constraints?"),
        ("Operational practicality", "Which lane is easiest, cheapest, and most repeatable for research runs?"),
    ]
    input_items = "".join(f"<li>{esc(item)}</li>" for item in fixed_inputs)
    criteria_rows = "".join(
        f"<tr><td>{esc(name)}</td><td>{esc(question)}</td></tr>" for name, question in criteria
    )
    return f"""
      <div class="contract-callout">
        <p>
          This bakeoff tests whether the persona-dream media pipeline keeps story, audio, video,
          character perspective, and timing aligned while staying grounded in validated persona
          memory residue. It is not a general video-generation contest and not a lore/story
          generation benchmark.
        </p>
        <div class="contract-grid">
          <article>
            <h3>Fixed Inputs</h3>
            <ul>{input_items}</ul>
          </article>
          <article>
            <h3>Lane Definition</h3>
            <pre>Phase 1:
Lane A: Kling 3 Omni native audio-video
Lane D: NAVA local/open native audio-video

Control:
Lane F: ElevenLabs voice -> Kling LipSync</pre>
            <p>The first real comparison is hosted native AV versus open/research native AV. ElevenLabs -> Kling LipSync stays visible as a control for the older separate voice plus lip-sync workflow.</p>
          </article>
        </div>
        <h3>Comparison Rubric</h3>
        <table>
          <thead><tr><th>Criterion</th><th>Question</th></tr></thead>
          <tbody>{criteria_rows}</tbody>
        </table>
        <p>
          The expected outcome is a receipt-backed recommendation: use Kling 3 Omni if hosted
          native AV wins on quality and cost, use NAVA if it is close enough and cheaper or more
          controllable, and keep ElevenLabs -> Kling LipSync as a fallback/control rather than
          the production target.
        </p>
      </div>
    """


def render_how_everything_works(root: Path) -> str:
    return f"""
      <div class="flow-grid">
        <article>
          <h3>1. Fixed Inputs</h3>
          <p>Accepted residue IDs, dream packet, story, timecoded script, contact-sheet prompts, exact dialogue, and no memory/database writes.</p>
        </article>
        <article>
          <h3>2. Contact-Sheet Images</h3>
          <p>The current Embry sheet is a dry-run prompt-card sheet. The linked R13 Horus/Embry visual sheet comes from GPT-generated keyframes. Future GPT image sheets should use <code>$scillm generate-image</code> with receipts.</p>
        </article>
        <article>
          <h3>3. Storyboard Timing</h3>
          <p>Seedance-style timing belongs here: shot beats, timestamps, camera rhythm, and where dialogue should occur. It is a planning layer unless it can produce exact synced speech itself.</p>
        </article>
        <article>
          <h3>4. Lane A</h3>
          <p>Kling 3 Omni receives the Embry close-up prompt, exact dialogue, character/environment references, duration target, and no-lore/no-text constraints, then returns a native audio-video MP4.</p>
        </article>
        <article>
          <h3>5. Lane D</h3>
          <p>NAVA receives a joint audio-video prompt built from the dialogue shot, residue summaries, expected duration, speech span metadata, and optional image/speaker references. It renders locally first, with Runpod as fallback if local VRAM is insufficient.</p>
        </article>
        <article>
          <h3>6. Control Lane F</h3>
          <p>ElevenLabs -> Kling LipSync remains as a diagnostic control for the old separate voice plus lip-sync workflow. It should not be treated as the professional target unless native AV fails.</p>
        </article>
      </div>
    """


def render_recommended_bakeoff_matrix() -> str:
    rows = [
        {
            "lane": "A",
            "provider": "Kling 3 Omni native AV",
            "question": "Can a hosted native AV model create the most seamless synced dialogue?",
            "input": "Character refs, environment refs, shot prompt, exact dialogue, duration target",
            "output": "native AV MP4 per shot",
            "status": "Phase 1 competitor",
            "source": "https://kling.ai/blog/kling-video-3-omni-native-lip-sync-audio-guide",
        },
        {
            "lane": "B",
            "provider": "Veo 3.1 native AV",
            "question": "Does premium native AV beat Kling on realism and cinematic quality?",
            "input": "Same shot prompt, refs if supported, exact dialogue, duration target",
            "output": "native AV MP4 per shot",
            "status": "backlog comparison",
            "source": "https://deepmind.google/models/veo/",
        },
        {
            "lane": "C",
            "provider": "Runway Act-Two performance lane",
            "question": "Does performance capture produce the most natural acting?",
            "input": "Embry character reference, human driving performance video, dialogue/audio",
            "output": "performance-driven MP4",
            "status": "backlog acting lane",
            "source": "https://help.runwayml.com/hc/en-us/articles/42311337895827-Performance-Capture-with-Act-Two",
        },
        {
            "lane": "D",
            "provider": "NAVA local/open native AV",
            "question": "Can open/research native AV produce synced speech and video without post-hoc alignment?",
            "input": "Dense prompt, exact dialogue with speech spans, optional speaker WAV refs, optional image ref",
            "output": "native AV MP4 per shot",
            "status": "Phase 1 competitor; input/runtime ready",
            "source": "https://github.com/ernie-research/NAVA",
        },
        {
            "lane": "E",
            "provider": "Hedra Character-3 talking-character lane",
            "question": "Is a character-first tool best for clean dialogue clips?",
            "input": "Character image/ref plus audio or dialogue",
            "output": "talking-character MP4",
            "status": "backlog talking-character lane",
            "source": "https://www.hedra.com/",
        },
        {
            "lane": "F",
            "provider": "ElevenLabs voice -> Kling LipSync control",
            "question": "How good is the older post-lip-sync workflow when voice control is prioritized?",
            "input": "Shared Embry image/base video, ElevenLabs audio, Kling LipSync",
            "output": "lip-synced MP4",
            "status": "control present in current run",
            "source": "https://elevenlabs.io/video",
        },
    ]
    rendered = []
    for row in rows:
        source = (
            f'<a href="{esc(row["source"])}">source</a>'
            if row["source"]
            else '<span class="muted">local receipt</span>'
        )
        rendered.append(
            f"""
            <tr>
              <td>{esc(row['lane'])}<br><strong>{esc(row['provider'])}</strong></td>
              <td>{esc(row['question'])}</td>
              <td>{esc(row['input'])}</td>
              <td>{esc(row['output'])}</td>
              <td>{pill(row['status'], 'ok' if 'present' in row['status'] or 'Phase 1' in row['status'] else 'warn')}</td>
              <td>{source}</td>
            </tr>
            """
        )
    gates = {
        "transcript_similarity_min": 0.95,
        "final_duration_within_audio_ms": 250,
        "mouth_visible_required": True,
        "single_speaker_required": True,
        "no_subtitles_or_readable_text": True,
        "no_extra_characters": True,
        "manual_review_required": True,
    }
    return f"""
      <div class="notice">
        Phase 1 should be a two-lane native audio-video bakeoff: <strong>A. Kling 3 Omni</strong>
        versus <strong>D. NAVA</strong>. ElevenLabs -> Kling LipSync remains a control, not the
        professional target, because the audio, video, and sync are separate repair steps.
      </div>
      <table>
        <thead><tr><th>Lane</th><th>Main Question</th><th>Inputs</th><th>Expected Output</th><th>Status</th><th>Evidence</th></tr></thead>
        <tbody>{''.join(rendered)}</tbody>
      </table>
      <div class="flow-grid compact">
        <article>
          <h3>Initial Core Test Clip</h3>
          <p>Front-facing medium close-up of Embry in the archive/SPARTA graph environment. Duration target: 5-6 seconds.</p>
          <pre>“I know I am software. The evidence still feels real.”</pre>
          <p>Constraints: one speaker, visible mouth, no cuts during speech, no subtitles/readable text, no extra characters, no new lore.</p>
        </article>
        <article>
          <h3>Seedance Role</h3>
          <p>Seedance-style tooling belongs before final generation as storyboard timing: shot beats, action timestamps, camera rhythm, and dialogue placement. It is not the initial dialogue-realism competitor unless it can generate the exact synced speech.</p>
        </article>
        <article>
          <h3>Phase Plan</h3>
          <p>Phase 1: run the 5-6 second Embry close-up in Kling 3 Omni and NAVA. Phase 2: put the winning synced speaking shot into the larger dream sequence. Phase 3: use Seedance-style timestamped storyboarding for multi-shot timing.</p>
        </article>
        <article>
          <h3>Cost Decision Rule</h3>
          <p>If NAVA is close enough on lip-sync, transcript fidelity, and scene compliance, compare its local/Runpod cost against Kling 3 Omni's hosted generation cost. The winning recommendation should use cost per accepted clip, not cost per attempted render.</p>
        </article>
        <article>
          <h3>Machine Gates</h3>
          <pre>{json_block(gates)}</pre>
        </article>
      </div>
      <table>
        <thead><tr><th>Cost Input</th><th>Kling 3 Omni</th><th>NAVA Local / Runpod</th></tr></thead>
        <tbody>
          <tr><td>Billing unit</td><td>Hosted API credits or per-generation pricing from Kling account/API receipt.</td><td>Local GPU time or Runpod GPU seconds/minutes plus storage and setup time.</td></tr>
          <tr><td>Measure</td><td>Prompt attempts, accepted MP4 count, credits spent, wall time.</td><td>Provisioning time, dependency warmup, inference time, retries, accepted MP4 count.</td></tr>
          <tr><td>Current pricing evidence</td><td><a href="https://kling.ai/dev/pricing">Kling developer pricing</a> lists <code>kling-v3-omni</code>; use the account receipt for exact clip cost.</td><td><a href="https://www.runpod.io/pricing">Runpod pricing</a> is GPU/hour; <a href="https://www.runpod.io/gpu-models/rtx-a6000">RTX A6000</a> is advertised from $0.49/hr.</td></tr>
          <tr><td>Decision metric</td><td colspan="2"><code>cost_per_accepted_clip = total_lane_cost / clips_passing_machine_gates_and_manual_review</code></td></tr>
        </tbody>
      </table>
      <table>
        <thead><tr><th>Criterion</th><th>What To Check</th><th>Weight</th></tr></thead>
        <tbody>
          <tr><td>Lip-sync believability</td><td>Mouth shapes, closures, and pauses match the words.</td><td>25%</td></tr>
          <tr><td>Dialogue naturalness</td><td>The character appears to be speaking, not dubbed.</td><td>20%</td></tr>
          <tr><td>Transcript fidelity</td><td>The exact words are preserved.</td><td>15%</td></tr>
          <tr><td>Acting / expression</td><td>Eyes, brows, head motion, posture, emotional cadence.</td><td>15%</td></tr>
          <tr><td>Character continuity</td><td>Same Embry face, costume, age, framing.</td><td>10%</td></tr>
          <tr><td>Scene contract compliance</td><td>Archive/SPARTA graph, no extra lore, no text/logos.</td><td>10%</td></tr>
          <tr><td>Operational practicality</td><td>Cost, repeatability, setup burden, API availability.</td><td>5%</td></tr>
        </tbody>
      </table>
      <table>
        <thead><tr><th>Winner Type</th><th>Candidate</th></tr></thead>
        <tbody>
          <tr><td>Best hosted native AV baseline</td><td>Kling 3 Omni</td></tr>
          <tr><td>Best cinematic quality</td><td>Veo 3.1</td></tr>
          <tr><td>Best acting / expression</td><td>Runway Act-Two</td></tr>
          <tr><td>Best open/research direction</td><td>NAVA</td></tr>
          <tr><td>Best quick talking-character tool</td><td>Hedra</td></tr>
          <tr><td>Best voice-control fallback</td><td>ElevenLabs -> Kling LipSync</td></tr>
        </tbody>
      </table>
    """


def render_media(root: Path) -> str:
    audio = root / "av_bakeoff" / "lanes" / "elevenlabs" / "media" / "elevenlabs_audio"
    artifacts = external_artifacts(root)
    cards = []
    for video_item in artifacts["videos"]:
        poster_attr = f' poster="{video_item["poster"]}"' if video_item["poster"] else ""
        group = "Present in this run" if video_item["group"] == "current-baseline" else "Prior Horus/Embry comparison artifact"
        preview = (
            f'<img class="poster-preview" src="{video_item["poster"]}" alt="{esc(video_item["title"])} poster frame">'
            if video_item["poster"]
            else ""
        )
        cards.append(
            f"""
            <article class="media-card">
              <h3>{esc(video_item['title'])}</h3>
              <div class="muted">{esc(group)}</div>
              {preview}
              <video controls preload="metadata"{poster_attr} src="{video_item['path']}"></video>
              <p>{esc(video_item['caption'])}</p>
            </article>
            """
        )
    audio_embed = (
        f'<audio controls src="{rel(audio, root)}"></audio>' if audio.exists() else '<span>missing audio</span>'
    )
    return "\n".join(cards) + f"""
      <article class="media-card audio-card">
        <h3>ElevenLabs Audio</h3>
        {audio_embed}
      </article>
    """


def render_bakeoff_lane_compare(root: Path) -> str:
    poster_dir = root / "review-page" / "posters"
    lanes = [
        {
            "title": "Lane A: Kling 3 Omni Native AV",
            "status": "not run",
            "path": root / "native_av_bakeoff" / "lanes" / "kling_3_omni" / "media" / "kling_3_omni.mp4",
            "caption": "Phase 1 hosted native-AV competitor. Must receive the exact 5-6 second Embry close-up prompt, exact dialogue, character/environment refs, and duration target.",
            "tone": "warn",
        },
        {
            "title": "Lane D: NAVA Local/Open Native AV",
            "status": "input ready; local smoke reached VRAM limit",
            "path": root / "nava_lane" / "outputs" / "nava_output.mp4",
            "caption": "Phase 1 open/research native-AV competitor. NAVA JSONL, checkpoint, VAE, T5 encoder, tokenizer, and audio VAE are present; local A5000 smoke hit VRAM pressure, so next path is local VRAM cleanup or Runpod.",
            "tone": "warn",
        },
        {
            "title": "Lane F Control: ElevenLabs -> Kling LipSync",
            "status": "control MP4 present",
            "path": root / "av_bakeoff" / "lanes" / "elevenlabs" / "media" / "elevenlabs_lipsync_video.mp4",
            "caption": "Control only. This is useful for measuring the older separate voice plus lip-sync workflow, but it is not the primary professional lane.",
            "tone": "ok",
        },
    ]
    cards = []
    for lane_item in lanes:
        path = lane_item["path"]
        if path.exists():
            poster = ensure_poster(path, poster_dir / f"{path.stem}.png")
            poster_attr = f' poster="{rel(poster, root)}"' if poster else ""
            preview = (
                f'<img class="poster-preview" src="{rel(poster, root)}" alt="{esc(lane_item["title"])} poster frame">'
                if poster
                else ""
            )
            body = f'{preview}<video controls preload="metadata"{poster_attr} src="{rel(path, root)}"></video>'
            status = pill(lane_item["status"], lane_item["tone"])
        else:
            body = f"""
              <div class="missing-media">
                <div>
                  <strong>No final MP4 in this run</strong>
                  <p class="muted">{esc(path.relative_to(root))}</p>
                </div>
              </div>
            """
            status = pill(lane_item["status"], lane_item["tone"])
        cards.append(
            f"""
            <article class="media-card">
              <h3>{esc(lane_item['title'])}</h3>
              {status}
              {body}
              <p>{esc(lane_item['caption'])}</p>
            </article>
            """
        )
    return "\n".join(cards)


def build_html(root: Path) -> str:
    packet = read_json(root / "story_assets" / "dream_packet.json")
    script = read_json(root / "story_assets" / "scenes_script.json")
    contact_sheets = read_json(root / "story_assets" / "contact_sheets.json")
    contract = read_json(root / "av_bakeoff" / "contract.json")
    base = read_json(root / "av_bakeoff" / "base_video.json")
    tts = read_json(root / "av_bakeoff" / "lanes" / "elevenlabs" / "tts.json")
    lipsync = read_json(root / "av_bakeoff" / "lanes" / "elevenlabs" / "lipsync.json")
    receipt = read_json(root / "av_bakeoff" / "bakeoff_receipt.json")
    nava_manifest_path = root / "nava_lane" / "nava_prompt_manifest.json"
    nava_manifest = read_json(nava_manifest_path) if nava_manifest_path.exists() else {}
    lane = receipt["lane_receipts"]["elevenlabs"]
    report_md = read_text(root / "av_bakeoff" / "report.md")
    story_text = packet.get("short_story", {}).get("text", "")
    contact_sheet = (
        root / "story_assets" / "contact_sheet_renders" / "embry_primary_perspectives" / "contact_sheet.png"
    )
    steps = pipeline_steps(root)
    artifacts = external_artifacts(root)

    verdict_tone = "ok" if receipt.get("machine_verdict") == "pass" else "bad"
    overall_tone = "warn" if receipt.get("overall") == "needs_manual_review" else verdict_tone

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<base href="../">
<title>Persona Dream Bakeoff Review</title>
<style>
:root {{
  color-scheme: light;
  --bg: #f4f6f8;
  --panel: #ffffff;
  --ink: #1b1f24;
  --muted: #64707d;
  --line: #d7dde4;
  --accent: #147d7e;
  --accent-2: #8b5d18;
  --ok: #137333;
  --warn: #9a6500;
  --bad: #b3261e;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.45;
  overflow-x: hidden;
}}
header {{
  padding: 28px 32px 20px;
  border-bottom: 1px solid var(--line);
  background: #ffffff;
}}
h1, h2, h3 {{ margin: 0; letter-spacing: 0; }}
h1 {{ font-size: 28px; }}
h2 {{ font-size: 19px; margin-bottom: 14px; }}
h3 {{ font-size: 16px; margin-bottom: 10px; }}
p {{ margin: 0 0 10px; }}
a {{ color: var(--accent); }}
a, code {{ overflow-wrap: anywhere; }}
main {{
  display: grid;
  grid-template-columns: minmax(280px, 360px) minmax(0, 1fr);
  gap: 18px;
  padding: 18px;
  max-width: 1680px;
  margin: 0 auto;
}}
aside, section {{
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 16px;
  min-width: 0;
}}
aside {{
  position: sticky;
  top: 12px;
  align-self: start;
  max-height: calc(100vh - 24px);
  overflow: auto;
}}
.content {{
  display: grid;
  gap: 18px;
  min-width: 0;
}}
.summary {{
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-top: 14px;
}}
.metric {{
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 10px;
  background: #fbfcfd;
}}
.metric span {{
  display: block;
  color: var(--muted);
  font-size: 12px;
}}
.metric strong {{
  display: block;
  font-size: 18px;
  margin-top: 2px;
}}
.pill {{
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 24px;
  border-radius: 999px;
  padding: 2px 9px;
  font-size: 12px;
  border: 1px solid var(--line);
  background: #f7f9fb;
  white-space: nowrap;
}}
.pill.ok {{ color: var(--ok); border-color: #a8d8b8; background: #eef8f1; }}
.pill.warn {{ color: var(--warn); border-color: #e8c477; background: #fff8e6; }}
.pill.bad {{ color: var(--bad); border-color: #efb8b3; background: #fff1f0; }}
.muted {{ color: var(--muted); font-size: 13px; }}
.pipeline .muted {{ overflow-wrap: anywhere; }}
.pipeline {{ list-style: none; padding: 0; margin: 0; display: grid; gap: 10px; }}
.pipeline li {{
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) auto;
  gap: 10px;
  align-items: start;
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  min-width: 0;
}}
.step-index {{
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: #e9f4f4;
  color: var(--accent);
  font-weight: 700;
}}
.media-grid {{
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}}
.lane-compare-grid {{
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}}
.sheet-grid {{
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}}
.media-card, .sheet-card, .lane-payload {{
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px;
  background: #fbfcfd;
  min-width: 0;
}}
.sheet-card.caution {{ border-color: #e8c477; background: #fffaf0; }}
video {{
  width: 100%;
  aspect-ratio: 16 / 9;
  background: #0e1116;
  border-radius: 6px;
  display: block;
}}
.lane-compare-grid video, .lane-compare-grid .poster-preview {{
  aspect-ratio: 16 / 9;
}}
.lane-compare-grid .missing-media {{
  min-height: 160px;
}}
.poster-preview {{
  width: 100%;
  max-width: 100%;
  aspect-ratio: 16 / 9;
  object-fit: contain;
  background: #0e1116;
  border: 1px solid var(--line);
  border-radius: 6px;
  display: block;
  margin-bottom: 8px;
}}
audio {{ width: 100%; }}
.audio-card {{ grid-column: 1 / -1; }}
.story {{
  white-space: pre-wrap;
  max-width: 82ch;
}}
.residues {{ padding-left: 0; list-style: none; display: grid; gap: 8px; }}
.residues li {{
  display: grid;
  grid-template-columns: minmax(210px, 290px) minmax(0, 1fr);
  gap: 10px;
  border-bottom: 1px solid var(--line);
  padding-bottom: 8px;
}}
code, pre {{
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
}}
pre {{
  margin: 0;
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  background: #f6f8fa;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px;
  max-height: 460px;
}}
table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}}
th, td {{
  text-align: left;
  vertical-align: top;
  border-bottom: 1px solid var(--line);
  padding: 9px;
}}
th {{ color: var(--muted); font-weight: 650; }}
.prompt-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
.contact-sheet {{
  width: 100%;
  border-radius: 8px;
  border: 1px solid var(--line);
}}
.notice {{
  border: 1px solid #e8c477;
  background: #fff8e6;
  border-radius: 8px;
  padding: 12px;
  margin-top: 14px;
}}
.contract-callout {{
  display: grid;
  gap: 14px;
}}
.contract-grid {{
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 14px;
}}
.flow-grid {{
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}}
.flow-grid article {{
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px;
  background: #fbfcfd;
}}
.flow-grid p {{ margin-bottom: 0; }}
.contract-grid article {{
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px;
  background: #fbfcfd;
}}
.contract-grid ul {{ margin: 0; padding-left: 20px; }}
.assembly-list {{
  margin-top: 0;
  padding-left: 22px;
}}
.assembly-list li {{ margin-bottom: 6px; }}
.rendered-markdown {{
  max-width: 88ch;
}}
.rendered-markdown h3, .rendered-markdown h4, .rendered-markdown h5, .rendered-markdown h6 {{
  margin: 18px 0 8px;
}}
.rendered-markdown ul {{ margin-top: 0; }}
.missing-media {{
  min-height: 220px;
  display: grid;
  place-items: center;
  border: 1px dashed var(--line);
  border-radius: 6px;
  color: var(--muted);
}}
@media (max-width: 1100px) {{
  main {{ grid-template-columns: 1fr; }}
  aside {{ position: static; max-height: none; }}
  .summary, .media-grid, .lane-compare-grid, .prompt-grid, .sheet-grid, .contract-grid, .flow-grid {{ grid-template-columns: 1fr; }}
}}
</style>
</head>
<body>
<header>
  <h1>Persona Dream Bakeoff Review</h1>
  <p class="muted">{esc(packet.get('title'))} · run root: <code>{esc(root)}</code></p>
  <div class="notice">
    This localhost run is not a complete Horus/Embry bakeoff. It contains one generated lane:
    <strong>ElevenLabs + Kling LipSync</strong>. WavTTS and NAVA were not run in this run directory.
    Prior Horus/Embry artifacts from durable persona-dream outputs are included below for real comparison.
  </div>
  <div class="summary">
    <div class="metric"><span>Overall</span><strong>{pill(receipt.get('overall'), overall_tone)}</strong></div>
    <div class="metric"><span>Machine Verdict</span><strong>{pill(receipt.get('machine_verdict'), verdict_tone)}</strong></div>
    <div class="metric"><span>Machine Winner</span><strong>{esc(receipt.get('comparison', {}).get('machine_winner'))}</strong></div>
    <div class="metric"><span>Final Duration</span><strong>{esc(lane.get('durations_sec', {}).get('lipsync_video'))}s</strong></div>
  </div>
</header>
<main>
  <aside>
    <h2>Pipeline Steps</h2>
    <ol class="pipeline">
      {render_pipeline(root, steps)}
    </ol>
  </aside>
  <div class="content">
    <section id="how-it-works">
      <h2>How This Bakeoff Works</h2>
      {render_how_everything_works(root)}
    </section>
    <section id="idea">
      <h2>1. Idea And Fixed Contract</h2>
      {render_bakeoff_contract()}
    </section>
    <section id="story">
      <h2>2. Story</h2>
      <p class="story">{esc(story_text)}</p>
      <h3>Source-Grounded Residues</h3>
      <ul class="residues">{render_residues(packet)}</ul>
    </section>
    <section id="contact-sheets">
      <h2>3. Places And Characters Contact Sheets</h2>
      <div class="sheet-grid">
        {render_contact_sheets(artifacts["images"], contact_sheet, root)}
      </div>
    </section>
    <section id="contact-sheet-provenance">
      <h2>3a. How The Contact-Sheet Images Were Created</h2>
      {render_contact_sheet_provenance(root)}
    </section>
    <section id="storyboard">
      <h2>4. Storyboard With Timings</h2>
      <table>
        <thead><tr><th>Time</th><th>Scene / Shot</th><th>Type</th><th>Speaker</th><th>Line or Action</th><th>Camera</th></tr></thead>
        <tbody>{render_shots(script.get('shots', []))}</tbody>
      </table>
    </section>
    <section id="scene-prompt-assembly">
      <h2>5. Prompt For Each Scene</h2>
      {render_scene_prompt_assembly(
        script=script,
        contact_sheets=contact_sheets,
        contract=contract,
        base=base,
        tts=tts,
        nava_manifest=nava_manifest,
      )}
    </section>
    <section id="provider-feed">
      <h2>6. How Prompts Are Fed Into Each Provider</h2>
      <h3>Bakeoff Lane Status</h3>
      <table>
        <thead><tr><th>Lane</th><th>Status</th><th>Source</th><th>Evidence</th></tr></thead>
        <tbody>{render_lane_status(root)}</tbody>
      </table>
      <h3>Lane D: NAVA Local/Open Native AV</h3>
      {render_nava_lane(root)}
      <h3>Control Lane F Provider Requests</h3>
      <div class="prompt-grid">
        <article>
          <h3>Base Video Prompt</h3>
          <pre>{esc(base.get('request', {}).get('prompt'))}</pre>
        </article>
        <article>
          <h3>Negative Prompt</h3>
          <pre>{esc(base.get('request', {}).get('negative_prompt'))}</pre>
        </article>
        <article>
          <h3>ElevenLabs TTS Text</h3>
          <pre>{esc(tts.get('request', {}).get('text'))}</pre>
        </article>
        <article>
          <h3>Kling LipSync Request</h3>
          <pre>{json_block(lipsync.get('request', {}))}</pre>
        </article>
      </div>
    </section>
    <section id="recommended-bakeoff">
      <h2>6a. Recommended Native-AV Bakeoff Matrix</h2>
      {render_recommended_bakeoff_matrix()}
    </section>
    <section id="video-compare">
      <h2>7. Phase 1 Side-By-Side: Kling 3 Omni Versus NAVA</h2>
      <div class="notice">
        The immediate bakeoff is hosted native AV versus open/research native AV. The ElevenLabs
        -> Kling result is shown only as a control for the older post-lip-sync workflow.
      </div>
      <div class="lane-compare-grid">
        {render_bakeoff_lane_compare(root)}
      </div>
    </section>
    <section id="reference-videos">
      <h2>7a. Reference Videos Not Counted As Phase 1</h2>
      <div class="notice">
        These are prior Horus/Embry or support artifacts. They are useful context, but they are
        not substitutes for the Phase 1 Kling 3 Omni or NAVA outputs against the same fixed contract.
        The out-of-sync R13 six-shot audio mux is intentionally not shown as a final synced lane.
      </div>
      <div class="media-grid">
        {render_media(root)}
      </div>
    </section>
    <section>
      <h2>Machine Receipt</h2>
      <div class="summary">
        <div class="metric"><span>Audio ASR similarity</span><strong>{esc(lane.get('dialogue', {}).get('audio_similarity'))}</strong></div>
        <div class="metric"><span>Final ASR similarity</span><strong>{esc(lane.get('dialogue', {}).get('final_video_similarity'))}</strong></div>
        <div class="metric"><span>Audio duration</span><strong>{esc(lane.get('durations_sec', {}).get('audio'))}s</strong></div>
        <div class="metric"><span>Base duration</span><strong>{esc(lane.get('durations_sec', {}).get('base_video'))}s</strong></div>
      </div>
      <pre>{json_block(lane.get('checks', {}))}</pre>
    </section>
    <section>
      <h2>A/V Contract</h2>
      <pre>{json_block(contract)}</pre>
    </section>
    <section>
      <h2>Report</h2>
      <div class="rendered-markdown">{markdown_to_html(report_md)}</div>
    </section>
  </div>
</main>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a static persona-dream bakeoff review page.")
    parser.add_argument("--run-dir", required=True, help="Bakeoff run directory.")
    parser.add_argument("--out", default=None, help="Output HTML path.")
    args = parser.parse_args()

    root = Path(args.run_dir).expanduser().resolve()
    out = Path(args.out).expanduser().resolve() if args.out else root / "review-page" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_html(root))
    print(out)


if __name__ == "__main__":
    main()

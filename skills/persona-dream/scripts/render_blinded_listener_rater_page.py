#!/usr/bin/env python3
"""Render a static blinded listener-study rater page.

The page is a collection aid, not an analyzer. It exposes only stimulus ids and
blinded audio filenames, produces schema-compatible JSONL, and writes a receipt
that explicitly does not prove perceived emotion or Embry identity.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent.parent
DEFAULT_STUDY_DIR = ROOT / "reports/goal_v5/continuity/blinded_listener_study"


def utc_now() -> str:
    return datetime.now().astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def artifact(path: Path) -> dict[str, Any]:
    return {
        "path": rel(path),
        "exists": path.is_file(),
        "bytes": path.stat().st_size if path.is_file() else 0,
        "sha256": sha_file(path) if path.is_file() else None,
    }


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_bundle_path(study_dir: Path, raw: str | None) -> Path:
    if not isinstance(raw, str) or not raw:
        return Path("")
    path = Path(raw)
    if path.is_absolute():
        return path
    if raw.startswith("reports/"):
        return ROOT / raw
    return study_dir / raw


def allowed_tones(response_schema: dict[str, Any], prereg: dict[str, Any]) -> list[str]:
    schema_values = (
        response_schema.get("response_object_contract", {})
        .get("target_emotion_choice", {})
        .get("allowed_values")
    )
    if isinstance(schema_values, list) and schema_values:
        return [str(value) for value in schema_values]
    tones = {
        str((stimulus.get("voice_delivery") or {}).get("tone"))
        for stimulus in prereg.get("stimuli") or []
        if (stimulus.get("voice_delivery") or {}).get("tone")
    }
    return sorted(tones)


def build_blinded_stimuli(study_dir: Path, prereg: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    stimuli_by_condition = {str(item.get("condition")): item for item in prereg.get("stimuli") or []}
    out_dir = study_dir / "blinded_stimuli"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    failed_gates: list[str] = []
    for manifest in sorted(prereg.get("presentation_manifest") or [], key=lambda item: int(item.get("slot") or 0)):
        condition = str(manifest.get("condition") or "")
        stimulus_id = str(manifest.get("stimulus_id") or "")
        source = stimuli_by_condition.get(condition)
        if not source:
            failed_gates.append(f"stimulus_in_preregistration:{stimulus_id}")
            continue
        source_audio = resolve_bundle_path(study_dir, source.get("audio"))
        blinded_audio = out_dir / f"{stimulus_id}.wav"
        source_exists = source_audio.is_file()
        source_hash = sha_file(source_audio) if source_exists else None
        source_bytes = source_audio.stat().st_size if source_exists else None
        hash_match = source_exists and source_hash == source.get("sha256")
        bytes_match = source_exists and source_bytes == source.get("bytes")
        if not hash_match:
            failed_gates.append(f"stimulus_hash_match:{stimulus_id}")
        if not bytes_match:
            failed_gates.append(f"stimulus_bytes_match:{stimulus_id}")
        if source_exists and (not blinded_audio.is_file() or sha_file(blinded_audio) != source_hash):
            shutil.copyfile(source_audio, blinded_audio)
        blinded_hash = sha_file(blinded_audio) if blinded_audio.is_file() else None
        rows.append(
            {
                "stimulus_id": stimulus_id,
                "slot": int(manifest.get("slot") or 0),
                "condition_key_for_receipt_only": condition,
                "source_audio": artifact(source_audio),
                "blinded_audio": artifact(blinded_audio),
                "hash_match": bool(hash_match and blinded_hash == source_hash),
                "bytes_match": bool(bytes_match and blinded_audio.is_file() and blinded_audio.stat().st_size == source_bytes),
                "page_audio_src": f"blinded_stimuli/{stimulus_id}.wav",
            }
        )
    return rows, failed_gates


def render_html(
    *,
    stimuli: list[dict[str, Any]],
    tones: list[str],
    schema: dict[str, Any],
    v2: dict[str, Any] | None = None,
) -> str:
    page_stimuli = [
        {
            "stimulus_id": row["stimulus_id"],
            "slot": row["slot"],
            "audio_src": row["page_audio_src"],
        }
        for row in stimuli
    ]
    config: dict[str, Any] = {"stimuli": page_stimuli, "tones": tones}
    if v2:
        config["v2"] = v2
    config_json = json.dumps(config, sort_keys=True)
    sample_schema = json.dumps(schema.get("example_row") or {}, indent=2, sort_keys=True)
    tone_options = "\n".join(
        f'<option value="{html.escape(tone)}">{html.escape(tone.replace("_", " "))}</option>' for tone in tones
    )
    cards: list[str] = []
    for row in page_stimuli:
        stimulus_id = html.escape(row["stimulus_id"])
        audio_src = html.escape(row["audio_src"])
        cards.append(
            f"""
      <section class="stimulus" data-stimulus-id="{stimulus_id}">
        <div class="stimulus-head">
          <h2>{stimulus_id}</h2>
          <audio controls preload="metadata" src="{audio_src}"></audio>
        </div>
        <label>Emotion
          <select data-field="target_emotion_choice">
            <option value=""></option>
            {tone_options}
          </select>
        </label>
        <label>Same Speaker
          <select data-field="embry_identity">
            <option value=""></option>
            <option value="yes">yes</option>
            <option value="no">no</option>
          </select>
        </label>
        <label>Speaker Confidence
          <input data-field="identity_confidence" type="number" min="1" max="5" step="1">
        </label>
        <label>Naturalness
          <input data-field="naturalness" type="number" min="1" max="5" step="1">
        </label>
        <label>Same Meaning
          <select data-field="content_equivalent">
            <option value=""></option>
            <option value="yes">yes</option>
            <option value="no">no</option>
          </select>
        </label>
        <label>Rank
          <input data-field="preference_rank" type="number" min="1" max="{len(page_stimuli)}" step="1">
        </label>
      </section>
"""
        )
    cards_html = "\n".join(cards)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Listener Study Rater</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #17202a;
      --muted: #5c6670;
      --line: #d7dce2;
      --paper: #f7f8fa;
      --panel: #ffffff;
      --accent: #0f766e;
      --bad: #a32020;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font: 15px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--paper);
      letter-spacing: 0;
    }}
    main {{
      width: min(1180px, calc(100vw - 32px));
      margin: 24px auto;
      display: grid;
      grid-template-columns: minmax(0, 1fr) 360px;
      gap: 18px;
      align-items: start;
    }}
    header {{
      grid-column: 1 / -1;
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: end;
      border-bottom: 1px solid var(--line);
      padding-bottom: 12px;
    }}
    h1, h2 {{ margin: 0; font-weight: 650; }}
    h1 {{ font-size: 24px; }}
    h2 {{ font-size: 18px; }}
    .meta {{ color: var(--muted); font-size: 13px; }}
    .stimuli {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }}
    .stimulus, .output {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }}
    .stimulus {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      min-width: 0;
    }}
    .stimulus-head {{
      grid-column: 1 / -1;
      display: grid;
      gap: 8px;
    }}
    audio {{ width: 100%; min-width: 0; }}
    label {{ display: grid; gap: 5px; font-size: 13px; color: var(--muted); }}
    input, select, textarea {{
      width: 100%;
      min-height: 36px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      padding: 7px 9px;
      font: inherit;
    }}
    textarea {{
      min-height: 220px;
      resize: vertical;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
    }}
    .output {{ display: grid; gap: 12px; position: sticky; top: 16px; }}
    .actions {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    button {{
      min-height: 36px;
      border: 1px solid var(--accent);
      border-radius: 6px;
      background: var(--accent);
      color: white;
      padding: 7px 10px;
      font: inherit;
      cursor: pointer;
    }}
    button.secondary {{ background: #fff; color: var(--accent); }}
    .status {{ min-height: 22px; color: var(--muted); font-size: 13px; }}
    .status.error {{ color: var(--bad); }}
    details {{
      border-top: 1px solid var(--line);
      padding-top: 10px;
      color: var(--muted);
      font-size: 13px;
    }}
    pre {{
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      margin: 8px 0 0;
      color: var(--ink);
      font-size: 12px;
    }}
    @media (max-width: 860px) {{
      main {{ grid-template-columns: 1fr; width: min(100vw - 20px, 680px); }}
      .stimuli {{ grid-template-columns: 1fr; }}
      .output {{ position: static; }}
    }}
    @media (max-width: 520px) {{
      header {{ display: grid; }}
      .stimulus {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Listener Study Rater</h1>
        <div class="meta">{len(page_stimuli)} audio stimuli; one JSONL row per rater.</div>
      </div>
      <label>Rater ID
        <input id="rater-id" autocomplete="off" placeholder="human_001">
      </label>
      <label id="attention-wrap" hidden>Final word of the sentence
        <input id="attention-word" autocomplete="off" placeholder="one word">
      </label>
    </header>
    <div class="stimuli">
      {cards_html}
    </div>
    <aside class="output">
      <h2>Response Row</h2>
      <div class="actions">
        <button id="build-row" type="button">Build Row</button>
        <button id="copy-row" type="button" class="secondary">Copy</button>
        <button id="download-row" type="button" class="secondary">Download</button>
      </div>
      <textarea id="jsonl-row" spellcheck="false"></textarea>
      <div id="status" class="status"></div>
      <details>
        <summary>Schema Example</summary>
        <pre>{html.escape(sample_schema)}</pre>
      </details>
    </aside>
  </main>
  <script type="application/json" id="study-config">{html.escape(config_json)}</script>
  <script>
    const config = JSON.parse(document.getElementById("study-config").textContent);
    const statusEl = document.getElementById("status");
    const outputEl = document.getElementById("jsonl-row");

    function intValue(value) {{
      const parsed = Number.parseInt(value, 10);
      return Number.isInteger(parsed) ? parsed : null;
    }}

    function setStatus(message, isError = false) {{
      statusEl.textContent = message;
      statusEl.classList.toggle("error", isError);
    }}

    function fnv1a32(text) {{
      let value = 0x811c9dc5;
      for (const byte of new TextEncoder().encode(text)) {{
        value ^= byte;
        value = Math.imul(value, 0x01000193) >>> 0;
      }}
      return value >>> 0;
    }}

    function appliedOrder(raterId) {{
      if (!config.v2 || !raterId) return null;
      const sequences = config.v2.orders;
      return sequences[fnv1a32(config.v2.salt + ":" + raterId) % sequences.length];
    }}

    function reorderStimuli() {{
      const raterId = document.getElementById("rater-id").value.trim();
      const order = appliedOrder(raterId);
      if (!order) return;
      const container = document.querySelector(".stimuli");
      order.forEach((stimulusId) => {{
        const section = container.querySelector(`[data-stimulus-id="${{stimulusId}}"]`);
        if (section) container.appendChild(section);
      }});
    }}

    if (config.v2) {{
      document.getElementById("attention-wrap").hidden = false;
      document.getElementById("rater-id").addEventListener("input", reorderStimuli);
    }}

    function buildRow() {{
      const raterId = document.getElementById("rater-id").value.trim();
      const errors = [];
      if (!raterId) errors.push("rater_id");
      const attentionWord = config.v2
        ? document.getElementById("attention-word").value.trim()
        : null;
      if (config.v2 && !attentionWord) errors.push("attention_final_word");
      const responses = [];
      document.querySelectorAll(".stimulus").forEach((section) => {{
        const response = {{ stimulus_id: section.dataset.stimulusId }};
        section.querySelectorAll("[data-field]").forEach((field) => {{
          const name = field.dataset.field;
          const raw = field.value;
          if (["identity_confidence", "naturalness", "preference_rank"].includes(name)) {{
            response[name] = intValue(raw);
          }} else {{
            response[name] = raw;
          }}
        }});
        responses.push(response);
      }});
      const ranks = responses.map((row) => row.preference_rank).filter((value) => Number.isInteger(value));
      const rankSet = new Set(ranks);
      const expectedRanks = config.stimuli.map((_, index) => index + 1).join(",");
      const actualRanks = [...rankSet].sort((a, b) => a - b).join(",");
      responses.forEach((response) => {{
        ["target_emotion_choice", "embry_identity", "content_equivalent"].forEach((field) => {{
          if (!response[field]) errors.push(`${{response.stimulus_id}}:${{field}}`);
        }});
        ["identity_confidence", "naturalness"].forEach((field) => {{
          if (!Number.isInteger(response[field]) || response[field] < 1 || response[field] > 5) {{
            errors.push(`${{response.stimulus_id}}:${{field}}`);
          }}
        }});
      }});
      if (actualRanks !== expectedRanks) errors.push("preference_rank_permutation");
      const row = {{
        rater_id: raterId,
        created_at: new Date().toISOString().replace(/\\.\\d{{3}}Z$/, "Z"),
        responses
      }};
      if (config.v2) {{
        row.attention_final_word = attentionWord;
        row.presentation_order = appliedOrder(raterId);
      }}
      outputEl.value = JSON.stringify(row);
      setStatus(errors.length ? `Missing or invalid: ${{errors.join(", ")}}` : "Ready to append.", errors.length > 0);
      return errors.length === 0 ? row : null;
    }}

    document.getElementById("build-row").addEventListener("click", buildRow);
    document.getElementById("copy-row").addEventListener("click", async () => {{
      if (!outputEl.value) buildRow();
      if (!outputEl.value) return;
      await navigator.clipboard.writeText(outputEl.value + "\\n");
      setStatus("Copied JSONL row.");
    }});
    document.getElementById("download-row").addEventListener("click", () => {{
      if (!outputEl.value) buildRow();
      if (!outputEl.value) return;
      const blob = new Blob([outputEl.value + "\\n"], {{ type: "application/x-ndjson" }});
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "listener-response.jsonl";
      anchor.click();
      URL.revokeObjectURL(url);
      setStatus("Downloaded JSONL row.");
    }});
  </script>
</body>
</html>
"""


def run(args: argparse.Namespace) -> dict[str, Any]:
    study_dir = args.study_dir
    prereg_path = study_dir / "PREREGISTRATION.json"
    schema_path = study_dir / "RESPONSE_SCHEMA.json"
    failed_gates: list[str] = []
    prereg = load_json(prereg_path) if prereg_path.is_file() else {}
    response_schema = load_json(schema_path) if schema_path.is_file() else {}
    if not prereg:
        failed_gates.append("preregistration_exists")
    if not response_schema:
        failed_gates.append("response_schema_exists")
    stimuli, stimulus_gates = build_blinded_stimuli(study_dir, prereg)
    failed_gates.extend(stimulus_gates)
    if not stimuli:
        failed_gates.append("blinded_stimuli_present")
    tones = allowed_tones(response_schema, prereg)
    if not tones:
        failed_gates.append("allowed_tones_present")
    prereg_v2_path = study_dir / "PREREGISTRATION_V2.json"
    v2cfg = None
    if prereg_v2_path.is_file():
        prereg_v2 = load_json(prereg_v2_path)
        presentation = prereg_v2.get("presentation") or {}
        slot_ids = presentation.get("stimulus_ids_in_slot_order") or []
        v2cfg = {
            "salt": presentation.get("order_salt"),
            "orders": [
                [slot_ids[slot] for slot in row]
                for row in presentation.get("williams_square_slots") or []
                if all(isinstance(slot, int) and slot < len(slot_ids) for slot in row)
            ],
            "attention_question": (prereg_v2.get("attention_check") or {}).get("question"),
        }
    html_text = render_html(stimuli=stimuli, tones=tones, schema=response_schema, v2=v2cfg)
    forbidden_condition_labels = sorted(
        {
            str(item.get("condition"))
            for item in prereg.get("presentation_manifest") or []
            if item.get("condition")
            and (
                f"stimuli/{item.get('condition')}.wav" in html_text
                or f">{item.get('condition')}<" in html_text
                or f'"condition":"{item.get("condition")}"' in html_text
            )
        }
    )
    if forbidden_condition_labels:
        failed_gates.append("condition_labels_absent_from_page")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html_text, encoding="utf-8")
    created_at = utc_now()
    if args.receipt_out and args.receipt_out.is_file():
        try:
            existing = load_json(args.receipt_out)
            if existing.get("schema") == "persona_dream.blinded_listener_rater_page_receipt.v1":
                created_at = str(existing.get("created_at") or created_at)
        except Exception:
            created_at = utc_now()
    receipt = {
        "schema": "persona_dream.blinded_listener_rater_page_receipt.v1",
        "created_at": created_at,
        "status": "PASS_BLINDED_LISTENER_RATER_PAGE_READY" if not failed_gates else "BLOCKED_BLINDED_LISTENER_RATER_PAGE",
        "mocked": False,
        "live": False,
        "study_dir": rel(study_dir),
        "design_version": "v2" if v2cfg else "v1",
        "page": artifact(args.out),
        "preregistration": artifact(prereg_path),
        "preregistration_v2": artifact(prereg_v2_path) if v2cfg else None,
        "response_schema": artifact(schema_path),
        "responses_target": rel(study_dir / ("responses_v2.jsonl" if v2cfg else "responses.jsonl")),
        "blinded_stimuli": stimuli,
        "failed_gates": failed_gates,
        "claims": {
            "proves": [
                "a static rater page was rendered from the preregistered bundle",
                "raters receive stimulus ids and blinded audio filenames instead of condition-labelled audio filenames",
                "the page can produce rows matching the listener response field contract",
            ]
            if not failed_gates
            else [],
            "does_not_prove": [
                "human perception of target emotion",
                "human recognition of Embry",
                "listener-study analysis",
                "SPARTA production conversation-service consumption",
                "Persona Dream immutable-goal completion",
            ],
        },
    }
    if args.receipt_out:
        args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
        args.receipt_out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir", type=Path, default=DEFAULT_STUDY_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_STUDY_DIR / "rater_page.html")
    parser.add_argument("--receipt-out", type=Path, default=DEFAULT_STUDY_DIR / "RATER_PAGE_RECEIPT.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt = run(args)
    summary = {
        "status": receipt["status"],
        "page": receipt["page"]["path"],
        "receipt": rel(args.receipt_out),
        "blinded_stimuli_count": len(receipt["blinded_stimuli"]),
        "failed_gates": receipt["failed_gates"],
    }
    print(json.dumps(summary if args.json else summary, indent=2, sort_keys=True))
    return 0 if receipt["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())

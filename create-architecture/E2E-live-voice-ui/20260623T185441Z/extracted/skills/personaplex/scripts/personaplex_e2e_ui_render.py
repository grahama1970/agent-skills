#!/usr/bin/env python3
from __future__ import annotations
"""Render PersonaPlex live voice session receipts as a SPARTA Chat-style UI.

The renderer is intentionally static-output friendly: the generated HTML can be
opened directly from disk, served via ``python -m http.server``, or checked by
unit tests without launching a browser.  It does not invent proof.  It renders
whatever the receipt says and highlights any false ``real_*`` row.
"""

import argparse
import html
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _bool_text(value: Any) -> str:
    return "true" if value is True else "false" if value is False else _esc(value)


def _load_json(path: str | Path) -> dict[str, Any]:
    raw = Path(path).read_text(encoding="utf-8")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"receipt must be a JSON object: {path}")
    return value


def _conversation(receipt: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    convo = receipt.get("conversation")
    if isinstance(convo, list):
        return [item for item in convo if isinstance(item, Mapping)]
    user_text = receipt.get("transcript") or receipt.get("user_transcript") or ""
    assistant_text = receipt.get("embry_response") or receipt.get("assistant_response") or ""
    return [
        {"role": "user", "speaker": "User", "text": user_text},
        {"role": "assistant", "speaker": "Embry", "text": assistant_text},
    ]


def _tool_trace(receipt: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    trace = receipt.get("tool_trace")
    if isinstance(trace, list):
        return [row for row in trace if isinstance(row, Mapping)]
    flags = receipt.get("real_flags") if isinstance(receipt.get("real_flags"), Mapping) else {}
    return [
        {
            "step": "deepgram_asr",
            "label": "Deepgram ASR",
            "summary": "speech_final=true" if flags.get("real_deepgram") else "speech_final not proven",
            "real_flag_name": "real_deepgram",
            "real_flag_value": bool(flags.get("real_deepgram")),
        },
        {
            "step": "turn_gate",
            "label": "Turn gate",
            "summary": "gate state recorded",
            "real_flag_name": "real_turn_gate",
            "real_flag_value": bool(flags.get("real_turn_gate")),
        },
        {
            "step": "memory_intent",
            "label": "Memory intent",
            "summary": "intent route recorded",
            "real_flag_name": "real_memory_intent",
            "real_flag_value": bool(flags.get("real_memory_intent")),
        },
        {
            "step": "recall_evidence",
            "label": "Recall / evidence",
            "summary": "evidence case attempted",
            "real_flag_name": "real_recall_evidence",
            "real_flag_value": bool(flags.get("real_recall_evidence")),
        },
        {
            "step": "gpu_personaplex",
            "label": "PersonaPlex GPU",
            "summary": "LMGen.step proof recorded",
            "real_flag_name": "real_gpu_personaplex",
            "real_flag_value": bool(flags.get("real_gpu_personaplex")),
        },
        {
            "step": "persistence_upsert",
            "label": "Persistence upsert",
            "summary": "conversation_history upsert attempted",
            "real_flag_name": "real_persistence_upsert",
            "real_flag_value": bool(flags.get("real_persistence_upsert")),
        },
        {
            "step": "session_compaction",
            "label": "Session compaction",
            "summary": "rolling summary / CAS head attempted",
            "real_flag_name": "real_session_compaction",
            "real_flag_value": bool(flags.get("real_session_compaction")),
        },
    ]


def _all_real(trace: Iterable[Mapping[str, Any]]) -> bool:
    rows = list(trace)
    return bool(rows) and all(row.get("real_flag_value") is True for row in rows)


def _render_chat_messages(receipt: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for index, msg in enumerate(_conversation(receipt), 1):
        role = str(msg.get("role") or "message").lower()
        speaker = msg.get("speaker") or ("Embry" if role == "assistant" else "User")
        text = msg.get("text") or msg.get("content") or ""
        parts.append(
            f'''<article class="chat-message chat-message--{_esc(role)}" data-testid="chat-message-{_esc(role)}" data-message-index="{index}">
  <div class="chat-speaker">{_esc(speaker)}</div>
  <p>{_esc(text)}</p>
</article>'''
        )
    return "\n".join(parts)


def _detail_list(row: Mapping[str, Any]) -> str:
    details = row.get("details")
    if not isinstance(details, Mapping) or not details:
        return ""
    items = []
    for key, value in details.items():
        if isinstance(value, (dict, list)):
            rendered = json.dumps(value, sort_keys=True, separators=(",", ":"))
        else:
            rendered = value
        items.append(f"<li><span>{_esc(key)}</span><strong>{_esc(rendered)}</strong></li>")
    return '<ul class="trace-details">' + "".join(items) + "</ul>"


def _render_tool_trace(receipt: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for index, row in enumerate(_tool_trace(receipt), 1):
        flag_name = str(row.get("real_flag_name") or "real_unknown")
        flag_value = row.get("real_flag_value") is True
        state = "true" if flag_value else "false"
        parts.append(
            f'''<section class="trace-row trace-row--{state}" data-testid="tool-row" data-step="{_esc(row.get('step'))}" data-real-flag-name="{_esc(flag_name)}" data-real-flag-value="{state}">
  <div class="trace-row-main">
    <div>
      <span class="trace-index">{index:02d}</span>
      <h3>{_esc(row.get('label') or row.get('step'))}</h3>
      <p>{_esc(row.get('summary'))}</p>
    </div>
    <code>{_esc(flag_name)}={state}</code>
  </div>
  {_detail_list(row)}
</section>'''
        )
    return "\n".join(parts)


def _render_status_bar(receipt: Mapping[str, Any]) -> str:
    gate = receipt.get("gate_state") if isinstance(receipt.get("gate_state"), Mapping) else {}
    state = gate.get("state") or receipt.get("gate_state_text") or "UNKNOWN"
    queue = gate.get("queue_depth", receipt.get("queue_depth_at_release", "?"))
    turn = gate.get("turn_id", receipt.get("turn_id", "?"))
    generation = gate.get("generation", receipt.get("generation", "?"))
    return (
        f'<div class="status-chip" data-testid="gate-state">gate: {_esc(state)} | queue: {_esc(queue)} | turn: {_esc(turn)} | generation: {_esc(generation)}</div>'
    )


def _render_recall_cards(receipt: Mapping[str, Any]) -> str:
    items = receipt.get("recall_items")
    if not isinstance(items, list):
        items = []
    if not items:
        return '<p class="empty">No recall items were returned in this receipt.</p>'
    cards = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        cards.append(
            f'''<article class="recall-card" data-testid="recall-item">
  <h4>{_esc(item.get('title') or item.get('key') or item.get('id') or 'recall item')}</h4>
  <p>{_esc(item.get('snippet') or item.get('text') or item.get('summary') or '')}</p>
  <div class="scoreline">BM25 {_esc(item.get('bm25_score', item.get('bm25')))} · dense {_esc(item.get('dense_score', item.get('dense')))} · score {_esc(item.get('score'))}</div>
</article>'''
        )
    return "\n".join(cards)


def render_receipt_html(receipt: Mapping[str, Any], *, title: str = "PersonaPlex E2E Live Voice UI") -> str:
    trace = _tool_trace(receipt)
    all_real = _all_real(trace)
    false_count = sum(1 for row in trace if row.get("real_flag_value") is not True)
    fixture_note = receipt.get("fixture_only") is True or "fixture" in str(receipt.get("claim_boundary", "")).lower()
    banner_class = "ok" if all_real and not fixture_note else "warn"
    banner_text = "ALL LIVE TOOL ROWS REAL=TRUE" if all_real and not fixture_note else f"NOT A FULL LIVE PROOF · false rows: {false_count}"
    if fixture_note:
        banner_text = "RENDERING FIXTURE · NOT LIVE SERVICE PROOF"
    created = receipt.get("created_at_utc") or receipt.get("created_at") or "unknown"
    session = receipt.get("session_id") or "unknown-session"
    source_hash = receipt.get("receipt_sha256") or "computed by probe"
    evidence = receipt.get("evidence_summary") if isinstance(receipt.get("evidence_summary"), Mapping) else {}
    intent = receipt.get("intent") if isinstance(receipt.get("intent"), Mapping) else {}

    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_esc(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --ink: #111827;
      --muted: #5b6472;
      --line: #d9dde5;
      --line-strong: #b9c0cc;
      --good-bg: #eefbf3;
      --good-ink: #17613a;
      --bad-bg: #fff2f2;
      --bad-ink: #9b1c1c;
      --accent: #243447;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--ink); }}
    .shell {{ max-width: 1200px; margin: 0 auto; padding: 28px; }}
    header {{ display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; margin-bottom: 20px; }}
    h1 {{ font-size: 28px; line-height: 1.1; margin: 0 0 8px; letter-spacing: -0.03em; }}
    .lede {{ margin: 0; color: var(--muted); max-width: 820px; }}
    .banner {{ border: 1px solid var(--line); border-radius: 999px; padding: 10px 14px; font-size: 12px; font-weight: 800; letter-spacing: 0.05em; white-space: nowrap; }}
    .banner.ok {{ color: var(--good-ink); background: var(--good-bg); }}
    .banner.warn {{ color: var(--bad-ink); background: var(--bad-bg); }}
    .grid {{ display: grid; grid-template-columns: 0.92fr 1.08fr; gap: 18px; align-items: start; }}
    .panel {{ background: var(--panel); border: 1px solid var(--line); border-radius: 22px; padding: 18px; box-shadow: 0 1px 2px rgba(17,24,39,0.04); }}
    .panel h2 {{ margin: 0 0 12px; font-size: 14px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); }}
    .chat-message {{ border: 1px solid var(--line); border-radius: 18px; padding: 14px 16px; margin-bottom: 12px; background: #fbfcfe; }}
    .chat-message--assistant {{ background: #f3f7fb; border-color: #cfd8e3; }}
    .chat-speaker {{ font-weight: 800; margin-bottom: 6px; color: var(--accent); }}
    .chat-message p {{ margin: 0; line-height: 1.45; }}
    .trace-row {{ border: 1px solid var(--line); border-radius: 16px; padding: 14px; margin-bottom: 10px; background: #fff; }}
    .trace-row--true {{ border-color: #b7dec4; background: var(--good-bg); }}
    .trace-row--false {{ border-color: #f0b2b2; background: var(--bad-bg); }}
    .trace-row-main {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; }}
    .trace-index {{ color: var(--muted); font-size: 12px; font-weight: 700; }}
    .trace-row h3 {{ margin: 3px 0 5px; font-size: 16px; }}
    .trace-row p {{ margin: 0; color: var(--muted); line-height: 1.4; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; border: 1px solid var(--line-strong); background: rgba(255,255,255,.7); border-radius: 999px; padding: 7px 9px; white-space: nowrap; }}
    .trace-details {{ display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 8px; padding: 12px 0 0; margin: 0; list-style: none; }}
    .trace-details li {{ border-top: 1px solid rgba(17,24,39,.08); padding-top: 8px; min-width: 0; }}
    .trace-details span {{ display: block; color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .07em; }}
    .trace-details strong {{ display: block; overflow-wrap: anywhere; font-size: 12px; margin-top: 2px; }}
    .status-row {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 18px; }}
    .status-chip {{ display: inline-flex; align-items: center; border: 1px solid var(--line); border-radius: 999px; background: #fff; padding: 9px 12px; font-weight: 700; color: var(--accent); }}
    .meta {{ display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 8px; margin-top: 12px; }}
    .meta div, .summary-card {{ border: 1px solid var(--line); border-radius: 14px; padding: 10px; background: #fbfcfe; overflow-wrap: anywhere; }}
    .meta span, .summary-card span {{ display: block; color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .07em; margin-bottom: 4px; }}
    .meta strong {{ font-size: 13px; }}
    .recall-card {{ border: 1px solid var(--line); border-radius: 14px; padding: 12px; margin-bottom: 10px; background: #fff; }}
    .recall-card h4 {{ margin: 0 0 6px; }}
    .recall-card p {{ margin: 0 0 8px; color: var(--muted); }}
    .scoreline {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; color: var(--accent); }}
    .empty {{ color: var(--muted); font-style: italic; }}
    footer {{ margin-top: 18px; color: var(--muted); font-size: 12px; }}
    @media (max-width: 900px) {{ .grid {{ grid-template-columns: 1fr; }} header {{ display: block; }} .banner {{ display: inline-flex; margin-top: 12px; }} }}
  </style>
</head>
<body>
  <main class="shell" data-testid="personaplex-e2e-ui">
    <header>
      <div>
        <h1>PersonaPlex E2E live voice verification</h1>
        <p class="lede">SPARTA Chat-style proof surface for Deepgram ASR → turn gate → memory intent → recall/evidence → PersonaPlex GPU → persistence upsert → session compaction.</p>
      </div>
      <div class="banner {banner_class}" data-testid="all-real-banner">{_esc(banner_text)}</div>
    </header>

    <div class="status-row">
      {_render_status_bar(receipt)}
      <div class="status-chip" data-testid="session-id">session: {_esc(session)}</div>
      <div class="status-chip" data-testid="created-at">created: {_esc(created)}</div>
    </div>

    <section class="grid">
      <div>
        <section class="panel" aria-label="Chat messages">
          <h2>Chat messages</h2>
          {_render_chat_messages(receipt)}
        </section>

        <section class="panel" aria-label="Intent and evidence" style="margin-top: 18px;">
          <h2>Intent / evidence summary</h2>
          <div class="summary-card" data-testid="intent-summary"><span>Intent route</span><strong>{_esc(intent.get('route'))} ({_esc(intent.get('confidence'))})</strong></div>
          <div class="summary-card" data-testid="evidence-summary" style="margin-top: 8px;"><span>Evidence</span><strong>can_answer={_bool_text(evidence.get('can_answer'))} · route={_esc(evidence.get('route'))}</strong></div>
          <div class="summary-card" data-testid="upsert-summary" style="margin-top: 8px;"><span>Upsert</span><strong>{_esc(receipt.get('upsert_summary'))}</strong></div>
        </section>
      </div>

      <div>
        <section class="panel" aria-label="Tool trace">
          <h2>Tool trace per turn</h2>
          {_render_tool_trace(receipt)}
        </section>

        <section class="panel" aria-label="Recall items" style="margin-top: 18px;">
          <h2>Recall items</h2>
          {_render_recall_cards(receipt)}
        </section>
      </div>
    </section>

    <section class="panel" aria-label="Receipt metadata" style="margin-top: 18px;">
      <h2>Receipt metadata</h2>
      <div class="meta">
        <div><span>schema</span><strong>{_esc(receipt.get('schema'))}</strong></div>
        <div><span>receipt hash</span><strong>{_esc(source_hash)}</strong></div>
        <div><span>fallback used</span><strong>{_bool_text(receipt.get('fallback_used'))}</strong></div>
        <div><span>claim boundary</span><strong>{_esc(receipt.get('claim_boundary'))}</strong></div>
      </div>
    </section>

    <footer>Rendered from a PersonaPlex E2E receipt. False real rows or fixture banners are not acceptable final live-demo proof.</footer>
  </main>
</body>
</html>
'''


def write_receipt_ui(receipt: Mapping[str, Any], out_path: str | Path) -> Path:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_receipt_html(receipt), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render PersonaPlex E2E live voice receipt as static HTML")
    parser.add_argument("receipt_json")
    parser.add_argument("--out", default="personaplex-e2e-live-voice-ui.html")
    parser.add_argument("--require-all-real", action="store_true", help="Exit 2 unless all rendered tool rows have real_flag_value=true and receipt is not fixture_only.")
    args = parser.parse_args(argv)
    receipt = _load_json(args.receipt_json)
    path = write_receipt_ui(receipt, args.out)
    print(str(path))
    trace = _tool_trace(receipt)
    if args.require_all_real and (not _all_real(trace) or receipt.get("fixture_only") is True):
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

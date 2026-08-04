#!/usr/bin/env python3
"""Render persona-dream run directories into one self-contained journal + chat page.

Scaffold, not a finished design. A designer restyles this later, so the output is
structured for that: semantic class names, a documented CSS custom-property
palette at the top of the stylesheet, and a comment block in the HTML naming
which blocks are structural (data-bound, do not remove) versus stylistic.

Inputs, all read-only, all produced by ``./run.sh generate``:

    journal.md                  annotated prose: ``[tone: x · 0.6 · requested]``
                                lines, ``[^n]`` markers, a ``## Sources`` block
    residue_links.json          ``items``: the recalled memories (id, scope, text)
    contradiction_report.json   ``contradictions``: item_a/item_b/bridge_a/bridge_b
    dream_packet.json           persona, run_id, memory_web_entities/size
    conversation.jsonl          optional: role/text/created_at/optional audio

Nothing is invented. Every field with no real source in the run dir renders as an
explicit empty state naming what is missing and, where useful, the command that
would produce it. Tone chips are labelled ``requested`` because the renderer can
only prove what was asked of Chatterbox, never what the audio achieved.

The page is self-contained: inline CSS and JS, no network references at all, so
it opens from ``file://``.
"""
from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any

#: Host directory Chatterbox's container ``/out`` maps to.
CHATTERBOX_LOGS = Path.home() / "workspace" / "experiments" / "chatterbox" / "logs"

TONE_LINE = re.compile(r"^\[tone:\s*([^·\]]+?)\s*·\s*([^·\]]+?)\s*·\s*([^\]]+?)\s*\]$")
FOOTNOTE_DEF = re.compile(r"^\[\^([^\]]+)\]:\s*(.*)$")
MARKER = re.compile(r"\[\^([^\]]+)\]")


# --------------------------------------------------------------------------- read


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def parse_journal(text: str) -> dict[str, Any]:
    """Split journal.md into title, preamble, tone-tagged paragraphs, footnote defs.

    The renderer that writes journal.md emits one ``[tone: ...]`` line immediately
    before each prose paragraph, so a paragraph inherits the last tone seen.
    """
    body, _, sources = text.partition("## Sources")
    title = ""
    preamble: list[str] = []
    paragraphs: list[dict[str, Any]] = []
    pending: dict[str, str] | None = None

    for block in [b.strip() for b in body.split("\n\n") if b.strip()]:
        if block.startswith("# "):
            title = block[2:].strip()
            continue
        m = TONE_LINE.match(block)
        if m:
            pending = {"tone": m.group(1), "intensity": m.group(2), "status": m.group(3)}
            continue
        # A tone line can share a block with its paragraph.
        first, _, rest = block.partition("\n")
        m = TONE_LINE.match(first.strip())
        if m and rest.strip():
            paragraphs.append({"tone": m.group(1), "intensity": m.group(2),
                               "status": m.group(3), "text": rest.strip()})
            pending = None
            continue
        if block.startswith("*") or block.startswith("**"):
            preamble.append(block.strip("*").strip())
            continue
        paragraphs.append({**(pending or {"tone": "", "intensity": "", "status": ""}),
                           "text": block})
        pending = None

    footnotes: dict[str, str] = {}
    for line in sources.splitlines():
        m = FOOTNOTE_DEF.match(line.strip())
        if m:
            footnotes[m.group(1)] = m.group(2).strip()
    return {"title": title, "preamble": preamble, "paragraphs": paragraphs,
            "footnotes": footnotes}


def marker_map(items: list[dict[str, Any]]) -> dict[str, int]:
    """source_id -> footnote number, in the same order render_journal_entry uses."""
    out: dict[str, int] = {}
    for item in items:
        sid = str(item.get("source_id") or "")
        if sid and sid not in out:
            out[sid] = len(out) + 1
    return out


def find_audio(run_dir: Path, label: str | None) -> tuple[Path | None, list[str]]:
    """Return (wav path or None, list of locations searched).

    Absence is a first-class outcome: a run may simply never have been spoken.
    """
    searched: list[str] = []
    candidates = [run_dir / "finished_response.wav"]
    if label:
        candidates.append(CHATTERBOX_LOGS / label / "finished_response.wav")
    for cand in candidates:
        searched.append(str(cand))
        if cand.is_file():
            return cand, searched
    searched.append(f"{run_dir}/*.wav")
    loose = sorted(run_dir.glob("*.wav"))
    if loose:
        return loose[0], searched
    return None, searched


def read_conversation(path: Path) -> tuple[list[dict[str, Any]], str | None]:
    """Return (messages, error). Absent file is not an error, it is an empty state."""
    if not path.is_file():
        return [], None
    messages: list[dict[str, Any]] = []
    bad = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            bad += 1
            continue
        if isinstance(row, dict):
            messages.append(row)
    return messages, (f"{bad} line(s) in conversation.jsonl were not valid JSON" if bad else None)


def load_run(run_dir: Path, label: str | None = None) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    packet = read_json(run_dir / "dream_packet.json")
    residue = read_json(run_dir / "residue_links.json")
    contra = read_json(run_dir / "contradiction_report.json")
    receipt = read_json(run_dir / "JOURNAL_RENDER_RECEIPT.json")
    manifest = read_json(run_dir / "manifest.json")

    journal_path = run_dir / "journal.md"
    journal = parse_journal(journal_path.read_text(encoding="utf-8")) if journal_path.is_file() else {
        "title": "", "preamble": [], "paragraphs": [], "footnotes": {}}

    items = residue.get("items") or []
    markers = marker_map(items)
    sources = []
    for item in items:
        sid = str(item.get("source_id") or "")
        if sid not in markers:
            continue
        sources.append({
            "n": markers[sid],
            "source_id": sid,
            "scope": item.get("scope") or "",
            "excerpt": " ".join(str(item.get("text") or "").split()),
            "synthetic": bool(item.get("synthetic")),
        })
    sources.sort(key=lambda s: s["n"])

    tensions = []
    for row in contra.get("contradictions") or []:
        a, b = str(row.get("item_a") or ""), str(row.get("item_b") or "")
        tensions.append({
            "a_n": markers.get(a), "b_n": markers.get(b),
            "a_id": a, "b_id": b,
            "bridge_a": row.get("bridge_a") or "", "bridge_b": row.get("bridge_b") or "",
            "description": row.get("description") or "", "score": row.get("score"),
        })

    web = {
        "entities": packet.get("memory_web_entities") or [],
        "size": packet.get("memory_web_size"),
        "footnote": journal["footnotes"].get("web", ""),
    }

    audio_label = label or str(packet.get("run_id") or run_dir.name)
    audio_path, audio_searched = find_audio(run_dir, audio_label)
    conversation, conv_error = read_conversation(run_dir / "conversation.jsonl")

    return {
        "run_dir": str(run_dir),
        "run_id": str(packet.get("run_id") or manifest.get("run_id") or run_dir.name),
        "persona": str(packet.get("persona") or receipt.get("persona") or ""),
        "created_at": str(packet.get("created_at") or manifest.get("created_at")
                          or receipt.get("created_at") or ""),
        "journal": journal,
        "journal_present": journal_path.is_file(),
        "sources": sources,
        "tensions": tensions,
        "web": web,
        "receipt": receipt,
        "audio": str(audio_path) if audio_path else "",
        "audio_searched": audio_searched,
        "conversation": conversation,
        "conversation_error": conv_error,
        "conversation_path": str(run_dir / "conversation.jsonl"),
        "conversation_present": (run_dir / "conversation.jsonl").is_file(),
    }


# --------------------------------------------------------------------------- html


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def prose_html(text: str, run_id: str) -> str:
    """Escape prose, then turn ``[^n]`` markers into in-page links."""
    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        return (f'<a class="pd-ref" href="#src-{esc(run_id)}-{esc(key)}" '
                f'data-ref="{esc(key)}">[{esc(key)}]</a>')
    return MARKER.sub(repl, esc(text)).replace("\n", "<br>")


def tone_chip(para: dict[str, Any]) -> str:
    tone = para.get("tone") or ""
    if not tone:
        return ('<span class="pd-chip pd-chip--empty">no tone annotation recorded'
                "</span>")
    status = para.get("status") or "requested"
    return (
        '<span class="pd-chip pd-chip--tone">'
        f'<span class="pd-chip__tone">{esc(tone)}</span>'
        f'<span class="pd-chip__intensity">{esc(para.get("intensity") or "—")}</span>'
        f'<span class="pd-chip__status">{esc(status)}</span>'
        "</span>"
    )


def empty(message: str, command: str = "") -> str:
    cmd = f'<pre class="pd-empty__cmd"><code>{esc(command)}</code></pre>' if command else ""
    return f'<div class="pd-empty"><p>{esc(message)}</p>{cmd}</div>'


def render_sources(run: dict[str, Any]) -> str:
    if not run["sources"]:
        return empty(
            "No recalled memories in residue_links.json for this run — nothing to cite.")
    rows = []
    for src in run["sources"]:
        rows.append(
            f'<li class="pd-source" id="src-{esc(run["run_id"])}-{src["n"]}">'
            f'<span class="pd-source__n">[{src["n"]}]</span>'
            f'<code class="pd-source__id">{esc(src["source_id"])}</code>'
            f'<span class="pd-source__scope">{esc(src["scope"] or "no scope recorded")}</span>'
            + ('<span class="pd-source__flag">synthetic</span>' if src["synthetic"] else "")
            + f'<p class="pd-source__excerpt">{esc(src["excerpt"]) or "no excerpt recorded"}</p>'
            "</li>"
        )
    return f'<ol class="pd-sources">{"".join(rows)}</ol>'


def render_tensions(run: dict[str, Any]) -> str:
    if not run["tensions"]:
        return empty("No tension pairs in contradiction_report.json for this run.")
    rows = []
    for t in run["tensions"]:
        a = f'[{t["a_n"]}]' if t["a_n"] else t["a_id"] or "unmapped"
        b = f'[{t["b_n"]}]' if t["b_n"] else t["b_id"] or "unmapped"
        score = "" if t["score"] is None else f'<span class="pd-tension__score">{esc(t["score"])}</span>'
        rows.append(
            '<li class="pd-tension">'
            f'<span class="pd-tension__axis">{esc(t["bridge_a"])}</span>'
            '<span class="pd-tension__vs">held against</span>'
            f'<span class="pd-tension__axis">{esc(t["bridge_b"])}</span>'
            f'<span class="pd-tension__pair">{esc(a)} ↔ {esc(b)}</span>'
            f"{score}"
            f'<p class="pd-tension__desc">{esc(t["description"])}</p>'
            "</li>"
        )
    return f'<ul class="pd-tensions">{"".join(rows)}</ul>'


def render_web(run: dict[str, Any]) -> str:
    web = run["web"]
    if not web["entities"] and web["size"] is None and not web["footnote"]:
        return empty(
            "No entity traversal recorded for this run — dream_packet.json has no "
            "memory_web_entities/memory_web_size and journal.md has no [^web] footnote.")
    size = web["size"] if web["size"] is not None else len(web["entities"])
    chips = "".join(f'<span class="pd-chip pd-chip--entity">{esc(e)}</span>'
                    for e in web["entities"])
    note = f'<p class="pd-web__note">{esc(web["footnote"])}</p>' if web["footnote"] else ""
    return (f'<div class="pd-web" id="src-{esc(run["run_id"])}-web">'
            f'<p class="pd-web__size">multi-hop traversal reached '
            f'<strong>{esc(size)}</strong> connected memories</p>'
            f'<div class="pd-web__entities">{chips or "<em>no entities recorded</em>"}</div>'
            f"{note}</div>")


def render_audio(run: dict[str, Any]) -> str:
    if not run["audio"]:
        looked = "; ".join(run["audio_searched"])
        return empty(f"No audio for this run. Looked in: {looked}")
    src = Path(run["audio"]).as_uri()
    return (f'<div class="pd-audio"><audio controls preload="none" src="{esc(src)}"></audio>'
            f'<code class="pd-audio__path">{esc(run["audio"])}</code></div>')


def render_journal_card(run: dict[str, Any]) -> str:
    if not run["journal_present"]:
        return (f'<article class="pd-card" data-run-id="{esc(run["run_id"])}">'
                f'<header class="pd-card__head"><h2>{esc(run["run_id"])}</h2></header>'
                + empty(f'No journal.md in {run["run_dir"]}.',
                        f'./skills/persona-dream/run.sh render-journal '
                        f'--run-dir {run["run_dir"]}')
                + "</article>")

    paras = "".join(
        '<div class="pd-para">'
        f'{tone_chip(p)}'
        f'<p class="pd-para__text">{prose_html(p["text"], run["run_id"])}</p>'
        "</div>"
        for p in run["journal"]["paragraphs"]
    ) or empty("journal.md has a header but no prose paragraphs.")

    preamble = "".join(f'<p class="pd-card__note">{esc(n)}</p>'
                       for n in run["journal"]["preamble"])
    receipt = run["receipt"]
    status = receipt.get("status") or "no render receipt"

    return (
        f'<article class="pd-card" data-run-id="{esc(run["run_id"])}">'
        '<header class="pd-card__head">'
        f'<h2 class="pd-card__title">{esc(run["journal"]["title"] or run["run_id"])}</h2>'
        '<dl class="pd-card__meta">'
        f'<dt>run</dt><dd><code>{esc(run["run_id"])}</code></dd>'
        f'<dt>created</dt><dd>{esc(run["created_at"] or "not recorded")}</dd>'
        f'<dt>receipt</dt><dd>{esc(status)}</dd>'
        f'<dt>dir</dt><dd><code>{esc(run["run_dir"])}</code></dd>'
        "</dl></header>"
        f'<div class="pd-card__preamble">{preamble}</div>'
        f'<section class="pd-section pd-section--prose">{paras}</section>'
        '<section class="pd-section pd-section--audio">'
        '<h3 class="pd-section__title">Spoken</h3>'
        f'{render_audio(run)}</section>'
        '<section class="pd-section pd-section--tensions">'
        '<h3 class="pd-section__title">Tensions</h3>'
        f'{render_tensions(run)}</section>'
        '<section class="pd-section pd-section--web">'
        '<h3 class="pd-section__title">Entity traversal</h3>'
        f'{render_web(run)}</section>'
        '<section class="pd-section pd-section--sources">'
        '<h3 class="pd-section__title">Sources</h3>'
        f'{render_sources(run)}</section>'
        "</article>"
    )


def render_chat(run: dict[str, Any]) -> str:
    head = (
        '<header class="pd-chat__head">'
        f'<h2 class="pd-chat__title">Discussion — <code>{esc(run["run_id"])}</code></h2>'
        f'<p class="pd-chat__path"><code>{esc(run["conversation_path"])}</code></p>'
        "</header>"
    )
    if not run["conversation_present"]:
        cmd = (f'printf \'%s\\n\' \'{{"role":"human","text":"first note",'
               f'"created_at":"1970-01-01T00:00:00Z"}}\' '
               f'> {run["conversation_path"]}')
        body = empty("No conversation.jsonl in this run directory yet. "
                     "Create it with one JSON object per line "
                     "(role: human|agent|embry, text, created_at, optional audio):", cmd)
    elif not run["conversation"]:
        body = empty("conversation.jsonl exists but contains no messages.")
    else:
        rows = []
        for msg in run["conversation"]:
            role = str(msg.get("role") or "unknown")
            audio = str(msg.get("audio") or "")
            audio_el = ""
            if audio:
                path = Path(audio)
                if not path.is_absolute():
                    path = Path(run["run_dir"]) / path
                audio_el = (f'<audio class="pd-msg__audio" controls preload="none" '
                            f'src="{esc(path.as_uri())}"></audio>' if path.is_file()
                            else f'<p class="pd-msg__audio-missing">audio referenced but '
                                 f'not found: <code>{esc(audio)}</code></p>')
            rows.append(
                f'<li class="pd-msg pd-msg--{esc(role)}" data-role="{esc(role)}">'
                f'<span class="pd-msg__role">{esc(role)}</span>'
                f'<time class="pd-msg__time">{esc(msg.get("created_at") or "no timestamp")}</time>'
                f'<p class="pd-msg__text">{esc(msg.get("text") or "")}</p>'
                f"{audio_el}</li>"
            )
        body = f'<ol class="pd-msgs">{"".join(rows)}</ol>'

    if run["conversation_error"]:
        body += f'<p class="pd-warn">{esc(run["conversation_error"])}</p>'

    composer = (
        '<form class="pd-composer" data-run-dir="' + esc(run["run_dir"]) + '">'
        '<label class="pd-composer__label">role'
        '<select class="pd-composer__role">'
        '<option value="human">human</option>'
        '<option value="agent">agent</option>'
        '<option value="embry">embry</option>'
        "</select></label>"
        '<textarea class="pd-composer__text" rows="3" '
        'placeholder="Write a message. Nothing is sent anywhere — this builds a '
        'JSONL line for you to append yourself."></textarea>'
        '<div class="pd-composer__actions">'
        '<button type="button" class="pd-btn" data-action="copy">Copy JSONL line</button>'
        '<button type="button" class="pd-btn" data-action="download">Download line</button>'
        "</div>"
        '<output class="pd-composer__out"></output>'
        "</form>"
    )
    return f'<section class="pd-chat" data-run-id="{esc(run["run_id"])}">{head}{body}{composer}</section>'


CSS = """
/* ---------------------------------------------------------------------------
   DESIGNER PALETTE. Restyling should be a change to these variables plus the
   rules below them -- not a rewrite of the markup. Every colour, radius, and
   spacing step in this sheet resolves through one of these.
   --------------------------------------------------------------------------- */
:root {
  --pd-bg:            #14131a;  /* page background                        */
  --pd-surface:       #1d1c26;  /* card / pane background                 */
  --pd-surface-alt:   #252430;  /* nested blocks: sources, messages       */
  --pd-ink:           #ece9f2;  /* primary text                           */
  --pd-ink-muted:     #a5a0b5;  /* metadata, timestamps, captions         */
  --pd-accent:        #c8a2ff;  /* tone chips, links, active affordances  */
  --pd-accent-soft:   #3a2f52;  /* accent fills behind text               */
  --pd-tension:       #ffb27a;  /* tension axis emphasis                  */
  --pd-entity:        #7fd8c4;  /* entity-traversal chips                 */
  --pd-empty:         #6f6a80;  /* explicit empty states                  */
  --pd-warn:          #ff8f8f;  /* parse warnings                         */
  --pd-rule:          #322f3f;  /* hairlines and borders                  */
  --pd-radius:        10px;
  --pd-radius-chip:   999px;
  --pd-gap:           16px;
  --pd-gap-tight:     8px;
  --pd-font:          ui-sans-serif, system-ui, sans-serif;
  --pd-font-mono:     ui-monospace, SFMono-Regular, Menlo, monospace;
  --pd-measure:       68ch;     /* prose line length                      */
}

/* Structural: layout skeleton. The two panes are the contract with the data. */
* { box-sizing: border-box; }
body { margin: 0; background: var(--pd-bg); color: var(--pd-ink);
       font-family: var(--pd-font); line-height: 1.55; }
.pd-app { display: grid; grid-template-columns: minmax(0, 3fr) minmax(0, 2fr);
          gap: var(--pd-gap); padding: var(--pd-gap); align-items: start; }
@media (max-width: 900px) { .pd-app { grid-template-columns: 1fr; } }
.pd-pane { min-width: 0; display: flex; flex-direction: column; gap: var(--pd-gap); }
.pd-pane__title { font-size: 0.8rem; letter-spacing: 0.12em; text-transform: uppercase;
                  color: var(--pd-ink-muted); margin: 0; }

/* Stylistic below this line: safe to rewrite wholesale. */
.pd-card, .pd-chat { background: var(--pd-surface); border: 1px solid var(--pd-rule);
                     border-radius: var(--pd-radius); padding: var(--pd-gap); }
.pd-card__title { margin: 0 0 var(--pd-gap-tight); font-size: 1.15rem; }
.pd-card__meta { display: grid; grid-template-columns: max-content 1fr;
                 gap: 2px var(--pd-gap-tight); margin: 0; font-size: 0.8rem;
                 color: var(--pd-ink-muted); }
.pd-card__meta dt { text-transform: uppercase; letter-spacing: 0.08em; }
.pd-card__meta dd { margin: 0; overflow-wrap: anywhere; }
.pd-card__note { color: var(--pd-ink-muted); font-size: 0.82rem;
                 max-width: var(--pd-measure); }
.pd-section { margin-top: var(--pd-gap); }
.pd-section__title { font-size: 0.75rem; letter-spacing: 0.12em; text-transform: uppercase;
                     color: var(--pd-ink-muted); margin: 0 0 var(--pd-gap-tight); }
.pd-para { margin-bottom: var(--pd-gap); }
.pd-para__text { margin: var(--pd-gap-tight) 0 0; max-width: var(--pd-measure); }

.pd-chip { display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px;
           border-radius: var(--pd-radius-chip); font-size: 0.72rem;
           font-family: var(--pd-font-mono); }
.pd-chip--tone { background: var(--pd-accent-soft); color: var(--pd-accent); }
.pd-chip__tone { font-weight: 700; }
.pd-chip__intensity { opacity: 0.8; }
.pd-chip__status { text-transform: uppercase; letter-spacing: 0.08em; opacity: 0.75; }
.pd-chip--entity { background: transparent; color: var(--pd-entity);
                   border: 1px solid var(--pd-entity); margin: 0 4px 4px 0; }
.pd-chip--empty { color: var(--pd-empty); border: 1px dashed var(--pd-empty); }

.pd-ref { color: var(--pd-accent); text-decoration: none; font-size: 0.75em;
          vertical-align: super; }
.pd-ref:hover { text-decoration: underline; }
.pd-sources { list-style: none; margin: 0; padding: 0; }
.pd-source { background: var(--pd-surface-alt); border-radius: var(--pd-radius);
             padding: var(--pd-gap-tight) var(--pd-gap); margin-bottom: var(--pd-gap-tight); }
.pd-source:target { outline: 2px solid var(--pd-accent); }
.pd-source__n { color: var(--pd-accent); font-family: var(--pd-font-mono);
                margin-right: var(--pd-gap-tight); }
.pd-source__id { font-family: var(--pd-font-mono); font-size: 0.78rem;
                 overflow-wrap: anywhere; }
.pd-source__scope { color: var(--pd-ink-muted); font-size: 0.75rem;
                    margin-left: var(--pd-gap-tight); }
.pd-source__flag { color: var(--pd-warn); font-size: 0.7rem; margin-left: var(--pd-gap-tight); }
.pd-source__excerpt { margin: 6px 0 0; font-size: 0.85rem; color: var(--pd-ink-muted);
                      max-width: var(--pd-measure); }

.pd-tensions { list-style: none; margin: 0; padding: 0; }
.pd-tension { border-left: 3px solid var(--pd-tension); padding-left: var(--pd-gap);
              margin-bottom: var(--pd-gap-tight); }
.pd-tension__axis { color: var(--pd-tension); font-weight: 700; }
.pd-tension__vs, .pd-tension__pair, .pd-tension__score {
  color: var(--pd-ink-muted); font-size: 0.78rem; margin: 0 6px; }
.pd-tension__desc { margin: 4px 0 0; font-size: 0.85rem; color: var(--pd-ink-muted);
                    max-width: var(--pd-measure); }

.pd-web__size { margin: 0 0 var(--pd-gap-tight); font-size: 0.85rem; }
.pd-web__note { font-size: 0.8rem; color: var(--pd-ink-muted); }
.pd-audio { display: flex; flex-direction: column; gap: 4px; }
.pd-audio audio { width: 100%; }
.pd-audio__path { font-size: 0.7rem; color: var(--pd-ink-muted); overflow-wrap: anywhere; }

.pd-empty { border: 1px dashed var(--pd-empty); border-radius: var(--pd-radius);
            padding: var(--pd-gap-tight) var(--pd-gap); color: var(--pd-empty);
            font-size: 0.82rem; }
.pd-empty p { margin: 0; }
.pd-empty__cmd { margin: var(--pd-gap-tight) 0 0; overflow-x: auto;
                 background: var(--pd-bg); padding: var(--pd-gap-tight);
                 border-radius: var(--pd-radius); }
.pd-empty__cmd code { font-family: var(--pd-font-mono); font-size: 0.75rem;
                      color: var(--pd-ink-muted); white-space: pre; }
.pd-warn { color: var(--pd-warn); font-size: 0.8rem; }

.pd-msgs { list-style: none; margin: 0 0 var(--pd-gap); padding: 0;
           display: flex; flex-direction: column; gap: var(--pd-gap-tight); }
.pd-msg { background: var(--pd-surface-alt); border-radius: var(--pd-radius);
          padding: var(--pd-gap-tight) var(--pd-gap); }
.pd-msg--human { border-left: 3px solid var(--pd-accent); }
.pd-msg--agent { border-left: 3px solid var(--pd-entity); }
.pd-msg--embry { border-left: 3px solid var(--pd-tension); }
.pd-msg__role { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.1em;
                color: var(--pd-ink-muted); }
.pd-msg__time { font-size: 0.7rem; color: var(--pd-ink-muted); margin-left: var(--pd-gap-tight); }
.pd-msg__text { margin: 4px 0 0; white-space: pre-wrap; }
.pd-msg__audio { width: 100%; margin-top: 6px; }
.pd-msg__audio-missing { font-size: 0.75rem; color: var(--pd-warn); }

.pd-composer { display: flex; flex-direction: column; gap: var(--pd-gap-tight);
               border-top: 1px solid var(--pd-rule); padding-top: var(--pd-gap); }
.pd-composer__label { font-size: 0.75rem; color: var(--pd-ink-muted);
                      display: flex; gap: var(--pd-gap-tight); align-items: center; }
.pd-composer__text { width: 100%; background: var(--pd-bg); color: var(--pd-ink);
                     border: 1px solid var(--pd-rule); border-radius: var(--pd-radius);
                     padding: var(--pd-gap-tight); font: inherit; resize: vertical; }
.pd-composer__actions { display: flex; gap: var(--pd-gap-tight); }
.pd-btn { background: var(--pd-accent-soft); color: var(--pd-accent);
          border: 1px solid var(--pd-accent); border-radius: var(--pd-radius-chip);
          padding: 6px 14px; font: inherit; font-size: 0.8rem; cursor: pointer; }
.pd-composer__out { font-family: var(--pd-font-mono); font-size: 0.72rem;
                    color: var(--pd-ink-muted); overflow-wrap: anywhere; }
"""

JS = """
// Composer only builds a JSONL line locally. There is no backend and this page
// never sends anything: copy or download, then append the line yourself.
(function () {
  function line(form) {
    var role = form.querySelector('.pd-composer__role').value;
    var text = form.querySelector('.pd-composer__text').value;
    if (!text.trim()) { return null; }
    return JSON.stringify({
      role: role,
      text: text,
      created_at: new Date().toISOString().replace(/\\.\\d{3}Z$/, 'Z')
    });
  }
  document.querySelectorAll('.pd-composer').forEach(function (form) {
    var out = form.querySelector('.pd-composer__out');
    form.addEventListener('click', function (ev) {
      var action = ev.target.getAttribute('data-action');
      if (!action) { return; }
      var payload = line(form);
      if (!payload) { out.textContent = 'Nothing to build: the message is empty.'; return; }
      if (action === 'copy') {
        if (navigator.clipboard) {
          navigator.clipboard.writeText(payload + '\\n').then(function () {
            out.textContent = 'Copied. Append it to conversation.jsonl in the run dir.';
          }, function () { out.textContent = payload; });
        } else { out.textContent = payload; }
      } else if (action === 'download') {
        var blob = new Blob([payload + '\\n'], { type: 'application/x-ndjson' });
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'conversation-line.jsonl';
        a.click();
        URL.revokeObjectURL(a.href);
        out.textContent = 'Downloaded. Append it to conversation.jsonl in the run dir.';
      }
    });
  });
})();
"""

TEMPLATE_COMMENT = """<!--
  persona-dream journal + chat UX (scaffold).

  STRUCTURAL blocks -- data-bound, keep the element and its class/id hooks:
    .pd-app                two-pane grid: journal (left) and chat (right)
    .pd-card               one dream run; data-run-id carries the run id
    .pd-para / .pd-chip    journal prose and its REQUESTED tone annotation
    .pd-ref -> .pd-source  footnote markers link to memory id/scope/excerpt
    .pd-tensions           contradiction pairs from contradiction_report.json
    .pd-web                entity traversal from dream_packet.json
    .pd-audio              <audio> when a wav exists, empty state when not
    .pd-msgs / .pd-msg     conversation.jsonl transcript, one <li> per line
    .pd-composer           builds a JSONL line client-side; no network calls
    .pd-empty              explicit empty state -- never replace with filler

  STYLISTIC: everything in the <style> block below the palette comment.
  Restyle by changing the --pd-* custom properties and the rules; the markup
  above is what the Python renderer guarantees.

  Generated by skills/persona-dream/ux/render_journal_ux.py -- edit that, not this.
-->"""


def render_page(runs: list[dict[str, Any]], title: str) -> str:
    personas = sorted({r["persona"] for r in runs if r["persona"]})
    subtitle = (f'{len(runs)} run(s)' + (f' · {", ".join(personas)}' if personas else ""))
    journal_pane = "".join(render_journal_card(r) for r in runs)
    chat_pane = "".join(render_chat(r) for r in runs)
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{esc(title)}</title>\n"
        f"<style>{CSS}</style>\n</head>\n<body>\n"
        f"{TEMPLATE_COMMENT}\n"
        '<main class="pd-app">\n'
        '<div class="pd-pane pd-pane--journal">'
        f'<h1 class="pd-pane__title">Journal — {esc(subtitle)}</h1>'
        f"{journal_pane}</div>\n"
        '<div class="pd-pane pd-pane--chat">'
        '<h1 class="pd-pane__title">Discussion</h1>'
        f"{chat_pane}</div>\n"
        "</main>\n"
        f"<script>{JS}</script>\n</body>\n</html>\n"
    )


def build(run_dirs: list[Path], out: Path, title: str = "Persona dream journal",
          labels: list[str] | None = None) -> Path:
    labels = labels or []
    runs = [load_run(d, labels[i] if i < len(labels) else None)
            for i, d in enumerate(run_dirs)]
    runs.sort(key=lambda r: (r["created_at"], r["run_id"]), reverse=True)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_page(runs, title), encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", type=Path, action="append", required=True,
                    help="a persona-dream run directory; repeat for multiple days")
    ap.add_argument("--out", type=Path, required=True, help="output HTML path")
    ap.add_argument("--audio-label", action="append", default=[],
                    help="Chatterbox label for the matching --run-dir (optional)")
    ap.add_argument("--title", default="Persona dream journal")
    args = ap.parse_args()

    missing = [str(d) for d in args.run_dir if not Path(d).is_dir()]
    if missing:
        raise SystemExit("run dir not found: " + ", ".join(missing))

    out = build(args.run_dir, args.out, args.title, args.audio_label)
    print(json.dumps({
        "schema": "persona_dream.journal_ux_render.v1",
        "out": str(out.resolve()),
        "bytes": out.stat().st_size,
        "run_dirs": [str(Path(d).resolve()) for d in args.run_dir],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

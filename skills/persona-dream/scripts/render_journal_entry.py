#!/usr/bin/env python3
"""Render one dream journal as a readable entry and a speakable text (#1201).

A journal entry has two audiences and they need different bytes.

A human reads tone. Inline annotations -- ``[wistful]``, ``[guarded]`` -- tell
you how a passage is meant to land, and footnotes tell you which memories the
passage came from, including the multi-hop entity traversal that connected
them. That is the artifact you scan to answer "did she change, and is she still
herself".

Chatterbox reads text literally. Its ``/health`` reports
``inline_text_tag_behavior: synthesized_as_literal_text`` and
``dedicated_tag_channel: unsupported``, so an inline ``[wistful]`` reaching the
TTS input is spoken aloud as the word "wistful". The spoken text must therefore
be the annotation-stripped form.

Two representations, one entry. The receipt binds them by hashing the stripped
annotation form against the spoken text: if they ever diverge, an annotation
leaked into speech or the spoken text drifted from what was published.

Tone tags record what was REQUESTED. The renderer never claims a tone was
achieved: the same ``/health`` reports preset-driven acoustic shifts measured
below same-parameter stochastic spread, so an achieved-tone claim would not be
supportable from this side.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]

#: Inline annotation form. Deliberately bracketed and on its own, so stripping
#: is a single unambiguous regex rather than a parser.
ANNOTATION = re.compile(r"\[(?:tone|emotion):[^\]]*\]\s*")

#: Contradiction axis -> the tone a passage carrying that tension asks for.
#: Requested, never achieved.
AXIS_TONE = {
    "Concealment": ("guarded", 0.55),
    "Disclosure": ("open", 0.5),
    "Competence": ("steady", 0.45),
    "Inadequacy": ("uncertain", 0.6),
    "Belonging": ("warm", 0.5),
    "Isolation": ("distant", 0.55),
    "Duty": ("formal", 0.4),
    "Desire": ("yearning", 0.6),
}


def utc_now() -> str:
    return datetime.now().astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def rel(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def sha_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def strip_annotations(text: str) -> str:
    """The speakable form: annotations removed, whitespace normalised."""
    out = ANNOTATION.sub("", text)
    return "\n".join(line.rstrip() for line in out.splitlines()).strip() + "\n"


def tone_for(contradictions: list[dict[str, Any]], index: int) -> tuple[str, float]:
    """Requested tone for paragraph ``index``, from the tension it carries."""
    if not contradictions:
        return ("reflective", 0.4)
    row = contradictions[index % len(contradictions)]
    axis = row.get("bridge_b") or row.get("bridge_a") or ""
    return AXIS_TONE.get(str(axis), ("reflective", 0.4))


def build_footnotes(items: list[dict[str, Any]], contradictions: list[dict[str, Any]],
                    web: dict[str, Any] | None) -> tuple[list[str], dict[str, int]]:
    """Footnote lines plus a source_id -> marker index map."""
    marker: dict[str, int] = {}
    lines: list[str] = []
    for item in items:
        sid = str(item.get("source_id") or "")
        if not sid or sid in marker:
            continue
        n = len(marker) + 1
        marker[sid] = n
        text = " ".join(str(item.get("text") or "").split())
        scope = item.get("scope") or "unknown-scope"
        lines.append(f"[^{n}]: `{sid}` ({scope}) — {text[:150]}")
    for row in contradictions:
        a, b = str(row.get("item_a") or ""), str(row.get("item_b") or "")
        if a in marker and b in marker:
            lines.append(
                f"[^t{marker[a]}x{marker[b]}]: tension — "
                f"{row.get('bridge_a')} held against {row.get('bridge_b')}, "
                f"between [^{marker[a]}] and [^{marker[b]}]"
            )
    if web:
        entities = web.get("memory_web_entities") or []
        size = web.get("memory_web_size")
        if entities or size:
            lines.append(
                f"[^web]: multi-hop traversal reached {size if size is not None else len(entities)} "
                f"connected memories via shared entities: "
                f"{', '.join(str(e) for e in list(entities)[:8]) or 'none recorded'}"
            )
    return lines, marker


def render(journal_text: str, *, persona: str, items: list[dict[str, Any]],
           contradictions: list[dict[str, Any]], web: dict[str, Any] | None,
           mood: dict[str, Any] | None) -> tuple[str, str]:
    """Return (annotated markdown, spoken text)."""
    paragraphs = [p.strip() for p in journal_text.split("\n\n") if p.strip()]
    footnotes, marker = build_footnotes(items, contradictions, web)

    body: list[str] = []
    for idx, para in enumerate(paragraphs):
        tone, intensity = tone_for(contradictions, idx)
        body.append(f"[tone: {tone} · {intensity} · requested]")
        refs = [f"[^{marker[str(i.get('source_id'))]}]"
                for i in items
                if str(i.get("source_id")) in marker
                and any(w in para.lower() for w in str(i.get("text") or "").lower().split()[:6] if len(w) > 5)]
        body.append(para + ("".join(dict.fromkeys(refs)) if refs else ""))
        body.append("")

    head = [
        f"# {persona} — dream journal",
        "",
        f"*Generated {utc_now()}. Tone annotations record what was REQUESTED of the",
        "renderer, not what the audio achieved; Chatterbox reports preset-driven",
        "shifts below same-parameter stochastic spread. Annotations are stripped",
        "before speech — inline tags would otherwise be spoken aloud as words.*",
        "",
    ]
    if mood:
        head += [
            f"**Session mood:** `{mood.get('mood_label') or mood.get('label') or 'unset'}`"
            + (f" — {mood.get('carried_tension')}" if mood.get("carried_tension") else ""),
            "",
        ]
    annotated = "\n".join(head + body + ["## Sources", ""] + footnotes) + "\n"
    spoken = strip_annotations("\n\n".join(paragraphs))
    return annotated, spoken


def run(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir)
    packet = json.loads((run_dir / "dream_packet.json").read_text(encoding="utf-8"))
    residue = json.loads((run_dir / "residue_links.json").read_text(encoding="utf-8"))
    contra = json.loads((run_dir / "contradiction_report.json").read_text(encoding="utf-8"))

    journal_text = args.journal_text
    if not journal_text:
        path = run_dir / "dream_reflection.md"
        journal_text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if not journal_text.strip():
        raise SystemExit("no journal text: pass --journal-text or produce dream_reflection.md")

    items = residue.get("items") or []
    contradictions = contra.get("contradictions") or []
    web = {k: packet.get(k) for k in ("memory_web_entities", "memory_web_size") if k in packet}
    mood = packet.get("session_mood") if isinstance(packet.get("session_mood"), dict) else None

    annotated, spoken = render(
        journal_text, persona=args.persona, items=items,
        contradictions=contradictions, web=web or None, mood=mood,
    )

    md_path = run_dir / "journal.md"
    spoken_path = run_dir / "journal_spoken.txt"
    md_path.write_text(annotated, encoding="utf-8")
    spoken_path.write_text(spoken, encoding="utf-8")

    # The binding: the annotated form with annotations removed must be exactly
    # what gets spoken. A mismatch means an annotation leaked into speech or the
    # spoken text drifted from the published entry.
    stripped_from_md = strip_annotations(
        "\n\n".join(p.strip() for p in annotated.split("## Sources")[0].split("\n\n")
                    if p.strip() and not p.strip().startswith(("#", "*", "**")))
    )
    bound = sha_text(re.sub(r"\[\^[^\]]*\]", "", stripped_from_md)) == sha_text(spoken)

    receipt = {
        "schema": "persona_dream.journal_render_receipt.v1",
        "created_at": utc_now(),
        "status": "PASS_JOURNAL_RENDERED" if bound else "BLOCKED_JOURNAL_SPEECH_BINDING",
        "mocked": False,
        "live": False,
        "persona": args.persona,
        "journal_markdown": rel(md_path),
        "journal_spoken": rel(spoken_path),
        "spoken_sha256": sha_text(spoken),
        "annotation_free_speech": not bool(ANNOTATION.search(spoken)),
        "speech_binding_holds": bound,
        "source_memory_count": len(items),
        "tension_count": len(contradictions),
        "footnote_count": annotated.count("\n[^"),
        "claims": {
            "proves": [
                "the entry is published in a readable annotated form and a separate spoken form",
                "no tone annotation reaches the text sent to the renderer",
            ] if bound else [],
            "does_not_prove": [
                "that any requested tone was achieved in the audio",
                "perceived emotion or human acceptance",
            ],
        },
    }
    out = Path(args.out) if args.out else run_dir / "JOURNAL_RENDER_RECEIPT.json"
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--persona", default="Embry")
    ap.add_argument("--journal-text", default="")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    r = run(args)
    print(json.dumps(r, indent=2, sort_keys=True) if args.json
          else f"{r['status']}  spoken={r['journal_spoken']}  footnotes={r['footnote_count']}")
    return 0 if r["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())

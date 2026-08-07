#!/usr/bin/env python3
"""Hash-pinned exemplar corpus tooling (pitchdeck.style_corpus.v1, #1274).

build   — regenerate references/style_corpus.json from committed assets +
          the (optional, workstation-only) source-deck store, recording
          sha256 for every image and reachable source deck.
verify  — fail-closed integrity gate, runnable from a CLEAN CLONE with no
          /mnt/storage12tb: every manifest entry must exist with a matching
          image hash and provenance, and every exemplar id referenced by
          SKILL.md must resolve. Exit 1 names the exact exemplar.
sheet   — self-contained HTML contact sheet for human inspection.

stdlib only (hashlib/json/base64) so a clean clone needs no environment.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "references" / "style_corpus.json"
CORPUS_STORE = Path("/mnt/storage12tb/skills/pitchdeck/sources/style-corpus")

# id -> (rule, kind, deck file, slides, audience, rationale)
EXEMPLARS = {
    "cybersummit-01-cover": ("cover-brand", "exemplar", "SpartaAI_CyberSummitv_v3.pptx", [1], "conference", "Wordmark + one-phrase tagline + brand glyph; ~5 words."),
    "cybersummit-04-problem-solution": ("distance-legibility-chrome", "exemplar", "SpartaAI_CyberSummitv_v3.pptx", [4], "conference", "Teal band + white title separates header from body at 5-20ft; color-coded label prefixes."),
    "cybersummit-12-how-diagram": ("one-big-diagram", "exemplar", "SpartaAI_CyberSummitv_v3.pptx", [12], "conference", "Process slide carried by ONE large line-art diagram."),
    "cybersummit-18-multichannel": ("multi-channel-reinforcement", "exemplar", "SpartaAI_CyberSummitv_v3.pptx", [18], "conference", "Headline asserts, chevrons state, diagram shows, badge sets register — one idea."),
    "cybersummit-21-ANTIPATTERN-wall": ("density-5x5", "anti-exemplar", "SpartaAI_CyberSummitv_v3.pptx", [21], "conference", "224-word wall; the lint exists because taste alone does not hold."),
    "cybersummit-42-manual-build-1": ("builds-are-fragments", "anti-exemplar", "SpartaAI_CyberSummitv_v3.pptx", [42, 43, 44, 45], "conference", "Duplicated slides hand-fake a build; fragments replace this."),
    "cybersummit-43-manual-build-2": ("builds-are-fragments", "anti-exemplar", "SpartaAI_CyberSummitv_v3.pptx", [42, 43, 44, 45], "conference", "Second frame of the duplicated-slide build run."),
    "cybersummit-49-assertion-humor": ("headline-as-assertion", "exemplar", "SpartaAI_CyberSummitv_v3.pptx", [49], "conference", "Assertion headline + humor as retention (Pluto as heat sink)."),
    "ftworth-04-pipeline-position": ("audience-required-slides", "exemplar", "ACERT_Darpa_PI_Meeting_FtWorth.pptx", [4], "program-review", "PI reviews require an early pipeline-position slide."),
    "reqml-04-pipeline-position": ("audience-required-slides", "exemplar", "ReqML_GE_Presentation.pptx", [4], "program-review", "Same required slide in a second program-review deck."),
    "reqml-12-statement-slide": ("thesis-as-statement", "exemplar", "ReqML_GE_Presentation.pptx", [12], "program-review", "One 112pt assertion + one icon: the correct thesis form."),
}
RENDER_TOOLS = {"soffice": "LibreOffice 24.x impress_pdf_Export", "pdftoppm": "poppler -r 55"}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> int:
    entries = []
    for ex_id, (rule, kind, deck, slides, audience, rationale) in sorted(EXEMPLARS.items()):
        image = ROOT / "assets" / f"{ex_id}.png"
        if not image.exists():
            print(f"ERROR: missing committed image for '{ex_id}'", file=sys.stderr)
            return 1
        source = CORPUS_STORE / deck
        entries.append({
            "id": ex_id, "rule": rule, "kind": kind,
            "source_deck": deck,
            "source_deck_sha256": _sha(source) if source.exists() else None,
            "source_classification": "private-local" if source.exists() else "unavailable-by-policy",
            "slides": slides, "audience": audience, "rationale": rationale,
            "image": f"assets/{ex_id}.png", "image_sha256": _sha(image),
            "render_tools": RENDER_TOOLS,
        })
    MANIFEST.write_text(json.dumps({"schema": "pitchdeck.style_corpus.v1", "exemplars": entries}, indent=1), encoding="utf-8")
    print(f"manifest written: {MANIFEST} ({len(entries)} exemplars)")
    return 0


def verify() -> int:
    problems: list[str] = []
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if data.get("schema") != "pitchdeck.style_corpus.v1":
        problems.append("manifest schema mismatch")
    by_id = {}
    for entry in data.get("exemplars", []):
        ex_id = entry.get("id", "<missing-id>")
        by_id[ex_id] = entry
        image = ROOT / entry.get("image", "")
        if not image.exists():
            problems.append(f"{ex_id}: image missing ({entry.get('image')})")
            continue
        if _sha(image) != entry.get("image_sha256"):
            problems.append(f"{ex_id}: image hash mismatch")
        for field in ("rule", "kind", "source_deck", "slides", "rationale", "source_classification"):
            if not entry.get(field):
                problems.append(f"{ex_id}: missing provenance field '{field}'")
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    referenced = set(re.findall(r"\b(cybersummit-\d+[a-zA-Z-]*|reqml-\d+[a-zA-Z-]*|ftworth-\d+[a-zA-Z-]*)\b", skill))
    for ref in sorted(referenced):
        if not any(k.startswith(ref) or ref.startswith(k.rsplit("-", 1)[0]) or k == ref for k in by_id):
            matches = [k for k in by_id if k.startswith(ref)]
            if not matches:
                problems.append(f"SKILL.md references '{ref}' with no manifest exemplar")
    kinds = {e["kind"] for e in data.get("exemplars", [])}
    if not {"exemplar", "anti-exemplar"} <= kinds:
        problems.append("corpus must retain both exemplars and anti-exemplars")
    if problems:
        for problem in problems:
            print(f"FAIL: {problem}", file=sys.stderr)
        return 1
    print(f"PASS: {len(by_id)} exemplars verified (hashes, provenance, SKILL.md references, both kinds present)")
    return 0


def sheet() -> int:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cells = []
    for entry in data["exemplars"]:
        img = ROOT / entry["image"]
        uri = "data:image/png;base64," + base64.b64encode(img.read_bytes()).decode()
        border = "#A14240" if entry["kind"] == "anti-exemplar" else "#065E7C"
        cells.append(
            f"<figure style='border:3px solid {border};padding:8px;margin:8px;width:360px;display:inline-block;vertical-align:top;'>"
            f"<img src='{uri}' style='width:100%'/>"
            f"<figcaption style='font:12px sans-serif'><b>{entry['id']}</b> · {entry['kind']}<br>rule: {entry['rule']}<br>"
            f"{entry['source_deck']} slide {entry['slides']}<br><i>{entry['rationale']}</i></figcaption></figure>"
        )
    out = ROOT / "references" / "exemplar-contact-sheet.html"
    out.write_text("<!doctype html><meta charset='utf-8'><title>Exemplar corpus</title><body style='background:#111'>" + "".join(cells), encoding="utf-8")
    print(f"contact sheet: {out}")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "verify"
    sys.exit({"build": build, "verify": verify, "sheet": sheet}[cmd]())

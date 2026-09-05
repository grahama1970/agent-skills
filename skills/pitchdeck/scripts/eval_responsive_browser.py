#!/usr/bin/env python3
"""Live Surf regression: existing emitted decks, real Chrome, no browser stubs.

Requires the pitchdeck Vite server and the workstation's approved document.
Only a dedicated unfocused window is changed; no edit API is called. Receipts include source
hashes, actual CSS viewport sizes, rendered strings, and screenshot paths.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / "skills/pitchdeck"
SURF = ROOT / "skills/surf/run.sh"


def run(*args: str) -> str:
    result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=180)
    if result.returncode:
        raise RuntimeError(f"{args[0]} {args[1]}: {result.stdout}\n{result.stderr}")
    return result.stdout


# The oracle reads actual DOM text and geometry, not a component success flag.
PROBE = r"""
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const q = id => document.querySelector(`[data-qid="${id}"]`);
const assert = (ok, why) => { if (!ok) throw new Error(why); };
const waitFor = async (check, why) => {
  for (let i = 0; i < 100; i++) { if (check()) return; await sleep(50); }
  throw new Error(why);
};
const response = await fetch(new URL(new URLSearchParams(location.search).get('deck') || './deck.data.json', location.href));
assert(response.ok, 'payload HTTP failure');
const deck = await response.json();
const initial = JSON.stringify(deck);
const slides = deck.slides.filter(s => !s.hidden);
// Each trial starts at a known slide through the real UI. Per-deck resume may
// legitimately restore the final slide after a prior trial or interrupted run.
q('deck:view:overview').click();
await waitFor(() => q('deck:overview:slide:' + slides[0].id), 'overview did not open');
q('deck:overview:slide:' + slides[0].id).click();
await waitFor(() => document.querySelector('.slide-viewport')?.dataset.slideId === slides[0].id, 'first-slide selection failed');
const results = [];
const textStrings = slide => slide.layout === 'freeform'
  ? [slide.title, slide.footer, ...slide.elements.flatMap(e => [e.text,
      ...(e.diagram?.nodes.flatMap(n => [n.label, n.sublabel]) || []),
      ...(e.diagram?.edges.map(e => e.label) || [])])].filter(Boolean)
  : [slide.title, slide.message, slide.footer,
      ...(slide.layout === 'cover' ? [] : slide.body), ...slide.visual.items, slide.visual.caption].filter(Boolean);
for (const slide of slides) {
  for (let step = 0; step < 30; step++) {
    const pane = document.querySelector('.slide-viewport');
    if (pane?.dataset.slideId === slide.id) break;
    q('deck:nav:next')?.click(); await sleep(80);
  }
  await document.fonts.ready;
  await sleep(100);
  const pane = document.querySelector('.slide-viewport');
  assert(pane?.dataset.slideId === slide.id, 'navigation failed: ' + slide.id);
  // Consume click-gated builds without crossing to the next slide.
  if (slide.reveal === 'step') {
    for (let step = 0; step < Math.max(slide.body.length, slide.visual.items.length); step++) {
      q('deck:nav:next').click(); await sleep(100);
    }
  }
  await Promise.all(pane.getAnimations({subtree:true})
    .filter(a => a.effect?.getTiming().iterations !== Infinity).map(a => a.finished.catch(() => {})));
  const rendered = pane.innerText;
  const missing = textStrings(slide).filter(s => !rendered.includes(s));
  assert(!missing.length, 'missing text: ' + JSON.stringify({slide:slide.id, missing}));
  assert(document.documentElement.scrollWidth <= innerWidth + 1, 'viewport horizontal overflow');
  const narrow = innerWidth < 1100;
  assert(pane.dataset.layout === (narrow ? 'responsive' : 'canvas'), 'wrong display mode');
  const textNodes = [...pane.querySelectorAll('p, li, h1, h2, strong, .freeform-band span')]
    .filter(e => e.innerText.trim() && getComputedStyle(e).visibility !== 'hidden');
  const fonts = textNodes.map(e => Number.parseFloat(getComputedStyle(e).fontSize));
  if (narrow) {
    assert(pane.scrollWidth <= pane.clientWidth + 1, 'slide horizontal overflow: ' + slide.id);
    assert(fonts.every(size => size >= 16), 'unreadable computed text: ' + JSON.stringify(fonts));
    assert(getComputedStyle(pane.firstElementChild).transform === 'none', 'whole-slide scaling instead of reflow');
    for (const e of textNodes) {
      assert(e.getBoundingClientRect().right <= innerWidth + 1, 'text beyond viewport: ' + e.innerText);
    }
  }
  if (narrow) {
    pane.focus();
    pane.dispatchEvent(new KeyboardEvent('keydown', {key:'ArrowDown', bubbles:true}));
    await sleep(50);
    assert(document.querySelector('.slide-viewport').dataset.slideId === slide.id, 'vertical reading key changed slides');
  }
  const images = [...pane.querySelectorAll('img')];
  assert(images.every(i => i.complete && i.naturalWidth > 0), 'missing rendered image: ' + slide.id);
  results.push({slide_id:slide.id, layout:pane.dataset.layout, viewport:[innerWidth, innerHeight],
    client_width:pane.clientWidth, scroll_width:pane.scrollWidth, min_font:Math.min(...fonts),
    expected_text:textStrings(slide), rendered_text:rendered, images:images.map(i => i.currentSrc)});
}
// Previous, keyboard forward, and overview direct selection use the real app.
q('deck:view:overview').click(); await sleep(100);
q('deck:overview:slide:' + slides[0].id).click(); await sleep(150);
let pane = document.querySelector('.slide-viewport');
assert(pane.dataset.slideId === slides[0].id, 'overview selection lost to fragment state');
pane.focus(); pane.dispatchEvent(new KeyboardEvent('keydown', {key:'ArrowRight', bubbles:true})); await sleep(150);
assert(document.querySelector('.slide-viewport').dataset.slideId === slides[1].id, 'keyboard next failed');
q('deck:nav:prev').click(); await sleep(150);
assert(document.querySelector('.slide-viewport').dataset.slideId === slides[0].id, 'previous failed');
q('deck:view:notes').click(); await sleep(350);
const sheet = q('deck:pane:chat');
assert(sheet.getBoundingClientRect().right <= innerWidth + 1, 'notes beyond viewport');
q('deck:chat:collapse').click(); await sleep(300);
assert(sheet.inert, 'collapsed sheet remains keyboard accessible');
q('deck:mode:design').click(); await sleep(250);
pane = document.querySelector('.slide-viewport');
assert(pane.dataset.layout === 'canvas' && pane.firstElementChild.style.width === '1920px', 'Design coordinates changed');
q('deck:mode:present').click(); await sleep(150);
document.body.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', ctrlKey:true, bubbles:true}));
await waitFor(() => {
  const p = document.querySelector('.presenter-shell .slide-viewport');
  return p?.clientWidth > 0 && p.dataset.layout === (p.clientWidth < 1100 ? 'responsive' : 'canvas');
}, 'presenter did not reflow');
const presenter = document.querySelector('.presenter-shell');
assert(presenter && presenter.scrollWidth <= presenter.clientWidth + 1, 'presenter horizontal overflow');
const presented = presenter.querySelector('.slide-viewport');
if (presented.dataset.layout === 'responsive') {
  presented.focus();
  presented.dispatchEvent(new KeyboardEvent('keydown', {key:'PageDown', bubbles:true}));
  await sleep(50);
  assert(presenter.querySelector('.slide-viewport').dataset.slideId === slides[0].id, 'presenter reading key changed slides');
}
q('deck:presenter:next').click(); await sleep(150);
assert(presenter.querySelector('.slide-viewport').dataset.slideId === slides[1].id, 'presenter next failed');
q('deck:presenter:exit').click(); await sleep(150);
assert(document.querySelector('.slide-viewport').dataset.slideId === slides[0].id, 'presenter changed underlying navigation');
const after = await fetch(response.url).then(r => r.json());
assert(JSON.stringify(after) === initial, 'display resize mutated payload');
return {slides:results, navigation:true, presenter:true, notes_drawer:true, design_geometry_unchanged:true, payload_unchanged:true};
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:3006/")
    parser.add_argument("--document", default="/mnt/storage12tb/skills/pitchdeck/outputs/ticket-1278/approved.document.json")
    parser.add_argument("--out", default="/tmp/pitchdeck-responsive-live.json")
    parser.add_argument("--negative", action="store_true", help="Prove the live oracle rejects forced whole-slide scaling")
    args = parser.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    receipt: dict = {"schema": "pitchdeck.responsive_browser.v1", "live": True, "mocked": False, "checks": []}
    tab = None
    try:
        # Exercise the canonical production emitter, including DIAGRAM projection.
        os.environ.setdefault("SPARTA_PUBLIC_ROOT", "/mnt/storage12tb/skills/pitchdeck/sources/sparta-public")
        run(str(SKILL / "run.sh"), "emit-document-ui", "--document", args.document,
            "--asset-base", str(SKILL / "examples/sparta-explorer"),
            "--output-dir", str(SKILL / "ui/public/responsive-eval"))
        os.environ.setdefault("SPARTA_CANONICAL_ROOT", "/mnt/storage12tb/skills/pitchdeck/sources/sparta-canonical")
        os.environ.setdefault("SPARTA_ROOT", str(ROOT.parent / "sparta"))
        run(str(SKILL / "run.sh"), "emit-ui", "--bundle-dir", str(SKILL / "examples/sparta-explorer"),
            "--output-dir", str(SKILL / "ui/public/responsive-semantic"))
        document_bytes = Path(args.document).read_bytes()
        document = json.loads(document_bytes)
        projected = json.loads((SKILL / "ui/public/responsive-eval/deck.data.json").read_text())
        source_diagrams = [(s["id"], e["id"]) for s in document["slides"] if not s.get("hidden")
                           for e in s["elements"] if e["kind"] == "diagram"]
        rendered_diagrams = [(s["id"], e["id"]) for s in projected["slides"] for e in s["elements"] if e.get("diagram")]
        assert source_diagrams and source_diagrams == rendered_diagrams, "canonical diagrams lost in projection"
        receipt["document_sha256"] = hashlib.sha256(document_bytes).hexdigest()
        receipt["projected_diagrams"] = rendered_diagrams
        run(str(SURF), "tab.list", "--json")
        # A selected tab in an unfocused window can paint; a hidden tab in a
        # shared window throttles timers/ResizeObserver and invalidates UI timing.
        created = run(str(SURF), "window.new", args.url, "--unfocused", "--width", "1200", "--height", "1100")
        tab = re.search(r"\(tab (\d+)\)", created).group(1)

        def surf(*argv: str) -> str:
            return run(str(SURF), *argv, "--tab-id", tab, "--no-activate")

        def js(code: str):
            return json.loads(surf("js", "return (async () => {" + code + "})()"))

        def ready(url: str):
            # Poll the committed document through Surf's JS path. A DOM wait
            # depends on a content script that may not yet exist after go.
            deadline = time.monotonic() + 15
            last_state = None
            while time.monotonic() < deadline:
                try:
                    last_state = js("const p=document.querySelector('.slide-viewport'); return {url:location.href, ready:document.readyState, settled:!!p && p.clientWidth>0 && p.dataset.layout===(p.clientWidth<1100?'responsive':'canvas')};")
                except RuntimeError as exc:
                    if not any(message in str(exc) for message in (
                        "Execution context was destroyed", "Cannot find context with specified id",
                    )):
                        raise
                    last_state = {"navigation_pending": str(exc)}
                if (last_state.get("url") == url and last_state.get("ready") == "complete"
                        and last_state.get("settled")):
                    return
                time.sleep(0.1)
            raise RuntimeError(f"page did not settle at {url}: {last_state}")

        # Wait for a committed app page: Chrome rejects setZoom during navigation.
        ready(args.url)
        receipt["visibility"] = js("return {hidden:document.hidden, state:document.visibilityState};")
        assert not receipt["visibility"]["hidden"], "eval window must have a visible selected tab"
        if "Zoom: 100%" not in surf("zoom"):
            surf("emulate.device", "reset")
            surf("zoom", "1")
        receipt["zoom_readback"] = surf("zoom").strip()
        if args.negative:
            surf("emulate.viewport", "--width", "390", "--height", "844")
            url = args.url + "?deck=./responsive-eval/deck.data.json"
            surf("go", url)
            ready(url)
            try:
                # Inject after PROBE's first-slide reset, which remounts the canvas.
                js(PROBE.replace('const results = [];', "document.querySelector('.responsive-slide').style.transform='scale(0.2)';\nconst results = [];"))
            except RuntimeError as exc:
                assert "whole-slide scaling instead of reflow" in str(exc), str(exc)
            else:
                raise AssertionError("oracle failed to reject injected scaling")
            receipt["scaling_defect_detected"] = True
        else:
            for width, height in [(1920, 1080), (960, 1080), (390, 844)]:
                surf("emulate.viewport", "--width", str(width), "--height", str(height))
                for lane in ["responsive-eval", "responsive-semantic", "default"]:
                    url = args.url if lane == "default" else args.url + f"?deck=./{lane}/deck.data.json"
                    surf("go", url)
                    ready(url)
                    actual = js("return {width:innerWidth,height:innerHeight};")
                    assert actual == {"width": width, "height": height}, f"wrong real viewport: {actual}"
                    result = js(PROBE)
                    shot = str(out.with_name(f"{out.stem}-{lane}-{width}.png"))
                    surf("snap", "--output", shot)
                    receipt["checks"].append({"lane": lane, "width": width, "screenshot": shot, **result})
            assert Path(args.document).read_bytes() == document_bytes, "canonical document mutated"
        receipt["status"] = "PASS"
    except Exception as exc:
        receipt.update(status="FAIL", error=str(exc))
    finally:
        if tab and receipt.get("status") == "PASS":
            run(str(SURF), "tab.close", tab)
        receipt["tab_id"] = tab
        out.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"status": receipt["status"], "receipt": str(out), "error": receipt.get("error")}))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

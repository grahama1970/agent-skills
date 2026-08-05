"""Emit a self-contained interactive HTML deck from a validated bundle.

Server-side adaptation of the client 'htmlExporter' spec: the HTML is built
from manifests that passed the same fail-closed validate_bundle gates as every
other target (via emit_ui_bundle), assets are inlined as base64 data URIs, and
no external resource (CDN framework, fonts) is referenced — the file presents
offline. Runtime features: keyboard/click navigation, per-slide transitions
and durations from the manifest, staggered reveals, notes drawer (N),
fullscreen (F), autoplay (A), progress bar. Hidden slides are excluded.
Failure modes: validation errors raise before anything is written.
"""

from __future__ import annotations

import base64
import html
import json
import mimetypes
from pathlib import Path
from tempfile import TemporaryDirectory

from loguru import logger

from .models import (
    AssetManifest,
    ClaimLedger,
    DeckManifest,
    OperationClaims,
    OperationReceipt,
    Readiness,
    SeamValidation,
    SourceManifest,
)

_RUNTIME_CSS = """
* { box-sizing: border-box; }
body { margin: 0; background: #020617; color: #e6edf3; font-family: system-ui, sans-serif;
       height: 100vh; overflow: hidden; display: flex; flex-direction: column; }
#progress { height: 3px; background: #0f172a; } #progress > div { height: 100%; background: #22d3ee; transition: width .3s; }
header { display: flex; justify-content: space-between; align-items: center; padding: 8px 16px;
         border-bottom: 1px solid #1e293b; font: 600 12px/1 ui-monospace, monospace; }
header .title { color: #22d3ee; text-transform: uppercase; letter-spacing: .08em; }
header button { background: #1e293b; color: #e2e8f0; border: 1px solid #334155; border-radius: 6px;
                padding: 4px 10px; font: inherit; cursor: pointer; margin-left: 6px; }
main { flex: 1; position: relative; display: flex; align-items: center; justify-content: center; padding: 24px; overflow: hidden; }
#stage { position: relative; width: min(100%, 168vh); aspect-ratio: 16/9; }
.slide { position: absolute; inset: 0; background: #0a0f14; border: 1px solid #1e293b; border-radius: 16px;
         padding: 4.5%; display: none; flex-direction: column; justify-content: center; overflow: hidden; }
.slide.active { display: flex; }
.slide h1 { font-size: 3.2vw; margin: 0 0 1.2vw; color: #f8fafc; }
.slide .message { font-size: 1.7vw; color: #7dd3fc; margin: 0 0 1.6vw; }
.slide ul { margin: 0; padding-left: 1.8vw; font-size: 1.4vw; line-height: 1.7; color: #cbd5e1; }
.slide li { margin-bottom: .6vw; opacity: 0; animation: reveal .46s ease forwards; animation-delay: calc(.16s + var(--i) * .11s); }
.slide.no-reveal li { animation: none; opacity: 1; }
.slide img, .slide video { max-width: 42%; max-height: 60%; object-fit: contain; border-radius: 12px;
                           position: absolute; right: 4.5%; top: 50%; transform: translateY(-50%); }
.slide .footer { position: absolute; bottom: 3%; left: 4.5%; right: 4.5%; font-size: 1vw; color: #64748b; }
@keyframes reveal { from { opacity: 0; translate: 0 14px; } to { opacity: 1; translate: 0 0; } }
.t-slide.active { animation: a-slide var(--dur, .4s) ease both; }
.t-slide_up.active { animation: a-slide-up var(--dur, .4s) ease both; }
.t-fade.active { animation: a-fade var(--dur, .4s) ease both; }
.t-zoom.active { animation: a-zoom var(--dur, .4s) cubic-bezier(.2,.8,.2,1) both; }
.t-flip.active { animation: a-flip var(--dur, .5s) cubic-bezier(.16,1,.3,1) both; backface-visibility: hidden; }
.t-wipe.active { animation: a-wipe var(--dur, .5s) cubic-bezier(.25,1,.5,1) both; }
@keyframes a-slide { from { opacity: 0; translate: 48px 0; } }
@keyframes a-slide-up { from { opacity: 0; translate: 0 56px; } }
@keyframes a-fade { from { opacity: 0; } }
@keyframes a-zoom { from { opacity: 0; scale: .94; } }
@keyframes a-flip { from { opacity: 0; transform: perspective(1200px) rotateY(-90deg); } to { transform: perspective(1200px) rotateY(0); } }
@keyframes a-wipe { from { clip-path: inset(0 100% 0 0); } to { clip-path: inset(0 0 0 0); } }
#notes { display: none; border-top: 1px solid #1e293b; background: #0f172acc; padding: 12px 20px;
         height: 120px; overflow-y: auto; font-size: 13px; color: #cbd5e1; white-space: pre-wrap; }
#notes.open { display: block; }
footer.bar { display: flex; justify-content: space-between; padding: 6px 16px; border-top: 1px solid #1e293b;
             font: 11px/1.6 ui-monospace, monospace; color: #64748b; }
kbd { background: #1e293b; border-radius: 4px; padding: 1px 6px; color: #cbd5e1; }
@media (prefers-reduced-motion: reduce) { .slide.active, .slide li { animation: none !important; opacity: 1; } }
"""

_RUNTIME_JS = """
let index = 0, notesOpen = false, autoplay = false, autoplayTimer = null;
const slides = document.querySelectorAll('.slide');
function show(next) {
  index = Math.max(0, Math.min(slides.length - 1, next));
  slides.forEach((el, i) => el.classList.toggle('active', i === index));
  document.querySelector('#progress > div').style.width = (((index + 1) / slides.length) * 100) + '%';
  document.getElementById('counter').textContent = 'Slide ' + (index + 1) + ' of ' + slides.length;
  document.getElementById('notes').textContent = slides[index].dataset.notes || 'No speaker notes.';
}
function toggleAutoplay() {
  autoplay = !autoplay;
  document.getElementById('autoplay').textContent = autoplay ? 'Pause (A)' : 'AutoPlay (A)';
  clearInterval(autoplayTimer);
  if (autoplay) autoplayTimer = setInterval(() => show(index + 1 >= slides.length ? 0 : index + 1), 4000);
}
document.getElementById('notesBtn').onclick = () => { notesOpen = !notesOpen; document.getElementById('notes').classList.toggle('open', notesOpen); };
document.getElementById('autoplay').onclick = toggleAutoplay;
document.getElementById('fs').onclick = () => document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen();
window.addEventListener('keydown', (e) => {
  if (e.key === 'ArrowRight' || e.key === ' ' || e.key === 'PageDown') { e.preventDefault(); show(index + 1); }
  else if (e.key === 'ArrowLeft' || e.key === 'PageUp') { e.preventDefault(); show(index - 1); }
  else if (e.key.toLowerCase() === 'n') document.getElementById('notesBtn').click();
  else if (e.key.toLowerCase() === 'f') document.getElementById('fs').click();
  else if (e.key.toLowerCase() === 'a') toggleAutoplay();
});
show(0);
"""


def _data_uri(path: Path, *, max_width: int = 1600, quality: int = 80) -> str:
    """Inline a file; raster images are resized/re-encoded (SVG/video pass through)."""
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if mime.startswith("image/") and mime not in {"image/svg+xml"}:
        from io import BytesIO

        from PIL import Image

        with Image.open(path) as image:
            if image.width > max_width:
                image = image.resize(
                    (max_width, round(image.height * max_width / image.width)), Image.LANCZOS
                )
            buffer = BytesIO()
            image.convert("RGB").save(buffer, format="WEBP", quality=quality)
            if buffer.tell() < path.stat().st_size:
                return f"data:image/webp;base64,{base64.b64encode(buffer.getvalue()).decode('ascii')}"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def emit_html(
    deck: DeckManifest,
    claim_ledger: ClaimLedger,
    source_manifest: SourceManifest,
    asset_manifest: AssetManifest,
    *,
    source_manifest_dir: Path,
    asset_manifest_dir: Path,
    output_path: Path,
    max_width: int = 1600,
    quality: int = 80,
) -> OperationReceipt:
    """Validate (via emit_ui_bundle) and write one self-contained deck.html."""
    from .ui_emitter import emit_ui_bundle

    with TemporaryDirectory(prefix="deck-html-") as tmp:
        tmp_dir = Path(tmp)
        _, bundle = emit_ui_bundle(
            deck,
            claim_ledger,
            source_manifest,
            asset_manifest,
            source_manifest_dir=source_manifest_dir,
            asset_manifest_dir=asset_manifest_dir,
            output_dir=tmp_dir,
        )
        slide_sections: list[str] = []
        inlined_assets = 0
        for slide in bundle.slides:
            if slide.hidden:
                continue
            bullets = "".join(
                f'<li style="--i:{i}">{html.escape(line)}</li>' for i, line in enumerate(slide.body)
            )
            visual = ""
            asset = slide.visual.asset
            if asset and asset.file and not asset.missing:
                file_path = tmp_dir / asset.file
                if file_path.exists():
                    uri = _data_uri(file_path, max_width=max_width, quality=quality)
                    inlined_assets += 1
                    if asset.kind == "video":
                        visual = f'<video src="{uri}" controls playsinline aria-label="{html.escape(asset.alt_text)}"></video>'
                    else:
                        visual = f'<img src="{uri}" alt="{html.escape(asset.alt_text)}">'
            footer = f'<p class="footer">{html.escape(slide.footer)}</p>' if slide.footer else ""
            reveal_class = "" if slide.reveal != "none" else " no-reveal"
            slide_sections.append(
                f'<section class="slide t-{slide.transition}{reveal_class}" '
                f'style="--dur:{slide.transition_duration_ms}ms" '
                f'data-notes="{html.escape(slide.notes)}">'
                f"<h1>{html.escape(slide.title)}</h1>"
                f'<p class="message">{html.escape(slide.message)}</p>'
                f"<ul>{bullets}</ul>{visual}{footer}</section>"
            )

    visible = len(slide_sections)
    document = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(bundle.title)}</title>
<style>{_RUNTIME_CSS}</style>
</head>
<body>
<div id="progress"><div style="width:0"></div></div>
<header>
  <span><span class="title">{html.escape(bundle.title)}</span>
  &nbsp;·&nbsp;<span id="counter">Slide 1 of {visible}</span>
  &nbsp;·&nbsp;{html.escape(bundle.visibility)} · {html.escape(bundle.validation_readiness)}</span>
  <span>
    <button id="notesBtn" type="button">Notes (N)</button>
    <button id="autoplay" type="button">AutoPlay (A)</button>
    <button id="fs" type="button">Fullscreen (F)</button>
  </span>
</header>
<main><div id="stage">{''.join(slide_sections)}</div></main>
<div id="notes"></div>
<footer class="bar">
  <span><kbd>←</kbd> <kbd>→</kbd> <kbd>Space</kbd> navigate · <kbd>N</kbd> notes · <kbd>A</kbd> autoplay · <kbd>F</kbd> fullscreen</span>
  <span>self-contained · generated by readme-to-pitchdeck from a validated bundle</span>
</footer>
<script>{_RUNTIME_JS}</script>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8")
    from .artifact_scan import scan_artifact

    scan_artifact(output_path, deck, claim_ledger, source_manifest)
    logger.info("html bundle written: {} ({} slides, {} inlined assets)", output_path, visible, inlined_assets)

    return OperationReceipt(
        schema="readme_to_pitchdeck.emit_html_receipt.v1",
        operation="emit-html",
        readiness=Readiness.READY,
        mocked=False,
        live=False,
        inputs={"deck_id": bundle.deck_id, "slides": str(visible)},
        outputs={"deck_html": str(output_path.resolve())},
        counts={"slides": visible, "inlined_assets": inlined_assets, "bytes": output_path.stat().st_size},
        gaps=[],
        claims=OperationClaims(
            proves=[
                "deck.html was generated from manifests that passed fail-closed validation.",
                "The file references no external resources; assets are inlined data URIs.",
            ],
            does_not_prove=[
                "Visual parity with the React renderer or PPTX (simplified standalone layout).",
                "Later manifest edits are reflected; re-run emit-html.",
            ],
        ),
        seam_validation=SeamValidation(kind="emit_html_receipt"),
    )

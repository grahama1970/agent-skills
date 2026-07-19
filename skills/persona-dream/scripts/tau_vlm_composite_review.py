#!/usr/bin/env python3
"""Route a multi-image OpenAI-style VLM review payload through the single-image Tau node.

Standing operator rule: only /tau may reach /scillm. The sanctioned Tau
panel-reviewer VLM node (via ``tau_vlm_review_adapter``) accepts exactly ONE
image per call. Several persona-dream reviewers (identity/temporal continuity,
face-crop advisory) hand the VLM an ORDERED set of images (an accepted frame
plus one or more identity reference sheets) in a single OpenAI
``messages[].content`` list of ``text`` + ``image_url`` parts.

This module is persona-dream-side glue (NOT a new Tau node): it deterministically
composites the payload's ordered images into ONE labeled vertical montage PNG,
concatenates the payload's text parts (plus a montage legend), routes that single
image + prompt through the existing single-image Tau adapter, and reshapes the
Tau VLM receipt back into an OpenAI-shaped ``{"choices": [...]}`` response so it
is a drop-in for a direct chat-completions image_url POST.

Transport only changes: the caller's model, prompt evidence, and verdict shape
are preserved. The montage is rendered at full per-image width (up to
``_MAX_TILE_W`` px, ``detail: high``) so scene/wardrobe/composition review keeps
its fidelity; where a caller treats the VLM identity verdict as advisory (the
authoritative identity check is a deterministic ArcFace embedding subgate), the
montage layout does not affect the gating decision.
"""
from __future__ import annotations

import base64
import importlib.util as _ilu
import re
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, ImageDraw

_ADAPTER_PATH = Path(__file__).resolve().parent / "tau_vlm_review_adapter.py"
_aspec = _ilu.spec_from_file_location("tau_vlm_review_adapter", _ADAPTER_PATH)
assert _aspec and _aspec.loader
_tau_vlm = _ilu.module_from_spec(_aspec)
_aspec.loader.exec_module(_tau_vlm)

TauVlmRoutingError = _tau_vlm.TauVlmRoutingError

_MAX_TILE_W = 1024
_LABEL_H = 28
_DATA_URI_RE = re.compile(r"^data:(?P<mt>[^;]+);base64,(?P<b64>.+)$", re.DOTALL)


class CompositeVlmError(RuntimeError):
    """Raised when the composited Tau VLM route cannot be completed."""


def _decode_data_uri(url: str) -> bytes:
    m = _DATA_URI_RE.match(url.strip())
    if not m:
        raise CompositeVlmError("image_url is not an inline base64 data URI")
    return base64.b64decode(m.group("b64"))


def _extract_parts(payload: Mapping[str, Any]) -> tuple[list[str], list[tuple[str, bytes]]]:
    """Return (ordered text fragments, ordered [(label, image_bytes)])."""
    texts: list[str] = []
    images: list[tuple[str, bytes]] = []
    for message in payload.get("messages", []):
        role = str(message.get("role", "user")).upper()
        # Preserve the OpenAI message-role hierarchy through the single-prompt
        # Tau node (GOAL_V2 P0.3 / issues-428): system/developer instructions
        # stay distinguishable from user content instead of flattening to
        # peer paragraphs.
        marker = (
            f"[{role} INSTRUCTIONS - highest authority]"
            if role in ("SYSTEM", "DEVELOPER")
            else f"[{role}]"
        )
        content = message.get("content")
        if isinstance(content, str):
            if content.strip():
                texts.append(f"{marker}\n{content.strip()}")
            continue
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, Mapping):
                continue
            ptype = part.get("type")
            if ptype == "text":
                txt = str(part.get("text", "")).strip()
                if txt:
                    texts.append(f"{marker}\n{txt}")
            elif ptype == "image_url":
                url = str((part.get("image_url") or {}).get("url", ""))
                label = str(part.get("label") or f"image {len(images) + 1}")
                images.append((label, _decode_data_uri(url)))
    return texts, images


def _composite(images: list[tuple[str, bytes]], out_path: Path) -> list[str]:
    """Stack the labeled images vertically into out_path. Returns the ordered labels."""
    from io import BytesIO

    tiles: list[tuple[str, Image.Image]] = []
    for label, raw in images:
        img = Image.open(BytesIO(raw)).convert("RGB")
        if img.width > _MAX_TILE_W:
            new_h = round(img.height * (_MAX_TILE_W / img.width))
            img = img.resize((_MAX_TILE_W, new_h))
        tiles.append((label, img))

    width = max((img.width for _, img in tiles), default=_MAX_TILE_W)
    total_h = sum(img.height + _LABEL_H for _, img in tiles)
    canvas = Image.new("RGB", (width, total_h), (16, 16, 16))
    draw = ImageDraw.Draw(canvas)
    labels: list[str] = []
    y = 0
    for label, img in tiles:
        draw.rectangle([0, y, width, y + _LABEL_H], fill=(0, 0, 0))
        draw.text((6, 6 + y), label, fill=(255, 255, 255))
        y += _LABEL_H
        canvas.paste(img, (0, y))
        y += img.height
        labels.append(label)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, format="PNG")
    return labels


IDENTITY_AUTHORITY = "face_embedding_subgate"


def assert_not_identity_decision(purpose: str | None) -> None:
    """GOAL_V2 P0.3 enforcement: this VLM adapter may inform but never DECIDE
    identity. Identity decisions belong to the deterministic ArcFace embedding
    subgate (identity_authority=face_embedding_subgate on every phase-07
    receipt). Callers wanting identity input pass purpose="identity_advisory"."""
    if purpose == "identity_decision":
        raise RuntimeError(
            "identity decisions are reserved for the ArcFace embedding subgate; "
            "this VLM adapter is advisory-only (pass purpose='identity_advisory')"
        )


def post_openai_vlm_via_tau(
    payload: Mapping[str, Any],
    *,
    artifact_dir: str | Path,
    caller_skill: str = "persona-dream",
    purpose: str | None = None,
) -> dict[str, Any]:
    """Drop-in for a direct multi-image chat-completions VLM POST.

    Composites the payload's ordered images, routes the single montage + combined
    prompt through the Tau panel-reviewer VLM node, and returns an OpenAI-shaped
    ``{"choices": [{"message": {"content": <text>}}]}`` dict. Raises
    ``CompositeVlmError`` when the Tau route does not return HTTP 200 so existing
    callers' error handling fails closed exactly as before.
    """
    assert_not_identity_decision(purpose)
    artifact_dir = Path(artifact_dir)
    texts, images = _extract_parts(payload)
    if not images:
        raise CompositeVlmError("no images found in VLM payload")

    composite_path = artifact_dir / "tau_vlm_composite.png"
    labels = _composite(images, composite_path)

    legend = (
        "The single image supplied is a top-to-bottom montage of "
        f"{len(labels)} labeled panels, in this order: "
        + "; ".join(f"{i + 1}) {lbl}" for i, lbl in enumerate(labels))
        + ". Each panel is captioned with its label inside the image. Judge the "
        "actual pixels of each labeled panel."
    )
    prompt = "\n\n".join([*texts, legend]) if texts else legend

    try:
        receipt = _tau_vlm.dispatch_vlm_review(
            composite_path,
            prompt,
            artifact_dir=artifact_dir,
            model=payload.get("model"),
        )
    except TauVlmRoutingError as exc:
        raise CompositeVlmError(f"tau vlm route failed: {exc}") from exc

    if receipt.get("http_status") != 200 or not receipt.get("live_call_performed"):
        raise CompositeVlmError(
            f"tau vlm route did not return HTTP 200 (http={receipt.get('http_status')}, "
            f"error={receipt.get('error')})"
        )
    content = receipt.get("response_content") or ""
    return {
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "_tau_vlm_receipt": receipt,
        "_tau_route": "tau:persona-dream-panel-reviewer:composite",
    }

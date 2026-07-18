#!/usr/bin/env python3
"""Face-crop identity subgate for the Phase 07 storyboard identity reviewer.

Closes the full-frame dilution blind spot: at full-frame scale the vision model
can miss a structural identity divergence (a cooler/paler, narrower-faced Embry)
because the face occupies a small fraction of the panel. This subgate zooms in.

Mechanism (all vision calls go through an injected ``post_fn`` so the geometry
and verdict logic can be unit-tested with no live calls):

  1. Ask the SAME gpt-5.5 vision model to return face bounding boxes for the
     prominent foreground people in the candidate frame (strict JSON, normalized
     0..1 coordinates), and separately for the single clearest front-facing face
     in each reference sheet cell.
  2. Map candidate faces to the required entities by apparent sex, then position.
  3. Crop each face at a generous margin with PIL and upscale the crop to a
     workable resolution.
  4. Run a dedicated FACE-TO-FACE comparison prompt (feature level: face
     shape/width, complexion warmth/undertone, freckling, age markers) for each
     required entity's candidate crop vs its reference crop.

Both the full-frame review AND this subgate must PASS for an identity PASS.
Subgate failure code: ``FAIL_FACE_CROP_IDENTITY_MISMATCH``.

The subgate is purely ADDITIVE — it can only turn a full-frame PASS into a FAIL,
never relax the full-frame gate. It fails closed: if a required entity's face
cannot be located or a comparison call fails, the subgate FAILs.

No provenance (file paths, filenames, "known-bad" labels) is ever placed into a
vision prompt; prompts describe pixels only.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

try:  # PIL is available in the persona-dream venv; import lazily for test isolation.
    from PIL import Image
except Exception:  # pragma: no cover - exercised only where PIL is absent
    Image = None  # type: ignore[assignment]

SUBGATE_FAILURE_CODE = "FAIL_FACE_CROP_IDENTITY_MISMATCH"
SUBGATE_SCHEMA = "persona_dream.identity_face_crop_subgate.v1"

# Candidate-frame category expectation per required identity. Mirrors the
# full-frame contract (Embry = adult woman, Kai = young man); introduces no new
# provenance about which frames are known-bad.
ENTITY_SEX = {"Embry": "female", "Kai": "male"}
ENTITY_POSITION = {"Embry": "left", "Kai": "right"}


# --------------------------------------------------------------------------- #
# Pure geometry / mapping / verdict helpers (unit-tested, no IO, no live calls)
# --------------------------------------------------------------------------- #
def _clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


def normalize_bbox(bbox: Sequence[float], width: int, height: int) -> list[float]:
    """Return ``[x0, y0, x1, y1]`` in normalized 0..1 coordinates.

    Accepts either already-normalized (all values <= 1.0) or pixel coordinates
    (any value > 1.0, divided by the image dimensions). Coordinates are ordered
    and clamped so ``x0 <= x1`` and ``y0 <= y1``.
    """
    if len(bbox) != 4:
        raise ValueError(f"bbox must have 4 values, got {len(bbox)}")
    x0, y0, x1, y1 = (float(v) for v in bbox)
    looks_pixel = any(v > 1.0 for v in (x0, y0, x1, y1))
    if looks_pixel:
        if width <= 0 or height <= 0:
            raise ValueError("image dimensions required to normalize pixel bbox")
        x0, x1 = x0 / width, x1 / width
        y0, y1 = y0 / height, y1 / height
    x0, x1 = sorted((_clamp01(x0), _clamp01(x1)))
    y0, y1 = sorted((_clamp01(y0), _clamp01(y1)))
    return [x0, y0, x1, y1]


def expand_bbox(bbox_norm: Sequence[float], margin: float) -> list[float]:
    """Expand a normalized bbox by ``margin`` (fraction of box size) each side."""
    x0, y0, x1, y1 = bbox_norm
    w, h = (x1 - x0), (y1 - y0)
    return [
        _clamp01(x0 - w * margin),
        _clamp01(y0 - h * margin),
        _clamp01(x1 + w * margin),
        _clamp01(y1 + h * margin),
    ]


def bbox_to_pixels(bbox_norm: Sequence[float], width: int, height: int) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = bbox_norm
    px0, py0 = int(round(x0 * width)), int(round(y0 * height))
    px1, py1 = int(round(x1 * width)), int(round(y1 * height))
    # Keep the origin strictly inside the image so a >=1px box always fits.
    px0 = min(max(px0, 0), max(0, width - 1))
    py0 = min(max(py0, 0), max(0, height - 1))
    px1 = min(max(px1, px0 + 1), width)
    py1 = min(max(py1, py0 + 1), height)
    return px0, py0, px1, py1


def _box_area(face: Mapping[str, Any]) -> float:
    bbox = face.get("bbox_norm") or face.get("bbox") or [0, 0, 0, 0]
    try:
        x0, y0, x1, y1 = bbox
        return max(0.0, (float(x1) - float(x0))) * max(0.0, (float(y1) - float(y0)))
    except Exception:
        return 0.0


def pick_entity_face(faces: Sequence[Mapping[str, Any]], entity: str) -> dict[str, Any] | None:
    """Choose the candidate-frame face that corresponds to ``entity``.

    Priority: prominent foreground faces of the expected apparent sex, largest
    box first; then fall back to expected screen position; then largest box.
    Returns ``None`` if there is no plausible face at all.
    """
    if not faces:
        return None
    want_sex = ENTITY_SEX.get(entity)
    want_pos = ENTITY_POSITION.get(entity)

    def prominent(f: Mapping[str, Any]) -> bool:
        p = str(f.get("prominence") or "").lower()
        return p in ("", "foreground", "midforeground", "mid-foreground", "primary")

    pool = [f for f in faces if prominent(f)] or list(faces)

    by_sex = [f for f in pool if str(f.get("apparent_sex") or "").lower().startswith(want_sex[0])] if want_sex else []
    if by_sex:
        return dict(max(by_sex, key=_box_area))
    by_pos = [f for f in pool if str(f.get("position") or "").lower().startswith(want_pos)] if want_pos else []
    if by_pos:
        return dict(max(by_pos, key=_box_area))
    return dict(max(pool, key=_box_area))


def subgate_verdict(entity_results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate per-entity crop comparisons into the subgate verdict.

    PASS only if every required entity produced a comparison that PASSed. Any
    entity FAIL (mismatch, missing face, or errored call) fails the subgate with
    the ``FAIL_FACE_CROP_IDENTITY_MISMATCH`` code plus a per-entity reason.
    """
    blocking: list[str] = []
    all_pass = bool(entity_results)
    for res in entity_results:
        entity = res.get("entity")
        status = res.get("status")
        if status != "PASS":
            all_pass = False
            reason = res.get("reason") or "; ".join(res.get("divergences") or []) or "face-crop identity mismatch"
            blocking.append(f"{SUBGATE_FAILURE_CODE}: {entity}: {reason}")
    return {
        "status": "PASS" if all_pass else "FAIL",
        "blocking_findings": blocking,
    }


# --------------------------------------------------------------------------- #
# Vision-call helpers (live; ``post_fn`` injected for testing)
# --------------------------------------------------------------------------- #
def _image_url_part(path: Path, label: str) -> dict[str, Any]:
    import base64

    media_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{media_type};base64,{encoded}", "detail": "high"},
        "label": label,
    }


_FRAME_BBOX_PROMPT = "\n".join(
    [
        "You are a face-detection utility. Look at the attached image and locate every",
        "prominent human face (foreground or mid-foreground people; ignore tiny distant",
        "background people).",
        "For EACH such face return a strict-JSON object with:",
        '  "bbox": [x0, y0, x1, y1] as NORMALIZED coordinates in 0..1 (fractions of image',
        "          width/height), tightly around the face (forehead to chin, ear to ear),",
        '  "apparent_sex": "female" | "male" | "unclear",',
        '  "apparent_age": short phrase (e.g. "late 20s", "40s"),',
        '  "position": "left" | "center" | "right",',
        '  "prominence": "foreground" | "midforeground" | "background".',
        "Return ONLY: {\"faces\":[ ... ]}. No prose. If no clear face, return {\"faces\":[]}.",
    ]
)

_REFERENCE_BBOX_PROMPT = "\n".join(
    [
        "You are a face-detection utility. The attached image is a character reference",
        "sheet containing several head/face photos of the SAME person in different poses.",
        "Select UP TO THREE clear, well-lit face photos that span DIFFERENT poses — ideally",
        "one FRONTAL, one THREE-QUARTER, and one PROFILE view (pick the clearest available;",
        "if only some poses exist, return what is available, best first).",
        "For EACH selected face return a strict-JSON object with:",
        '  "bbox": [x0,y0,x1,y1] as NORMALIZED coordinates in 0..1 (fractions of image',
        "          width/height), tight around that one face (forehead to chin, ear to ear),",
        '  "pose": "frontal" | "three-quarter" | "profile".',
        "Return ONLY: {\"faces\":[ ... ]}. No prose. If no usable face, return {\"faces\":[]}.",
    ]
)


def request_face_boxes(
    image_path: Path,
    *,
    model: str,
    post_fn: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    kind: str,
) -> list[dict[str, Any]]:
    """Ask the vision model for face bounding boxes. ``kind`` in {frame, reference}."""
    prompt = _FRAME_BBOX_PROMPT if kind == "frame" else _REFERENCE_BBOX_PROMPT
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You return strict JSON only. No prose."},
            {"role": "user", "content": [{"type": "text", "text": prompt}, _image_url_part(image_path, label=kind)]},
        ],
        "response_format": {"type": "json_object"},
    }
    raw = post_fn(payload)
    text = raw["choices"][0]["message"]["content"]
    parsed = json.loads(text)
    # Both frame and (multi-pose) reference detection now return a "faces" list.
    faces = parsed.get("faces")
    if faces is None and parsed.get("bbox"):  # tolerate legacy single-bbox shape
        faces = [{"bbox": parsed.get("bbox")}]
    faces = faces or []
    valid = [dict(f) for f in faces if isinstance(f, Mapping) and f.get("bbox")]
    return valid[:3] if kind == "reference" else valid


_COMPARE_PROMPT = "\n".join(
    [
        "You are a careful face-identity examiner. IMAGE 1 is a face cropped from a",
        "generated storyboard frame (the CANDIDATE). The remaining images (IMAGE 2, and",
        "IMAGE 3 / IMAGE 4 if present) are multiple views of ONE authoritative TARGET",
        "individual — the SAME reference person shown from different angles (frontal, three-",
        "quarter, profile). Use ALL of them together as your model of the target's face.",
        "Decide whether IMAGE 1 depicts that SAME SPECIFIC INDIVIDUAL — not merely the same",
        "demographic category (same sex / hair colour / age band).",
        "",
        "USE THE POSE-MATCHED REFERENCE. The candidate is often in a 3/4 or profile pose.",
        "Compare its bone proportions against the reference view whose POSE is CLOSEST to",
        "the candidate's (compare a 3/4 candidate to the 3/4 reference view, a profile to",
        "the profile view). This removes pose as an excuse: at a MATCHED pose you can judge",
        "true face width-to-length and jaw/cheek fullness.",
        "",
        "TREAT AS SURFACE / NON-IDENTITY (do NOT fail on these alone):",
        "  - a WARMER, darker, more SUN-TANNED, or more evenly-lit complexion in IMAGE 1",
        "    (expected outdoors; the target is warm-olive-skinned, so warmer is CONSISTENT),",
        "  - wet/slicked hair, sweat, spray, glare, harsh shadow, squint or expression.",
        "",
        "WEIGH HEAVILY AS IDENTITY (judge these at a MATCHED pose):",
        "  - FACE BONE GEOMETRY: width-to-length ratio and overall shape. If, compared at",
        "    the closest-matching pose, the candidate face is clearly NARROWER / LONGER than",
        "    the target's fuller oval face, that is a DIFFERENT person — do NOT excuse a",
        "    narrowness that persists even against the target's OWN 3/4 or profile view.",
        "  - jaw and cheek fullness, cheekbone position, chin shape,",
        "  - nose LENGTH and bridge, brow shape and set, inter-eye spacing,",
        "  - a COOLER or PALER undertone than the warm-olive target (paleness, not tan),",
        "  - a clearly different apparent AGE (a decade or more).",
        "",
        "Method: (1) note the candidate's pose and pick the closest reference view; (2) at",
        "that matched pose, compare width-to-length, jaw/cheek fullness, nose length; (3)",
        "list divergences, labelling each 'surface' (lighting/pose/wetness) or 'structural'",
        "(bone geometry/proportion/age/cool-pale undertone); (4) decide on STRUCTURAL only.",
        "Return strict JSON only with exactly these keys:",
        '{"verdict":"SAME|DIFFERENT","candidate_pose":"frontal|three-quarter|profile",',
        '"matching_features":["..."],"divergences":["..."],',
        '"confidence":"high|medium|low","notes":"<=40 words"}',
        "Decision rule:",
        "  - Return DIFFERENT if there is ANY clear STRUCTURAL divergence at a matched pose",
        "    (face too narrow/long vs the fuller oval target, wrong nose length, cool-pale",
        "    undertone, decade+ age gap).",
        "  - Otherwise, if bone geometry and proportions correspond against the pose-matched",
        "    reference and you can name >=2 concrete matching STRUCTURAL features, return",
        "    SAME. Medium confidence is acceptable for a genuine match across different",
        "    capture conditions; do NOT downgrade a real match to DIFFERENT merely because",
        "    it is not a pixel-identical studio shot.",
        "",
        "DO NOT HEDGE. The faces are clearly visible — you must COMMIT to SAME or DIFFERENT",
        "and cite concrete features. Never answer 'cannot verify' or return DIFFERENT with",
        "an empty divergences list. Reserve 'low' confidence strictly for a genuinely",
        "occluded, tiny, or blurred candidate face (treated as FAIL, fail-closed).",
    ]
)


def _is_noncommittal(parsed: Mapping[str, Any]) -> bool:
    """A response that names neither a matching feature nor a divergence is a hedge."""
    matching = [m for m in (parsed.get("matching_features") or []) if isinstance(m, str)]
    divergences = [d for d in (parsed.get("divergences") or []) if isinstance(d, str)]
    return not matching and not divergences


def compare_face_crops(
    candidate_crop: Path,
    reference_crop: Path | Sequence[Path],
    *,
    entity: str,
    model: str,
    post_fn: Callable[[Mapping[str, Any]], Mapping[str, Any]],
) -> dict[str, Any]:
    reference_crops = [reference_crop] if isinstance(reference_crop, (str, Path)) else list(reference_crop)
    content: list[dict[str, Any]] = [
        {"type": "text", "text": _COMPARE_PROMPT},
        {"type": "text", "text": "IMAGE 1 (CANDIDATE face crop):"},
        _image_url_part(Path(candidate_crop), label="candidate_face"),
    ]
    for i, ref in enumerate(reference_crops, start=2):
        content.append({"type": "text", "text": f"IMAGE {i} (TARGET reference view {i - 1}, same person):"})
        content.append(_image_url_part(Path(ref), label=f"reference_face_{i - 1}"))
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You return strict JSON only. No prose. Judge clearly-visible faces; do not hedge."},
            {"role": "user", "content": content},
        ],
        "response_format": {"type": "json_object"},
    }
    raw = post_fn(payload)
    parsed = json.loads(raw["choices"][0]["message"]["content"])
    # One retry against model variance if the first answer is a non-committal hedge
    # (names neither a matching feature nor a divergence for two clearly-visible faces).
    if _is_noncommittal(parsed):
        raw = post_fn(payload)
        retry = json.loads(raw["choices"][0]["message"]["content"])
        if not _is_noncommittal(retry):
            parsed = retry
    verdict = str(parsed.get("verdict") or "").upper()
    confidence = str(parsed.get("confidence") or "").lower()
    divergences = [str(d) for d in (parsed.get("divergences") or []) if isinstance(d, str)]
    matching = [str(m) for m in (parsed.get("matching_features") or []) if isinstance(m, str)]
    # Fail-closed: SAME counts only with sufficient confidence (high OR medium — a
    # genuine match across different capture conditions, render vs studio photo,
    # rarely reads as "high") and >=2 concrete matching features. "low" confidence
    # means the face was too occluded/blurred to judge structure -> FAIL.
    is_pass = verdict == "SAME" and confidence in ("high", "medium") and len(matching) >= 2
    reason = ""
    if not is_pass:
        if verdict != "SAME":
            reason = "reviewer judged a DIFFERENT specific individual"
        elif confidence not in ("high", "medium"):
            reason = f"match confidence only '{confidence or 'unknown'}' (face not structurally judgeable; fail-closed)"
        else:
            reason = "fewer than 2 concrete matching structural features named (fail-closed)"
        if divergences:
            reason += " | divergences: " + "; ".join(divergences[:4])
    return {
        "entity": entity,
        "status": "PASS" if is_pass else "FAIL",
        "verdict": verdict,
        "confidence": confidence,
        "matching_features": matching,
        "divergences": divergences,
        "reason": reason,
        "notes": parsed.get("notes"),
    }


# --------------------------------------------------------------------------- #
# Crop IO
# --------------------------------------------------------------------------- #
def crop_and_upscale(
    image_path: Path,
    bbox_norm: Sequence[float],
    out_path: Path,
    *,
    margin: float = 0.4,
    min_side: int = 768,
) -> Path:
    """Crop ``image_path`` at ``bbox_norm`` (+margin) and upscale to >= ``min_side``."""
    if Image is None:  # pragma: no cover
        raise RuntimeError("PIL is required for face cropping")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(image_path) as im:
        im = im.convert("RGB")
        width, height = im.size
        expanded = expand_bbox(bbox_norm, margin)
        px = bbox_to_pixels(expanded, width, height)
        crop = im.crop(px)
        cw, ch = crop.size
        longest = max(cw, ch)
        if longest < min_side and longest > 0:
            scale = min_side / longest
            crop = crop.resize((max(1, int(cw * scale)), max(1, int(ch * scale))), Image.LANCZOS)
        crop.save(out_path)
    return out_path


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run_face_crop_subgate(
    *,
    frame_path: Path,
    references: Mapping[str, Path],
    required_entities: Sequence[str],
    model: str,
    post_fn: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    work_dir: Path,
    crop_fn: Callable[..., Path] = crop_and_upscale,
    read_size: Callable[[Path], tuple[int, int]] | None = None,
) -> dict[str, Any]:
    """Run the full face-crop subgate over a frame. Fails closed on any error.

    Returns a receipt dict with ``status`` (PASS|FAIL), ``blocking_findings``,
    and per-entity detail. ``crop_fn`` and ``read_size`` are injectable for tests.
    """
    work_dir.mkdir(parents=True, exist_ok=True)

    def _size(path: Path) -> tuple[int, int]:
        if read_size is not None:
            return read_size(path)
        if Image is None:  # pragma: no cover
            raise RuntimeError("PIL required")
        with Image.open(path) as im:
            return im.size

    entity_results: list[dict[str, Any]] = []
    frame_w, frame_h = _size(frame_path)

    try:
        frame_faces_raw = request_face_boxes(frame_path, model=model, post_fn=post_fn, kind="frame")
    except Exception as exc:
        frame_faces_raw = []
        frame_error = f"frame face detection failed: {exc}"
    else:
        frame_error = ""

    # Normalize candidate face boxes once.
    frame_faces: list[dict[str, Any]] = []
    for f in frame_faces_raw:
        try:
            f = dict(f)
            f["bbox_norm"] = normalize_bbox(f["bbox"], frame_w, frame_h)
            frame_faces.append(f)
        except Exception:
            continue

    for entity in required_entities:
        detail: dict[str, Any] = {"entity": entity, "status": "FAIL"}
        ref_path = references.get(entity)
        if frame_error:
            detail["reason"] = frame_error
            entity_results.append(detail)
            continue
        if ref_path is None or not Path(ref_path).exists():
            detail["reason"] = "missing reference asset for face crop"
            entity_results.append(detail)
            continue
        face = pick_entity_face(frame_faces, entity)
        if not face:
            detail["reason"] = "no candidate face located for required identity (fail-closed)"
            entity_results.append(detail)
            continue
        try:
            ref_faces = request_face_boxes(Path(ref_path), model=model, post_fn=post_fn, kind="reference")
            if not ref_faces:
                detail["reason"] = "no reference face located (fail-closed)"
                entity_results.append(detail)
                continue
            ref_w, ref_h = _size(Path(ref_path))
            cand_crop = crop_fn(frame_path, face["bbox_norm"], work_dir / f"{entity}_candidate_face.png")
            ref_crops: list[Path] = []
            ref_bboxes: list[dict[str, Any]] = []
            for ri, rf in enumerate(ref_faces):
                rbbox = normalize_bbox(rf["bbox"], ref_w, ref_h)
                rc = crop_fn(Path(ref_path), rbbox, work_dir / f"{entity}_reference_face_{ri + 1}.png")
                ref_crops.append(rc)
                ref_bboxes.append({"bbox_norm": rbbox, "pose": rf.get("pose")})
            cmp = compare_face_crops(cand_crop, ref_crops, entity=entity, model=model, post_fn=post_fn)
            cmp["candidate_bbox_norm"] = face["bbox_norm"]
            cmp["reference_views"] = ref_bboxes
            cmp["candidate_crop"] = str(cand_crop)
            cmp["reference_crops"] = [str(p) for p in ref_crops]
            cmp["candidate_face_descriptor"] = {
                k: face.get(k) for k in ("apparent_sex", "apparent_age", "position", "prominence")
            }
            entity_results.append(cmp)
        except Exception as exc:
            detail["reason"] = f"face-crop comparison failed: {exc} (fail-closed)"
            entity_results.append(detail)

    verdict = subgate_verdict(entity_results)
    return {
        "schema": SUBGATE_SCHEMA,
        "status": verdict["status"],
        "blocking_findings": verdict["blocking_findings"],
        "model": model,
        "reviewer_source": f"scillm:{model}:face_crop",
        "frame_path": str(frame_path),
        "entity_results": entity_results,
        "mocked": False,
        "live": True,
    }

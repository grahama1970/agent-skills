#!/usr/bin/env python3
"""Deterministic face-embedding identity subgate for the Phase 07 reviewer.

Why this exists
---------------
gpt-5.5 vision cannot reliably discriminate a near-look-alike (the
``known_bad_sb_001`` case): its face-to-face VERDICT is unstable run-to-run, and
every full-frame prompt strict enough to catch the look-alike over-rejected
genuine matches (see ``reviewer_calibration_receipt.v3.json``). VLMs are not
metric identity verifiers.

The solved approach is ArcFace-family embeddings (InsightFace ``buffalo_l``,
``w600k_r50`` recognition head): detect -> 5-point align -> L2-normalized
embedding -> cosine similarity vs a calibrated threshold. This is the standard
1:1 verification methodology
(https://www.insightface.ai/guides/choose-face-recognition-model-and-evaluate).

Role in the gate
----------------
This subgate is the IDENTITY VERDICT AUTHORITY. The full-frame VLM review still
gates scene / wardrobe / composition and face-visibility, but whether the
depicted person IS the referenced person is decided here by cosine distance, not
by the VLM. Failure code: ``FAIL_FACE_EMBEDDING_IDENTITY_MISMATCH`` (the offending
cosine score is always included in the receipt). The VLM face-crop comparison is
kept only as advisory context.

Determinism
-----------
Same input pixels -> same embeddings -> same scores. All model access goes
through an injected :class:`Embedder`, so verdict/geometry logic is unit-tested
with a mock embedder and no model download.

No provenance (file paths, "known-bad" labels) influences any score; only pixels
and the calibrated threshold matter.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

FAILURE_CODE = "FAIL_FACE_EMBEDDING_IDENTITY_MISMATCH"
SCHEMA = "persona_dream.identity_face_embedding_subgate.v1"

# Calibrated cosine threshold. Chosen from the empirical margin between the
# genuine same-person distribution and the known-bad distribution measured live
# in reviewer_calibration_receipt.v4.json: midpoint of [known_bad_edge 0.3430,
# genuine_edge 0.4991], margin 0.1561. Genuine matches score >= this; identity
# mismatches score below it.
DEFAULT_THRESHOLD = 0.421

# Candidate-frame layout expectation per required identity. Mirrors the
# full-frame / face-crop contract (Embry = adult woman on the left, Kai = young
# man on the right). Position is the deterministic primary key; detected sex is
# recorded as advisory cross-check only.
ENTITY_SEX = {"Embry": "F", "Kai": "M"}
ENTITY_POSITION = {"Embry": "left", "Kai": "right"}


@dataclass
class FaceDet:
    """A single detected + aligned face with its L2-normalized embedding."""

    bbox: list[float]  # [x1, y1, x2, y2] in pixels
    embedding: list[float]  # L2-normalized (‖e‖ == 1) recognition embedding
    det_score: float = 0.0
    sex: str | None = None  # "M" / "F" advisory (from genderage head)

    @property
    def area(self) -> float:
        x1, y1, x2, y2 = self.bbox
        return max(0.0, x2 - x1) * max(0.0, y2 - y1)

    @property
    def cx(self) -> float:
        return (self.bbox[0] + self.bbox[2]) / 2.0


class Embedder(Protocol):
    """Face detector + embedder. Real impl wraps InsightFace; tests inject a mock."""

    def detect(self, image_path: Path) -> list[FaceDet]:
        ...


# --------------------------------------------------------------------------- #
# Pure math / mapping / verdict helpers (unit-tested, no IO, no model)
# --------------------------------------------------------------------------- #
def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity. Inputs are already L2-normalized so this is a dot product,
    but we normalize defensively to stay correct for un-normalized test vectors."""
    import math

    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return float(dot / (na * nb))


def select_foreground_faces(faces: Sequence[FaceDet], n: int) -> list[FaceDet]:
    """Pick the ``n`` largest faces (foreground subjects), rejecting small
    background faces (e.g. distant surfers), then order them left-to-right."""
    by_area = sorted(faces, key=lambda f: f.area, reverse=True)[: max(0, n)]
    return sorted(by_area, key=lambda f: f.cx)


def assign_candidate_faces(
    faces: Sequence[FaceDet], required_entities: Sequence[str]
) -> dict[str, FaceDet | None]:
    """Deterministically map foreground candidate faces to required entities.

    Primary key is horizontal position (ENTITY_POSITION); the top-N largest
    faces are ordered left-to-right and assigned in the required entities'
    position order. Returns ``None`` for any entity whose face is not present.
    """
    ordered_entities = sorted(
        required_entities, key=lambda e: 0 if ENTITY_POSITION.get(e) == "left" else 1
    )
    fg = select_foreground_faces(faces, len(ordered_entities))
    mapping: dict[str, FaceDet | None] = {e: None for e in required_entities}
    for entity, face in zip(ordered_entities, fg):
        mapping[entity] = face
    return mapping


def best_and_pairwise(
    candidate: FaceDet, reference_faces: Sequence[FaceDet]
) -> tuple[float, list[float]]:
    """Cosine of candidate vs every reference-cell view; return (best, all-scores)."""
    scores = [round(cosine(candidate.embedding, r.embedding), 6) for r in reference_faces]
    best = max(scores) if scores else -1.0
    return best, scores


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


# --------------------------------------------------------------------------- #
# Subgate entry point
# --------------------------------------------------------------------------- #
def run_face_embedding_subgate(
    *,
    frame_path: Path,
    references: Mapping[str, Path],
    required_entities: Sequence[str],
    embedder: Embedder,
    threshold: float = DEFAULT_THRESHOLD,
    work_dir: Path | None = None,
) -> dict[str, Any]:
    """Deterministic embedding identity verdict.

    For each required entity: locate its candidate face, compute the cosine
    similarity against the best-matching reference-cell view (plus all pairwise
    scores), and PASS iff best >= ``threshold``. Fails closed: a missing/
    unlocatable candidate face is an identity FAIL, never a silent PASS.
    """
    frame_path = Path(frame_path)
    entity_results: list[dict[str, Any]] = []
    blocking_findings: list[str] = []

    try:
        candidate_faces = embedder.detect(frame_path)
    except Exception as exc:  # fail closed
        return _fail_closed(frame_path, references, threshold, f"candidate detection error: {exc}")

    mapping = assign_candidate_faces(candidate_faces, required_entities)

    for entity in required_entities:
        ref_path = Path(references[entity]) if entity in references else None
        cand = mapping.get(entity)
        if cand is None:
            blocking_findings.append(
                f"{FAILURE_CODE}: {entity}: no foreground face located in candidate frame"
            )
            entity_results.append(
                {
                    "entity": entity,
                    "status": "FAIL",
                    "verdict": "FACE_NOT_LOCATED",
                    "best_cosine": None,
                    "threshold": threshold,
                    "candidate_bbox": None,
                    "reference_face_count": 0,
                    "pairwise_cosine": [],
                }
            )
            continue
        if ref_path is None or not ref_path.exists():
            blocking_findings.append(
                f"{FAILURE_CODE}: {entity}: reference asset missing ({ref_path})"
            )
            entity_results.append(
                {
                    "entity": entity,
                    "status": "FAIL",
                    "verdict": "REFERENCE_MISSING",
                    "best_cosine": None,
                    "threshold": threshold,
                    "candidate_bbox": [round(v, 1) for v in cand.bbox],
                    "reference_face_count": 0,
                    "pairwise_cosine": [],
                }
            )
            continue

        try:
            ref_faces = embedder.detect(ref_path)
        except Exception as exc:
            blocking_findings.append(
                f"{FAILURE_CODE}: {entity}: reference detection error: {exc}"
            )
            entity_results.append(
                {
                    "entity": entity,
                    "status": "FAIL",
                    "verdict": "REFERENCE_DETECTION_ERROR",
                    "best_cosine": None,
                    "threshold": threshold,
                    "candidate_bbox": [round(v, 1) for v in cand.bbox],
                    "reference_face_count": 0,
                    "pairwise_cosine": [],
                }
            )
            continue

        if not ref_faces:
            blocking_findings.append(
                f"{FAILURE_CODE}: {entity}: no face detected in reference sheet"
            )
            entity_results.append(
                {
                    "entity": entity,
                    "status": "FAIL",
                    "verdict": "REFERENCE_NO_FACE",
                    "best_cosine": None,
                    "threshold": threshold,
                    "candidate_bbox": [round(v, 1) for v in cand.bbox],
                    "reference_face_count": 0,
                    "pairwise_cosine": [],
                }
            )
            continue

        best, scores = best_and_pairwise(cand, ref_faces)
        passed = best >= threshold
        if not passed:
            blocking_findings.append(
                f"{FAILURE_CODE}: {entity}: best cosine {best:.4f} < threshold {threshold:.4f} "
                f"(metric identity mismatch)"
            )
        entity_results.append(
            {
                "entity": entity,
                "status": "PASS" if passed else "FAIL",
                "verdict": "SAME" if passed else "DIFFERENT",
                "best_cosine": round(best, 6),
                "threshold": threshold,
                "candidate_bbox": [round(v, 1) for v in cand.bbox],
                "candidate_det_score": round(cand.det_score, 4),
                "candidate_detected_sex": cand.sex,
                "expected_sex": ENTITY_SEX.get(entity),
                "reference_face_count": len(ref_faces),
                "pairwise_cosine": scores,
            }
        )

    status = "PASS" if not blocking_findings else "FAIL"
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "status": status,
        "authority": "embedding_cosine",
        "model": "insightface:buffalo_l:w600k_r50",
        "reviewer_source": "insightface:buffalo_l:cosine",
        "threshold": threshold,
        "failure_code": FAILURE_CODE,
        "frame_path": str(frame_path),
        "frame_sha256": _sha256_file(frame_path) if frame_path.exists() else None,
        "entity_results": entity_results,
        "blocking_findings": blocking_findings,
        "candidate_faces_detected": len(candidate_faces),
        "mocked": getattr(embedder, "mocked", False),
        "live": not getattr(embedder, "mocked", False),
    }
    return result


def _fail_closed(
    frame_path: Path, references: Mapping[str, Path], threshold: float, reason: str
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "status": "FAIL",
        "authority": "embedding_cosine",
        "model": "insightface:buffalo_l:w600k_r50",
        "reviewer_source": "insightface:buffalo_l:cosine",
        "threshold": threshold,
        "failure_code": FAILURE_CODE,
        "frame_path": str(frame_path),
        "entity_results": [],
        "blocking_findings": [f"{FAILURE_CODE}: {reason}"],
        "candidate_faces_detected": 0,
        "mocked": False,
        "live": True,
    }


# --------------------------------------------------------------------------- #
# Real embedder (InsightFace buffalo_l). Imported lazily so tests stay light.
# --------------------------------------------------------------------------- #
@dataclass
class InsightFaceEmbedder:
    """Live embedder backed by InsightFace ``buffalo_l`` on CPU (deterministic).

    The A5000 GPU is acceptable when free, but CPU onnxruntime is the deterministic
    default and the documented acceptable fallback. The model is prepared once and
    reused across calls.
    """

    model_name: str = "buffalo_l"
    providers: tuple[str, ...] = ("CPUExecutionProvider",)
    det_size: tuple[int, int] = (640, 640)
    mocked: bool = field(default=False, init=False)
    _app: Any = field(default=None, init=False, repr=False)

    def _ensure(self) -> Any:
        if self._app is None:
            from insightface.app import FaceAnalysis

            app = FaceAnalysis(name=self.model_name, providers=list(self.providers))
            app.prepare(ctx_id=-1, det_size=self.det_size)
            self._app = app
        return self._app

    def detect(self, image_path: Path) -> list[FaceDet]:
        import cv2
        import numpy as np

        app = self._ensure()
        img = cv2.imread(str(image_path))
        if img is None:
            raise FileNotFoundError(f"could not read image: {image_path}")
        out: list[FaceDet] = []
        for f in app.get(img):
            emb = np.asarray(f.normed_embedding, dtype=np.float64)
            out.append(
                FaceDet(
                    bbox=[float(v) for v in f.bbox],
                    embedding=[float(v) for v in emb],
                    det_score=float(getattr(f, "det_score", 0.0)),
                    sex=getattr(f, "sex", None),
                )
            )
        return out

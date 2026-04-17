"""Merge diagnosis and human label collection for table-lab.

Provides the ``tune-merge`` command that:
1. Diagnoses cross-page merge decisions for a PDF
2. Compares classifier vs. heuristic predictions
3. Collects human corrections → ``data/merge_labels/human_corrections.jsonl``
4. Signals retrain when corrections exceed threshold

Usage::

    # Diagnose merge decisions for a specific PDF
    table-lab tune-merge document.pdf

    # JSON output for programmatic use
    table-lab tune-merge document.pdf --json

    # Label mode — record human corrections
    table-lab tune-merge document.pdf --label
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from .config import CORPUS_ROOT

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_CLASSIFIER_SKILL = Path(__file__).resolve().parents[2] / "create-table-classifier"
HUMAN_LABELS_DIR = _CLASSIFIER_SKILL / "data" / "merge_labels"
HUMAN_CORRECTIONS_PATH = HUMAN_LABELS_DIR / "human_corrections.jsonl"
RETRAIN_THRESHOLD = 50  # trigger retrain after N new corrections


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@dataclass
class MergeDiagnosis:
    """Diagnosis of a single cross-page table pair."""
    pair_index: int
    page_n: int
    page_n1: int
    table_i: int
    table_j: int
    heuristic_merge: bool
    classifier_merge: Optional[bool] = None
    classifier_confidence: float = 0.0
    classifier_model: str = "n/a"
    disagreement: bool = False
    features: Dict[str, Any] = field(default_factory=dict)
    human_label: Optional[str] = None  # "merge" | "separate" | None

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Heuristic re-evaluation (mirrors s05c logic)
# ---------------------------------------------------------------------------

def _heuristic_should_merge(t1: Dict, t2: Dict) -> bool:
    """Re-evaluate s05c heuristic decision for a pair."""
    import pandas as pd

    df1_data = t1.get("pandas_df", [])
    df2_data = t2.get("pandas_df", [])
    if not df1_data or not df2_data:
        return False

    try:
        df1 = pd.DataFrame(df1_data)
        df2 = pd.DataFrame(df2_data)
    except Exception:
        return False

    if df1.empty or df2.empty:
        return False

    title2 = (t2.get("llm_title") or t2.get("title") or "").lower()
    if "continued" in title2:
        return True

    if len(df1.columns) != len(df2.columns):
        return False

    h2 = list(df2.columns)
    is_numeric = all(str(c).isdigit() for c in h2)
    h1 = list(df1.columns)

    b1 = t1.get("bbox")
    b2 = t2.get("bbox")
    if b1 and b2 and len(b1) == 4 and len(b2) == 4:
        w1 = b1[2] - b1[0]
        w2 = b2[2] - b2[0]
        if max(w1, w2) <= 0:
            return False
        inter = max(0, min(b1[2], b2[2]) - max(b1[0], b2[0]))
        width_ratio = min(w1, w2) / max(w1, w2)
        min_w = min(w1, w2)
        if min_w <= 0 or (inter / min_w) <= 0.5 or width_ratio <= 0.9:
            return False
        if is_numeric or h1 == h2:
            return True
    elif is_numeric or h1 == h2:
        return True

    return False


# ---------------------------------------------------------------------------
# Page-half image generation (inlined — only needs fitz + PIL)
# ---------------------------------------------------------------------------

def _extract_page_half_image(pdf_path: Path, page_index: int, half: str, dpi: int = 200):
    """Render top or bottom half of a PDF page to PIL Image."""
    import fitz
    from PIL import Image as PILImage

    doc = fitz.open(str(pdf_path))
    try:
        page = doc[page_index]
        rect = page.rect
        mid_y = (rect.y0 + rect.y1) / 2.0
        if half == "top":
            clip = fitz.Rect(rect.x0, rect.y0, rect.x1, mid_y)
        elif half == "bottom":
            clip = fitz.Rect(rect.x0, mid_y, rect.x1, rect.y1)
        else:
            raise ValueError(f"half must be 'top' or 'bottom', got {half!r}")
        pix = page.get_pixmap(clip=clip, dpi=dpi)
        img = PILImage.frombytes("RGB", (pix.width, pix.height), pix.samples)
    finally:
        doc.close()
    return img


def _concat_page_halves(
    pdf_path: Path, page_n: int, page_n1: int,
    output_path: Optional[Path] = None, dpi: int = 200,
    target_size: Tuple[int, int] = (224, 224),
):
    """Concatenate bottom of page N + top of page N+1 side-by-side."""
    from PIL import Image as PILImage

    bottom = _extract_page_half_image(pdf_path, page_n, "bottom", dpi=dpi)
    top = _extract_page_half_image(pdf_path, page_n1, "top", dpi=dpi)

    target_h = max(bottom.height, top.height)
    if bottom.height != target_h:
        ratio = target_h / bottom.height
        bottom = bottom.resize((int(bottom.width * ratio), target_h))
    if top.height != target_h:
        ratio = target_h / top.height
        top = top.resize((int(top.width * ratio), target_h))

    combined = PILImage.new("RGB", (bottom.width + top.width, target_h))
    combined.paste(bottom, (0, 0))
    combined.paste(top, (bottom.width, 0))
    combined = combined.resize(target_size)

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        combined.save(str(output_path))

    return combined


# ---------------------------------------------------------------------------
# Classifier evaluation (via subprocess to create-table-classifier venv)
# ---------------------------------------------------------------------------

def _classifier_should_merge(
    t1: Dict, t2: Dict, pdf_path: Path
) -> Tuple[Optional[bool], float, str]:
    """Evaluate classifier prediction for a pair.

    Generates the pair image locally (fitz + PIL), then invokes
    merge_inference.py via the create-table-classifier uv venv
    so torch/timm are available without polluting table-lab's deps.

    Returns (should_merge, confidence, model_type).
    """
    import subprocess
    import tempfile

    p1 = t1.get("page_index", 0)
    p2 = t2.get("page_index", 0)

    # Generate pair image locally (fitz + PIL available in table-lab)
    tmp = Path(tempfile.mktemp(suffix=".png"))
    try:
        _concat_page_halves(pdf_path, p1, p2, output_path=tmp)
    except Exception as e:
        logger.debug(f"Image generation failed: {e}")
        return None, 0.0, "image_error"

    # Call merge_inference.py predict via create-table-classifier's uv env
    inference_script = _CLASSIFIER_SKILL / "scripts" / "merge_inference.py"
    if not inference_script.exists():
        logger.debug(f"merge_inference.py not found at {inference_script}")
        try:
            tmp.unlink()
        except Exception as e:
            logger.debug("tmp failed: {}", e)
        return None, 0.0, "unavailable"

    try:
        # Clean env: remove VIRTUAL_ENV so uv uses create-table-classifier's venv
        clean_env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
        result = subprocess.run(
            ["uv", "run", "--project", str(_CLASSIFIER_SKILL),
             "python", str(inference_script), str(tmp), "--json"],
            capture_output=True, text=True, timeout=30,
            cwd=str(_CLASSIFIER_SKILL),
            env=clean_env,
        )
        if result.returncode != 0:
            logger.debug(f"merge_inference.py failed (rc={result.returncode}): {result.stderr[:200]}")
            return None, 0.0, "inference_error"

        # Parse JSON output
        import json as _json
        pred = _json.loads(result.stdout.strip())
        return pred["should_merge"], pred["confidence"], pred.get("model_type", "unknown")

    except subprocess.TimeoutExpired:
        logger.debug("merge_inference.py timed out")
        return None, 0.0, "timeout"
    except Exception as e:
        logger.debug(f"merge_inference.py error: {e}")
        return None, 0.0, "error"
    finally:
        try:
            tmp.unlink()
        except Exception as e:
            logger.debug("tmp failed: {}", e)


# ---------------------------------------------------------------------------
# Main diagnosis
# ---------------------------------------------------------------------------

def diagnose_merges(
    pdf_path: Path,
    tables_json: Optional[Path] = None,
    profile_dir: Optional[Path] = None,
) -> List[MergeDiagnosis]:
    """Diagnose all cross-page merge decisions for a PDF.

    Args:
        pdf_path: Source PDF.
        tables_json: Path to pre-merge tables JSON (S05b or S05).
        profile_dir: Pipeline output directory containing S05/S05b output.

    Returns:
        List of MergeDiagnosis, one per consecutive-page pair.
    """
    # Find tables JSON
    if tables_json is None and profile_dir is not None:
        for candidate in [
            profile_dir / "05b_table_describer" / "json_output" / "05b_tables.json",
            profile_dir / "05_table_extractor" / "json_output" / "05_tables.json",
        ]:
            if candidate.exists():
                tables_json = candidate
                break

    if tables_json is None or not tables_json.exists():
        logger.warning("No tables JSON found for diagnosis")
        return []

    data = json.loads(tables_json.read_text())
    tables = data.get("tables", [])
    if len(tables) < 2:
        return []

    tables.sort(key=lambda t: (t.get("page_index", 0), t.get("bbox", [0])[1]))

    diagnoses: List[MergeDiagnosis] = []
    pair_idx = 0

    for i in range(len(tables) - 1):
        t1 = tables[i]
        t2 = tables[i + 1]
        p1 = t1.get("page_index", 0)
        p2 = t2.get("page_index", 0)

        if p2 != p1 + 1:
            continue

        heur = _heuristic_should_merge(t1, t2)
        cls_merge, cls_conf, cls_model = _classifier_should_merge(t1, t2, pdf_path)

        diag = MergeDiagnosis(
            pair_index=pair_idx,
            page_n=p1,
            page_n1=p2,
            table_i=t1.get("table_index", i),
            table_j=t2.get("table_index", i + 1),
            heuristic_merge=heur,
            classifier_merge=cls_merge,
            classifier_confidence=cls_conf,
            classifier_model=cls_model,
            disagreement=(cls_merge is not None and heur != cls_merge),
        )
        diagnoses.append(diag)
        pair_idx += 1

    return diagnoses


# ---------------------------------------------------------------------------
# Human label recording
# ---------------------------------------------------------------------------

def record_human_label(
    diagnosis: MergeDiagnosis,
    label: str,
    pdf_name: str = "",
    notes: str = "",
) -> None:
    """Append a human correction to the labels file."""
    HUMAN_LABELS_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": time.time(),
        "pdf": pdf_name,
        "page_n": diagnosis.page_n,
        "page_n1": diagnosis.page_n1,
        "table_i": diagnosis.table_i,
        "table_j": diagnosis.table_j,
        "heuristic": "merge" if diagnosis.heuristic_merge else "separate",
        "classifier": "merge" if diagnosis.classifier_merge else ("separate" if diagnosis.classifier_merge is not None else "n/a"),
        "human_label": label,
        "notes": notes,
    }
    with open(HUMAN_CORRECTIONS_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def corrections_count() -> int:
    """Count accumulated human corrections."""
    if not HUMAN_CORRECTIONS_PATH.exists():
        return 0
    return sum(1 for _ in HUMAN_CORRECTIONS_PATH.open())


def should_retrain() -> bool:
    """Check if enough corrections have accumulated to trigger retraining."""
    return corrections_count() >= RETRAIN_THRESHOLD


# ---------------------------------------------------------------------------
# Pair image generation for visual labeling
# ---------------------------------------------------------------------------

def generate_pair_images(
    diagnoses: List[MergeDiagnosis],
    pdf_path: Path,
    output_dir: Optional[Path] = None,
) -> List[Path]:
    """Generate side-by-side page-half images for each diagnosis pair.

    Creates images showing bottom of page N + top of page N+1 concatenated,
    suitable for visual merge/separate labeling.

    Returns list of image paths (one per diagnosis).
    """
    if output_dir is None:
        import tempfile
        output_dir = Path(tempfile.mkdtemp(prefix="merge_pairs_"))

    output_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []

    for diag in diagnoses:
        img_path = output_dir / f"pair_{diag.pair_index}_p{diag.page_n+1}_p{diag.page_n1+1}.png"
        try:
            _concat_page_halves(pdf_path, diag.page_n, diag.page_n1, output_path=img_path)
            paths.append(img_path)
        except Exception as e:
            logger.warning(f"Failed to generate pair image for pair {diag.pair_index}: {e}")
            paths.append(None)

    return paths


# ---------------------------------------------------------------------------
# Interview session for visual labeling
# ---------------------------------------------------------------------------

def create_visual_labeling_session(
    diagnoses: List[MergeDiagnosis],
    pair_images: List[Path],
    pdf_name: str = "",
) -> dict:
    """Create an /interview session for visual merge labeling.

    Args:
        diagnoses: List of MergeDiagnosis to label.
        pair_images: Corresponding pair images from generate_pair_images().
        pdf_name: Source PDF name for context.

    Returns:
        Session questions list for Interview.run().
    """
    questions = []
    for diag, img_path in zip(diagnoses, pair_images):
        if img_path is None or not Path(img_path).exists():
            continue

        heur_str = "MERGE" if diag.heuristic_merge else "SEPARATE"
        cls_str = "MERGE" if diag.classifier_merge else ("SEPARATE" if diag.classifier_merge is not None else "N/A")
        cls_conf = f" ({diag.classifier_confidence:.2f})" if diag.classifier_merge is not None else ""

        q = {
            "id": f"pair_{diag.pair_index}",
            "text": (
                f"Should tables on pages {diag.page_n+1}→{diag.page_n1+1} be merged?\n\n"
                f"Heuristic says: {heur_str}\n"
                f"Classifier says: {cls_str}{cls_conf} ({diag.classifier_model})"
            ),
            "type": "image_compare",
            "header": f"P{diag.page_n+1}→{diag.page_n1+1}",
            "recommendation": "merge" if diag.classifier_merge else "separate",
            "reason": f"Classifier confidence: {diag.classifier_confidence:.2f}",
            "comparison_images": [
                {"path": str(img_path), "label": "Page boundary", "description": "Bottom of page N + Top of page N+1"},
            ],
            "options": [
                {"label": "merge", "description": "These tables should be merged (same table split across pages)"},
                {"label": "separate", "description": "These are distinct tables (should NOT be merged)"},
                {"label": "skip", "description": "Uncertain / cannot tell from image"},
            ],
        }
        questions.append(q)

    return questions


def should_merge_native(
    t1_dict: Dict, t2_dict: Dict, pdf_path: str | Path,
) -> Tuple[bool, float, str]:
    """Public API for /extract-tables to query merge decision.

    Accepts table dicts with keys:
        page_index, page_number, bbox, cols, rows, title, _data (2D list)

    Returns (should_merge, confidence, method) where method is:
        "heuristic", "classifier", or "heuristic+classifier"
    """
    pdf_path = Path(pdf_path)

    # Convert native Table dicts to format expected by heuristic
    def _to_s05_format(t: Dict) -> Dict:
        data = t.get("_data", [])
        return {
            "page_index": t.get("page_index", 0),
            "bbox": t.get("bbox", (0, 0, 0, 0)),
            "title": t.get("title", ""),
            "llm_title": t.get("ai_title", ""),
            "table_index": 0,
            "pandas_df": data,  # 2D list works with pd.DataFrame()
        }

    s05_t1 = _to_s05_format(t1_dict)
    s05_t2 = _to_s05_format(t2_dict)

    # Heuristic
    heur = _heuristic_should_merge(s05_t1, s05_t2)

    # Try classifier (graceful if unavailable)
    cls_merge, cls_conf, cls_model = None, 0.0, "n/a"
    try:
        cls_merge, cls_conf, cls_model = _classifier_should_merge(s05_t1, s05_t2, pdf_path)
    except Exception:
        pass

    # Decision logic
    if cls_merge is not None and cls_conf >= 0.7:
        # High-confidence classifier overrides heuristic
        if cls_merge != heur:
            logger.debug(
                f"Merge disagreement: heuristic={heur}, classifier={cls_merge} "
                f"(conf={cls_conf:.2f}). Using classifier."
            )
        return cls_merge, cls_conf, "classifier"
    elif cls_merge is not None:
        # Low-confidence classifier — use heuristic but report both
        return heur, max(0.5, cls_conf), "heuristic+classifier"
    else:
        # Classifier unavailable — pure heuristic
        return heur, 0.5, "heuristic"


def run_visual_labeling(
    diagnoses: List[MergeDiagnosis],
    pdf_path: Path,
    timeout: int = 600,
) -> int:
    """Run full visual labeling flow via /interview.

    1. Generate pair images
    2. Create interview session
    3. Collect responses
    4. Record human labels

    Returns number of labels recorded.
    """
    import sys

    # Only label disagreements or all if few pairs
    to_label = [d for d in diagnoses if d.disagreement] if len(diagnoses) > 5 else diagnoses
    if not to_label:
        to_label = diagnoses

    if not to_label:
        return 0

    # Generate pair images
    pair_images = generate_pair_images(to_label, pdf_path)
    if not any(p for p in pair_images):
        logger.warning("No pair images generated, cannot run visual labeling")
        return 0

    # Create interview questions
    questions = create_visual_labeling_session(to_label, pair_images, pdf_name=pdf_path.name)
    if not questions:
        return 0

    # Run interview
    try:
        interview_skill = Path(__file__).resolve().parents[2] / "interview"
        if str(interview_skill) not in sys.path:
            sys.path.insert(0, str(interview_skill))
        from interview import Interview
    except ImportError as e:
        logger.warning(f"Interview skill not importable: {e}")
        return 0

    iv = Interview(
        title=f"Merge Labeling: {pdf_path.name}",
        context="Label cross-page table merge decisions. The image shows the bottom of one page and the top of the next.",
    )
    result = iv.run(questions, mode="html", timeout=timeout)

    # Record labels from responses
    labels_recorded = 0
    for diag in to_label:
        qid = f"pair_{diag.pair_index}"
        resp = result.get("responses", {}).get(qid)
        if resp is None:
            continue

        label = resp.get("value", "")
        if label in ("merge", "separate"):
            record_human_label(diag, label, pdf_name=pdf_path.name, notes=resp.get("note", ""))
            labels_recorded += 1

    return labels_recorded

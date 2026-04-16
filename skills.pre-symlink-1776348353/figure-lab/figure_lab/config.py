"""Configuration and paths for figure-lab."""
from __future__ import annotations

from pathlib import Path

# Skill directory
SKILL_DIR = Path(__file__).resolve().parent.parent
GALLERY_DIR = SKILL_DIR / "gallery"
PRESETS_DIR = SKILL_DIR / "presets"
FAILED_DIR = GALLERY_DIR / "_failed"

# Sibling skill paths
SKILLS_ROOT = SKILL_DIR.parent  # .pi/skills/
CREATE_FIGURE_DIR = SKILLS_ROOT / "create-figure"
MEMORY_SKILL = SKILLS_ROOT / "memory"

# d3_catalog.py lives in create-figure
D3_CATALOG_PATH = CREATE_FIGURE_DIR / "d3_catalog.py"

# Evaluation thresholds
PROMOTE_THRESHOLD = 0.75   # Score needed to promote to /create-figure (lowered: heuristic evaluator caps at ~0.78)
RECOMPOSE_THRESHOLD = 0.50 # Below this, start from scratch
MAX_ITERATIONS = 3         # Max self-improvement rounds per composition

# Evaluation weights
EVAL_WEIGHTS = {
    "render_success": 0.30,
    "data_marks": 0.25,
    "axes_labels": 0.15,
    "intent_match": 0.20,
    "distance_aware": 0.10,
}

# Distance-aware requirements (5ft viewing)
MIN_FONT_SIZE_PX = 18
MIN_STROKE_WIDTH_PX = 2
MIN_CONTRAST_RATIO = 4.5  # WCAG AA

# Canvas defaults
CANVAS_ANIMATION_MS = 800
CANVAS_BG = "#f8fafc"
CANVAS_FG = "#1e293b"

# Ensure directories exist
GALLERY_DIR.mkdir(parents=True, exist_ok=True)
PRESETS_DIR.mkdir(parents=True, exist_ok=True)
FAILED_DIR.mkdir(parents=True, exist_ok=True)

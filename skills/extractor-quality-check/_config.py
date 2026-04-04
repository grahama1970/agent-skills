"""Persona autonomous loop — shared constants, paths, and persona configurations.

Central configuration for the persona autonomous loop system. All path
setup, persona definitions, and learning-phase weights live here so
that other modules can import them without circular dependencies.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ── Path setup ──
THIS_DIR = Path(__file__).resolve().parent
SKILLS_DIR = THIS_DIR.parent
ASK_DIR = SKILLS_DIR / "ask"

sys.path.insert(0, str(ASK_DIR))
sys.path.insert(0, str(THIS_DIR))

# ── scillm paved path: add scillm site-packages only if scillm isn't already available ──
# The scillm skill's venv may be a different Python version (e.g. 3.13) than this
# process (e.g. 3.11), causing pydantic_core ABI mismatch.  Only fall back to
# injecting the skill's site-packages when the current interpreter has no scillm.
try:
    import scillm as _scillm_probe  # noqa: F401
except ImportError:
    _SCILLM_VENV = SKILLS_DIR / "scillm" / ".venv"
    # Find a site-packages matching this interpreter's major.minor version
    _PY_VER = f"python{sys.version_info.major}.{sys.version_info.minor}"
    _SCILLM_SITE_PACKAGES = _SCILLM_VENV / "lib" / _PY_VER / "site-packages"
    if not _SCILLM_SITE_PACKAGES.is_dir():
        # Fallback: try any available python version (may cause ABI errors)
        _SCILLM_SITE_PACKAGES = SKILLS_DIR / "scillm" / ".venv" / "lib" / "python3.13" / "site-packages"
    if _SCILLM_SITE_PACKAGES.is_dir() and str(_SCILLM_SITE_PACKAGES) not in sys.path:
        sys.path.insert(0, str(_SCILLM_SITE_PACKAGES))

# ── Teacher label paths (for /create-gpt training) ──
EMBRY_STORAGE = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb"))
CREATE_GPT_DATA = EMBRY_STORAGE / "media/agents/shared/create-gpt/data"
TEACHER_LABELS_DIR = CREATE_GPT_DATA / "tasks" / "raw"
TRAINING_TRIGGER_THRESHOLD = int(os.getenv("TEACHER_LABEL_THRESHOLD", "2000"))
CREATE_GPT_DIR = SKILLS_DIR / "create-gpt"
ASSISTANT_DIR = SKILLS_DIR / "assistant"

# ── Evidence verification for teacher labels ──
VERIFY_TEACHER_LABELS = os.getenv("VERIFY_TEACHER_LABELS", "false").lower() in ("1", "true")
LEAN4_VERIFY_LABELS = os.getenv("LEAN4_VERIFY_LABELS", "false").lower() in ("1", "true")
EVIDENCE_CASE_TIMEOUT = int(os.getenv("EVIDENCE_CASE_TIMEOUT", "30"))
EVIDENCE_CASE_DIR = SKILLS_DIR / "create-evidence-case"
LEAN4_PROVE_DIR = SKILLS_DIR / "lean4-prove"

# ── Data paths ──
SCENARIOS_FILE = Path(os.path.expanduser(
    "~/workspace/experiments/extractor/scenarios/datalake_query_scenarios.json"
))
PROJECT_CONTEXT_FILE = THIS_DIR / "f35_project_context.yaml"
SESSION_DIR = Path(os.path.expanduser("~/.pi/sessions/ask"))

# Memory CLI
MEMORY_AGENT_CLI = Path(os.path.expanduser("~/.local/bin/memory-agent"))
ASK_RUN_SH = ASK_DIR / "run.sh"

# ---------------------------------------------------------------------------
# Shadow method gateway: route teacher calls through /assistant validate()
# ---------------------------------------------------------------------------
use_gateway = os.environ.get("EXTRACTOR_QC_USE_GATEWAY", "1") == "1"
gateway_available = False
gw_validate = None
if use_gateway:
    try:
        if str(ASSISTANT_DIR) not in sys.path:
            sys.path.insert(0, str(ASSISTANT_DIR))
        from assistant import validate as _gw_validate_import
        gw_validate = _gw_validate_import
        gateway_available = True
    except ImportError:
        gateway_available = False

# ── Persona configs ──
PERSONAS = {
    "margaret_chen": {
        "name": "Margaret Chen",
        "scope": "margaret_chen",
        "role": "Senior Requirements Engineer, V&V",
        "org": "Pratt & Whitney",
        "focus": "propulsion",
        # Early phase: extraction cleanup concerns (the datalake is a mess)
        "early_concerns": [
            "tables extracted with wrong column count or merged cells collapsed",
            "section hierarchy flattened -- 4-level DO-178C structure showing as flat",
            "multi-page tables split into fragments instead of merged",
            "OCR garbled numeric values in specification tables",
            "headers and footers extracted as content instead of filtered",
            "figures missing captions or descriptions",
            "empty chunks with no meaningful content",
            "temperature values corrupted by extraction (e.g., 1,832F -> 1832F)",
            "requirement IDs (REQ-xxx, F135-SRS-xxx) not preserved",
            "units lost or mixed up between metric and imperial",
        ],
        # Later phase: real engineering questions (once datalake has integrity)
        "key_concerns": [
            "thermal limit tables from Honeywell Rev C FADEC spec",
            "GKN fan blade fatigue life tables with merged cells",
            "Rolls-Royce unit consistency (Celsius/bar vs Fahrenheit/psi)",
            "F135-SRS requirements traceability",
            "DO-178C section hierarchy preservation",
            "FADEC software requirement shall-statements",
        ],
        "vendor_queries": [
            "Honeywell FADEC interface spec",
            "GKN Aerospace fan blade structural analysis",
            "Rolls-Royce LiftFan interface spec",
            "Pratt & Whitney F135 engine health monitoring",
        ],
    },
    "jennifer_cheung": {
        "name": "Jennifer Cheung",
        "scope": "jennifer_cheung",
        "role": "Systems Engineer, Cybersecurity Division",
        "org": "NIWC Pacific",
        "focus": "mission_systems",
        # Early phase: extraction cleanup concerns
        "early_concerns": [
            "classification markings (CUI, FOUO) extracted as section titles",
            "control tables with merged cells losing column alignment",
            "NIST control IDs (AC-2, SC-7) not preserved as identifiers",
            "multi-column MIL-STD layouts with garbled reading order",
            "CAT I/II/III severity lost when color-coded cells are stripped",
            "page headers/footers polluting section content",
            "protocol tables with misaligned columns after extraction",
            "bibliography references fragmented across multiple chunks",
            "acronym definitions split from their usage context",
            "embedded figures losing their caption and context",
        ],
        # Later phase: real engineering questions
        "key_concerns": [
            "RMF control inheritance chains (AC-2(1) from AC-2)",
            "STIG CAT I/II/III severity classification accuracy",
            "CUI//SP-EXPT markings detected as markings not titles",
            "Link-16 TADIL J message format table column alignment",
            "NIST SP 800-53 Rev.5 control tables",
            "BLOS link budget table extraction fidelity",
        ],
        "vendor_queries": [
            "DAS/EO-DAS sensor fusion interface spec",
            "Link-16 MIDS-JTRS datalink security architecture",
            "Mission Data File loading verification spec",
            "cybersecurity Assessment and Authorization package",
        ],
    },
}

# Learning progression: early = cleanup (extraction errors, fragmentation),
# later = real engineering questions (requirements, cross-doc analysis).
# Margaret and Jennifer arrive at a messy datalake. Their first job is to
# find broken extractions and flag them. As integrity improves, they graduate
# to asking the questions they actually came here to answer.
LEVEL_WEIGHTS = {
    #                   cleanup   triage    stabilize  trust     operate
    "quality":      {"week_1": 0.35, "week_2": 0.25, "week_3": 0.15, "week_4": 0.10, "ongoing": 0.10},
    "corrective":   {"week_1": 0.25, "week_2": 0.20, "week_3": 0.15, "week_4": 0.10, "ongoing": 0.10},
    "discovery":    {"week_1": 0.20, "week_2": 0.15, "week_3": 0.10, "week_4": 0.05, "ongoing": 0.05},
    "table_ops":    {"week_1": 0.10, "week_2": 0.20, "week_3": 0.15, "week_4": 0.10, "ongoing": 0.05},
    "learning":     {"week_1": 0.05, "week_2": 0.10, "week_3": 0.10, "week_4": 0.10, "ongoing": 0.10},
    "cross_doc":    {"week_1": 0.03, "week_2": 0.05, "week_3": 0.15, "week_4": 0.20, "ongoing": 0.20},
    "requirements": {"week_1": 0.02, "week_2": 0.05, "week_3": 0.20, "week_4": 0.35, "ongoing": 0.40},
}

# Task name mapping used across modules
TASK_MAP = {
    "margaret_chen": "extraction-quality-assessor",
    "jennifer_cheung": "cybersecurity-extraction-auditor",
}

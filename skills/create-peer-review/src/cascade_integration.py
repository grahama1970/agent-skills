"""Shadow-LEGO cascade integration for peer review.

Builds a 4-tier CascadeRunner configured for paper section review:
    Tier 0:   Heuristic checks (review_heuristics.py)
    Tier 0.5: Section quality classifier (via /create-classifier)
    Tier 1.5: Reviewer persona GPT (via /create-gpt, QLoRA Qwen2.5-1.5B)
    Tier 2:   Teacher review (via /scillm batch.py)

Shadow mode: Tier 0.5 and 1.5 run alongside the teacher.
Agreement is logged per reviewer persona. When a reviewer GPT
reaches 90% agreement, it is promoted to autonomous operation.

This module imports from common/cascade.py — the same CascadeRunner
used by /assistant, /monitor-taxonomy, and all other Shadow-LEGO skills.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# Resolve paths to common modules
# ---------------------------------------------------------------------------
SKILL_DIR = Path(__file__).parent.parent
SKILLS_DIR = SKILL_DIR.parent
COMMON_DIR = SKILLS_DIR / "common"
SHADOW_FILE = Path.home() / ".pi" / "peer_review" / "shadow.jsonl"
METRICS_FILE = Path.home() / ".pi" / "peer_review" / "metrics.jsonl"

# Ensure directories exist
SHADOW_FILE.parent.mkdir(parents=True, exist_ok=True)

# Add common to path for cascade imports
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))


# Cache cascade imports at module level (Fix #3: avoid per-call reimport)
_cascade_classes: tuple | None = None


def _import_cascade():
    """Lazy import of CascadeRunner and related classes from common/cascade.py.

    Cached at module level — only attempts import once.
    """
    global _cascade_classes
    if _cascade_classes is not None:
        return _cascade_classes

    try:
        from cascade import CascadeRunner, TierDef, TierResult
        _cascade_classes = (CascadeRunner, TierDef, TierResult)
    except ImportError:
        logger.warning("common/cascade.py not importable — using fallback cascade")
        _cascade_classes = (None, None, None)
    return _cascade_classes


# ---------------------------------------------------------------------------
# Tier 0: Heuristic review
# ---------------------------------------------------------------------------
def tier0_heuristic(input_data: dict[str, Any], **kw) -> Any:
    """Tier 0: Fast heuristic checks returning pass/fail with score."""
    from .review_heuristics import HeuristicReviewer

    reviewer = HeuristicReviewer()
    result = reviewer.review_section(
        section_key=input_data.get("section_key", "unknown"),
        content=input_data.get("content", ""),
        references=input_data.get("references", ""),
    )

    CascadeRunner, TierDef, TierResult = _import_cascade()
    if TierResult is not None:
        confidence = 0.95 if result.passed and not result.issues else 0.50
        return TierResult(
            result=result.to_dict(),
            confidence=confidence,
            tier=0,
            source="heuristic",
            latency_ms=0.1,
            cached=False,
            scope="peer_review",
            task="peer_review_section",
        )

    # Fallback: return dict directly
    return {"result": result.to_dict(), "confidence": 0.95 if result.passed else 0.50, "tier": 0}


# ---------------------------------------------------------------------------
# Tier 0.5: Section quality classifier
# ---------------------------------------------------------------------------
def tier05_classifier(input_data: dict[str, Any], **kw) -> Any:
    """Tier 0.5: Lightweight classifier for section quality pass/fail.

    Uses a DistilBERT classifier trained via /create-classifier on
    labeled section quality data. Falls back to heuristic if model
    not available.
    """
    CascadeRunner, TierDef, TierResult = _import_cascade()

    # Try to use /assistant classify() if available
    try:
        assistant_dir = SKILLS_DIR / "assistant"
        if str(assistant_dir) not in sys.path:
            sys.path.insert(0, str(assistant_dir))
        from assistant import classify

        tier_result = classify(
            text=input_data.get("content", ""),
            task="paper_section_quality",
            scope="peer_review",
        )
        return tier_result
    except Exception as e:
        logger.debug(f"Classifier not available, skipping Tier 0.5: {e}")

    # Return low-confidence result to trigger escalation
    if TierResult is not None:
        return TierResult(
            result={"prediction": "unknown", "note": "classifier not available"},
            confidence=0.0,
            tier=0.5,
            source="classifier_unavailable",
            latency_ms=0.0,
            cached=False,
            scope="peer_review",
            task="peer_review_section",
        )
    return {"result": "unknown", "confidence": 0.0, "tier": 0.5}


# ---------------------------------------------------------------------------
# Tier 1.5: Reviewer persona GPT
# ---------------------------------------------------------------------------
def tier15_reviewer_gpt(input_data: dict[str, Any], **kw) -> Any:
    """Tier 1.5: Local reviewer GPT generating full review with scores.

    Uses a QLoRA-fine-tuned Qwen2.5-1.5B model trained on teacher
    reviews harvested from shadow observation. Runs on-device via
    GGUF quantization.
    """
    CascadeRunner, TierDef, TierResult = _import_cascade()

    # Check for trained reviewer GPT model (GGUF or LoRA adapter)
    model_dir = SKILLS_DIR / "create-gpt" / "models" / "peer-review-critic"
    gguf_files = list(model_dir.glob("**/*.gguf")) if model_dir.exists() else []
    # Filter out mock GGUF markers
    gguf_files = [f for f in gguf_files if f.stat().st_size > 1000]
    # Also check for LoRA adapter (safetensors)
    adapter_files = list(model_dir.glob("**/adapter_model.safetensors")) if model_dir.exists() else []

    if not gguf_files and not adapter_files:
        logger.debug("No trained peer-review-critic GPT found, skipping Tier 1.5")
        if TierResult is not None:
            return TierResult(
                result={"note": "reviewer GPT not yet trained"},
                confidence=0.0,
                tier=1.5,
                source="gpt_unavailable",
                latency_ms=0.0,
                cached=False,
                scope="peer_review",
                task="peer_review_section",
            )
        return {"result": "unavailable", "confidence": 0.0, "tier": 1.5}

    # Invoke local GPT inference via infer.py CLI
    try:
        infer_script = SKILLS_DIR / "create-gpt" / "scripts" / "infer.py"
        persona = input_data.get("reviewer_persona", {})
        prompt = _build_review_prompt(input_data, persona)

        # Select inference mode: GGUF (fast, quantized) or HF (adapter, slower)
        if gguf_files:
            mode_args = ["--mode", "gguf", "--model", str(gguf_files[0])]
        else:
            mode_args = ["--mode", "hf"]

        import time as _time
        t0 = _time.monotonic()
        result = subprocess.run(
            ["uv", "run", "--project", str(SKILLS_DIR / "create-gpt"),
             "python", str(infer_script),
             prompt,
             "--task", "peer-review-critic",
             *mode_args,
             "--max-tokens", "512"],
            capture_output=True, text=True, timeout=180,
        )
        latency_ms = (_time.monotonic() - t0) * 1000

        if result.returncode == 0:
            parsed = json.loads(result.stdout.strip())
            # Extract the actual output from infer.py's wrapper
            output = parsed.get("output", parsed)
            confidence = 0.75 if not parsed.get("mock") else 0.3
            if TierResult is not None:
                return TierResult(
                    result=output,
                    confidence=confidence,
                    tier=1.5,
                    source="reviewer_gpt",
                    latency_ms=latency_ms,
                    cached=False,
                    scope="peer_review",
                    task="peer_review_section",
                )
            return {"result": output, "confidence": confidence, "tier": 1.5}
        else:
            logger.warning(f"Tier 1.5 infer.py exit {result.returncode}: {result.stderr[:200]}")
    except Exception as e:
        logger.warning(f"Tier 1.5 GPT inference failed: {e}")

    if TierResult is not None:
        return TierResult(
            result={"note": f"GPT inference failed"},
            confidence=0.0,
            tier=1.5,
            source="gpt_error",
            latency_ms=0.0,
            cached=False,
            scope="peer_review",
            task="peer_review_section",
        )
    return {"result": "error", "confidence": 0.0, "tier": 1.5}


def _parse_llm_response(raw: str) -> dict:
    """Parse raw LLM response text into a structured dict.

    Handles: plain JSON, markdown-fenced JSON (```json ... ```),
    and scillm --json wrapped responses ({"content": "..."}).
    """
    raw = raw.strip()

    # Try direct JSON parse (handles both raw JSON and scillm --json wrapper)
    try:
        parsed = json.loads(raw)
        # scillm --json wraps in {"content": "..."} — unwrap
        if isinstance(parsed, dict) and "content" in parsed and isinstance(parsed["content"], str):
            inner = parsed["content"]
            try:
                return json.loads(inner)
            except json.JSONDecodeError:
                return {"raw_review": inner}
        # Direct JSON (scores, overall_score, etc.) — already structured
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Strip markdown code fences (```json ... ```)
    if raw.startswith("```"):
        lines = raw.split("\n")
        if lines[-1].strip() == "```":
            raw = "\n".join(lines[1:-1]).strip()
        else:
            raw = "\n".join(lines[1:]).strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

    return {"raw_review": raw}


# ---------------------------------------------------------------------------
# Tier 2: Teacher review (scillm)
# ---------------------------------------------------------------------------
def tier2_teacher_review(input_data: dict[str, Any], **kw) -> Any:
    """Tier 2: Authoritative teacher review via /scillm batch.py.

    Generates a full multi-aspect review with scores and rationale.
    Every teacher invocation is logged as potential training data
    for Tier 1.5 reviewer GPTs.
    """
    CascadeRunner, TierDef, TierResult = _import_cascade()

    persona = input_data.get("reviewer_persona", {})
    prompt = _build_review_prompt(input_data, persona)

    try:
        scillm_script = SKILLS_DIR / "scillm" / "batch.py"

        def _run_teacher(model: str, env: dict, use_json: bool = True) -> subprocess.CompletedProcess:
            cmd = [
                "uv", "run", "--project", str(SKILLS_DIR / "scillm"),
                "python", str(scillm_script), "single",
                "--model", model,
                "--timeout", "120",
            ]
            if use_json:
                cmd.append("--json")
            cmd.append(prompt)
            return subprocess.run(cmd, capture_output=True, text=True, timeout=180, env=env)

        # Try Chutes.ai first (free tier)
        chutes_model = os.environ.get("PEER_REVIEW_MODEL", "Qwen/Qwen3-32B")
        result = _run_teacher(chutes_model, os.environ.copy())

        # Fallback to DeepSeek direct API if proxy fails (429/503)
        if result.returncode != 0:
            deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
            if deepseek_key:
                logger.info("Proxy failed, falling back to DeepSeek direct API")
                ds_env = os.environ.copy()
                ds_env["SCILLM_API_BASE"] = "https://api.deepseek.com/v1"
                ds_env["SCILLM_PROXY_KEY"] = deepseek_key
                # DeepSeek returns 400 with json_mode via openai, skip --json
                result = _run_teacher("deepseek-chat", ds_env, use_json=False)

        if result.returncode == 0:
            raw = result.stdout.strip()
            content = _parse_llm_response(raw)

            if TierResult is not None:
                return TierResult(
                    result=content,
                    confidence=0.95,
                    tier=2,
                    source="scillm_teacher",
                    latency_ms=5000.0,
                    cached=False,
                    scope="peer_review",
                    task="peer_review_section",
                )
            return {"result": content, "confidence": 0.95, "tier": 2}

    except Exception as e:
        logger.error(f"Teacher review failed: {e}")

    # Teacher failure: return low-confidence fallback
    if TierResult is not None:
        return TierResult(
            result={"error": "teacher unavailable"},
            confidence=0.3,
            tier=2,
            source="scillm_error",
            latency_ms=0.0,
            cached=False,
            scope="peer_review",
            task="peer_review_section",
        )
    return {"result": "teacher error", "confidence": 0.3, "tier": 2}


# ---------------------------------------------------------------------------
# Cascade builder
# ---------------------------------------------------------------------------
def build_review_cascade(shadow_mode: bool = True):
    """Build a 4-tier CascadeRunner for peer review.

    Args:
        shadow_mode: If True, Tier 0.5 and 1.5 run alongside teacher
                     with agreement logging for self-improvement.

    Returns:
        CascadeRunner instance, or a FallbackCascade if common/cascade.py
        is not importable.
    """
    CascadeRunner, TierDef, TierResult = _import_cascade()

    if CascadeRunner is not None and TierDef is not None:
        tiers = [
            TierDef(
                tier=0,
                name="heuristic",
                fn=tier0_heuristic,
                threshold=0.90,
                shadow_mode=shadow_mode,
                is_teacher=False,
            ),
            TierDef(
                tier=0.5,
                name="classifier",
                fn=tier05_classifier,
                threshold=0.85,
                shadow_mode=shadow_mode,
                is_teacher=False,
            ),
            TierDef(
                tier=1.5,
                name="reviewer_gpt",
                fn=tier15_reviewer_gpt,
                threshold=0.70,
                shadow_mode=shadow_mode,
                is_teacher=False,
            ),
            TierDef(
                tier=2,
                name="teacher",
                fn=tier2_teacher_review,
                threshold=0.0,
                shadow_mode=False,
                is_teacher=True,
            ),
        ]

        return CascadeRunner(
            tiers=tiers,
            shadow_file=SHADOW_FILE,
            metrics_file=METRICS_FILE,
        )

    # Fallback cascade when common/cascade.py is not available
    logger.warning("Using FallbackCascade — common/cascade.py not importable")
    return FallbackCascade(shadow_mode=shadow_mode)


class FallbackCascade:
    """Minimal cascade implementation when common/cascade.py is unavailable.

    Runs tiers sequentially with shadow logging to SHADOW_FILE.
    This ensures the self-improvement loop works even without
    the full CascadeRunner from common/cascade.py.
    """

    def __init__(self, shadow_mode: bool = True):
        self.shadow_mode = shadow_mode
        self.tier_fns = [
            (0, "heuristic", tier0_heuristic, 0.90),
            (0.5, "classifier", tier05_classifier, 0.85),
            (1.5, "reviewer_gpt", tier15_reviewer_gpt, 0.70),
            (2, "teacher", tier2_teacher_review, 0.0),
        ]
        self._shadow_entries: list[dict] = []

    def run(self, input_data: Any, task: str = "", scope: str = "", **kw):
        """Run through tiers until one meets its confidence threshold.

        In shadow mode, the teacher (Tier 2) always runs and its result
        is compared against lower-tier results for agreement tracking.
        """
        last_result = None
        lower_tier_results: list[dict] = []
        teacher_result = None

        for tier_num, name, fn, threshold in self.tier_fns:
            try:
                result = fn(input_data)
                confidence = (
                    result.confidence if hasattr(result, "confidence")
                    else result.get("confidence", 0.0) if isinstance(result, dict)
                    else 0.0
                )
                last_result = result

                if tier_num == 2:
                    teacher_result = result
                elif confidence >= threshold and not self.shadow_mode:
                    return result
                else:
                    lower_tier_results.append({
                        "tier": tier_num,
                        "name": name,
                        "confidence": confidence,
                        "result": result.result if hasattr(result, "result") else result,
                    })

                if confidence >= threshold and not self.shadow_mode:
                    return result
            except Exception as e:
                logger.warning(f"Tier {tier_num} ({name}) failed: {e}")
                continue

        # Shadow logging: compare lower-tier results against teacher
        if self.shadow_mode and teacher_result is not None:
            teacher_score = self._extract_overall(teacher_result)
            teacher_data = teacher_result.result if hasattr(teacher_result, "result") else teacher_result
            input_meta = {k: v for k, v in input_data.items() if k != "content"}

            if lower_tier_results:
                for ltr in lower_tier_results:
                    local_score = self._extract_overall(ltr["result"])
                    agreed = abs(teacher_score - local_score) <= 1.0 if teacher_score > 0 else False
                    entry = {
                        "tier": ltr["tier"],
                        "name": ltr["name"],
                        "local_score": local_score,
                        "teacher_score": teacher_score,
                        "agreed": agreed,
                        "input_data": input_meta,
                        "teacher_result": teacher_data,
                        "task": task,
                        "scope": scope,
                    }
                    self._shadow_entries.append(entry)
                    self._write_shadow_entry(entry)
            else:
                # No lower tiers produced results — log teacher baseline
                # for future training data (Phase 3 bootstrapping)
                entry = {
                    "tier": 2,
                    "name": "teacher_baseline",
                    "local_score": 0.0,
                    "teacher_score": teacher_score,
                    "agreed": False,
                    "input_data": input_meta,
                    "teacher_result": teacher_data,
                    "task": task,
                    "scope": scope,
                }
                self._shadow_entries.append(entry)
                self._write_shadow_entry(entry)

        # Return teacher result if available, else last non-None result
        if teacher_result is not None:
            return teacher_result
        if last_result is not None:
            return last_result

        # All tiers failed
        logger.error("All cascade tiers failed")
        return {"result": "all_tiers_failed", "confidence": 0.0, "tier": -1}

    def _extract_overall(self, result) -> float:
        """Extract overall score from a tier result."""
        if hasattr(result, "result"):
            result = result.result
        if isinstance(result, dict):
            if "overall_score" in result:
                return float(result["overall_score"])
            if "score" in result:
                return float(result["score"])
        return 0.0

    def _write_shadow_entry(self, entry: dict) -> None:
        """Append a shadow observation entry to the shadow JSONL file."""
        try:
            import json as _json
            from datetime import datetime, timezone
            entry["timestamp"] = datetime.now(timezone.utc).isoformat()
            SHADOW_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(SHADOW_FILE, "a") as f:
                f.write(_json.dumps(entry) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write shadow entry: {e}")

    def shadow_report(self) -> dict:
        """Return shadow agreement statistics from the shadow journal."""
        if not SHADOW_FILE.exists():
            return {"total": 0, "agreed": 0, "rate": 0.0, "status": "no_data"}

        try:
            import json as _json
            entries = []
            for line in SHADOW_FILE.read_text().strip().split("\n"):
                if line.strip():
                    entries.append(_json.loads(line))
            total = len(entries)
            agreed = sum(1 for e in entries if e.get("agreed", False))
            rate = agreed / total if total > 0 else 0.0
            status = "ready" if rate >= 0.90 and total >= 50 else "learning" if rate >= 0.70 else "early"
            return {"total": total, "agreed": agreed, "rate": round(rate, 3), "status": status}
        except Exception as e:
            logger.warning(f"Failed to read shadow report: {e}")
            return {"total": 0, "agreed": 0, "rate": 0.0, "status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------
def _build_review_prompt(input_data: dict, persona: dict) -> str:
    """Build the review prompt for Tier 1.5 and Tier 2."""
    section_key = input_data.get("section_key", "unknown")
    content = input_data.get("content", "")
    reviewer_name = persona.get("name", "Anonymous Reviewer")
    voice = persona.get("voice", "")
    expertise = persona.get("expertise", {})
    biases = persona.get("known_biases", {})

    return f"""You are {reviewer_name}, reviewing the "{section_key}" section of a research paper.

Your expertise: {json.dumps(expertise)}
Your reviewing voice: {voice}
You favor: {json.dumps(biases.get('favors', []))}
You are skeptical of: {json.dumps(biases.get('skeptical_of', []))}

SECTION CONTENT:
{content}

Provide a structured JSON review with VENUE-CALIBRATED scoring:
{{
  "scores": {{
    "soundness": <1-4>,
    "technical_novelty": <1-4>,
    "empirical_novelty": <1-4>,
    "significance": <1-4>,
    "clarity": <1-4>,
    "presentation": <1-4>
  }},
  "overall_score": <1-10 HOLISTIC recommendation, DECOUPLED from dimension scores>,
  "confidence": <1-5 self-assessed expertise for this section>,
  "strengths": ["<specific strength with text reference>", ...],
  "weaknesses": ["<specific weakness with actionable fix>", ...],
  "questions": ["<question for authors>", ...],
  "suggestions": ["<concrete improvement suggestion>", ...],
  "code_issues": ["<missing or broken code example>", ...]
}}

SCALE: Dimensions are 1-4 (NeurIPS/ICLR: 1=poor, 2=weak, 3=good, 4=excellent).
Overall is 1-10 HOLISTIC judgment. Do NOT average dimensions mechanically.
A fatal soundness flaw = reject regardless of other scores.

Be specific. Reference exact text. Every weakness must suggest a fix.
If code examples are present, verify syntax. If absent where expected, flag it."""

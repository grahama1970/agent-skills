"""Model Factory — shared train/eval/shadow/promote lifecycle engine.

Composable by any skill that needs model lifecycle management:
  - assistant-lab: CLI + remote training orchestration
  - skill-lab: bond prediction model lifecycle
  - Any future skill needing train → eval → shadow → promote

Usage:
    from model_factory import ModelFactory, ModelFactoryConfig

    # Default: backward-compatible /assistant paths
    factory = ModelFactory()

    # Custom: skill-lab bond predictor
    factory = ModelFactory(ModelFactoryConfig(
        skills_dir=SKILLS_DIR,
        registry_path=STATE_DIR / "bond_registry.json",
        shadow_file=STATE_DIR / "shadow.jsonl",
        metrics_dir=STATE_DIR,
        promote_threshold=0.70,
        min_shadow_samples=20,
    ))

    # Train a new GPT for a task from harvested teacher labels
    result = factory.train_gpt("stress-test-grader", labels_path="...")

    # Evaluate it against the teacher baseline
    eval_result = factory.evaluate_gpt("stress-test-grader")

    # Promote if passing
    if eval_result.passing:
        factory.promote("stress-test-grader", model_type="gpt")

    # Or let the factory decide autonomously
    factory.auto_improve("stress-test-grader")
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

try:
    from model_factory_evidence import build_promotion_evidence, log_non_promotion_evidence
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from model_factory_evidence import build_promotion_evidence, log_non_promotion_evidence

try:
    from model_factory_shadow import check_mode_collapse, shadow_status
except ImportError:
    from model_factory_shadow import check_mode_collapse, shadow_status


def _find_skills_dir() -> Path:
    """Find the skills directory by walking up from this file."""
    return Path(__file__).resolve().parent.parent


def _default_assistant_config() -> "ModelFactoryConfig":
    """Build backward-compatible config for /assistant paths."""
    skills_dir = _find_skills_dir()
    assistant_dir = skills_dir / "assistant"
    metrics_dir = Path(os.environ.get(
        "ASSISTANT_METRICS_DIR",
        str(Path.home() / ".pi" / "assistant"),
    ))
    return ModelFactoryConfig(
        skills_dir=skills_dir,
        registry_path=assistant_dir / "model_registry.json",
        shadow_file=metrics_dir / "shadow.jsonl",
        metrics_dir=metrics_dir,
    )


# Module-level threshold defaults (importable for backward compat)
SHADOW_AGREEMENT_PROMOTE = 0.90
SHADOW_AGREEMENT_RETRAIN = 0.70
SHADOW_AGREEMENT_PLATEAU = 0.80
MIN_SHADOW_SAMPLES = 50


@dataclass
class ModelFactoryConfig:
    """Parameterized configuration for ModelFactory."""
    skills_dir: Path
    registry_path: Path
    shadow_file: Path
    metrics_dir: Path
    promote_threshold: float = SHADOW_AGREEMENT_PROMOTE
    retrain_threshold: float = SHADOW_AGREEMENT_RETRAIN
    plateau_threshold: float = SHADOW_AGREEMENT_PLATEAU
    min_shadow_samples: int = MIN_SHADOW_SAMPLES


@dataclass
class TrainResult:
    """Result from a training operation."""
    task: str
    model_type: str  # "gpt", "classifier", "regressor"
    success: bool
    model_path: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    elapsed_seconds: float = 0.0


@dataclass
class EvalResult:
    """Result from an evaluation operation."""
    task: str
    model_type: str
    agreement_rate: float = 0.0
    accuracy: float = 0.0
    latency_p50_ms: float = 0.0
    passing: bool = False
    details: Dict[str, Any] = field(default_factory=dict)


class ModelFactory:
    """Autonomous model training, evaluation, and promotion engine.

    The warm pond: skills generate what they need for each task by
    composing /create-gpt, /create-classifier, /create-regressor, and
    evaluating with /gpt-lab, /classifier-lab.
    """

    def __init__(
        self,
        config: ModelFactoryConfig | None = None,
        *,
        registry_path: Path | None = None,
    ):
        if config is not None:
            self.config = config
        elif registry_path is not None:
            # Backward compat: old callers passing registry_path positionally
            default = _default_assistant_config()
            default.registry_path = registry_path
            self.config = default
        else:
            self.config = _default_assistant_config()

        self.registry_path = self.config.registry_path  # backward compat alias
        self._registry = self._load_registry()

    def _load_registry(self) -> Dict[str, Any]:
        if self.config.registry_path.exists():
            return json.loads(self.config.registry_path.read_text())
        return {"validators": {}, "classifiers": {}, "regressors": {}}

    def _save_registry(self) -> None:
        self.config.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.registry_path.write_text(
            json.dumps(self._registry, indent=2) + "\n"
        )

    # ------------------------------------------------------------------
    # Training: call create-* skills
    # ------------------------------------------------------------------

    def train_gpt(
        self,
        task: str,
        *,
        labels_path: Optional[str] = None,
        base_model: str = "Qwen/Qwen2.5-1.5B-Instruct",
        method: str = "sft",
        target: str = "local",
    ) -> TrainResult:
        """Train a GPT for a task via /create-gpt.

        Args:
            target: Training target — 'local' uses the local GPU via /create-gpt;
                    'flash' submits to RunPod via FlashTrainer (for 3B+ models).
        """
        start = time.monotonic()

        if target == "flash":
            logger.info(f"train_gpt task={task}: routing to FlashTrainer (target=flash)")
            return self.train_gpt_remote(task)

        create_gpt = self.config.skills_dir / "create-gpt"

        if labels_path is None:
            labels_path = str(self._harvest_labels(task, "gpt"))
            if not labels_path:
                return TrainResult(task=task, model_type="gpt", success=False,
                                   error="No training labels available")

        cmd = (
            f"cd {create_gpt} && ./run.sh train "
            f"--task {task} "
            f"--train-file {labels_path} "
            f"--sft-only"
        )
        logger.info(f"Training GPT for task={task}: {cmd}")
        proc = self._run(cmd, timeout=3600)

        elapsed = time.monotonic() - start
        if proc.returncode != 0:
            return TrainResult(task=task, model_type="gpt", success=False,
                               error=proc.stderr[-500:], elapsed_seconds=elapsed)

        model_path = self._extract_model_path(proc.stdout, "gpt")

        # Auto-export to GGUF for immediate use in Tier 1.5 cascade
        gguf_path = self._export_gguf(task)
        if gguf_path:
            model_path = gguf_path

        return TrainResult(
            task=task, model_type="gpt", success=True,
            model_path=model_path, elapsed_seconds=elapsed,
        )

    def train_classifier(
        self,
        task: str,
        *,
        labels_path: Optional[str] = None,
        model_type: str = "distilbert",
    ) -> TrainResult:
        """Train a classifier for a task via /create-classifier."""
        start = time.monotonic()
        create_classifier = self.config.skills_dir / "create-classifier"

        if labels_path is None:
            labels_path = str(self._harvest_labels(task, "classifier"))
            if not labels_path:
                return TrainResult(task=task, model_type="classifier", success=False,
                                   error="No training labels available")

        cmd = (
            f"cd {create_classifier} && ./run.sh train "
            f"--task {task} "
            f"--train-file {labels_path} "
            f"--model-type {model_type}"
        )
        logger.info(f"Training classifier for task={task}")
        proc = self._run(cmd, timeout=1800)

        elapsed = time.monotonic() - start
        if proc.returncode != 0:
            return TrainResult(task=task, model_type="classifier", success=False,
                               error=proc.stderr[-500:], elapsed_seconds=elapsed)

        model_path = self._extract_model_path(proc.stdout, "classifier")
        return TrainResult(
            task=task, model_type="classifier", success=True,
            model_path=model_path, elapsed_seconds=elapsed,
        )

    def train_regressor(
        self,
        task: str,
        *,
        labels_path: Optional[str] = None,
    ) -> TrainResult:
        """Train a regressor for a task via /create-regressor."""
        start = time.monotonic()
        create_regressor = self.config.skills_dir / "create-regressor"

        if labels_path is None:
            labels_path = str(self._harvest_labels(task, "regressor"))
            if not labels_path:
                return TrainResult(task=task, model_type="regressor", success=False,
                                   error="No training labels available")

        cmd = (
            f"cd {create_regressor} && ./run.sh train "
            f"--task {task} "
            f"{labels_path}"
        )
        logger.info(f"Training regressor for task={task}")
        proc = self._run(cmd, timeout=1800)

        elapsed = time.monotonic() - start
        if proc.returncode != 0:
            return TrainResult(task=task, model_type="regressor", success=False,
                               error=proc.stderr[-500:], elapsed_seconds=elapsed)

        model_path = self._extract_model_path(proc.stdout, "regressor")
        return TrainResult(
            task=task, model_type="regressor", success=True,
            model_path=model_path, elapsed_seconds=elapsed,
        )

    # ------------------------------------------------------------------
    # Evaluation: call *-lab skills
    # ------------------------------------------------------------------

    def evaluate_gpt(self, task: str) -> EvalResult:
        """Benchmark a GPT model via /gpt-lab."""
        gpt_lab = self.config.skills_dir / "gpt-lab"
        cmd = f"cd {gpt_lab} && ./run.sh benchmark --task {task} --json"
        proc = self._run(cmd, timeout=600)

        if proc.returncode != 0:
            return EvalResult(task=task, model_type="gpt",
                              details={"error": proc.stderr[-300:]})

        try:
            result = json.loads(proc.stdout)
            agreement = result.get("agreement_rate", 0.0)
            accuracy = result.get("accuracy", 0.0)
            latency = result.get("latency_p50_ms", 0.0)
            return EvalResult(
                task=task, model_type="gpt",
                agreement_rate=agreement, accuracy=accuracy,
                latency_p50_ms=latency,
                passing=agreement >= self.config.promote_threshold,
                details=result,
            )
        except (json.JSONDecodeError, KeyError) as e:
            return EvalResult(task=task, model_type="gpt",
                              details={"parse_error": str(e)})

    def evaluate_classifier(self, task: str) -> EvalResult:
        """Evaluate a classifier via its lab or built-in eval."""
        create_classifier = self.config.skills_dir / "create-classifier"
        cmd = f"cd {create_classifier} && ./run.sh evaluate --task {task} --json"
        proc = self._run(cmd, timeout=300)

        if proc.returncode != 0:
            return EvalResult(task=task, model_type="classifier",
                              details={"error": proc.stderr[-300:]})

        try:
            result = json.loads(proc.stdout)
            accuracy = result.get("accuracy", 0.0)
            return EvalResult(
                task=task, model_type="classifier",
                accuracy=accuracy,
                passing=accuracy >= 0.85,
                details=result,
            )
        except (json.JSONDecodeError, KeyError) as e:
            return EvalResult(task=task, model_type="classifier",
                              details={"parse_error": str(e)})

    # ------------------------------------------------------------------
    # Promotion: update registry + evidence case
    # ------------------------------------------------------------------

    def promote(
        self,
        task: str,
        model_type: str,
        *,
        model_path: Optional[str] = None,
        confidence_threshold: float = 0.85,
        agreement_rate: float = 0.0,
        sample_count: int = 0,
        wilson_lb: Optional[float] = None,
    ) -> bool:
        """Promote a trained model into the registry.

        Disables shadow_mode if the model was previously shadowed.
        Builds a formal evidence case via /create-evidence-case (non-blocking).
        """
        self._registry = self._load_registry()

        if model_type == "gpt":
            section = "validators"
        elif model_type == "classifier":
            section = "classifiers"
        elif model_type == "regressor":
            if "regressors" not in self._registry:
                self._registry["regressors"] = {}
            section = "regressors"
        else:
            logger.error(f"Unknown model_type: {model_type}")
            return False

        entry = self._registry.get(section, {}).get(task, {})
        if model_path:
            if model_type == "gpt":
                entry["gpt_model_path"] = model_path
            else:
                entry["model_path"] = model_path

        entry["shadow_mode"] = False
        entry["promoted_at"] = int(time.time())
        entry["confidence_threshold"] = confidence_threshold

        if section not in self._registry:
            self._registry[section] = {}
        self._registry[section][task] = entry

        # Build promotion evidence case (non-blocking enrichment)
        ev_agreement = agreement_rate or entry.get("last_agreement_rate", 0.0)
        ev_samples = sample_count or entry.get("last_sample_count", 0)
        ev_wilson = wilson_lb if wilson_lb is not None else entry.get("wilson_lb")
        evidence_case_path = build_promotion_evidence(
            task_name=task,
            model_entry=entry,
            agreement_rate=ev_agreement,
            sample_count=ev_samples,
            wilson_lb=ev_wilson,
        )
        if evidence_case_path:
            entry["evidence_case_path"] = str(evidence_case_path)

        self._save_registry()

        logger.info(f"Promoted {model_type} for task={task} (shadow_mode=False)")
        return True

    # ------------------------------------------------------------------
    # Registry management (public for consumers like skill-lab)
    # ------------------------------------------------------------------

    def update_registry(
        self,
        task: str,
        model_type: str,
        entry: Dict[str, Any],
    ) -> None:
        """Add or update a registry entry for a task."""
        self._registry = self._load_registry()

        if model_type == "gpt":
            section = "validators"
        elif model_type == "classifier":
            section = "classifiers"
        elif model_type == "regressor":
            section = "regressors"
        else:
            logger.error(f"Unknown model_type: {model_type}")
            return

        if section not in self._registry:
            self._registry[section] = {}
        self._registry[section][task] = entry
        self._save_registry()
        logger.info(f"Registry updated: {section}/{task}")

    # ------------------------------------------------------------------
    # Autonomous improvement loop
    # ------------------------------------------------------------------

    def _check_mode_collapse(self, task: str, hours: int = 168) -> Dict[str, Any]:
        """Delegate to model_factory_shadow.check_mode_collapse."""
        return check_mode_collapse(self.config.shadow_file, task, hours)

    def auto_improve(self, task: str) -> Dict[str, Any]:
        """Autonomously decide what to do for a task.

        Reads shadow file to determine agreement rate, then:
          - Check for mode collapse first (force retrain if detected)
          - agreement >= promote_threshold: promote (disable shadow mode)
          - agreement plateau-retrain: try /prompt-lab redesign
          - agreement retrain range: retrain with more teacher labels
          - agreement < retrain: retrain aggressively
          - no model: create from scratch
        """
        status = self._shadow_status(task)
        agreement = status.get("agreement_rate", 0.0)
        sample_count = status.get("sample_count", 0)
        model_type = status.get("model_type", "gpt")

        logger.info(
            f"auto_improve task={task}: agreement={agreement:.1%}, "
            f"samples={sample_count}, model_type={model_type}"
        )

        actions_taken: Dict[str, Any] = {"task": task, "status": status, "actions": []}

        # Suggest FlashTrainer for models >= 3B (too large for local A5000 LoRA)
        model_size_b = self._model_size_b(task)
        if model_size_b >= 3.0:
            flash_hint = (
                f"model ~{model_size_b:.0f}B ≥ 3B — consider FlashTrainer: "
                f"./assistant-lab/run.sh train-remote "
                f"--task {task} --size {model_size_b:.0f}B --target flash"
            )
            actions_taken["flash_suggestion"] = flash_hint
            logger.info(f"auto_improve task={task}: {flash_hint}")

        # Mode collapse check — before any agreement-based decisions
        collapse = self._check_mode_collapse(task)
        if collapse["collapsed"]:
            logger.warning(
                f"Mode collapse detected for task={task}: {collapse['reason']}"
            )
            actions_taken["actions"].append(
                f"mode_collapse_risk: {collapse['reason']} — forcing retrain"
            )
            actions_taken["mode_collapse"] = collapse
            train_result = self._retrain(task, model_type)
            actions_taken["actions"].append(
                f"retrained_due_to_collapse (success={train_result.success})"
            )
            return actions_taken

        if sample_count < self.config.min_shadow_samples:
            actions_taken["actions"].append(
                f"insufficient_samples ({sample_count} < "
                f"{self.config.min_shadow_samples}), need more shadow data"
            )
            return actions_taken

        if agreement >= self.config.promote_threshold:
            self.promote(
                task, model_type,
                agreement_rate=agreement, sample_count=sample_count,
            )
            actions_taken["actions"].append(f"promoted (agreement={agreement:.1%})")

        elif agreement >= self.config.plateau_threshold:
            log_non_promotion_evidence(
                task, "plateau", agreement, sample_count,
                reason=f"agreement {agreement:.1%} between plateau and promote thresholds",
            )
            prompt_result = self._trigger_prompt_lab(task)
            actions_taken["actions"].append(
                f"prompt_lab_triggered (agreement={agreement:.1%}, "
                f"result={prompt_result})"
            )

        elif agreement >= self.config.retrain_threshold:
            log_non_promotion_evidence(
                task, "retrain", agreement, sample_count,
                reason=f"agreement {agreement:.1%} in retrain range",
            )
            train_result = self._retrain(task, model_type)
            trained_on = train_result.metrics.get("trained_on", "local")
            actions_taken["actions"].append(
                f"retrained (agreement={agreement:.1%}, "
                f"success={train_result.success}, via={trained_on})"
            )
            if train_result.success:
                eval_result = self._evaluate(task, model_type)
                actions_taken["actions"].append(
                    f"evaluated (passing={eval_result.passing}, "
                    f"accuracy={eval_result.accuracy:.1%})"
                )
                if eval_result.passing:
                    self.promote(
                        task, model_type, model_path=train_result.model_path,
                        agreement_rate=agreement, sample_count=sample_count,
                    )
                    actions_taken["actions"].append("promoted after retrain+eval")

        else:
            log_non_promotion_evidence(
                task, "low_agreement", agreement, sample_count,
                reason=f"agreement {agreement:.1%} below retrain threshold",
            )
            actions_taken["actions"].append(
                f"low_agreement ({agreement:.1%}), retraining aggressively"
            )
            train_result = self._retrain(task, model_type)
            trained_on = train_result.metrics.get("trained_on", "local")
            actions_taken["actions"].append(
                f"retrained (success={train_result.success}, "
                f"via={trained_on})"
            )

        return actions_taken

    def needs_model(self, task: str) -> Dict[str, Any]:
        """Check if a task needs a model and what type."""
        self._registry = self._load_registry()

        has_gpt = task in self._registry.get("validators", {})
        has_classifier = task in self._registry.get("classifiers", {})
        has_regressor = task in self._registry.get("regressors", {})

        gpt_exists = False
        cls_exists = False
        reg_exists = False

        if has_gpt:
            gpt_path = self._registry["validators"][task].get("gpt_model_path", "")
            gpt_exists = bool(gpt_path) and Path(gpt_path).expanduser().exists()
        if has_classifier:
            cls_path = self._registry["classifiers"][task].get("model_path", "")
            cls_exists = bool(cls_path) and Path(cls_path).expanduser().exists()
        if has_regressor:
            reg_path = self._registry["regressors"][task].get("model_path", "")
            reg_exists = bool(reg_path) and Path(reg_path).expanduser().exists()

        recommendations = []
        if not gpt_exists:
            recommendations.append({
                "action": "train_gpt",
                "skill": "/create-gpt",
                "reason": "no GPT model for tier 1.5",
            })
        if not cls_exists:
            recommendations.append({
                "action": "train_classifier",
                "skill": "/create-classifier",
                "reason": "no classifier for tier 0.5",
            })

        return {
            "task": task,
            "has_gpt": gpt_exists,
            "has_classifier": cls_exists,
            "has_regressor": reg_exists,
            "recommendations": recommendations,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _shadow_status(self, task: str, hours: int = 2160) -> Dict[str, Any]:
        """Delegate to model_factory_shadow.shadow_status."""
        return shadow_status(self.config.shadow_file, task, hours)

    def _harvest_labels(self, task: str, model_type: str) -> Optional[Path]:
        """Harvest teacher labels from shadow file for training."""
        if not self.config.shadow_file.exists():
            return None

        output_dir = self.config.metrics_dir / "training_data" / task
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"labels_{int(time.time())}.jsonl"

        count = 0
        with open(self.config.shadow_file) as sf, open(output_path, "w") as of:
            for line in sf:
                try:
                    entry = json.loads(line)
                    if entry.get("task") != task:
                        continue
                    # Accept both schema variants
                    input_data = entry.get("input_data") or entry.get("input", {})
                    teacher_grade = entry.get("teacher_grade", "")
                    if not teacher_grade:
                        continue
                    # Build chat messages format for /create-gpt SFT trainer
                    user_content = json.dumps(input_data) if isinstance(input_data, dict) else str(input_data)
                    assistant_content = json.dumps({
                        "teacher_grade": teacher_grade,
                        "teacher_confidence": entry.get("teacher_confidence", 0.9),
                    })
                    label = {
                        "messages": [
                            {"role": "user", "content": user_content},
                            {"role": "assistant", "content": assistant_content},
                        ],
                        "teacher_grade": teacher_grade,
                        "source": "shadow_harvest",
                    }
                    of.write(json.dumps(label) + "\n")
                    count += 1
                except json.JSONDecodeError:
                    continue

        if count == 0:
            output_path.unlink(missing_ok=True)
            return None

        logger.info(f"Harvested {count} labels for task={task} → {output_path}")
        return output_path

    def _export_gguf(self, task: str, quantize: str = "Q4_K_M") -> Optional[str]:
        """Export trained LoRA to GGUF via /create-gpt export."""
        create_gpt = self.config.skills_dir / "create-gpt"
        cmd = f"cd {create_gpt} && ./run.sh export --task {task} --quantize {quantize}"
        logger.info(f"Auto-exporting GGUF for task={task} (quantize={quantize})")
        proc = self._run(cmd, timeout=1800)

        if proc.returncode != 0:
            logger.warning(
                f"GGUF export failed for task={task} (non-fatal): "
                f"{proc.stderr[-200:] if proc.stderr else 'unknown error'}"
            )
            return None

        for line in proc.stdout.splitlines():
            if line.strip().endswith(".gguf"):
                return line.strip().split()[-1]
            if "Export complete:" in line:
                return line.split("Export complete:")[-1].strip()
        return None

    def _retrain(self, task: str, model_type: str) -> TrainResult:
        """Retrain the appropriate model type for a task.

        For GPT training: tries local GPU first, falls back to RunPod
        if the error looks GPU-related (OOM, CUDA, no GPU detected).
        """
        if model_type in ("gpt", "validator"):
            result = self.train_gpt(task)
            if not result.success and self._is_gpu_error(result.error):
                logger.warning(
                    f"Local GPU training failed for task={task}, "
                    f"escalating to RunPod: {result.error[:100]}"
                )
                return self.train_gpt_remote(task)
            return result
        elif model_type in ("classifier",):
            return self.train_classifier(task)
        elif model_type in ("regressor",):
            return self.train_regressor(task)
        else:
            result = self.train_gpt(task)
            if not result.success and self._is_gpu_error(result.error):
                logger.warning(
                    f"Local GPU training failed for task={task}, "
                    f"escalating to RunPod"
                )
                return self.train_gpt_remote(task)
            return result

    def _model_size_b(self, task: str) -> float:
        """Estimate model size in billions from the registry entry.

        Checks 'model_size_b' field first, then parses the base_model or
        gpt_model_path string for a pattern like '7B' or '3.8b'.  Falls
        back to 1.5 (the default Qwen2.5-1.5B base) if nothing is found.
        """
        import re
        entry = (
            self._registry.get("validators", {}).get(task)
            or self._registry.get("classifiers", {}).get(task)
            or {}
        )
        if "model_size_b" in entry:
            return float(entry["model_size_b"])
        candidate = entry.get("base_model", "") or entry.get("gpt_model_path", "")
        m = re.search(r"(\d+(?:\.\d+)?)\s*[Bb]", candidate)
        if m:
            return float(m.group(1))
        return 1.5  # default: assume 1.5B (Qwen2.5-1.5B-Instruct)

    def _is_gpu_error(self, error: str) -> bool:
        """Detect if a training failure is GPU-related (worth escalating to RunPod)."""
        gpu_indicators = [
            "cuda", "gpu", "out of memory", "oom", "no gpu",
            "torch.cuda", "nvidia", "nccl", "cublas",
            "RuntimeError: CUDA", "no CUDA GPUs", "TIMEOUT",
        ]
        error_lower = error.lower()
        return any(indicator.lower() in error_lower for indicator in gpu_indicators)

    def train_gpt_remote(
        self,
        task: str,
        *,
        model_size: str = "1.5B",
        max_cost: str = "15.00",
    ) -> TrainResult:
        """Train a GPT on RunPod when local GPU is unavailable."""
        start = time.monotonic()
        assistant_lab = self.config.skills_dir / "assistant-lab"

        cmd = (
            f"cd {assistant_lab} && ./run.sh train-remote "
            f"--task {task} "
            f"--size {model_size} "
            f"--max-cost {max_cost} "
            f"--confirm"
        )
        logger.info(f"FlashTrainer remote training for task={task} size={model_size}")
        proc = self._run(cmd, timeout=7200)  # 2h for remote training

        elapsed = time.monotonic() - start
        if proc.returncode != 0:
            return TrainResult(
                task=task, model_type="gpt", success=False,
                error=f"RunPod training failed: {proc.stderr[-500:]}",
                elapsed_seconds=elapsed,
            )

        model_path = self._extract_model_path(proc.stdout, "gpt")
        return TrainResult(
            task=task, model_type="gpt", success=True,
            model_path=model_path, elapsed_seconds=elapsed,
            metrics={"trained_on": "flash", "model_size": model_size},
        )

    def _evaluate(self, task: str, model_type: str) -> EvalResult:
        """Evaluate via the appropriate lab skill."""
        if model_type in ("gpt", "validator"):
            return self.evaluate_gpt(task)
        elif model_type in ("classifier",):
            return self.evaluate_classifier(task)
        else:
            return EvalResult(task=task, model_type=model_type)

    def _trigger_prompt_lab(self, task: str) -> str:
        """Signal /prompt-lab to redesign prompts for a task."""
        prompt_lab = self.config.skills_dir / "prompt-lab"
        cmd = (
            f"cd {prompt_lab} && ./run.sh iterate "
            f"--task {task} --scope brandon_bailey --max-rounds 3"
        )
        proc = self._run(cmd, timeout=600)
        return "ok" if proc.returncode == 0 else f"failed (rc={proc.returncode})"

    def _extract_model_path(self, stdout: str, model_type: str) -> str:
        """Extract model output path from training command stdout."""
        for line in stdout.splitlines():
            line = line.strip()
            if "model_path=" in line:
                return line.split("model_path=")[-1].strip()
            if "saved to" in line.lower() or "output:" in line.lower():
                parts = line.split()
                for p in reversed(parts):
                    if "/" in p and (p.endswith(".gguf") or p.endswith(".joblib")
                                     or Path(p).suffix == "" and len(p) > 10):
                        return p
        return ""

    def _run(self, cmd: str, timeout: int = 300) -> Any:
        """Run a subprocess command."""
        try:
            proc = subprocess.run(
                ["bash", "-lc", cmd],
                capture_output=True, text=True,
                timeout=timeout, check=False,
                env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
            )
            return proc
        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out after {timeout}s: {cmd[:80]}")

            class TimedOut:
                returncode = -1
                stdout = ""
                stderr = f"TIMEOUT after {timeout}s"
            return TimedOut()

"""
Prompt Lab Skill - Evaluation
Test cases, evaluation results, and metrics calculation.
"""
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from config import (
    SKILL_DIR,
    PROMPTS_DIR,
    GROUND_TRUTH_DIR,
    VOCABULARY_PROMPT_SECTION,
)


@dataclass
class TestCase:
    """A single test case with input and expected output."""
    id: str
    name: str
    description: str
    expected_conceptual: List[str]
    expected_tactical: List[str]
    notes: str = ""


@dataclass
class EvalResult:
    """Result of evaluating a single test case."""
    case_id: str
    predicted_conceptual: List[str]
    predicted_tactical: List[str]
    expected_conceptual: List[str]
    expected_tactical: List[str]
    rejected_tags: List[str]
    confidence: float
    latency_ms: float
    correction_rounds: int = 0
    correction_success: bool = True

    @property
    def conceptual_precision(self) -> float:
        if not self.predicted_conceptual:
            return 1.0 if not self.expected_conceptual else 0.0
        correct = len(set(self.predicted_conceptual) & set(self.expected_conceptual))
        return correct / len(self.predicted_conceptual)

    @property
    def conceptual_recall(self) -> float:
        if not self.expected_conceptual:
            return 1.0
        correct = len(set(self.predicted_conceptual) & set(self.expected_conceptual))
        return correct / len(self.expected_conceptual)

    @property
    def tactical_precision(self) -> float:
        if not self.predicted_tactical:
            return 1.0 if not self.expected_tactical else 0.0
        correct = len(set(self.predicted_tactical) & set(self.expected_tactical))
        return correct / len(self.predicted_tactical)

    @property
    def tactical_recall(self) -> float:
        if not self.expected_tactical:
            return 1.0
        correct = len(set(self.predicted_tactical) & set(self.expected_tactical))
        return correct / len(self.expected_tactical)

    @property
    def f1(self) -> float:
        """Combined F1 across both tag types."""
        all_pred = set(self.predicted_conceptual + self.predicted_tactical)
        all_exp = set(self.expected_conceptual + self.expected_tactical)

        if not all_pred and not all_exp:
            return 1.0
        if not all_pred or not all_exp:
            return 0.0

        correct = len(all_pred & all_exp)
        precision = correct / len(all_pred)
        recall = correct / len(all_exp)

        if precision + recall == 0:
            return 0.0
        return 2 * precision * recall / (precision + recall)


@dataclass
class EvalSummary:
    """Summary of evaluation run."""
    prompt_name: str
    model_name: str
    timestamp: str
    results: List[EvalResult]

    @property
    def avg_f1(self) -> float:
        return sum(r.f1 for r in self.results) / len(self.results) if self.results else 0.0

    @property
    def avg_conceptual_precision(self) -> float:
        return sum(r.conceptual_precision for r in self.results) / len(self.results) if self.results else 0.0

    @property
    def avg_conceptual_recall(self) -> float:
        return sum(r.conceptual_recall for r in self.results) / len(self.results) if self.results else 0.0

    @property
    def avg_tactical_precision(self) -> float:
        return sum(r.tactical_precision for r in self.results) / len(self.results) if self.results else 0.0

    @property
    def avg_tactical_recall(self) -> float:
        return sum(r.tactical_recall for r in self.results) / len(self.results) if self.results else 0.0

    @property
    def total_rejected(self) -> int:
        return sum(len(r.rejected_tags) for r in self.results)

    @property
    def avg_latency_ms(self) -> float:
        return sum(r.latency_ms for r in self.results) / len(self.results) if self.results else 0.0

    @property
    def total_correction_rounds(self) -> int:
        return sum(r.correction_rounds for r in self.results)

    @property
    def correction_success_rate(self) -> float:
        if not self.results:
            return 1.0
        return sum(1 for r in self.results if r.correction_success) / len(self.results)

    @property
    def cases_needing_correction(self) -> int:
        return sum(1 for r in self.results if r.correction_rounds > 0)


@dataclass
class QRATestCase:
    """A QRA test case with input and expected keywords."""
    id: str
    name: str
    description: str
    collection: str
    item_type: str
    question_keywords: List[str]
    reasoning_keywords: List[str]
    min_reasoning_sentences: int
    notes: str = ""


@dataclass
class QRAResult:
    """Result of evaluating a QRA generation."""
    case_id: str
    question: str
    reasoning: str
    answer: str
    confidence: float
    question_keyword_hits: int
    question_keyword_total: int
    reasoning_keyword_hits: int
    reasoning_keyword_total: int
    reasoning_sentences: int
    latency_ms: float

    @property
    def question_score(self) -> float:
        if self.question_keyword_total == 0:
            return 1.0
        return self.question_keyword_hits / self.question_keyword_total

    @property
    def reasoning_score(self) -> float:
        if self.reasoning_keyword_total == 0:
            return 1.0
        return self.reasoning_keyword_hits / self.reasoning_keyword_total

    @property
    def overall_score(self) -> float:
        return (self.question_score + self.reasoning_score) / 2


def count_sentences(text: str) -> int:
    """Count approximate sentences in text."""
    sentences = re.split(r'[.!?]+', text)
    return len([s for s in sentences if s.strip()])


def check_keywords(text: str, keywords: List[str]) -> int:
    """Count how many keywords appear in text (case-insensitive)."""
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw.lower() in text_lower)


def load_prompt(prompt_name: str, skill_dir: Optional[Path] = None) -> tuple[str, str]:
    """
    Load a prompt template.

    Args:
        prompt_name: Name of the prompt file (without .txt)
        skill_dir: Override skill directory

    Returns:
        Tuple of (system_prompt, user_template)
    """
    if skill_dir is None:
        skill_dir = SKILL_DIR

    prompt_file = skill_dir / "prompts" / f"{prompt_name}.txt"

    if not prompt_file.exists():
        # Create default taxonomy prompt
        default_prompt = f"""[SYSTEM]
You are a cybersecurity taxonomy classifier.
Extract conceptual and tactical bridge tags from the given security control or technique.

Return ONLY valid JSON in this format:
{{"conceptual": ["tag1", "tag2"], "tactical": ["tag1"], "confidence": 0.8}}

{VOCABULARY_PROMPT_SECTION}

Choose tags that best describe the PRIMARY purpose. Include confidence (0.0-1.0).
Extract 1-3 conceptual tags and 1-2 tactical tags. Be precise, not exhaustive.

[USER]
Control: {{name}}

Description: {{description}}
"""
        prompt_file.parent.mkdir(parents=True, exist_ok=True)
        prompt_file.write_text(default_prompt)

    content = prompt_file.read_text()

    # Parse [SYSTEM] and [USER] sections
    if "[SYSTEM]" in content and "[USER]" in content:
        parts = content.split("[USER]")
        system = parts[0].replace("[SYSTEM]", "").strip()
        user = parts[1].strip()
    else:
        system = content.strip()
        user = "Control: {name}\n\nDescription: {description}"

    return system, user


def load_ground_truth(name: str, skill_dir: Optional[Path] = None) -> List[TestCase]:
    """
    Load ground truth test cases.

    Args:
        name: Name of the ground truth file
        skill_dir: Override skill directory

    Returns:
        List of TestCase objects
    """
    if skill_dir is None:
        skill_dir = SKILL_DIR

    gt_file = skill_dir / "ground_truth" / f"{name}.json"

    if not gt_file.exists():
        # Create default taxonomy ground truth
        default_gt = {
            "name": "taxonomy",
            "description": "Bridge tag extraction for SPARTA controls",
            "cases": [
                {
                    "id": "T1547.001",
                    "input": {
                        "name": "Registry Run Keys / Startup Folder",
                        "description": "Adversaries may achieve persistence by adding a program to a startup folder or referencing it with a Registry run key."
                    },
                    "expected": {
                        "conceptual": ["Corruption"],
                        "tactical": ["Persist"]
                    },
                    "notes": "Classic persistence technique"
                },
                {
                    "id": "SI-2",
                    "input": {
                        "name": "Flaw Remediation",
                        "description": "The organization identifies, reports, and corrects information system flaws."
                    },
                    "expected": {
                        "conceptual": ["Resilience", "Fragility"],
                        "tactical": ["Harden"]
                    },
                    "notes": "NIST hardening control"
                },
                {
                    "id": "d3f:NetworkIsolation",
                    "input": {
                        "name": "Network Isolation",
                        "description": "Configuring a network to deny connections based on source or destination IP address ranges."
                    },
                    "expected": {
                        "conceptual": ["Resilience"],
                        "tactical": ["Isolate"]
                    },
                    "notes": "D3FEND isolation technique"
                },
                {
                    "id": "CWE-89",
                    "input": {
                        "name": "SQL Injection",
                        "description": "The software constructs SQL commands using externally-influenced input without proper neutralization."
                    },
                    "expected": {
                        "conceptual": ["Fragility"],
                        "tactical": ["Exploit"]
                    },
                    "notes": "Classic injection weakness"
                },
                {
                    "id": "T1070.001",
                    "input": {
                        "name": "Clear Windows Event Logs",
                        "description": "Adversaries may clear Windows Event Logs to hide the activity of an intrusion."
                    },
                    "expected": {
                        "conceptual": ["Stealth"],
                        "tactical": ["Evade"]
                    },
                    "notes": "Defense evasion technique"
                },
                {
                    "id": "AC-2",
                    "input": {
                        "name": "Account Management",
                        "description": "The organization manages information system accounts including establishing, activating, modifying, reviewing, disabling, and removing accounts."
                    },
                    "expected": {
                        "conceptual": ["Loyalty"],
                        "tactical": ["Harden", "Detect"]
                    },
                    "notes": "NIST access control"
                },
                {
                    "id": "T1595",
                    "input": {
                        "name": "Active Scanning",
                        "description": "Adversaries may execute active reconnaissance scans to gather information that can be used during targeting."
                    },
                    "expected": {
                        "conceptual": ["Precision"],
                        "tactical": ["Model"]
                    },
                    "notes": "Reconnaissance technique"
                },
                {
                    "id": "CP-9",
                    "input": {
                        "name": "Information System Backup",
                        "description": "The organization conducts backups of user-level and system-level information contained in the information system."
                    },
                    "expected": {
                        "conceptual": ["Resilience"],
                        "tactical": ["Restore"]
                    },
                    "notes": "NIST backup control"
                }
            ]
        }
        gt_file.parent.mkdir(parents=True, exist_ok=True)
        gt_file.write_text(json.dumps(default_gt, indent=2))

    data = json.loads(gt_file.read_text())

    cases = []
    for c in data.get("cases", []):
        cases.append(TestCase(
            id=c["id"],
            name=c["input"]["name"],
            description=c["input"]["description"],
            expected_conceptual=c["expected"].get("conceptual", []),
            expected_tactical=c["expected"].get("tactical", []),
            notes=c.get("notes", "")
        ))

    return cases


def load_qra_ground_truth(skill_dir: Optional[Path] = None) -> List[QRATestCase]:
    """Load QRA ground truth test cases."""
    if skill_dir is None:
        skill_dir = SKILL_DIR

    gt_file = skill_dir / "ground_truth" / "qra.json"
    if not gt_file.exists():
        return []

    data = json.loads(gt_file.read_text())
    cases = []
    for c in data.get("cases", []):
        cases.append(QRATestCase(
            id=c["id"],
            name=c["input"]["name"],
            description=c["input"]["description"],
            collection=c["input"].get("collection", ""),
            item_type=c["input"].get("type", ""),
            question_keywords=c["expected"].get("question_contains", []),
            reasoning_keywords=c["expected"].get("reasoning_contains", []),
            min_reasoning_sentences=c["expected"].get("min_reasoning_sentences", 2),
            notes=c.get("notes", "")
        ))
    return cases


def load_models_config(skill_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Load models configuration from models.json."""
    if skill_dir is None:
        skill_dir = SKILL_DIR

    from config import DEFAULT_MODELS_CONFIG, MODELS_FILE

    models_file = skill_dir / "models.json"
    if not models_file.exists():
        models_file.write_text(json.dumps(DEFAULT_MODELS_CONFIG, indent=2))

    return json.loads(models_file.read_text())


def save_eval_results(
    summary: EvalSummary,
    results: List[EvalResult],
    passed: bool,
    skill_dir: Optional[Path] = None,
) -> Path:
    """
    Save evaluation results to JSON file.

    Returns:
        Path to saved results file
    """
    if skill_dir is None:
        skill_dir = SKILL_DIR

    results_dir = skill_dir / "results"
    results_dir.mkdir(exist_ok=True)
    results_file = results_dir / f"{summary.prompt_name}_{summary.model_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    results_data = {
        "prompt": summary.prompt_name,
        "model": summary.model_name,
        "timestamp": summary.timestamp,
        "passed": passed,
        "metrics": {
            "avg_f1": summary.avg_f1,
            "conceptual_precision": summary.avg_conceptual_precision,
            "conceptual_recall": summary.avg_conceptual_recall,
            "tactical_precision": summary.avg_tactical_precision,
            "tactical_recall": summary.avg_tactical_recall,
            "total_rejected": summary.total_rejected,
            "avg_latency_ms": summary.avg_latency_ms,
            "correction_rounds": summary.total_correction_rounds,
            "cases_needing_correction": summary.cases_needing_correction,
            "correction_success_rate": summary.correction_success_rate,
        },
        "cases": [
            {
                "id": r.case_id,
                "predicted": {"conceptual": r.predicted_conceptual, "tactical": r.predicted_tactical},
                "expected": {"conceptual": r.expected_conceptual, "tactical": r.expected_tactical},
                "rejected": r.rejected_tags,
                "f1": r.f1,
                "latency_ms": r.latency_ms,
                "correction_rounds": r.correction_rounds,
                "correction_success": r.correction_success,
            }
            for r in results
        ]
    }

    results_file.write_text(json.dumps(results_data, indent=2))
    return results_file

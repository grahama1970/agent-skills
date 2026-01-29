#!/usr/bin/env python3
"""
Prompt Lab: Systematic prompt engineering with ground truth evaluation.

Architecture:
  Stage 1: LLM extraction with vocabulary presented in prompt
  Stage 2: Pydantic validation to detect hallucinated outputs
  Stage 3: SELF-CORRECTION LOOP - If invalid tags detected, send assistant
           correction message back to LLM asking it to fix its output

This three-stage approach ensures:
  - LLM knows valid options (vocabulary in prompt)
  - Invalid outputs are detected (Pydantic validation)
  - LLM gets a chance to self-correct before we reject
  - Metrics track correction rounds and success rate

Integration:
  - Iteration rounds (like /code-review)
  - Task-monitor integration for quality gates
"""

import json
import os
import re
import sys
import asyncio
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set
from enum import Enum

try:
    import typer
    from pydantic import BaseModel, Field, field_validator
    from rich.console import Console
    from rich.table import Table
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "typer", "pydantic", "rich", "-q"])
    import typer
    from pydantic import BaseModel, Field, field_validator
    from rich.console import Console
    from rich.table import Table

# =============================================================================
# VOCABULARY DEFINITIONS (Presented to LLM in prompt)
# =============================================================================

TIER0_CONCEPTUAL = {"Precision", "Resilience", "Fragility", "Corruption", "Loyalty", "Stealth"}
TIER1_TACTICAL = {"Model", "Harden", "Detect", "Isolate", "Restore", "Evade", "Exploit", "Persist"}

VOCABULARY_PROMPT_SECTION = """
Valid conceptual tags (Tier 0 - abstract concepts):
- Precision: Exactness, targeting, reconnaissance, enumeration
- Resilience: Recovery, hardening, defense, protection, restoration
- Fragility: Weakness, vulnerability, exploit, misconfiguration
- Corruption: Persistence, backdoor, unauthorized modification, malware
- Loyalty: Authentication, authorization, trust, access control
- Stealth: Evasion, obfuscation, anti-forensics, defense evasion

Valid tactical tags (Tier 1 - D3FEND actions):
- Model: Enumerate, map, discover, fingerprint
- Harden: Patch, configure, restrict, secure
- Detect: Monitor, alert, log, analyze
- Isolate: Segment, quarantine, contain
- Restore: Backup, recover, rollback
- Evade: Bypass, obfuscate, hide
- Exploit: Attack, weaponize, abuse vulnerability
- Persist: Maintain access, implant, backdoor
"""

# =============================================================================
# STAGE 2: PYDANTIC VALIDATION (Filters hallucinated outputs)
# =============================================================================

class TaxonomyResponse(BaseModel):
    """Pydantic model for validating LLM taxonomy extraction responses."""

    conceptual: List[str] = Field(default_factory=list, description="Tier 0 conceptual bridge tags")
    tactical: List[str] = Field(default_factory=list, description="Tier 1 tactical bridge tags")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Confidence score")

    @field_validator('conceptual', mode='before')
    @classmethod
    def validate_conceptual(cls, v):
        """Filter to only valid Tier 0 tags."""
        if not isinstance(v, list):
            v = [v] if v else []
        return [tag for tag in v if tag in TIER0_CONCEPTUAL]

    @field_validator('tactical', mode='before')
    @classmethod
    def validate_tactical(cls, v):
        """Filter to only valid Tier 1 tags."""
        if not isinstance(v, list):
            v = [v] if v else []
        return [tag for tag in v if tag in TIER1_TACTICAL]


def parse_llm_response(content: str) -> tuple[TaxonomyResponse, List[str]]:
    """
    Stage 2: Parse and validate LLM response.

    Returns:
        Tuple of (validated_response, rejected_tags)
    """
    rejected = []

    # Handle dict input
    if isinstance(content, dict):
        data = content
    else:
        # Extract JSON from response (handle markdown wrapping)
        json_str = str(content)
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        try:
            data = json.loads(json_str.strip())
        except json.JSONDecodeError:
            return TaxonomyResponse(), ["PARSE_ERROR"]

    # Track rejected tags for analysis
    raw_conceptual = data.get("conceptual", [])
    raw_tactical = data.get("tactical", [])

    if isinstance(raw_conceptual, list):
        rejected.extend([t for t in raw_conceptual if t not in TIER0_CONCEPTUAL])
    if isinstance(raw_tactical, list):
        rejected.extend([t for t in raw_tactical if t not in TIER1_TACTICAL])

    # Pydantic validation filters invalid tags
    validated = TaxonomyResponse(**data)

    return validated, rejected


# =============================================================================
# GROUND TRUTH AND EVALUATION
# =============================================================================

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
    correction_rounds: int = 0  # How many self-correction attempts were needed
    correction_success: bool = True  # Did correction loop succeed?

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
        # Combined F1 across both tag types
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


# =============================================================================
# PROMPT LOADING
# =============================================================================

def load_prompt(prompt_name: str, skill_dir: Path) -> tuple[str, str]:
    """
    Load a prompt template.

    Returns:
        Tuple of (system_prompt, user_template)
    """
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


def load_ground_truth(name: str, skill_dir: Path) -> List[TestCase]:
    """Load ground truth test cases."""
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


# =============================================================================
# LLM CALLING WITH SELF-CORRECTION LOOP
# =============================================================================

# Correction prompt sent when LLM outputs invalid tags
CORRECTION_PROMPT = """Your response contained invalid tags that are not in the allowed vocabulary.

Invalid tags you used: {rejected_tags}

Valid conceptual tags (Tier 0): {valid_conceptual}
Valid tactical tags (Tier 1): {valid_tactical}

Please correct your response. Return ONLY valid JSON with tags from the allowed vocabulary above.
Do NOT invent new categories. Only use the exact tag names listed."""


@dataclass
class LLMCallResult:
    """Result of LLM call with correction tracking."""
    content: str
    validated: Optional['TaxonomyResponse']
    rejected_tags: List[str]
    correction_rounds: int
    total_latency_ms: float
    success: bool
    error: Optional[str] = None


async def call_llm_single(
    messages: List[Dict[str, str]],
    model_config: Dict[str, Any],
) -> tuple[str, float]:
    """
    Single LLM call using scillm paved path. Returns (content, latency_ms).

    Uses parallel_acompletions with proper request dict format per SCILLM_PAVED_PATH_CONTRACT.md.
    """
    import time

    try:
        from scillm.batch import parallel_acompletions
    except ImportError:
        raise RuntimeError("scillm not installed. Run 'uv sync' or 'pip install scillm'.")

    # Load environment variables (strip quotes if present)
    api_base = os.environ.get("CHUTES_API_BASE", "").strip('"\'')
    api_key = os.environ.get("CHUTES_API_KEY", "").strip('"\'')
    model_id = (
        model_config.get("model") or
        os.environ.get("CHUTES_MODEL_ID", "").strip('"\'') or
        os.environ.get("CHUTES_TEXT_MODEL", "").strip('"\'')
    )

    if not api_base or not api_key:
        raise RuntimeError("CHUTES_API_BASE and CHUTES_API_KEY required")
    if not model_id:
        raise RuntimeError("Model ID required (CHUTES_MODEL_ID or CHUTES_TEXT_MODEL)")

    start = time.perf_counter()

    # Build request per SCILLM_PAVED_PATH_CONTRACT.md
    # Each request dict contains: model, messages, max_tokens, temperature, response_format
    request = {
        "model": model_id,
        "messages": messages,  # Use full messages list (system, user, assistant for corrections)
        "response_format": {"type": "json_object"},
        "max_tokens": 256,
        "temperature": 0,
    }

    # Use parallel_acompletions with single request
    results = await parallel_acompletions(
        [request],
        api_base=api_base,
        api_key=api_key,
        custom_llm_provider="openai_like",
        concurrency=1,
        timeout=30,
        wall_time_s=60,
        tenacious=False,
    )

    latency = (time.perf_counter() - start) * 1000

    if results and not results[0].get("error"):
        content = results[0].get("content", "")
        # Handle case where content is already parsed dict
        if isinstance(content, dict):
            content = json.dumps(content)
        return content, latency
    else:
        error = results[0].get("error", "Unknown error") if results else "No response"
        raise RuntimeError(f"LLM call failed: {error}")


async def call_llm_with_correction(
    system: str,
    user: str,
    model_config: Dict[str, Any],
    max_correction_rounds: int = 2,
) -> LLMCallResult:
    """
    Call LLM with self-correction loop.

    If the LLM outputs invalid tags, we send an assistant correction message
    back to the model asking it to fix its output. This gives the model a
    chance to self-correct rather than silently filtering.

    Args:
        system: System prompt
        user: User message
        model_config: Model configuration
        max_correction_rounds: Maximum number of correction attempts (default 2)

    Returns:
        LLMCallResult with validation status and correction tracking
    """
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    total_latency = 0.0
    correction_round = 0
    all_rejected = []

    while correction_round <= max_correction_rounds:
        try:
            content, latency = await call_llm_single(messages, model_config)
            total_latency += latency

            validated, rejected = parse_llm_response(content)

            if not rejected:
                # Success! No invalid tags
                return LLMCallResult(
                    content=content,
                    validated=validated,
                    rejected_tags=all_rejected,
                    correction_rounds=correction_round,
                    total_latency_ms=total_latency,
                    success=True,
                )

            # Invalid tags found - track them
            all_rejected.extend(rejected)

            if correction_round >= max_correction_rounds:
                # Max corrections reached - return partial result
                return LLMCallResult(
                    content=content,
                    validated=validated,
                    rejected_tags=all_rejected,
                    correction_rounds=correction_round,
                    total_latency_ms=total_latency,
                    success=False,
                    error=f"Max corrections reached. Still invalid: {rejected}",
                )

            # Send correction message back to LLM
            correction_msg = CORRECTION_PROMPT.format(
                rejected_tags=", ".join(rejected),
                valid_conceptual=", ".join(sorted(TIER0_CONCEPTUAL)),
                valid_tactical=", ".join(sorted(TIER1_TACTICAL)),
            )

            # Add the assistant's invalid response and our correction to conversation
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": correction_msg})

            correction_round += 1

        except Exception as e:
            return LLMCallResult(
                content="",
                validated=None,
                rejected_tags=all_rejected,
                correction_rounds=correction_round,
                total_latency_ms=total_latency,
                success=False,
                error=str(e),
            )

    # Should not reach here, but handle it
    return LLMCallResult(
        content="",
        validated=TaxonomyResponse(),
        rejected_tags=all_rejected,
        correction_rounds=correction_round,
        total_latency_ms=total_latency,
        success=False,
        error="Unexpected exit from correction loop",
    )


# Legacy function for backwards compatibility
async def call_llm(
    system: str,
    user: str,
    model_config: Dict[str, Any],
) -> tuple[str, float]:
    """
    Simple LLM call without correction loop.
    Use call_llm_with_correction for production.
    """
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    return await call_llm_single(messages, model_config)


# =============================================================================
# TASK-MONITOR INTEGRATION
# =============================================================================

def notify_task_monitor(task_name: str, passed: bool, summary: 'EvalSummary'):
    """Notify task-monitor of evaluation result for quality gate."""
    try:
        import httpx

        status = "passed" if passed else "failed"
        payload = {
            "name": task_name,
            "status": status,
            "metrics": {
                "avg_f1": summary.avg_f1,
                "correction_success_rate": summary.correction_success_rate,
                "total_rejected": summary.total_rejected,
            },
            "message": f"Prompt validation {status}: F1={summary.avg_f1:.3f}, corrections={summary.total_correction_rounds}",
        }

        # Try to notify task-monitor (if running)
        try:
            resp = httpx.post("http://localhost:8765/tasks/update", json=payload, timeout=2.0)
            if resp.status_code == 200:
                console.print(f"[dim]Task-monitor notified: {task_name} = {status}[/dim]")
        except httpx.ConnectError:
            console.print("[dim]Task-monitor not running, skipping notification[/dim]")

    except ImportError:
        console.print("[dim]httpx not installed, skipping task-monitor notification[/dim]")


# =============================================================================
# CLI
# =============================================================================

app = typer.Typer(help="Prompt Lab: Systematic prompt engineering with self-correction")
console = Console()

SKILL_DIR = Path(__file__).parent


@app.command()
def eval(
    prompt: str = typer.Option("taxonomy_v1", "--prompt", "-p", help="Prompt name"),
    model: str = typer.Option("deepseek", "--model", "-m", help="Model to use"),
    cases: int = typer.Option(0, "--cases", "-n", help="Number of cases (0=all)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show per-case details"),
    max_corrections: int = typer.Option(2, "--max-corrections", help="Max self-correction rounds"),
    task_name: str = typer.Option("", "--task-name", help="Task-monitor task name for quality gate"),
    no_correction: bool = typer.Option(False, "--no-correction", help="Disable self-correction loop"),
):
    """Run evaluation with a prompt and model.

    Uses self-correction loop: if LLM outputs invalid tags, sends correction
    message back to model asking it to fix its output.
    """

    # Load model config
    models_file = SKILL_DIR / "models.json"
    if not models_file.exists():
        # Create default models config
        default_models = {
            "deepseek": {
                "provider": "chutes",
                "model": "deepseek-ai/DeepSeek-V3-0324-TEE",
                "api_base": "$CHUTES_API_BASE",
                "api_key": "$CHUTES_API_KEY"
            },
            "deepseek-direct": {
                "provider": "openai_like",
                "model": "deepseek-chat",
                "api_base": "https://api.deepseek.com",
                "api_key": "$DEEPSEEK_API_KEY"
            }
        }
        models_file.write_text(json.dumps(default_models, indent=2))

    models_config = json.loads(models_file.read_text())

    if model not in models_config:
        console.print(f"[red]Model '{model}' not found. Available: {list(models_config.keys())}[/red]")
        raise typer.Exit(1)

    model_config = models_config[model]

    # Load prompt and ground truth
    system_prompt, user_template = load_prompt(prompt, SKILL_DIR)
    test_cases = load_ground_truth("taxonomy", SKILL_DIR)

    if cases > 0:
        test_cases = test_cases[:cases]

    console.print(f"[bold]Evaluating prompt '{prompt}' with model '{model}'[/bold]")
    console.print(f"Test cases: {len(test_cases)}")
    if not no_correction:
        console.print(f"Self-correction: enabled (max {max_corrections} rounds)")
    console.print()

    # Run evaluation
    results = []

    async def run_eval():
        for tc in test_cases:
            user_msg = user_template.format(name=tc.name, description=tc.description)

            try:
                if no_correction:
                    # Simple call without correction loop
                    content, latency = await call_llm(system_prompt, user_msg, model_config)
                    validated, rejected = parse_llm_response(content)
                    correction_rounds = 0
                    correction_success = len(rejected) == 0
                else:
                    # Use self-correction loop
                    llm_result = await call_llm_with_correction(
                        system_prompt, user_msg, model_config,
                        max_correction_rounds=max_corrections
                    )
                    validated = llm_result.validated or TaxonomyResponse()
                    rejected = llm_result.rejected_tags
                    latency = llm_result.total_latency_ms
                    correction_rounds = llm_result.correction_rounds
                    correction_success = llm_result.success

                result = EvalResult(
                    case_id=tc.id,
                    predicted_conceptual=validated.conceptual,
                    predicted_tactical=validated.tactical,
                    expected_conceptual=tc.expected_conceptual,
                    expected_tactical=tc.expected_tactical,
                    rejected_tags=rejected,
                    confidence=validated.confidence,
                    latency_ms=latency,
                    correction_rounds=correction_rounds,
                    correction_success=correction_success,
                )
                results.append(result)

                if verbose:
                    status = "[green]PASS[/green]" if result.f1 >= 0.8 else "[yellow]PARTIAL[/yellow]" if result.f1 > 0 else "[red]FAIL[/red]"
                    correction_info = f" (corrected x{correction_rounds})" if correction_rounds > 0 else ""
                    console.print(f"  {tc.id}: {status} F1={result.f1:.2f}{correction_info}")
                    console.print(f"    Expected: C={tc.expected_conceptual} T={tc.expected_tactical}")
                    console.print(f"    Got:      C={validated.conceptual} T={validated.tactical}")
                    if rejected:
                        console.print(f"    [dim]Rejected tags: {rejected}[/dim]")
                    if not correction_success:
                        console.print(f"    [yellow]⚠ Correction failed[/yellow]")
                else:
                    correction_info = f" 🔄{correction_rounds}" if correction_rounds > 0 else ""
                    console.print(f"  {tc.id}: F1={result.f1:.2f}{correction_info}")

            except Exception as e:
                console.print(f"  [red]{tc.id}: ERROR - {e}[/red]")
                results.append(EvalResult(
                    case_id=tc.id,
                    predicted_conceptual=[],
                    predicted_tactical=[],
                    expected_conceptual=tc.expected_conceptual,
                    expected_tactical=tc.expected_tactical,
                    rejected_tags=["ERROR"],
                    confidence=0,
                    latency_ms=0,
                    correction_rounds=0,
                    correction_success=False,
                ))

    asyncio.run(run_eval())

    # Summary
    summary = EvalSummary(
        prompt_name=prompt,
        model_name=model,
        timestamp=datetime.now().isoformat(),
        results=results,
    )

    console.print()
    console.print("[bold]Summary[/bold]")

    table = Table()
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Avg F1", f"{summary.avg_f1:.3f}")
    table.add_row("Conceptual Precision", f"{summary.avg_conceptual_precision:.3f}")
    table.add_row("Conceptual Recall", f"{summary.avg_conceptual_recall:.3f}")
    table.add_row("Tactical Precision", f"{summary.avg_tactical_precision:.3f}")
    table.add_row("Tactical Recall", f"{summary.avg_tactical_recall:.3f}")
    table.add_row("Total Rejected Tags", str(summary.total_rejected))
    table.add_row("Avg Latency", f"{summary.avg_latency_ms:.0f}ms")

    # Correction metrics
    if not no_correction:
        table.add_row("─" * 20, "─" * 10)
        table.add_row("Correction Rounds", str(summary.total_correction_rounds))
        table.add_row("Cases Needing Correction", str(summary.cases_needing_correction))
        table.add_row("Correction Success Rate", f"{summary.correction_success_rate:.1%}")

    console.print(table)

    # Quality gate check
    passed = summary.avg_f1 >= 0.8 and summary.correction_success_rate >= 0.9
    if passed:
        console.print("\n[green]✓ QUALITY GATE PASSED[/green]")
    else:
        console.print("\n[red]✗ QUALITY GATE FAILED[/red]")
        if summary.avg_f1 < 0.8:
            console.print(f"  - F1 score {summary.avg_f1:.3f} < 0.8 threshold")
        if summary.correction_success_rate < 0.9:
            console.print(f"  - Correction success {summary.correction_success_rate:.1%} < 90% threshold")

    # Notify task-monitor if task_name provided
    if task_name:
        notify_task_monitor(task_name, passed, summary)

    # Save results
    results_dir = SKILL_DIR / "results"
    results_dir.mkdir(exist_ok=True)
    results_file = results_dir / f"{prompt}_{model}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    results_data = {
        "prompt": prompt,
        "model": model,
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
    console.print(f"\nResults saved to: {results_file}")

    # Exit with appropriate code for CI/CD
    if not passed:
        raise typer.Exit(1)


@app.command()
def compare(
    prompt: str = typer.Option("taxonomy_v1", "--prompt", "-p", help="Prompt name"),
    models: str = typer.Option("deepseek", "--models", "-m", help="Comma-separated model names"),
):
    """Compare multiple models on the same prompt."""
    model_list = [m.strip() for m in models.split(",")]

    console.print(f"[bold]Comparing {len(model_list)} models on prompt '{prompt}'[/bold]")
    console.print()

    for model in model_list:
        console.print(f"[bold cyan]--- {model} ---[/bold cyan]")
        # Call eval for each model
        eval(prompt=prompt, model=model, cases=0, verbose=False)
        console.print()


@app.command()
def list_prompts():
    """List available prompts."""
    prompts_dir = SKILL_DIR / "prompts"
    if prompts_dir.exists():
        for f in prompts_dir.glob("*.txt"):
            console.print(f"  {f.stem}")
    else:
        console.print("No prompts found. Run 'eval' to create default.")


@app.command()
def show_prompt(name: str = typer.Argument(..., help="Prompt name")):
    """Show a prompt's content."""
    prompt_file = SKILL_DIR / "prompts" / f"{name}.txt"
    if prompt_file.exists():
        console.print(prompt_file.read_text())
    else:
        console.print(f"[red]Prompt '{name}' not found[/red]")


@app.command()
def iterate(
    prompt: str = typer.Option("taxonomy_v1", "--prompt", "-p", help="Starting prompt"),
    model: str = typer.Option("deepseek", "--model", "-m", help="Model to use"),
    max_rounds: int = typer.Option(5, "--max-rounds", help="Maximum iteration rounds"),
    target_f1: float = typer.Option(0.9, "--target-f1", help="Target F1 score to stop"),
):
    """Interactive iteration loop (like /code-review).

    Runs evaluation, shows results, waits for prompt edits, re-runs.
    Continues until target F1 reached or max rounds hit.
    """
    import shutil

    prompt_file = SKILL_DIR / "prompts" / f"{prompt}.txt"
    if not prompt_file.exists():
        # Create default prompt
        load_prompt(prompt, SKILL_DIR)

    console.print(f"[bold]Iteration Mode[/bold]")
    console.print(f"Prompt: {prompt_file}")
    console.print(f"Target F1: {target_f1}")
    console.print(f"Max rounds: {max_rounds}")
    console.print()

    iteration_history = []

    for round_num in range(1, max_rounds + 1):
        console.print(f"\n[bold cyan]═══ Round {round_num}/{max_rounds} ═══[/bold cyan]\n")

        # Run evaluation (capture results)
        from io import StringIO
        import contextlib

        # Load and run eval
        models_file = SKILL_DIR / "models.json"
        models_config = json.loads(models_file.read_text())
        model_config = models_config[model]

        system_prompt, user_template = load_prompt(prompt, SKILL_DIR)
        test_cases = load_ground_truth("taxonomy", SKILL_DIR)

        results = []

        async def run_round():
            for tc in test_cases:
                user_msg = user_template.format(name=tc.name, description=tc.description)
                llm_result = await call_llm_with_correction(
                    system_prompt, user_msg, model_config, max_correction_rounds=2
                )
                validated = llm_result.validated or TaxonomyResponse()

                result = EvalResult(
                    case_id=tc.id,
                    predicted_conceptual=validated.conceptual,
                    predicted_tactical=validated.tactical,
                    expected_conceptual=tc.expected_conceptual,
                    expected_tactical=tc.expected_tactical,
                    rejected_tags=llm_result.rejected_tags,
                    confidence=validated.confidence,
                    latency_ms=llm_result.total_latency_ms,
                    correction_rounds=llm_result.correction_rounds,
                    correction_success=llm_result.success,
                )
                results.append(result)

                status = "✓" if result.f1 >= 0.8 else "○" if result.f1 > 0 else "✗"
                console.print(f"  {status} {tc.id}: F1={result.f1:.2f}")

        asyncio.run(run_round())

        # Calculate summary
        avg_f1 = sum(r.f1 for r in results) / len(results)
        total_corrections = sum(r.correction_rounds for r in results)
        total_rejected = sum(len(r.rejected_tags) for r in results)

        iteration_history.append({
            "round": round_num,
            "avg_f1": avg_f1,
            "corrections": total_corrections,
            "rejected": total_rejected,
        })

        console.print()
        console.print(f"[bold]Round {round_num} Results:[/bold]")
        console.print(f"  Avg F1: {avg_f1:.3f}")
        console.print(f"  Corrections needed: {total_corrections}")
        console.print(f"  Rejected tags: {total_rejected}")

        # Check if target reached
        if avg_f1 >= target_f1:
            console.print(f"\n[green]✓ TARGET REACHED! F1={avg_f1:.3f} >= {target_f1}[/green]")
            break

        if round_num < max_rounds:
            console.print()
            console.print(f"[yellow]Edit prompt and save: {prompt_file}[/yellow]")
            console.print("Press Enter to continue, or 'q' to quit...")

            try:
                user_input = input().strip().lower()
                if user_input == 'q':
                    console.print("Iteration stopped by user.")
                    break
            except EOFError:
                console.print("Non-interactive mode, stopping iteration.")
                break

    # Final summary
    console.print("\n[bold]═══ Iteration History ═══[/bold]")
    table = Table()
    table.add_column("Round", style="cyan")
    table.add_column("Avg F1", style="green")
    table.add_column("Corrections", style="yellow")
    table.add_column("Rejected", style="red")

    for h in iteration_history:
        table.add_row(
            str(h["round"]),
            f"{h['avg_f1']:.3f}",
            str(h["corrections"]),
            str(h["rejected"]),
        )

    console.print(table)

    # Calculate improvement
    if len(iteration_history) > 1:
        improvement = iteration_history[-1]["avg_f1"] - iteration_history[0]["avg_f1"]
        console.print(f"\nTotal F1 improvement: {improvement:+.3f}")


@app.command()
def history(
    prompt: str = typer.Option("taxonomy_v1", "--prompt", "-p", help="Prompt name"),
):
    """View evaluation history for a prompt."""
    results_dir = SKILL_DIR / "results"
    if not results_dir.exists():
        console.print("No results found.")
        return

    # Find all results for this prompt
    pattern = f"{prompt}_*.json"
    result_files = sorted(results_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)

    if not result_files:
        console.print(f"No results found for prompt '{prompt}'")
        return

    console.print(f"[bold]History for prompt '{prompt}'[/bold]\n")

    table = Table()
    table.add_column("Timestamp", style="dim")
    table.add_column("Model", style="cyan")
    table.add_column("F1", style="green")
    table.add_column("Corrections", style="yellow")
    table.add_column("Status")

    for rf in result_files[:10]:  # Last 10 results
        data = json.loads(rf.read_text())
        metrics = data.get("metrics", {})
        passed = data.get("passed", metrics.get("avg_f1", 0) >= 0.8)

        table.add_row(
            data.get("timestamp", "")[:19],
            data.get("model", ""),
            f"{metrics.get('avg_f1', 0):.3f}",
            str(metrics.get("correction_rounds", 0)),
            "[green]PASS[/green]" if passed else "[red]FAIL[/red]",
        )

    console.print(table)


# =============================================================================
# QRA EVALUATION (Different from taxonomy - keyword/quality based)
# =============================================================================

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


def load_qra_ground_truth(skill_dir: Path) -> List[QRATestCase]:
    """Load QRA ground truth test cases."""
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


def parse_qra_response(content: str) -> Dict[str, Any]:
    """Parse QRA JSON response."""
    if isinstance(content, dict):
        return content

    json_str = str(content)
    if "```json" in json_str:
        json_str = json_str.split("```json")[1].split("```")[0]
    elif "```" in json_str:
        json_str = json_str.split("```")[1].split("```")[0]

    try:
        return json.loads(json_str.strip())
    except json.JSONDecodeError:
        return {"question": "", "reasoning": "", "answer": "", "confidence": 0}


def count_sentences(text: str) -> int:
    """Count approximate sentences in text."""
    import re
    sentences = re.split(r'[.!?]+', text)
    return len([s for s in sentences if s.strip()])


def check_keywords(text: str, keywords: List[str]) -> int:
    """Count how many keywords appear in text (case-insensitive)."""
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw.lower() in text_lower)


@app.command("eval-qra")
def eval_qra(
    prompt: str = typer.Option("qra_v1", "--prompt", "-p", help="QRA prompt name"),
    model: str = typer.Option("deepseek", "--model", "-m", help="Model to use"),
    cases: int = typer.Option(0, "--cases", "-n", help="Number of cases (0=all)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show per-case details"),
):
    """Evaluate QRA (Question-Reasoning-Answer) generation quality."""

    # Load model config
    models_file = SKILL_DIR / "models.json"
    models_config = json.loads(models_file.read_text())

    if model not in models_config:
        console.print(f"[red]Model '{model}' not found. Available: {list(models_config.keys())}[/red]")
        raise typer.Exit(1)

    model_config = models_config[model]

    # Load prompt and ground truth
    system_prompt, user_template = load_prompt(prompt, SKILL_DIR)
    test_cases = load_qra_ground_truth(SKILL_DIR)

    if not test_cases:
        console.print("[red]No QRA ground truth found. Create ground_truth/qra.json[/red]")
        raise typer.Exit(1)

    if cases > 0:
        test_cases = test_cases[:cases]

    console.print(f"[bold]Evaluating QRA prompt '{prompt}' with model '{model}'[/bold]")
    console.print(f"Test cases: {len(test_cases)}")
    console.print()

    results = []

    async def run_qra_eval():
        for tc in test_cases:
            user_msg = user_template.format(
                name=tc.name,
                description=tc.description,
                collection=tc.collection,
                type=tc.item_type,
            )

            try:
                import time
                start = time.perf_counter()

                # Simple LLM call (no correction loop for QRA)
                from scillm.batch import parallel_acompletions

                api_base = os.environ.get("CHUTES_API_BASE", "").strip('"\'')
                api_key = os.environ.get("CHUTES_API_KEY", "").strip('"\'')
                model_id = model_config.get("model") or os.environ.get("CHUTES_TEXT_MODEL", "").strip('"\'')

                req = {
                    "model": model_id,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_msg},
                    ],
                    "response_format": {"type": "json_object"},
                    "max_tokens": 512,
                    "temperature": 0.3,
                }

                resp = await parallel_acompletions(
                    [req],
                    api_base=api_base,
                    api_key=api_key,
                    custom_llm_provider="openai_like",
                    concurrency=1,
                    timeout=60,
                    wall_time_s=120,
                    tenacious=False,
                )

                latency = (time.perf_counter() - start) * 1000

                if resp and not resp[0].get("error"):
                    content = resp[0].get("content", {})
                    qra = parse_qra_response(content)
                else:
                    qra = {"question": "", "reasoning": "", "answer": "", "confidence": 0}
                    latency = 0

                # Evaluate
                q_hits = check_keywords(qra.get("question", ""), tc.question_keywords)
                r_hits = check_keywords(qra.get("reasoning", ""), tc.reasoning_keywords)
                r_sentences = count_sentences(qra.get("reasoning", ""))

                result = QRAResult(
                    case_id=tc.id,
                    question=qra.get("question", ""),
                    reasoning=qra.get("reasoning", ""),
                    answer=qra.get("answer", ""),
                    confidence=qra.get("confidence", 0),
                    question_keyword_hits=q_hits,
                    question_keyword_total=len(tc.question_keywords),
                    reasoning_keyword_hits=r_hits,
                    reasoning_keyword_total=len(tc.reasoning_keywords),
                    reasoning_sentences=r_sentences,
                    latency_ms=latency,
                )
                results.append(result)

                if verbose:
                    status = "[green]GOOD[/green]" if result.overall_score >= 0.7 else "[yellow]PARTIAL[/yellow]" if result.overall_score > 0.3 else "[red]WEAK[/red]"
                    console.print(f"  {tc.id}: {status} Score={result.overall_score:.2f}")
                    console.print(f"    Q: {result.question[:80]}...")
                    console.print(f"    Keywords: Q={q_hits}/{len(tc.question_keywords)} R={r_hits}/{len(tc.reasoning_keywords)}")
                else:
                    console.print(f"  {tc.id}: Score={result.overall_score:.2f}")

            except Exception as e:
                console.print(f"  [red]{tc.id}: ERROR - {e}[/red]")

    asyncio.run(run_qra_eval())

    # Summary
    if results:
        avg_score = sum(r.overall_score for r in results) / len(results)
        avg_q_score = sum(r.question_score for r in results) / len(results)
        avg_r_score = sum(r.reasoning_score for r in results) / len(results)
        avg_latency = sum(r.latency_ms for r in results) / len(results)

        console.print()
        console.print("[bold]Summary[/bold]")

        table = Table()
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Overall Score", f"{avg_score:.3f}")
        table.add_row("Question Keyword Score", f"{avg_q_score:.3f}")
        table.add_row("Reasoning Keyword Score", f"{avg_r_score:.3f}")
        table.add_row("Avg Latency", f"{avg_latency:.0f}ms")

        console.print(table)

        # Quality gate
        passed = avg_score >= 0.6
        if passed:
            console.print("\n[green]✓ QRA QUALITY GATE PASSED[/green]")
        else:
            console.print("\n[red]✗ QRA QUALITY GATE FAILED[/red]")
            console.print(f"  - Score {avg_score:.3f} < 0.6 threshold")

        # Save results
        results_dir = SKILL_DIR / "results"
        results_dir.mkdir(exist_ok=True)
        results_file = results_dir / f"qra_{prompt}_{model}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        results_data = {
            "prompt": prompt,
            "model": model,
            "task": "qra",
            "timestamp": datetime.now().isoformat(),
            "passed": passed,
            "metrics": {
                "overall_score": avg_score,
                "question_score": avg_q_score,
                "reasoning_score": avg_r_score,
                "avg_latency_ms": avg_latency,
            },
            "cases": [
                {
                    "id": r.case_id,
                    "question": r.question,
                    "reasoning": r.reasoning,
                    "answer": r.answer,
                    "scores": {
                        "question": r.question_score,
                        "reasoning": r.reasoning_score,
                        "overall": r.overall_score,
                    },
                }
                for r in results
            ]
        }

        results_file.write_text(json.dumps(results_data, indent=2))
        console.print(f"\nResults saved to: {results_file}")

        if not passed:
            raise typer.Exit(1)


@app.command()
def analyze(
    results_file: Optional[Path] = typer.Option(None, "--results", "-r", help="Results JSON to analyze"),
    prompt: str = typer.Option("taxonomy_v1", "--prompt", "-p", help="Prompt to analyze results for"),
    background: bool = typer.Option(False, "--background", "-b", help="Run analysis in background"),
    suggest_improvements: bool = typer.Option(True, "--suggest/--no-suggest", help="Generate improvement suggestions"),
):
    """Analyze previous evaluation results and suggest prompt improvements.

    Can re-analyze stored request/response payloads to:
    - Identify error patterns
    - Suggest prompt modifications
    - Rate prompt effectiveness over time
    """
    results_dir = SKILL_DIR / "results"

    # Find results file
    if results_file:
        if not results_file.exists():
            console.print(f"[red]Results file not found: {results_file}[/red]")
            raise typer.Exit(1)
        results_files = [results_file]
    else:
        # Find all results for this prompt
        pattern = f"{prompt}_*.json"
        results_files = sorted(results_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        if not results_files:
            console.print(f"[red]No results found for prompt '{prompt}'[/red]")
            raise typer.Exit(1)

    console.print(f"[bold]Analyzing {len(results_files)} result file(s)[/bold]\n")

    # Aggregate analysis across all results
    all_cases = []
    all_rejected = []
    all_corrections = []
    metrics_over_time = []

    for rf in results_files:
        data = json.loads(rf.read_text())

        metrics_over_time.append({
            "timestamp": data.get("timestamp", ""),
            "model": data.get("model", ""),
            "avg_f1": data.get("metrics", {}).get("avg_f1", 0),
            "correction_rounds": data.get("metrics", {}).get("correction_rounds", 0),
        })

        for case in data.get("cases", []):
            all_cases.append(case)
            if case.get("rejected"):
                all_rejected.extend(case["rejected"])
            if case.get("correction_rounds", 0) > 0:
                all_corrections.append(case)

    # Error pattern analysis
    console.print("[bold cyan]Error Pattern Analysis[/bold cyan]")

    if all_rejected:
        from collections import Counter
        rejected_counts = Counter(all_rejected)
        console.print("\nMost common invalid tags:")
        for tag, count in rejected_counts.most_common(10):
            console.print(f"  {tag}: {count}x")

    # Cases that needed correction
    if all_corrections:
        console.print(f"\nCases needing correction: {len(all_corrections)}/{len(all_cases)}")

    # Performance trend
    if len(metrics_over_time) > 1:
        console.print("\n[bold cyan]Performance Trend[/bold cyan]")
        table = Table()
        table.add_column("Timestamp", style="dim")
        table.add_column("Model")
        table.add_column("F1")
        table.add_column("Corrections")

        for m in metrics_over_time[:10]:
            table.add_row(
                m["timestamp"][:19],
                m["model"],
                f"{m['avg_f1']:.3f}",
                str(m["correction_rounds"]),
            )
        console.print(table)

    # Suggest improvements (simplified - could use LLM for more sophisticated suggestions)
    if suggest_improvements and all_rejected:
        console.print("\n[bold cyan]Suggested Improvements[/bold cyan]")

        # Analyze common errors
        rejected_counts = Counter(all_rejected)
        common_errors = rejected_counts.most_common(5)

        suggestions = []

        for error_tag, count in common_errors:
            # Check if it's a near-miss (close to valid tag)
            for valid in TIER0_CONCEPTUAL | TIER1_TACTICAL:
                if error_tag.lower() in valid.lower() or valid.lower() in error_tag.lower():
                    suggestions.append(f"Add explicit mapping: '{error_tag}' → '{valid}' in prompt")
                    break
            else:
                suggestions.append(f"Consider adding explicit instruction: 'Do NOT use \"{error_tag}\" - use the closest valid tag instead'")

        for i, suggestion in enumerate(suggestions[:5], 1):
            console.print(f"  {i}. {suggestion}")

    # Save analysis report
    analysis_file = results_dir / f"analysis_{prompt}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    analysis_data = {
        "prompt": prompt,
        "timestamp": datetime.now().isoformat(),
        "total_cases": len(all_cases),
        "total_rejected": len(all_rejected),
        "rejected_counts": dict(Counter(all_rejected)),
        "corrections_needed": len(all_corrections),
        "metrics_trend": metrics_over_time,
    }
    analysis_file.write_text(json.dumps(analysis_data, indent=2))
    console.print(f"\nAnalysis saved to: {analysis_file}")


@app.command()
def optimize(
    prompt: str = typer.Option("taxonomy_v1", "--prompt", "-p", help="Prompt to optimize"),
    model: str = typer.Option("deepseek", "--model", "-m", help="Model for optimization suggestions"),
):
    """Use LLM to suggest prompt optimizations based on error patterns.

    Analyzes past results and uses the LLM to generate improved prompt text.
    """
    results_dir = SKILL_DIR / "results"

    # Find all results for this prompt
    pattern = f"{prompt}_*.json"
    results_files = sorted(results_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)

    if not results_files:
        console.print(f"[red]No results found for prompt '{prompt}'. Run 'eval' first.[/red]")
        raise typer.Exit(1)

    # Collect error cases
    error_cases = []
    for rf in results_files[:5]:  # Last 5 result files
        data = json.loads(rf.read_text())
        for case in data.get("cases", []):
            if case.get("rejected") or case.get("f1", 1.0) < 0.8:
                error_cases.append(case)

    if not error_cases:
        console.print("[green]No significant errors found. Prompt appears to be working well.[/green]")
        return

    console.print(f"[bold]Analyzing {len(error_cases)} error cases for optimization[/bold]\n")

    # Load current prompt
    system_prompt, user_template = load_prompt(prompt, SKILL_DIR)

    # Build optimization request
    optimization_prompt = f"""Analyze this taxonomy extraction prompt and suggest improvements based on the error cases below.

CURRENT PROMPT:
{system_prompt}

ERROR CASES (cases where the model made mistakes):
"""
    for i, case in enumerate(error_cases[:10], 1):
        optimization_prompt += f"""
Case {i}: ID={case['id']}
  Expected: {case.get('expected', {})}
  Got: {case.get('predicted', {})}
  Rejected tags: {case.get('rejected', [])}
"""

    optimization_prompt += """

Based on these errors, suggest specific improvements to the prompt. Focus on:
1. Clarifying ambiguous tag definitions
2. Adding examples for commonly confused tags
3. Strengthening instructions to prevent hallucinated tags

Return your suggestions as a JSON object:
{"improvements": ["suggestion 1", "suggestion 2", ...], "revised_prompt_section": "..."}
"""

    console.print("Generating optimization suggestions...")

    # Call LLM for suggestions
    async def get_suggestions():
        try:
            from scillm.batch import parallel_acompletions

            api_base = os.environ.get("CHUTES_API_BASE", "").strip('"\'')
            api_key = os.environ.get("CHUTES_API_KEY", "").strip('"\'')
            model_id = os.environ.get("CHUTES_TEXT_MODEL", "").strip('"\'')

            req = {
                "model": model_id,
                "messages": [
                    {"role": "system", "content": "You are an expert prompt engineer. Analyze prompts and suggest improvements."},
                    {"role": "user", "content": optimization_prompt},
                ],
                "response_format": {"type": "json_object"},
                "max_tokens": 1024,
                "temperature": 0.3,
            }

            results = await parallel_acompletions(
                [req],
                api_base=api_base,
                api_key=api_key,
                custom_llm_provider="openai_like",
                concurrency=1,
                timeout=60,
                wall_time_s=120,
                tenacious=False,
            )

            if results and not results[0].get("error"):
                content = results[0].get("content", "{}")
                if isinstance(content, str):
                    return json.loads(content)
                return content
            else:
                return {"error": results[0].get("error", "Unknown error")}

        except Exception as e:
            return {"error": str(e)}

    suggestions = asyncio.run(get_suggestions())

    if "error" in suggestions:
        console.print(f"[red]Failed to generate suggestions: {suggestions['error']}[/red]")
        return

    console.print("\n[bold cyan]Optimization Suggestions[/bold cyan]")
    for i, suggestion in enumerate(suggestions.get("improvements", []), 1):
        console.print(f"  {i}. {suggestion}")

    if suggestions.get("revised_prompt_section"):
        console.print("\n[bold cyan]Suggested Prompt Revision[/bold cyan]")
        console.print(suggestions["revised_prompt_section"][:500])

    # Save suggestions
    opt_file = results_dir / f"optimization_{prompt}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    opt_file.write_text(json.dumps({
        "prompt": prompt,
        "timestamp": datetime.now().isoformat(),
        "error_cases_analyzed": len(error_cases),
        "suggestions": suggestions,
    }, indent=2))
    console.print(f"\nOptimization suggestions saved to: {opt_file}")


# =============================================================================
# GROUND TRUTH BUILDER (Stratified SPARTA Sampling)
# =============================================================================

# SPARTA data paths
SPARTA_DATA = Path("/home/graham/workspace/experiments/sparta/data/raw")
SPARTA_TAXONOMY = Path("/home/graham/workspace/experiments/sparta/src/sparta/taxonomy")


def load_attck_techniques(limit: int = 15) -> List[Dict[str, Any]]:
    """Load ATT&CK techniques from enterprise-attack.json."""
    attck_file = SPARTA_DATA / "enterprise-attack.json"
    if not attck_file.exists():
        console.print(f"[yellow]ATT&CK data not found: {attck_file}[/yellow]")
        return []

    import random
    data = json.loads(attck_file.read_text())

    # Filter for attack-pattern objects (techniques)
    techniques = [
        obj for obj in data.get("objects", [])
        if obj.get("type") == "attack-pattern" and not obj.get("revoked", False)
    ]

    # Stratified sample by kill chain phase
    by_tactic = {}
    for t in techniques:
        phases = t.get("kill_chain_phases", [])
        for phase in phases:
            tactic = phase.get("phase_name", "unknown")
            if tactic not in by_tactic:
                by_tactic[tactic] = []
            by_tactic[tactic].append(t)

    # Sample evenly across tactics
    sampled = []
    tactics = list(by_tactic.keys())
    random.shuffle(tactics)

    per_tactic = max(1, limit // len(tactics))
    for tactic in tactics:
        available = by_tactic[tactic]
        random.shuffle(available)
        sampled.extend(available[:per_tactic])
        if len(sampled) >= limit:
            break

    # Convert to standard format
    results = []
    for t in sampled[:limit]:
        results.append({
            "id": t.get("external_references", [{}])[0].get("external_id", t.get("id", "")),
            "name": t.get("name", ""),
            "description": t.get("description", "")[:500],
            "collection": "ATT&CK",
            "tactic": t.get("kill_chain_phases", [{}])[0].get("phase_name", ""),
        })

    return results


def load_nist_controls(limit: int = 15) -> List[Dict[str, Any]]:
    """Load NIST controls from CSV."""
    import csv
    nist_file = SPARTA_DATA / "nist_rev4_controls.csv"
    if not nist_file.exists():
        console.print(f"[yellow]NIST data not found: {nist_file}[/yellow]")
        return []

    import random

    # Read CSV
    with open(nist_file, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        controls = list(reader)

    # Group by family
    by_family = {}
    for c in controls:
        family = c.get("FAMILY", "Unknown")
        if family not in by_family:
            by_family[family] = []
        by_family[family].append(c)

    # Sample across families
    sampled = []
    families = list(by_family.keys())
    random.shuffle(families)

    per_family = max(1, limit // len(families))
    for family in families:
        available = by_family[family]
        random.shuffle(available)
        sampled.extend(available[:per_family])
        if len(sampled) >= limit:
            break

    # Convert to standard format
    results = []
    for c in sampled[:limit]:
        results.append({
            "id": c.get("NAME", ""),
            "name": c.get("TITLE", ""),
            "description": c.get("DESCRIPTION", "")[:500],
            "collection": "NIST",
            "family": c.get("FAMILY", ""),
        })

    return results


def load_cwe_weaknesses(limit: int = 10) -> List[Dict[str, Any]]:
    """Load CWE weaknesses from CSV."""
    import csv
    cwe_file = SPARTA_DATA / "cwe.csv"
    if not cwe_file.exists():
        console.print(f"[yellow]CWE data not found: {cwe_file}[/yellow]")
        return []

    import random

    with open(cwe_file, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        weaknesses = list(reader)

    # Sample randomly (CWE doesn't have clean hierarchy)
    random.shuffle(weaknesses)

    results = []
    for w in weaknesses[:limit]:
        results.append({
            "id": f"CWE-{w.get('cwe_id', '')}",
            "name": w.get("name", ""),
            "description": w.get("description", "")[:500],
            "collection": "CWE",
            "categories": w.get("categories", ""),
        })

    return results


def load_d3fend_techniques(limit: int = 10) -> List[Dict[str, Any]]:
    """Load D3FEND defensive techniques from CSV."""
    import csv
    d3fend_file = SPARTA_DATA / "d3fend_techniques.csv"
    if not d3fend_file.exists():
        console.print(f"[yellow]D3FEND data not found: {d3fend_file}[/yellow]")
        return []

    import random

    with open(d3fend_file, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        techniques = list(reader)

    # Group by tactic
    by_tactic = {}
    for t in techniques:
        tactic = t.get("Tactic", "Unknown")
        if tactic not in by_tactic:
            by_tactic[tactic] = []
        by_tactic[tactic].append(t)

    # Sample across tactics
    sampled = []
    tactics = list(by_tactic.keys())
    random.shuffle(tactics)

    per_tactic = max(1, limit // len(tactics))
    for tactic in tactics:
        available = by_tactic[tactic]
        random.shuffle(available)
        sampled.extend(available[:per_tactic])
        if len(sampled) >= limit:
            break

    results = []
    for t in sampled[:limit]:
        results.append({
            "id": f"d3f:{t.get('ID', '')}",
            "name": t.get("Name", ""),
            "description": t.get("Definition", "")[:500],
            "collection": "D3FEND",
            "tactic": t.get("Tactic", ""),
        })

    return results


def run_keyword_scorer(text: str) -> tuple[List[str], List[str]]:
    """Run SPARTA keyword extractor to get expected tags."""
    try:
        # Try importing from SPARTA
        sys.path.insert(0, str(SPARTA_TAXONOMY.parent.parent))
        from sparta.taxonomy.keyword_extractor import extract_tags_from_text
        return extract_tags_from_text(text, threshold=1)
    except ImportError:
        # Fallback: simple keyword matching
        text_lower = text.lower()

        conceptual = []
        tactical = []

        # Simple heuristics
        if any(kw in text_lower for kw in ["persistence", "backdoor", "implant", "maintain"]):
            conceptual.append("Corruption")
            tactical.append("Persist")
        if any(kw in text_lower for kw in ["vulnerability", "weakness", "exploit", "injection", "flaw"]):
            conceptual.append("Fragility")
            tactical.append("Exploit")
        if any(kw in text_lower for kw in ["evasion", "obfuscate", "bypass", "hide", "clear"]):
            conceptual.append("Stealth")
            tactical.append("Evade")
        if any(kw in text_lower for kw in ["authenticate", "authorization", "access control", "credential"]):
            conceptual.append("Loyalty")
            tactical.append("Harden")
        if any(kw in text_lower for kw in ["backup", "recover", "restore", "remediate"]):
            conceptual.append("Resilience")
            tactical.append("Restore")
        if any(kw in text_lower for kw in ["harden", "patch", "protect", "defense", "security"]):
            conceptual.append("Resilience")
            tactical.append("Harden")
        if any(kw in text_lower for kw in ["reconnaissance", "scan", "discover", "enumerate"]):
            conceptual.append("Precision")
            tactical.append("Model")
        if any(kw in text_lower for kw in ["isolate", "segment", "quarantine", "contain"]):
            conceptual.append("Resilience")
            tactical.append("Isolate")
        if any(kw in text_lower for kw in ["monitor", "detect", "alert", "log"]):
            conceptual.append("Loyalty")
            tactical.append("Detect")

        # Deduplicate
        conceptual = list(dict.fromkeys(conceptual))
        tactical = list(dict.fromkeys(tactical))

        # Default if nothing found
        if not conceptual:
            conceptual = ["Resilience"]
        if not tactical:
            tactical = ["Harden"]

        return conceptual, tactical


@app.command("build-llm-ground-truth")
def build_llm_ground_truth(
    output: str = typer.Option("taxonomy_llm", "--output", "-o", help="Output ground truth name"),
    model: str = typer.Option("deepseek-v3.2", "--model", "-m", help="Model for label generation"),
    prompt: str = typer.Option("taxonomy_v2", "--prompt", "-p", help="Prompt to use"),
    attck_count: int = typer.Option(15, "--attck", help="Number of ATT&CK samples"),
    nist_count: int = typer.Option(15, "--nist", help="Number of NIST samples"),
    cwe_count: int = typer.Option(10, "--cwe", help="Number of CWE samples"),
    d3fend_count: int = typer.Option(10, "--d3fend", help="Number of D3FEND samples"),
    confidence_threshold: float = typer.Option(0.7, "--threshold", help="Flag cases below this confidence"),
    seed: int = typer.Option(42, "--seed", help="Random seed for reproducibility"),
):
    """Build ground truth using LLM predictions with confidence flagging.

    RECOMMENDED approach for building ground truth:
    1. Stratified sampling from SPARTA data sources
    2. LLM generates labels with confidence scores
    3. Low-confidence cases flagged for human review

    Analysis showed LLM (DeepSeek V3.2) predictions are more accurate than keyword scorer.
    """
    import random
    random.seed(seed)

    # Load model config
    models_file = SKILL_DIR / "models.json"
    models_config = json.loads(models_file.read_text())

    if model not in models_config:
        console.print(f"[red]Model '{model}' not found[/red]")
        raise typer.Exit(1)

    model_config = models_config[model]

    console.print(f"[bold]Building LLM-based ground truth[/bold]")
    console.print(f"Model: {model}")
    console.print(f"Prompt: {prompt}")
    console.print()

    # Load samples
    samples = []

    console.print("Loading samples...")
    attck = load_attck_techniques(attck_count)
    samples.extend(attck)
    nist = load_nist_controls(nist_count)
    samples.extend(nist)
    cwe = load_cwe_weaknesses(cwe_count)
    samples.extend(cwe)
    d3fend = load_d3fend_techniques(d3fend_count)
    samples.extend(d3fend)

    console.print(f"Total samples: {len(samples)}")
    console.print()

    # Load prompt
    system_prompt, user_template = load_prompt(prompt, SKILL_DIR)

    # Generate LLM predictions
    console.print("Generating LLM labels...")

    cases = []
    flagged_count = 0

    async def generate_labels():
        nonlocal flagged_count

        for i, sample in enumerate(samples):
            user_msg = user_template.format(name=sample['name'], description=sample['description'])

            try:
                llm_result = await call_llm_with_correction(
                    system_prompt, user_msg, model_config, max_correction_rounds=2
                )

                if llm_result.validated:
                    validated = llm_result.validated
                    conceptual = validated.conceptual
                    tactical = validated.tactical
                    confidence = validated.confidence
                else:
                    conceptual = []
                    tactical = []
                    confidence = 0.0

                # Flag low confidence or empty results
                needs_review = (
                    confidence < confidence_threshold or
                    not conceptual or
                    not tactical or
                    llm_result.correction_rounds > 0
                )

                if needs_review:
                    flagged_count += 1

                cases.append({
                    "id": sample["id"],
                    "input": {
                        "name": sample["name"],
                        "description": sample["description"],
                    },
                    "expected": {
                        "conceptual": conceptual,
                        "tactical": tactical,
                    },
                    "metadata": {
                        "collection": sample["collection"],
                        "llm_confidence": confidence,
                        "correction_rounds": llm_result.correction_rounds,
                        "needs_review": needs_review,
                    },
                    "notes": f"LLM-generated from {sample['collection']}" + (" [REVIEW]" if needs_review else ""),
                })

                status = "⚠" if needs_review else "✓"
                console.print(f"  [{i+1}/{len(samples)}] {status} {sample['id']}: C={conceptual} T={tactical} (conf={confidence:.2f})")

            except Exception as e:
                console.print(f"  [{i+1}/{len(samples)}] ✗ {sample['id']}: ERROR - {e}")
                cases.append({
                    "id": sample["id"],
                    "input": {"name": sample["name"], "description": sample["description"]},
                    "expected": {"conceptual": [], "tactical": []},
                    "metadata": {"collection": sample["collection"], "error": str(e), "needs_review": True},
                    "notes": f"ERROR: {e}",
                })
                flagged_count += 1

    asyncio.run(generate_labels())

    # Save ground truth
    gt_data = {
        "name": output,
        "description": f"LLM-generated ground truth ({len(samples)} samples, {flagged_count} flagged)",
        "generated": datetime.now().isoformat(),
        "seed": seed,
        "model": model,
        "prompt": prompt,
        "confidence_threshold": confidence_threshold,
        "counts": {
            "attck": len(attck),
            "nist": len(nist),
            "cwe": len(cwe),
            "d3fend": len(d3fend),
            "total": len(cases),
            "flagged_for_review": flagged_count,
        },
        "cases": cases,
    }

    gt_file = SKILL_DIR / "ground_truth" / f"{output}.json"
    gt_file.parent.mkdir(parents=True, exist_ok=True)
    gt_file.write_text(json.dumps(gt_data, indent=2))

    console.print(f"\n[green]✓ Ground truth saved to: {gt_file}[/green]")
    console.print(f"  Total cases: {len(cases)}")
    console.print(f"  Flagged for review: {flagged_count}")

    if flagged_count > 0:
        console.print(f"\n[yellow]⚠ {flagged_count} cases flagged for review[/yellow]")


@app.command("build-ground-truth")
def build_ground_truth(
    output: str = typer.Option("taxonomy_large", "--output", "-o", help="Output ground truth name"),
    attck_count: int = typer.Option(15, "--attck", help="Number of ATT&CK samples"),
    nist_count: int = typer.Option(15, "--nist", help="Number of NIST samples"),
    cwe_count: int = typer.Option(10, "--cwe", help="Number of CWE samples"),
    d3fend_count: int = typer.Option(10, "--d3fend", help="Number of D3FEND samples"),
    seed: int = typer.Option(42, "--seed", help="Random seed for reproducibility"),
):
    """Build stratified ground truth from SPARTA data sources.

    Uses keyword scorer to generate baseline expected labels.
    The generated ground truth should be reviewed and refined.
    """
    import random
    random.seed(seed)

    console.print(f"[bold]Building ground truth with stratified sampling[/bold]")
    console.print(f"  ATT&CK: {attck_count}")
    console.print(f"  NIST: {nist_count}")
    console.print(f"  CWE: {cwe_count}")
    console.print(f"  D3FEND: {d3fend_count}")
    console.print()

    # Load samples
    samples = []

    console.print("Loading ATT&CK techniques...")
    attck = load_attck_techniques(attck_count)
    samples.extend(attck)
    console.print(f"  Loaded {len(attck)} ATT&CK samples")

    console.print("Loading NIST controls...")
    nist = load_nist_controls(nist_count)
    samples.extend(nist)
    console.print(f"  Loaded {len(nist)} NIST samples")

    console.print("Loading CWE weaknesses...")
    cwe = load_cwe_weaknesses(cwe_count)
    samples.extend(cwe)
    console.print(f"  Loaded {len(cwe)} CWE samples")

    console.print("Loading D3FEND techniques...")
    d3fend = load_d3fend_techniques(d3fend_count)
    samples.extend(d3fend)
    console.print(f"  Loaded {len(d3fend)} D3FEND samples")

    console.print()
    console.print(f"[bold]Total samples: {len(samples)}[/bold]")
    console.print()

    # Run keyword scorer for each sample
    console.print("Running keyword scorer for expected labels...")

    cases = []
    for sample in samples:
        text = f"{sample['name']} {sample['description']}"
        conceptual, tactical = run_keyword_scorer(text)

        cases.append({
            "id": sample["id"],
            "input": {
                "name": sample["name"],
                "description": sample["description"],
            },
            "expected": {
                "conceptual": conceptual[:2],  # Limit to top 2
                "tactical": tactical[:2],
            },
            "metadata": {
                "collection": sample["collection"],
                "keyword_scorer_raw": {
                    "conceptual": conceptual,
                    "tactical": tactical,
                },
            },
            "notes": f"Auto-generated from {sample['collection']}",
        })

    # Save ground truth
    gt_data = {
        "name": output,
        "description": f"Stratified ground truth from SPARTA data ({len(samples)} samples)",
        "generated": datetime.now().isoformat(),
        "seed": seed,
        "counts": {
            "attck": len(attck),
            "nist": len(nist),
            "cwe": len(cwe),
            "d3fend": len(d3fend),
        },
        "cases": cases,
    }

    gt_file = SKILL_DIR / "ground_truth" / f"{output}.json"
    gt_file.parent.mkdir(parents=True, exist_ok=True)
    gt_file.write_text(json.dumps(gt_data, indent=2))

    console.print(f"\n[green]✓ Ground truth saved to: {gt_file}[/green]")
    console.print(f"  Total cases: {len(cases)}")
    console.print()
    console.print("[yellow]⚠ Review and refine the expected labels before using for evaluation[/yellow]")

    # Summary by collection
    console.print("\n[bold]Breakdown by collection:[/bold]")
    table = Table()
    table.add_column("Collection", style="cyan")
    table.add_column("Count")
    table.add_column("Example ID")

    for collection, count, items in [
        ("ATT&CK", len(attck), attck),
        ("NIST", len(nist), nist),
        ("CWE", len(cwe), cwe),
        ("D3FEND", len(d3fend), d3fend),
    ]:
        example = items[0]["id"] if items else "N/A"
        table.add_row(collection, str(count), example)

    console.print(table)


# =============================================================================
# AUTO-ITERATE: Automated N-round prompt improvement
# =============================================================================

@app.command("auto-iterate")
def auto_iterate(
    prompt: str = typer.Option("taxonomy_v1", "--prompt", "-p", help="Starting prompt"),
    model: str = typer.Option("deepseek-v3.2", "--model", "-m", help="Model to use"),
    ground_truth: str = typer.Option("taxonomy_large", "--ground-truth", "-g", help="Ground truth to evaluate against"),
    max_rounds: int = typer.Option(5, "--rounds", "-n", help="Maximum iteration rounds"),
    target_f1: float = typer.Option(0.90, "--target", help="Target F1 score to stop"),
    improvement_threshold: float = typer.Option(0.02, "--threshold", help="Minimum F1 improvement per round"),
    task_monitor: bool = typer.Option(True, "--task-monitor/--no-task-monitor", help="Enable task-monitor integration"),
):
    """Automated N-round prompt improvement with task-monitor integration.

    Each round:
    1. Evaluate current prompt against ground truth
    2. Analyze errors and generate improvement suggestions
    3. Auto-apply suggested improvements to prompt
    4. Re-evaluate and repeat

    Stops when target F1 reached or improvement plateaus.
    """
    # Try to import Monitor from task-monitor
    monitor = None
    if task_monitor:
        try:
            sys.path.insert(0, str(Path.home() / ".claude/skills/task-monitor"))
            from monitor_adapter import Monitor
            monitor = Monitor(
                name=f"prompt-lab-{prompt}",
                total=max_rounds,
                desc=f"Optimizing {prompt} with {model}",
            )
        except ImportError:
            console.print("[dim]Task-monitor not available, running without progress tracking[/dim]")

    # Load model config
    models_file = SKILL_DIR / "models.json"
    models_config = json.loads(models_file.read_text())

    if model not in models_config:
        console.print(f"[red]Model '{model}' not found. Available: {list(models_config.keys())}[/red]")
        raise typer.Exit(1)

    model_config = models_config[model]

    # Check ground truth exists
    gt_file = SKILL_DIR / "ground_truth" / f"{ground_truth}.json"
    if not gt_file.exists():
        console.print(f"[red]Ground truth '{ground_truth}' not found. Run 'build-ground-truth' first.[/red]")
        raise typer.Exit(1)

    gt_data = json.loads(gt_file.read_text())
    console.print(f"[bold]Auto-Iterate: Optimizing prompt '{prompt}'[/bold]")
    console.print(f"Model: {model}")
    console.print(f"Ground truth: {ground_truth} ({len(gt_data['cases'])} cases)")
    console.print(f"Target F1: {target_f1}")
    console.print(f"Max rounds: {max_rounds}")
    console.print()

    iteration_history = []
    prompt_versions = []

    for round_num in range(1, max_rounds + 1):
        console.print(f"\n[bold cyan]═══ Round {round_num}/{max_rounds} ═══[/bold cyan]\n")

        if monitor:
            monitor.set_description(f"Round {round_num}: Evaluating")

        # Load current prompt
        system_prompt, user_template = load_prompt(prompt, SKILL_DIR)
        prompt_versions.append(system_prompt[:500])  # Track prompt changes

        # Load test cases from ground truth
        test_cases = []
        for c in gt_data.get("cases", []):
            test_cases.append(TestCase(
                id=c["id"],
                name=c["input"]["name"],
                description=c["input"]["description"],
                expected_conceptual=c["expected"].get("conceptual", []),
                expected_tactical=c["expected"].get("tactical", []),
                notes=c.get("notes", "")
            ))

        # Run evaluation
        results = []

        async def run_round():
            for tc in test_cases:
                user_msg = user_template.format(name=tc.name, description=tc.description)

                try:
                    llm_result = await call_llm_with_correction(
                        system_prompt, user_msg, model_config, max_correction_rounds=2
                    )
                    validated = llm_result.validated or TaxonomyResponse()

                    result = EvalResult(
                        case_id=tc.id,
                        predicted_conceptual=validated.conceptual,
                        predicted_tactical=validated.tactical,
                        expected_conceptual=tc.expected_conceptual,
                        expected_tactical=tc.expected_tactical,
                        rejected_tags=llm_result.rejected_tags,
                        confidence=validated.confidence,
                        latency_ms=llm_result.total_latency_ms,
                        correction_rounds=llm_result.correction_rounds,
                        correction_success=llm_result.success,
                    )
                    results.append(result)

                except Exception as e:
                    console.print(f"  [red]{tc.id}: ERROR - {e}[/red]")

        asyncio.run(run_round())

        # Calculate metrics
        avg_f1 = sum(r.f1 for r in results) / len(results) if results else 0
        total_corrections = sum(r.correction_rounds for r in results)
        total_rejected = sum(len(r.rejected_tags) for r in results)

        # Find worst cases for analysis
        worst_cases = sorted(results, key=lambda r: r.f1)[:5]

        iteration_history.append({
            "round": round_num,
            "avg_f1": avg_f1,
            "corrections": total_corrections,
            "rejected": total_rejected,
            "worst_case_ids": [c.case_id for c in worst_cases],
        })

        console.print(f"Round {round_num} Results:")
        console.print(f"  Avg F1: {avg_f1:.3f}")
        console.print(f"  Corrections: {total_corrections}")
        console.print(f"  Rejected: {total_rejected}")

        # Check stopping conditions
        if avg_f1 >= target_f1:
            console.print(f"\n[green]✓ TARGET REACHED! F1={avg_f1:.3f} >= {target_f1}[/green]")
            break

        # Check improvement plateau
        if len(iteration_history) > 1:
            improvement = avg_f1 - iteration_history[-2]["avg_f1"]
            console.print(f"  Improvement: {improvement:+.3f}")

            if improvement < improvement_threshold and round_num > 2:
                console.print(f"\n[yellow]⚠ Improvement plateau detected ({improvement:.3f} < {improvement_threshold})[/yellow]")
                if round_num >= 3:
                    console.print("Stopping early - consider manual prompt refinement.")
                    break

        if round_num < max_rounds:
            # Generate and apply improvements
            if monitor:
                monitor.set_description(f"Round {round_num}: Analyzing errors")

            console.print("\nAnalyzing errors for improvements...")

            # Collect error patterns
            error_patterns = []
            for r in results:
                if r.f1 < 1.0:
                    error_patterns.append({
                        "id": r.case_id,
                        "expected": {"c": r.expected_conceptual, "t": r.expected_tactical},
                        "got": {"c": r.predicted_conceptual, "t": r.predicted_tactical},
                        "rejected": r.rejected_tags,
                    })

            if error_patterns:
                # Generate improvement suggestions using LLM
                improvement_prompt = f"""Analyze these taxonomy extraction errors and suggest ONE specific prompt improvement.

ERRORS (showing expected vs predicted):
{json.dumps(error_patterns[:10], indent=2)}

Current prompt section (first 500 chars):
{system_prompt[:500]}...

VALID TAGS:
Conceptual (Tier 0): Precision, Resilience, Fragility, Corruption, Loyalty, Stealth
Tactical (Tier 1): Model, Harden, Detect, Isolate, Restore, Evade, Exploit, Persist

Return JSON with ONE specific improvement:
{{"improvement": "Add explicit instruction to...", "add_to_prompt": "..."}}"""

                try:
                    async def get_improvement():
                        from scillm.batch import parallel_acompletions

                        api_base = os.environ.get("CHUTES_API_BASE", "").strip('"\'')
                        api_key = os.environ.get("CHUTES_API_KEY", "").strip('"\'')
                        model_id = model_config.get("model", "")

                        req = {
                            "model": model_id,
                            "messages": [
                                {"role": "system", "content": "You are a prompt engineer. Suggest ONE specific improvement."},
                                {"role": "user", "content": improvement_prompt},
                            ],
                            "response_format": {"type": "json_object"},
                            "max_tokens": 512,
                            "temperature": 0.3,
                        }

                        resp = await parallel_acompletions(
                            [req], api_base=api_base, api_key=api_key,
                            custom_llm_provider="openai_like", concurrency=1,
                            timeout=60, wall_time_s=120, tenacious=False,
                        )

                        if resp and not resp[0].get("error"):
                            content = resp[0].get("content", "{}")
                            if isinstance(content, str):
                                return json.loads(content)
                            return content
                        return {}

                    suggestion = asyncio.run(get_improvement())

                    if suggestion.get("improvement"):
                        console.print(f"\n[bold cyan]Suggested improvement:[/bold cyan]")
                        console.print(f"  {suggestion.get('improvement', 'N/A')}")

                        # Auto-apply the improvement to the prompt
                        add_text = suggestion.get("add_to_prompt", "")
                        if add_text:
                            prompt_file = SKILL_DIR / "prompts" / f"{prompt}.txt"
                            current_content = prompt_file.read_text()

                            # Insert improvement after the vocabulary section
                            if "Valid tactical tags" in current_content:
                                insert_point = current_content.find("[USER]")
                                if insert_point > 0:
                                    new_content = (
                                        current_content[:insert_point] +
                                        f"\n{add_text}\n\n" +
                                        current_content[insert_point:]
                                    )
                                    prompt_file.write_text(new_content)
                                    console.print(f"  [green]✓ Applied improvement to prompt[/green]")

                except Exception as e:
                    console.print(f"  [dim]Could not generate improvement: {e}[/dim]")

        if monitor:
            monitor.update(1, f"Round {round_num} complete: F1={avg_f1:.3f}")

    # Final summary
    console.print("\n[bold]═══ Iteration Summary ═══[/bold]")

    table = Table()
    table.add_column("Round", style="cyan")
    table.add_column("Avg F1", style="green")
    table.add_column("Corrections", style="yellow")
    table.add_column("Rejected", style="red")

    for h in iteration_history:
        table.add_row(
            str(h["round"]),
            f"{h['avg_f1']:.3f}",
            str(h["corrections"]),
            str(h["rejected"]),
        )

    console.print(table)

    # Calculate total improvement
    if len(iteration_history) > 1:
        total_improvement = iteration_history[-1]["avg_f1"] - iteration_history[0]["avg_f1"]
        console.print(f"\nTotal F1 improvement: {total_improvement:+.3f}")

    final_f1 = iteration_history[-1]["avg_f1"] if iteration_history else 0
    if final_f1 >= target_f1:
        console.print(f"\n[green]✓ OPTIMIZATION COMPLETE - Target reached![/green]")
    else:
        console.print(f"\n[yellow]⚠ Optimization stopped - F1={final_f1:.3f} (target: {target_f1})[/yellow]")

    # Save optimization report
    report_file = SKILL_DIR / "results" / f"optimization_{prompt}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_file.parent.mkdir(exist_ok=True)
    report_file.write_text(json.dumps({
        "prompt": prompt,
        "model": model,
        "ground_truth": ground_truth,
        "timestamp": datetime.now().isoformat(),
        "target_f1": target_f1,
        "final_f1": final_f1,
        "total_rounds": len(iteration_history),
        "history": iteration_history,
    }, indent=2))

    console.print(f"\nReport saved: {report_file}")


@app.command("model-compare")
def model_compare(
    prompt: str = typer.Option("taxonomy_v2", "--prompt", "-p", help="Prompt to use"),
    ground_truth: str = typer.Option("taxonomy_large", "--ground-truth", "-g", help="Ground truth to evaluate against"),
    models_str: str = typer.Option(
        "deepseek-v3.2,qwen3-235b,qwen3-coder-480b",
        "--models", "-m",
        help="Comma-separated list of models to compare"
    ),
):
    """Compare multiple models on the same prompt and ground truth.

    Runs evaluation for each model and produces a comparison table.
    """
    model_list = [m.strip() for m in models_str.split(",")]

    # Load model configs
    models_file = SKILL_DIR / "models.json"
    models_config = json.loads(models_file.read_text())

    # Check ground truth exists
    gt_file = SKILL_DIR / "ground_truth" / f"{ground_truth}.json"
    if not gt_file.exists():
        console.print(f"[red]Ground truth '{ground_truth}' not found.[/red]")
        raise typer.Exit(1)

    gt_data = json.loads(gt_file.read_text())

    console.print(f"[bold]Model Comparison[/bold]")
    console.print(f"Prompt: {prompt}")
    console.print(f"Ground truth: {ground_truth} ({len(gt_data['cases'])} cases)")
    console.print(f"Models: {', '.join(model_list)}")
    console.print()

    comparison_results = []

    for model in model_list:
        if model not in models_config:
            console.print(f"[yellow]Skipping unknown model: {model}[/yellow]")
            continue

        console.print(f"\n[bold cyan]Evaluating: {model}[/bold cyan]")

        model_config = models_config[model]
        system_prompt, user_template = load_prompt(prompt, SKILL_DIR)

        # Load test cases
        test_cases = []
        for c in gt_data.get("cases", []):
            test_cases.append(TestCase(
                id=c["id"],
                name=c["input"]["name"],
                description=c["input"]["description"],
                expected_conceptual=c["expected"].get("conceptual", []),
                expected_tactical=c["expected"].get("tactical", []),
                notes=""
            ))

        results = []

        async def run_model_eval():
            for tc in test_cases:
                user_msg = user_template.format(name=tc.name, description=tc.description)

                try:
                    llm_result = await call_llm_with_correction(
                        system_prompt, user_msg, model_config, max_correction_rounds=2
                    )
                    validated = llm_result.validated or TaxonomyResponse()

                    result = EvalResult(
                        case_id=tc.id,
                        predicted_conceptual=validated.conceptual,
                        predicted_tactical=validated.tactical,
                        expected_conceptual=tc.expected_conceptual,
                        expected_tactical=tc.expected_tactical,
                        rejected_tags=llm_result.rejected_tags,
                        confidence=validated.confidence,
                        latency_ms=llm_result.total_latency_ms,
                        correction_rounds=llm_result.correction_rounds,
                        correction_success=llm_result.success,
                    )
                    results.append(result)

                except Exception as e:
                    console.print(f"  [dim]Error on {tc.id}: {e}[/dim]")

        asyncio.run(run_model_eval())

        if results:
            avg_f1 = sum(r.f1 for r in results) / len(results)
            avg_latency = sum(r.latency_ms for r in results) / len(results)
            total_corrections = sum(r.correction_rounds for r in results)

            comparison_results.append({
                "model": model,
                "avg_f1": avg_f1,
                "avg_latency_ms": avg_latency,
                "total_corrections": total_corrections,
                "cases_evaluated": len(results),
            })

            console.print(f"  F1={avg_f1:.3f}  Latency={avg_latency:.0f}ms  Corrections={total_corrections}")

    # Final comparison table
    console.print("\n[bold]═══ Model Comparison Results ═══[/bold]")

    # Sort by F1 score descending
    comparison_results.sort(key=lambda x: x["avg_f1"], reverse=True)

    table = Table()
    table.add_column("Rank", style="dim")
    table.add_column("Model", style="cyan")
    table.add_column("Avg F1", style="green")
    table.add_column("Latency", style="yellow")
    table.add_column("Corrections")

    for i, r in enumerate(comparison_results, 1):
        rank = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else str(i)
        table.add_row(
            rank,
            r["model"],
            f"{r['avg_f1']:.3f}",
            f"{r['avg_latency_ms']:.0f}ms",
            str(r["total_corrections"]),
        )

    console.print(table)

    # Recommendation
    if comparison_results:
        best = comparison_results[0]
        console.print(f"\n[green]✓ Recommended: {best['model']} (F1={best['avg_f1']:.3f})[/green]")

    # Save comparison
    compare_file = SKILL_DIR / "results" / f"model_compare_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    compare_file.write_text(json.dumps({
        "prompt": prompt,
        "ground_truth": ground_truth,
        "timestamp": datetime.now().isoformat(),
        "results": comparison_results,
    }, indent=2))

    console.print(f"\nResults saved: {compare_file}")


if __name__ == "__main__":
    app()

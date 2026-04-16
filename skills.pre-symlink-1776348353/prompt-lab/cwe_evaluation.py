"""
CWE Validation Evaluation - Brandon Bailey persona.

Tests the CWE relevance validation prompt against ground truth test cases.
Calculates precision/recall for CWE relevance predictions.
"""

import json
import sys
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

# Ensure this directory is importable
ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import typer
    from rich.console import Console
    from rich.table import Table
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "typer", "rich", "-q"])
    import typer
    from rich.console import Console
    from rich.table import Table

from evaluation import load_models_config

app = typer.Typer()
console = Console()


async def call_llm_cwe(
    system_prompt: str,
    user_prompt: str,
    model: str,
    max_tokens: int = 2000,
    temperature: float = 0.1,
) -> str:
    """Call LLM for CWE validation."""
    try:
        from scillm.batch import parallel_acompletions
        import os
    except ImportError:
        raise ImportError("scillm not installed. Run: uv add scillm")

    # Get API config
    api_base = os.environ.get("SCILLM_API_BASE", "http://localhost:4001").strip('"\'')
    api_key = os.environ.get("SCILLM_PROXY_KEY", "sk-dev-proxy-123").strip('"\'')

    # Model ID mapping
    model_map = {
        "deepseek": "deepseek-ai/DeepSeek-V3-0324-TEE",
        "gpt-4o": "openai/gpt-4o",
        "claude": "anthropic/claude-3.5-sonnet",
    }
    model_id = model_map.get(model, model)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    req = {
        "model": model_id,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    results = await parallel_acompletions(
        [req],
        api_base=api_base,
        api_key=api_key,
        custom_llm_provider="openai",
        concurrency=1,
        timeout=120,
        wall_time_s=180,
        tenacious=True,
        # max_retries_5xx removed from scillm.batch API (2026-03)
    )

    if results and not results[0].get("error"):
        return results[0].get("content", "[]")
    else:
        error = results[0].get("error", "Unknown error") if results else "No response"
        raise Exception(error)


@dataclass
class CWEValidationResult:
    """Result of validating a single CWE."""
    cwe_id: str
    predicted_relevant: bool
    expected_relevant: bool
    confidence: float
    reason: str

    @property
    def correct(self) -> bool:
        return self.predicted_relevant == self.expected_relevant


@dataclass
class CaseResult:
    """Result of evaluating a single test case."""
    case_id: str
    validations: list[CWEValidationResult] = field(default_factory=list)
    latency_ms: float = 0.0
    error: Optional[str] = None

    @property
    def precision(self) -> float:
        """Precision: of predicted relevant, how many are actually relevant."""
        predicted_relevant = [v for v in self.validations if v.predicted_relevant]
        if not predicted_relevant:
            return 1.0
        correct = sum(1 for v in predicted_relevant if v.expected_relevant)
        return correct / len(predicted_relevant)

    @property
    def recall(self) -> float:
        """Recall: of actually relevant, how many did we predict as relevant."""
        expected_relevant = [v for v in self.validations if v.expected_relevant]
        if not expected_relevant:
            return 1.0
        correct = sum(1 for v in expected_relevant if v.predicted_relevant)
        return correct / len(expected_relevant)

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        if p + r == 0:
            return 0.0
        return 2 * p * r / (p + r)

    @property
    def accuracy(self) -> float:
        if not self.validations:
            return 0.0
        return sum(1 for v in self.validations if v.correct) / len(self.validations)


@dataclass
class EvalSummary:
    """Summary of full evaluation run."""
    results: list[CaseResult] = field(default_factory=list)
    prompt_name: str = ""
    model_name: str = ""

    @property
    def avg_precision(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.precision for r in self.results) / len(self.results)

    @property
    def avg_recall(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.recall for r in self.results) / len(self.results)

    @property
    def avg_f1(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.f1 for r in self.results) / len(self.results)

    @property
    def avg_accuracy(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.accuracy for r in self.results) / len(self.results)

    @property
    def avg_latency_ms(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.latency_ms for r in self.results) / len(self.results)


def load_prompt(name: str) -> tuple[str, str]:
    """Load prompt from prompts directory.

    Returns:
        Tuple of (system_prompt, user_template)
    """
    prompt_path = ROOT / "prompts" / f"{name}.txt"
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt not found: {prompt_path}")

    content = prompt_path.read_text()

    # Parse [SYSTEM] and [USER] sections
    if "[SYSTEM]" in content and "[USER]" in content:
        parts = content.split("[USER]")
        system = parts[0].replace("[SYSTEM]", "").strip()
        user = parts[1].strip()
    else:
        # Treat entire prompt as system prompt
        system = content.strip()
        user = "Control Text:\n{control_text}\n\nCandidate CWEs to validate:\n{cwe_list}"

    return system, user


def load_ground_truth() -> dict:
    """Load CWE validation ground truth."""
    gt_path = ROOT / "ground_truth" / "cwe_validation.json"
    if not gt_path.exists():
        raise FileNotFoundError(f"Ground truth not found: {gt_path}")
    return json.loads(gt_path.read_text())


def format_cwe_list(cwes: list[str]) -> str:
    """Format CWE list for prompt."""
    return ", ".join(cwes)


def parse_cwe_response(response: str) -> list[dict]:
    """Parse LLM response as JSON array of CWE validations."""
    # Try to extract JSON from response
    response = response.strip()

    # Handle markdown code blocks
    if "```json" in response:
        start = response.find("```json") + 7
        end = response.find("```", start)
        response = response[start:end].strip()
    elif "```" in response:
        start = response.find("```") + 3
        end = response.find("```", start)
        response = response[start:end].strip()

    try:
        data = json.loads(response)
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            # Single object - wrap in array
            if "cwe_id" in data:
                return [data]
            # Maybe it's wrapped in a key like "validations"
            for key in ["validations", "items", "results", "cwes"]:
                if key in data and isinstance(data[key], list):
                    return data[key]
        return []
    except json.JSONDecodeError:
        console.print(f"[yellow]Failed to parse response as JSON[/yellow]")
        console.print(f"Response: {response[:500]}")
        return []


async def evaluate_case(
    system_prompt: str,
    user_template: str,
    case: dict,
    model: str,
) -> CaseResult:
    """Evaluate a single test case."""
    case_id = case["id"]
    control_text = case["control_text"]
    candidate_cwes = case["candidate_cwes"]
    expected = case["expected"]

    # Build expected lookup
    expected_relevant = set(expected.get("relevant", []))
    expected_irrelevant = set(expected.get("irrelevant", []))

    # Format user prompt
    user_prompt = user_template.replace("{control_text}", control_text)
    user_prompt = user_prompt.replace("{cwe_list}", format_cwe_list(candidate_cwes))

    # Call LLM
    start = time.time()
    try:
        response = await call_llm_cwe(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            temperature=0.1,
            max_tokens=2000,
        )
        latency_ms = (time.time() - start) * 1000
    except Exception as e:
        return CaseResult(case_id=case_id, error=str(e))

    # Parse response
    validations_data = parse_cwe_response(response)

    validations = []
    for v in validations_data:
        cwe_id = v.get("cwe_id", "")
        predicted_relevant = v.get("relevant", False)
        confidence = v.get("confidence", 0.0)
        reason = v.get("reason", "")

        # Determine expected
        if cwe_id in expected_relevant:
            exp_relevant = True
        elif cwe_id in expected_irrelevant:
            exp_relevant = False
        else:
            # CWE not in ground truth, skip
            continue

        validations.append(CWEValidationResult(
            cwe_id=cwe_id,
            predicted_relevant=predicted_relevant,
            expected_relevant=exp_relevant,
            confidence=confidence,
            reason=reason,
        ))

    return CaseResult(
        case_id=case_id,
        validations=validations,
        latency_ms=latency_ms,
    )


@app.command()
def eval(
    prompt: str = typer.Option("cwe_validation_v1", "--prompt", "-p", help="Prompt name"),
    model: str = typer.Option("deepseek", "--model", "-m", help="Model to use"),
    cases: Optional[int] = typer.Option(None, "--cases", "-n", help="Number of cases"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show per-case details"),
):
    """Evaluate CWE validation prompt against ground truth."""
    import asyncio

    console.print(f"[bold]CWE Validation Evaluation[/bold]")
    console.print(f"Prompt: {prompt}, Model: {model}")

    # Load prompt and ground truth
    try:
        system_prompt, user_template = load_prompt(prompt)
        gt = load_ground_truth()
    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    test_cases = gt.get("cases", [])
    if cases:
        test_cases = test_cases[:cases]

    console.print(f"Running {len(test_cases)} test cases...")

    # Run evaluation
    async def run_all():
        results = []
        for i, case in enumerate(test_cases):
            console.print(f"  [{i+1}/{len(test_cases)}] {case['id']}...", end="")
            result = await evaluate_case(system_prompt, user_template, case, model)

            if result.error:
                console.print(f" [red]ERROR: {result.error}[/red]")
            else:
                status = "[green]PASS[/green]" if result.accuracy >= 0.8 else "[yellow]WARN[/yellow]"
                console.print(f" {status} (P={result.precision:.2f}, R={result.recall:.2f}, F1={result.f1:.2f})")

            if verbose and not result.error:
                for v in result.validations:
                    mark = "[green]+[/green]" if v.correct else "[red]x[/red]"
                    pred = "relevant" if v.predicted_relevant else "irrelevant"
                    exp = "relevant" if v.expected_relevant else "irrelevant"
                    console.print(f"    {mark} {v.cwe_id}: predicted={pred}, expected={exp}, conf={v.confidence:.2f}")

            results.append(result)
        return results

    results = asyncio.run(run_all())

    # Summary
    summary = EvalSummary(results=results, prompt_name=prompt, model_name=model)

    console.print("\n[bold]Summary[/bold]")
    table = Table()
    table.add_column("Metric")
    table.add_column("Value")

    table.add_row("Avg Precision", f"{summary.avg_precision:.3f}")
    table.add_row("Avg Recall", f"{summary.avg_recall:.3f}")
    table.add_row("Avg F1", f"{summary.avg_f1:.3f}")
    table.add_row("Avg Accuracy", f"{summary.avg_accuracy:.3f}")
    table.add_row("Avg Latency", f"{summary.avg_latency_ms:.0f}ms")

    console.print(table)

    # Quality gate
    thresholds = gt.get("evaluation_criteria", {})
    precision_thresh = thresholds.get("precision_threshold", 0.85)
    recall_thresh = thresholds.get("recall_threshold", 0.80)

    if summary.avg_precision >= precision_thresh and summary.avg_recall >= recall_thresh:
        console.print(f"\n[green]PASS[/green]: Quality gates met (P>={precision_thresh}, R>={recall_thresh})")
    else:
        console.print(f"\n[red]FAIL[/red]: Quality gates not met")
        console.print(f"  Precision: {summary.avg_precision:.3f} (threshold: {precision_thresh})")
        console.print(f"  Recall: {summary.avg_recall:.3f} (threshold: {recall_thresh})")
        raise typer.Exit(1)


@app.command()
def analyze_errors(
    prompt: str = typer.Option("cwe_validation_v1", "--prompt", "-p", help="Prompt name"),
    model: str = typer.Option("deepseek", "--model", "-m", help="Model to use"),
):
    """Analyze error patterns in CWE validation."""
    import asyncio

    console.print(f"[bold]CWE Validation Error Analysis[/bold]")

    system_prompt, user_template = load_prompt(prompt)
    gt = load_ground_truth()
    test_cases = gt.get("cases", [])

    async def run_all():
        results = []
        for case in test_cases:
            result = await evaluate_case(system_prompt, user_template, case, model)
            results.append((case, result))
        return results

    results = asyncio.run(run_all())

    # Analyze error patterns
    false_positives = []  # Predicted relevant but actually irrelevant
    false_negatives = []  # Predicted irrelevant but actually relevant

    for case, result in results:
        for v in result.validations:
            if v.predicted_relevant and not v.expected_relevant:
                false_positives.append({
                    "case_id": case["id"],
                    "cwe_id": v.cwe_id,
                    "control_text": case["control_text"][:100],
                    "reason": v.reason,
                    "confidence": v.confidence,
                })
            elif not v.predicted_relevant and v.expected_relevant:
                false_negatives.append({
                    "case_id": case["id"],
                    "cwe_id": v.cwe_id,
                    "control_text": case["control_text"][:100],
                    "reason": v.reason,
                    "confidence": v.confidence,
                })

    console.print(f"\n[bold]False Positives ({len(false_positives)})[/bold]")
    for fp in false_positives[:5]:
        console.print(f"  - {fp['case_id']}/{fp['cwe_id']}: {fp['reason'][:80]}")

    console.print(f"\n[bold]False Negatives ({len(false_negatives)})[/bold]")
    for fn in false_negatives[:5]:
        console.print(f"  - {fn['case_id']}/{fn['cwe_id']}: {fn['reason'][:80]}")

    # Save for prompt optimization
    errors_path = ROOT / "results" / "cwe_validation_errors.json"
    errors_path.parent.mkdir(exist_ok=True)
    errors_path.write_text(json.dumps({
        "false_positives": false_positives,
        "false_negatives": false_negatives,
    }, indent=2))
    console.print(f"\nErrors saved to: {errors_path}")


if __name__ == "__main__":
    app()

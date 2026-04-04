"""Multi-model prompt review loop with deterministic scoring.

Same autoresearch pattern as code-runner, but simpler:
- No git stash/revert (just keep old text in memory)
- No allowlist/DoD enforcement
- No file writing by LLM
- Scoring = count of findings across N models (lower = better)

The agent sends prompt template + source to N models concurrently via /scillm,
parses findings, applies fixes, and repeats until score == 0 or max rounds.
"""
from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx
import typer
from loguru import logger

app = typer.Typer()

SCILLM_URL = os.environ.get("SCILLM_API_BASE", "http://localhost:4001/v1/chat/completions")
SCILLM_KEY = os.environ.get("SCILLM_PROXY_KEY", "sk-dev-proxy-123")

DEFAULT_MODELS = ["gpt-5.3-codex", "text-gemini", "text"]

SEVERITY_WEIGHTS = {"critical": 3, "major": 2, "minor": 1}

# ── Review prompt sent to each model ────────────────────────────────

REVIEW_SYSTEM = """You are a prompt engineering reviewer. You review LLM prompt templates for:
1. Clarity — will the target LLM understand exactly what to do?
2. Safety — is there protection against prompt injection from data fields?
3. Format spec — is the output format unambiguous and parseable?
4. Completeness — are edge cases handled (no changes needed, errors in data)?
5. Conciseness — is every instruction load-bearing? Remove dead weight.

Output your findings as a JSON array. Each finding:
{"severity": "critical|major|minor", "location": "section or line", "finding": "what's wrong", "fix": "specific fix"}

If no findings, return: []

Do NOT return prose. Only the JSON array."""

FOLLOWUP_SYSTEM = """You are a prompt engineering reviewer doing a SECOND pass.
The prior round found and fixed some issues. Your job: find what the prior round MISSED.
Focus on interactions between sections, edge cases, and subtle ambiguities.

Output findings as a JSON array. Each finding:
{"severity": "critical|major|minor", "location": "section or line", "finding": "what's wrong", "fix": "specific fix"}

If no new findings, return: []"""


def _build_review_prompt(
    template_text: str,
    source_texts: dict[str, str],
    context: str,
    round_num: int,
    prior_findings: list[dict] | None = None,
) -> str:
    """Build the user prompt for a review round."""
    parts = [f"## Context\n{context}\n"] if context else []

    parts.append(f"## Prompt Template\n```\n{template_text}\n```\n")

    for name, src in source_texts.items():
        parts.append(f"## Source: {name}\n```python\n{src}\n```\n")

    if prior_findings and round_num > 1:
        parts.append("## Prior Round Findings (already fixed)\n")
        for f in prior_findings:
            parts.append(f"- [{f.get('severity')}] {f.get('finding')}")
        parts.append("\nWhat did the prior round MISS? Focus on new issues only.\n")

    return "\n".join(parts)


def _call_scillm(model: str, system: str, user: str) -> str:
    """Single /scillm call. Returns response text."""
    try:
        resp = httpx.post(
            SCILLM_URL,
            headers={"Authorization": f"Bearer {SCILLM_KEY}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "max_tokens": 4000,
                "temperature": 0.1,
            },
            timeout=120.0,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error("scillm {} failed: {}", model, e)
        return "[]"


def _parse_findings(response: str) -> list[dict]:
    """Extract findings JSON array from model response."""
    # Try direct JSON parse
    text = response.strip()

    # Strip markdown fences if present
    fence_match = re.search(r'```(?:json)?\s*\n(.*?)```', text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [f for f in data if isinstance(f, dict) and "severity" in f]
        return []
    except json.JSONDecodeError:
        # Try finding array in response
        array_match = re.search(r'\[.*\]', text, re.DOTALL)
        if array_match:
            try:
                data = json.loads(array_match.group())
                if isinstance(data, list):
                    return [f for f in data if isinstance(f, dict) and "severity" in f]
            except json.JSONDecodeError:
                pass
        return []


def _score_findings(findings: list[dict]) -> int:
    """Deterministic score: weighted sum of findings. Lower = better."""
    return sum(SEVERITY_WEIGHTS.get(f.get("severity", "minor"), 1) for f in findings)


def _deduplicate_findings(all_findings: list[dict]) -> list[dict]:
    """Deduplicate findings from multiple models by similarity."""
    seen: set[str] = set()
    unique: list[dict] = []
    for f in all_findings:
        key = f.get("finding", "")[:80].lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


def _concurrent_review(
    models: list[str],
    system: str,
    user_prompt: str,
) -> list[dict]:
    """Send review to N models concurrently, merge and deduplicate findings."""
    all_findings: list[dict] = []

    with ThreadPoolExecutor(max_workers=len(models)) as pool:
        futures = {
            pool.submit(_call_scillm, model, system, user_prompt): model
            for model in models
        }
        for future in as_completed(futures):
            model = futures[future]
            try:
                response = future.result()
                findings = _parse_findings(response)
                for f in findings:
                    f["model"] = model  # tag source model
                all_findings.extend(findings)
                logger.info("  {} → {} findings", model, len(findings))
            except Exception as e:
                logger.error("  {} failed: {}", model, e)

    return _deduplicate_findings(all_findings)


@app.command()
def review(
    template: str = typer.Option(..., "--template", "-t", help="Prompt template file"),
    source: list[str] = typer.Option([], "--source", "-s", help="Source files that use the template"),
    context: str = typer.Option("", "--context", "-c", help="One-line description"),
    models: list[str] = typer.Option([], "--models", "-m", help="Models to use"),
    max_rounds: int = typer.Option(3, "--max-rounds", help="Max review rounds"),
    output: str = typer.Option("", "--output", "-o", help="Write final template to file"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show prompt without calling LLM"),
) -> None:
    """Review and optimize a prompt template using concurrent multi-model feedback."""
    if not models:
        models = DEFAULT_MODELS

    template_path = Path(template)
    if not template_path.exists():
        logger.error("Template not found: {}", template)
        raise typer.Exit(1)

    template_text = template_path.read_text().strip()
    best_text = template_text  # keep/revert anchor

    source_texts: dict[str, str] = {}
    for s in source:
        sp = Path(s)
        if sp.exists():
            source_texts[sp.name] = sp.read_text()[:8000]  # cap for context window

    logger.info("=== REVIEW-PROMPT: {} ===", template_path.name)
    logger.info("  Models: {}", ", ".join(models))
    logger.info("  Sources: {}", ", ".join(source_texts.keys()) or "(none)")
    logger.info("  Max rounds: {}", max_rounds)

    if dry_run:
        prompt = _build_review_prompt(template_text, source_texts, context, 1)
        print("=== SYSTEM ===")
        print(REVIEW_SYSTEM)
        print("\n=== USER ===")
        print(prompt)
        return

    all_prior_findings: list[dict] = []
    best_score = float("inf")
    rounds_log: list[dict] = []

    for round_num in range(1, max_rounds + 1):
        system = REVIEW_SYSTEM if round_num == 1 else FOLLOWUP_SYSTEM
        user_prompt = _build_review_prompt(
            template_text, source_texts, context, round_num, all_prior_findings,
        )

        logger.info("── Round {}/{} ──", round_num, max_rounds)
        findings = _concurrent_review(models, system, user_prompt)
        score = _score_findings(findings)

        round_entry = {
            "round": round_num,
            "findings_count": len(findings),
            "score": score,
            "findings": findings,
            "timestamp": time.time(),
        }
        rounds_log.append(round_entry)

        logger.info("  Score: {} ({} findings)", score, len(findings))

        if score == 0:
            logger.info("=== CLEAN: No findings on round {} ===", round_num)
            break

        # Print findings for human review
        for f in sorted(findings, key=lambda x: SEVERITY_WEIGHTS.get(x.get("severity", ""), 0), reverse=True):
            sev = f.get("severity", "?")
            loc = f.get("location", "?")
            finding = f.get("finding", "")
            fix = f.get("fix", "")
            model = f.get("model", "?")
            logger.info("  [{}] {} — {} (fix: {}) [{}]", sev, loc, finding, fix, model)

        # Keep/revert decision
        if score < best_score:
            best_score = score
            best_text = template_text
            all_prior_findings.extend(findings)
            logger.info("  KEEP (score {} < previous {})", score, best_score if best_score != float("inf") else "∞")
        else:
            template_text = best_text  # revert
            logger.info("  REVERT (score {} >= best {})", score, best_score)

    # Final output
    logger.info("=== RESULT: {} rounds, best score={} ===", len(rounds_log), best_score)

    if output:
        Path(output).write_text(best_text)
        logger.info("  Wrote optimized template to: {}", output)

    # Write rounds log
    log_file = template_path.parent / f"{template_path.stem}.review.json"
    log_file.write_text(json.dumps({
        "template": str(template_path),
        "models": models,
        "rounds": rounds_log,
        "best_score": best_score if best_score != float("inf") else None,
    }, indent=2))
    logger.info("  Review log: {}", log_file)

    # Print findings summary to stdout for agent consumption
    if all_prior_findings:
        print(json.dumps({
            "status": "findings",
            "total_findings": len(all_prior_findings),
            "best_score": best_score,
            "rounds": len(rounds_log),
            "critical": sum(1 for f in all_prior_findings if f.get("severity") == "critical"),
            "major": sum(1 for f in all_prior_findings if f.get("severity") == "major"),
            "minor": sum(1 for f in all_prior_findings if f.get("severity") == "minor"),
            "findings": all_prior_findings,
        }, indent=2))
    else:
        print(json.dumps({"status": "clean", "total_findings": 0, "rounds": len(rounds_log)}))


if __name__ == "__main__":
    app()

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

FIX_SYSTEM = """You are a prompt engineering editor. You receive a prompt template and a list of findings (bugs/issues).
Apply ALL fixes. Return ONLY the complete fixed prompt template text — no commentary, no markdown fences, no explanation.
Start with the first line of the prompt. End with the last line. Nothing else."""


def _build_review_prompt(
    template_text: str,
    source_texts: dict[str, str],
    context: str,
    round_num: int,
    prior_findings: list[dict] | None = None,
    payload_text: str = "",
) -> str:
    """Build the user prompt for a review round."""
    parts = [f"## Context\n{context}\n"] if context else []

    parts.append(f"## Prompt Template\n```\n{template_text}\n```\n")

    if payload_text:
        parts.append(f"## Actual Payload (this is the real data that fills the template placeholder)\n```json\n{payload_text}\n```\n")
        parts.append("IMPORTANT: Review the prompt WITH this payload. Check that every field path referenced in the prompt exists in the payload. Check that the instructions make sense given the actual data shape and content.\n")

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
                "temperature": 0.1,
            },
            timeout=180.0,
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


def _apply_fixes(template_text: str, findings: list[dict], context: str) -> str | None:
    """Send template + findings to LLM, get back the fixed template. Returns None on failure."""
    findings_text = "\n".join(
        f"- [{f.get('severity')}] {f.get('location')}: {f.get('finding')} → FIX: {f.get('fix')}"
        for f in findings
        if f.get("severity") in ("critical", "major")  # only fix critical/major
    )
    if not findings_text:
        return None

    user = f"## Context\n{context}\n\n## Current Prompt Template\n```\n{template_text}\n```\n\n## Findings to Fix\n{findings_text}\n\nApply ALL fixes above. Return the complete fixed prompt template."

    # Use deepseek for fixes — fast, large context, cheap
    fixed = _call_scillm("deepseek", FIX_SYSTEM, user)
    if not fixed or len(fixed) < len(template_text) * 0.5:
        logger.warning("  Fix attempt returned suspiciously short result ({} chars vs {} original)", len(fixed), len(template_text))
        return None

    # Strip markdown fences if present
    import re as _re
    fence = _re.search(r'```(?:\w+)?\s*\n(.*?)```', fixed, _re.DOTALL)
    if fence:
        fixed = fence.group(1).strip()

    return fixed


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
    payload: str = typer.Option("", "--payload", "-d", help="Real payload/data file that fills the template placeholder"),
    persona: str = typer.Option(..., "--persona", "-p", help="REQUIRED. Who reviews/consumes this prompt (e.g. 'brandon', 'nico', 'tim', or custom description)"),
    context: str = typer.Option(..., "--context", "-c", help="REQUIRED. What this prompt does, why it exists, what problem it solves"),
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

    # --- Hard fail: payload and context are REQUIRED ---
    # A prompt review without the actual data payload is meaningless.
    # The reviewer can't verify field paths, data shapes, or whether
    # instructions make sense given the actual data.
    has_placeholder = any(
        marker in template_text
        for marker in ["{evidence_case_json}", "{payload}", "{document}", "{input}", "<evidence", "<payload", "<document"]
    )
    if has_placeholder and not payload:
        logger.error("═══════════════════════════════════════════════════════════")
        logger.error("  BLOCKED: Prompt contains a data placeholder but no")
        logger.error("  --payload was provided.")
        logger.error("")
        logger.error("  A prompt review without the actual payload is UNTESTABLE.")
        logger.error("  The reviewer cannot verify field paths or data shapes.")
        logger.error("")
        logger.error("  Fix: add --payload <file> with the real data that fills")
        logger.error("  the template placeholder.")
        logger.error("═══════════════════════════════════════════════════════════")
        raise typer.Exit(2)

    missing = []
    if not context.strip():
        missing.append("--context")
    if not persona.strip():
        missing.append("--persona")
    if missing:
        logger.error("═══════════════════════════════════════════════════════════")
        logger.error("  BLOCKED: {} missing.", " and ".join(missing))
        logger.error("")
        logger.error("  Both --context AND --persona are REQUIRED.")
        logger.error("  Context-free reviews are shallow. Persona-free reviews")
        logger.error("  lack domain expertise.")
        logger.error("")
        logger.error("  --context  'what this prompt does, why, what problem'")
        logger.error("  --persona  'who consumes output (nico, brandon, tim,'")
        logger.error("              or custom description)'")
        logger.error("═══════════════════════════════════════════════════════════")
        raise typer.Exit(2)

    # Load payload
    payload_text = ""
    if payload:
        pp = Path(payload)
        if pp.exists():
            payload_text = pp.read_text()[:30000]  # cap for context window — must be large enough to avoid truncation artifacts
            logger.info("  Payload: {} ({} chars)", pp.name, len(payload_text))
        else:
            logger.error("  Payload file not found: {}", payload)
            raise typer.Exit(1)

    # Enrich context with persona if provided
    if persona:
        context = f"{context}\n\nIntended consumer/persona: {persona}" if context else f"Intended consumer/persona: {persona}"

    logger.info("=== REVIEW-PROMPT: {} ===", template_path.name)
    logger.info("  Models: {}", ", ".join(models))
    logger.info("  Sources: {}", ", ".join(source_texts.keys()) or "(none)")
    logger.info("  Payload: {}", "YES" if payload_text else "NO")
    logger.info("  Persona: {}", persona or "(none)")
    logger.info("  Max rounds: {}", max_rounds)

    if dry_run:
        prompt = _build_review_prompt(template_text, source_texts, context, 1, payload_text=payload_text)
        print("=== SYSTEM ===")
        print(REVIEW_SYSTEM)
        print("\n=== USER ===")
        print(prompt)
        return

    all_prior_findings: list[dict] = []
    best_score = float("inf")
    best_text = template_text
    rounds_log: list[dict] = []

    for round_num in range(1, max_rounds + 1):
        # ── Step 1: REVIEW (N models score the current template) ──
        system = REVIEW_SYSTEM if round_num == 1 else FOLLOWUP_SYSTEM
        user_prompt = _build_review_prompt(
            template_text, source_texts, context, round_num, all_prior_findings,
            payload_text=payload_text,
        )

        logger.info("── Round {}/{} ──", round_num, max_rounds)
        findings = _concurrent_review(models, system, user_prompt)
        score = _score_findings(findings)

        # Count critical+major only (these must converge to 0)
        n_critical = sum(1 for f in findings if f.get("severity") == "critical")
        n_major = sum(1 for f in findings if f.get("severity") == "major")

        round_entry = {
            "round": round_num,
            "findings_count": len(findings),
            "score": score,
            "critical": n_critical,
            "major": n_major,
            "findings": findings,
            "timestamp": time.time(),
        }

        logger.info("  Score: {} ({} findings: {} critical, {} major)", score, len(findings), n_critical, n_major)

        # Print findings
        for f in sorted(findings, key=lambda x: SEVERITY_WEIGHTS.get(x.get("severity", ""), 0), reverse=True):
            sev = f.get("severity", "?")
            loc = f.get("location", "?")
            finding = f.get("finding", "")
            fix = f.get("fix", "")
            model = f.get("model", "?")
            logger.info("  [{}] {} — {} (fix: {}) [{}]", sev, loc, finding, fix, model)

        # ── Stop condition: 0 critical and 0 major ──
        if n_critical == 0 and n_major == 0:
            logger.info("=== CONVERGED: 0 critical, 0 major on round {} ===", round_num)
            best_text = template_text
            best_score = score
            round_entry["action"] = "converged"
            rounds_log.append(round_entry)
            break

        # ── Step 2: APPLY FIXES (LLM rewrites template to fix critical+major) ──
        logger.info("  Applying fixes ({} critical + {} major)...", n_critical, n_major)
        fixed_text = _apply_fixes(template_text, findings, context)

        if fixed_text is None:
            logger.warning("  Fix attempt failed — no usable output from LLM")
            round_entry["action"] = "fix_failed"
            rounds_log.append(round_entry)
            all_prior_findings.extend(findings)
            continue

        # ── Step 3: RE-SCORE the fixed template ──
        logger.info("  Re-scoring fixed template...")
        fixed_prompt = _build_review_prompt(
            fixed_text, source_texts, context, round_num, [],
            payload_text=payload_text,
        )
        fixed_findings = _concurrent_review(models, REVIEW_SYSTEM, fixed_prompt)
        fixed_score = _score_findings(fixed_findings)
        fixed_critical = sum(1 for f in fixed_findings if f.get("severity") == "critical")
        fixed_major = sum(1 for f in fixed_findings if f.get("severity") == "major")

        logger.info("  Fixed score: {} (was {}), critical: {} (was {}), major: {} (was {})",
                     fixed_score, score, fixed_critical, n_critical, fixed_major, n_major)

        # ── Step 4: KEEP or REVERT ──
        if fixed_score < score:
            template_text = fixed_text
            best_text = fixed_text
            best_score = fixed_score
            # Write improved template to disk immediately
            template_path.write_text(fixed_text)
            logger.info("  KEEP — wrote improved template to {}", template_path.name)
            round_entry["action"] = "keep"
            round_entry["fixed_score"] = fixed_score
            round_entry["fixed_findings"] = fixed_findings
            all_prior_findings.extend(fixed_findings)
        else:
            template_text = best_text  # revert
            logger.info("  REVERT — fixed score {} >= original {}", fixed_score, score)
            round_entry["action"] = "revert"
            round_entry["fixed_score"] = fixed_score
            all_prior_findings.extend(findings)

        rounds_log.append(round_entry)

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

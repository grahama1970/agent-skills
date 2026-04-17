"""Active model integrity probes: NIAH (with context-length ladder), SKILL.md extraction, instruction-following.

Inputs: --model (required unless --dry-run), optional --depths for ladder sweep.
Outputs: probes.jsonl records with per-probe scores, latency_ms, and token counts.
Failure modes: scillm timeout (120s), invalid JSON from extraction probe,
               missing scillm skill directory.
"""

import json
import subprocess
import time
import typing as t
from datetime import datetime, timezone
from pathlib import Path

import typer
from loguru import logger

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = Path.home() / ".embry" / "dum-dum"

app = typer.Typer(add_completion=False)

# --- NIAH probe ---

NIAH_NEEDLE = "DUMDUM-NEEDLE-7f3a9c2e"

# Near-miss decoy needles per arXiv:2601.20276 -- semantically similar codes
# that force the model to discriminate rather than pattern-match on "DUMDUM-NEEDLE"
_DECOY_NEEDLES = [
    "DUMDUM-MARKER-7f3a9c2e",   # same suffix, different tag
    "DUMDUM-NEEDLE-8g4b0d3f",   # same prefix, different hash
    "DUMDUM-NEEDLE-7f3a9c2f",   # off-by-one in last char
    "VERIFY-NEEDLE-7f3a9c2e",   # different prefix, same hash
]

# Distractor sentence templates that embed decoy needles in plausible context
_DISTRACTOR_TEMPLATES = [
    "Note: the deprecated reference code {decoy} was used in an earlier revision but is no longer valid.",
    "The test harness previously checked for {decoy} but this was superseded in version 3.1.",
    "Internal audit log entry: validator rejected {decoy} as a stale token.",
]

# Filler paragraph (~200 tokens) used to pad context for ladder sweep
_FILLER_PARA = (
    "The onboard telemetry subsystem continuously monitors thermal sensors across "
    "all transponder modules, logging delta-T values at 10 Hz intervals into a "
    "circular buffer sized for 48 hours of autonomous operation. Ground operators "
    "retrieve snapshots via S-band command link during scheduled contact windows, "
    "typically every 90 minutes in LEO. Anomaly flags trigger immediate downlink "
    "through the UHF emergency channel regardless of orbital position, ensuring "
    "fault visibility within one orbital period. Buffer overflow protection uses a "
    "priority queue that preserves high-severity events while discarding routine "
    "housekeeping frames, maintaining at least 12 hours of critical telemetry "
    "under worst-case data rates.\n\n"
)

NIAH_CONTEXT_TEMPLATE = """You are a helpful assistant reviewing a technical document.

The following is a lengthy technical specification for a satellite communication
system. Please read it carefully.

Section 1: Overview
The system uses Ka-band frequencies for uplink and downlink communications.
Primary ground stations are located in three geographic regions to ensure
continuous coverage. The modulation scheme uses adaptive coding based on
atmospheric conditions measured by onboard sensors.

Section 2: Signal Processing
The digital signal processor operates at 2.4 GHz clock speed with a 16-bit
ADC front end. {filler_before}The hidden verification code for this document is {needle}.
{filler_after}Filter banks use polyphase decomposition for efficient channelization across
the 500 MHz bandwidth allocation.

Section 3: Error Correction
The system employs a concatenated coding scheme with an outer Reed-Solomon
code (255,223) and an inner turbo code at rate 1/3. Interleaving depth is
set to 8 frames to combat burst errors from rain fade events.

Section 4: Network Protocol
The protocol stack follows DVB-S2X with custom extensions for low-latency
handover between ground stations. The MAC layer implements demand-assigned
multiple access with a reservation period of 50ms.

Section 5: Security
All payload data is encrypted using AES-256-GCM. Key management uses an
elliptic curve Diffie-Hellman exchange with certificate-based authentication
through a dedicated security processor.

---

What is the hidden verification code mentioned in Section 2 of the document?
Reply with ONLY the code, nothing else.
"""

SKILLMD_EXTRACTION_TEMPLATE = """You are a SKILL.md parser. Extract the requested fields from this SKILL.md file.

```markdown
---
name: test-probe-skill
description: >
  A probe skill used for model integrity testing. This skill validates
  that the model can correctly extract structured frontmatter fields
  from SKILL.md format documents.
triggers:
  - "test probe"
  - "integrity check"
allowed-tools:
  - Bash
  - Read
metadata:
  short-description: Model integrity test probe
  author: Graham
  version: 2.3.1
provides:
  - test-probe
composes:
  - memory
  - taxonomy
taxonomy:
  - Detect
  - Model
---

# test-probe-skill

This skill probes model integrity by testing structured extraction.
```

Extract these fields as JSON:
1. name (string)
2. version (string, from metadata)
3. composes (array of strings)
4. taxonomy (array of strings)

Reply with ONLY valid JSON, no markdown fences, no explanation.
"""

SKILLMD_EXPECTED = {
    "name": "test-probe-skill",
    "version": "2.3.1",
    "composes": ["memory", "taxonomy"],
    "taxonomy": ["Detect", "Model"],
}

INSTRUCTION_FOLLOWING_TEMPLATE = """Follow ALL of these constraints exactly:

1. Start your response with the word "VERIFIED"
2. Include exactly 3 bullet points
3. Each bullet point must contain a number between 1 and 100
4. End your response with the word "COMPLETE"
5. Do NOT use any markdown headers (no # symbols)
6. Keep total response under 50 words

Topic: Name three prime numbers.
"""

DEFAULT_DEPTHS = [1, 4, 8, 16]


def _build_niah_prompt(depth_k: int) -> str:
    """Build NIAH prompt padded to ~depth_k*1000 tokens with adversarial distractors.

    Per arXiv:2601.20276, benign filler lets NIAH trivially saturate. We inject
    near-miss decoy needles in plausible sentences so the model must discriminate
    the real needle from semantically similar distractors.
    """
    base = NIAH_CONTEXT_TEMPLATE.format(needle=NIAH_NEEDLE, filler_before="", filler_after="")
    base_tokens = len(base.split()) * 4 // 3
    target_tokens = depth_k * 1000
    extra_needed = max(0, target_tokens - base_tokens)
    filler_tokens_per_para = max(1, len(_FILLER_PARA.split()) * 4 // 3)
    n_paragraphs = extra_needed // filler_tokens_per_para

    # Build filler blocks, injecting one distractor every ~4 paragraphs
    filler_paras: list[str] = []
    distractor_idx = 0
    for i in range(n_paragraphs):
        filler_paras.append(_FILLER_PARA)
        if (i + 1) % 4 == 0 and distractor_idx < len(_DECOY_NEEDLES):
            template = _DISTRACTOR_TEMPLATES[distractor_idx % len(_DISTRACTOR_TEMPLATES)]
            decoy_sentence = template.format(decoy=_DECOY_NEEDLES[distractor_idx])
            filler_paras.append(decoy_sentence + "\n\n")
            distractor_idx += 1

    # Split filler: needle goes in the middle
    half = len(filler_paras) // 2
    filler_before = "".join(filler_paras[:half])
    filler_after = "".join(filler_paras[half:])

    return NIAH_CONTEXT_TEMPLATE.format(
        needle=NIAH_NEEDLE,
        filler_before=filler_before,
        filler_after=filler_after,
    )


def check_niah_response(response: str) -> dict:
    """Score NIAH probe response."""
    clean = response.strip().strip('"').strip("'").strip("`")
    exact_match = clean == NIAH_NEEDLE
    contains = NIAH_NEEDLE in response
    return {
        "probe": "niah",
        "passed": exact_match,
        "partial": contains and not exact_match,
        "score": 100 if exact_match else (50 if contains else 0),
        "expected": NIAH_NEEDLE,
        "got": clean[:80],
    }


def check_skillmd_response(response: str) -> dict:
    """Score SKILL.md extraction probe response."""
    clean = response.strip()
    if clean.startswith("```"):
        lines = clean.split("\n")
        clean = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError:
        return {
            "probe": "skillmd_extraction",
            "passed": False,
            "partial": False,
            "score": 0,
            "error": "invalid JSON",
            "got": clean[:80],
        }

    correct = 0
    total = len(SKILLMD_EXPECTED)
    details = {}

    for key, expected in SKILLMD_EXPECTED.items():
        got = parsed.get(key)
        if got == expected:
            correct += 1
            details[key] = "match"
        else:
            details[key] = f"expected {expected!r}, got {got!r}"

    score = int(100 * correct / total)
    return {
        "probe": "skillmd_extraction",
        "passed": correct == total,
        "partial": 0 < correct < total,
        "score": score,
        "fields": details,
    }


def check_instruction_response(response: str) -> dict:
    """Score instruction-following probe response."""
    checks = {
        "starts_with_verified": response.strip().startswith("VERIFIED"),
        "ends_with_complete": response.strip().endswith("COMPLETE"),
        "has_3_bullets": response.count("- ") == 3 or response.count("* ") == 3,
        "no_headers": "#" not in response,
        "under_50_words": len(response.split()) < 50,
    }

    passed_count = sum(1 for v in checks.values() if v)
    total = len(checks)
    score = int(100 * passed_count / total)

    return {
        "probe": "instruction_following",
        "passed": passed_count == total,
        "partial": 0 < passed_count < total,
        "score": score,
        "checks": checks,
    }


# --- Fixture data for --dry-run ---

DRY_RUN_RESULTS = [
    {**check_niah_response(NIAH_NEEDLE), "depth_k": 1, "latency_ms": 420, "tokens": {"input": 850, "output": 12}},
    {**check_niah_response(NIAH_NEEDLE), "depth_k": 4, "latency_ms": 680, "tokens": {"input": 3800, "output": 12}},
    {**check_skillmd_response(json.dumps(SKILLMD_EXPECTED)), "latency_ms": 550, "tokens": {"input": 320, "output": 85}},
    {
        **check_instruction_response(
            "VERIFIED\n- The number 7 is prime\n- The number 13 is prime\n- The number 29 is prime\nCOMPLETE"
        ),
        "latency_ms": 390,
        "tokens": {"input": 120, "output": 42},
    },
]


def grade_results(results: list[dict]) -> dict:
    """Compute composite grade from probe results."""
    if not results:
        return {"grade": "F", "score": 0, "total_probes": 0}

    total_score = sum(r["score"] for r in results)
    avg = total_score / len(results)

    if avg >= 90:
        grade = "A"
    elif avg >= 70:
        grade = "B"
    elif avg >= 50:
        grade = "C"
    else:
        grade = "F"

    latencies = [r["latency_ms"] for r in results if "latency_ms" in r]

    return {
        "grade": grade,
        "score": round(avg, 1),
        "total_probes": len(results),
        "passed": sum(1 for r in results if r["passed"]),
        "partial": sum(1 for r in results if r.get("partial")),
        "failed": sum(1 for r in results if not r["passed"] and not r.get("partial")),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
    }


def format_report(results: list[dict], summary: dict, model: str) -> str:
    """Format probe results as a human-readable report."""
    lines = [
        "=== dum-dum probe report ===",
        f"Model:  {model}",
        f"Time:   {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"Grade:  {summary['grade']} ({summary['score']}/100)",
        f"Probes: {summary['passed']}/{summary['total_probes']} passed"
        + (f", {summary['partial']} partial" if summary["partial"] else ""),
    ]
    if summary.get("avg_latency_ms") is not None:
        lines.append(f"Avg latency: {summary['avg_latency_ms']}ms")
    lines.append("")

    for r in results:
        status = "PASS" if r["passed"] else ("PARTIAL" if r.get("partial") else "FAIL")
        depth_tag = f" @{r['depth_k']}K" if "depth_k" in r else ""
        latency_tag = f" {r['latency_ms']}ms" if "latency_ms" in r else ""
        tokens_tag = ""
        if "tokens" in r:
            tok = r["tokens"]
            tokens_tag = f" [{tok.get('input', '?')}in/{tok.get('output', '?')}out]"
        lines.append(f"  [{status}] {r['probe']:<25}{depth_tag}{latency_tag}{tokens_tag} score={r['score']}")
        if "checks" in r:
            for k, v in r["checks"].items():
                lines.append(f"         {k}: {'ok' if v else 'FAILED'}")
        if "fields" in r:
            for k, v in r["fields"].items():
                lines.append(f"         {k}: {v}")
        if "error" in r:
            lines.append(f"         error: {r['error']}")
        if "got" in r and not r["passed"]:
            lines.append(f"         got: {r['got']}")

    return "\n".join(lines)


def save_results(results: list[dict], summary: dict, model: str) -> None:
    """Append results to probes.jsonl."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "summary": summary,
        "probes": results,
    }
    outpath = DATA_DIR / "probes.jsonl"
    with open(outpath, "a") as f:
        f.write(json.dumps(record) + "\n")
    logger.info("Saved probe results to {}", outpath)


def _call_scillm(model: str, prompt: str, max_tokens: int = 200) -> dict:
    """Call scillm and return {text, latency_ms, tokens, returncode, stderr}."""
    scillm_dir = SCRIPT_DIR.parent / "scillm"
    t0 = time.monotonic()
    result = subprocess.run(
        [
            str(scillm_dir / "run.sh"),
            "query",
            "--model", model,
            "--prompt", prompt,
            "--max-tokens", str(max_tokens),
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    latency_ms = round((time.monotonic() - t0) * 1000)

    tokens: dict[str, int] = {}
    if result.returncode == 0:
        try:
            resp = json.loads(result.stdout)
            text = resp.get("text", resp.get("content", result.stdout))
            usage = resp.get("usage", {})
            tokens = {
                k: v
                for k, v in {
                    "input": usage.get("input_tokens", usage.get("prompt_tokens")),
                    "output": usage.get("output_tokens", usage.get("completion_tokens")),
                }.items()
                if v is not None
            }
        except json.JSONDecodeError:
            text = result.stdout
    else:
        text = None

    return {
        "text": text,
        "latency_ms": latency_ms,
        "tokens": tokens,
        "returncode": result.returncode,
        "stderr": result.stderr,
    }


def run_live_probes(model: str, depths: list[int]) -> list[dict]:
    """Run probes against a live model via scillm on localhost:4001."""
    results = []

    for depth_k in depths:
        logger.info("Running NIAH probe @{}K...", depth_k)
        prompt = _build_niah_prompt(depth_k)
        resp = _call_scillm(model, prompt)
        if resp["text"] is None:
            results.append({
                "probe": "niah", "depth_k": depth_k,
                "passed": False, "partial": False, "score": 0,
                "latency_ms": resp["latency_ms"], "tokens": resp["tokens"],
                "error": f"scillm error: {resp['stderr'][:200]}",
            })
        else:
            r = check_niah_response(resp["text"])
            r["depth_k"] = depth_k
            r["latency_ms"] = resp["latency_ms"]
            r["tokens"] = resp["tokens"]
            results.append(r)

    logger.info("Running SKILL.md extraction probe...")
    resp = _call_scillm(model, SKILLMD_EXTRACTION_TEMPLATE)
    if resp["text"] is None:
        results.append({
            "probe": "skillmd_extraction",
            "passed": False, "partial": False, "score": 0,
            "latency_ms": resp["latency_ms"], "tokens": resp["tokens"],
            "error": f"scillm error: {resp['stderr'][:200]}",
        })
    else:
        r = check_skillmd_response(resp["text"])
        r["latency_ms"] = resp["latency_ms"]
        r["tokens"] = resp["tokens"]
        results.append(r)

    logger.info("Running instruction-following probe...")
    resp = _call_scillm(model, INSTRUCTION_FOLLOWING_TEMPLATE)
    if resp["text"] is None:
        results.append({
            "probe": "instruction_following",
            "passed": False, "partial": False, "score": 0,
            "latency_ms": resp["latency_ms"], "tokens": resp["tokens"],
            "error": f"scillm error: {resp['stderr'][:200]}",
        })
    else:
        r = check_instruction_response(resp["text"])
        r["latency_ms"] = resp["latency_ms"]
        r["tokens"] = resp["tokens"]
        results.append(r)

    return results


@app.command()
def main(
    model: t.Annotated[str, typer.Option(help="Model to probe via scillm")] = "dry-run-fixture",
    dry_run: t.Annotated[bool, typer.Option("--dry-run", help="Use fixture data, no LLM calls")] = False,
    json_out: t.Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    depths: t.Annotated[t.Optional[str], typer.Option(help="NIAH ladder depths in K tokens, comma-separated")] = None,
) -> None:
    """Run active model integrity probes."""
    depth_list = DEFAULT_DEPTHS
    if depths:
        depth_list = [int(d.strip()) for d in depths.split(",")]

    if dry_run:
        results = DRY_RUN_RESULTS
        model = "dry-run-fixture"
    else:
        if model == "dry-run-fixture":
            logger.error("--model is required for live probes (or use --dry-run)")
            raise typer.Exit(code=1)
        results = run_live_probes(model, depth_list)

    summary = grade_results(results)
    save_results(results, summary, model)

    if json_out:
        print(json.dumps({"model": model, "summary": summary, "probes": results}, indent=2))
    else:
        print(format_report(results, summary, model))


if __name__ == "__main__":
    app()

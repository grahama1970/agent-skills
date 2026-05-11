"""Review-skill dispatch inside the /ask webgpt oracle.

When `/ask` parses a question like

  $ask webgpt /review-code our recent code changes over 2 iteration rounds

it routes here. This module:
  * builds a review-type-specific prompt (code | design | prompt | plan)
  * resolves the review target (e.g. a git diff scope) optionally with help
    from /interview when the description is ambiguous
  * issues N rounds against the controlled ChatGPT tab via webgpt_runtime,
    parsing the verdict JSON between rounds and emitting content-aware
    follow-up prompts when the verdict is not yet SAFE
  * returns a deterministic verdict dict for /ask to surface as the answer

Each round's artifact directory is recorded; round 1 is the bundle, rounds
2..N are content-aware refinements that reference ChatGPT's prior verdict.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .webgpt_runtime import call_webgpt


REVIEW_TYPES = {"code", "design", "prompt", "plan"}
VALID_VERDICTS = {"SAFE", "SAFE_WITH_CONDITIONS", "NOT_SAFE", "INSUFFICIENT_EVIDENCE"}

_VERDICT_RE = re.compile(
    r"(?im)^\s*(?:VERDICT|FINAL_VERDICT|SAFETY_VERDICT)\s*:\s*"
    r"(SAFE_WITH_CONDITIONS|INSUFFICIENT_EVIDENCE|NOT_SAFE|SAFE)\b"
)

_ROUNDS_RE = re.compile(
    r"\b(?:over\s+|in\s+|with\s+|across\s+)?(\d+)\s+(?:iteration\s+)?rounds?\b",
    re.IGNORECASE,
)


SYSTEM_PREAMBLES = {
    "code": (
        "You are a senior code reviewer. Return a strict JSON object only "
        "with this shape (no prose before or after):\n"
        "{\"verdict\":\"SAFE|SAFE_WITH_CONDITIONS|NOT_SAFE|INSUFFICIENT_EVIDENCE\","
        "\"blocking_findings\":[{\"id\":\"\",\"file\":\"\",\"lines\":\"\",\"summary\":\"\"}],"
        "\"conditions\":[],\"non_blocking_findings\":[],\"notes\":[]}\n"
        "SAFE only when the diff has no merge-blocking issues. SAFE_WITH_CONDITIONS only "
        "when every condition maps to a deterministic gate or explicit human-accepted risk. "
        "NOT_SAFE for any merge-blocking correctness, security, regression, contract, or "
        "test-coverage issue. INSUFFICIENT_EVIDENCE when the diff or context is incomplete."
    ),
    "design": (
        "You are a senior design reviewer. Return a strict JSON object only "
        "with this shape (no prose before or after):\n"
        "{\"verdict\":\"SAFE|SAFE_WITH_CONDITIONS|NOT_SAFE|INSUFFICIENT_EVIDENCE\","
        "\"blocking_findings\":[],\"conditions\":[],\"non_blocking_findings\":[],\"notes\":[]}"
        "\n"
        "Judge layout, hierarchy, workflow fit, and evidence clarity. Flag dashboard-theater "
        "and hide-failure patterns as NOT_SAFE."
    ),
    "prompt": (
        "You are a senior prompt-contract reviewer. Return a strict JSON object only:\n"
        "{\"verdict\":\"SAFE|SAFE_WITH_CONDITIONS|NOT_SAFE|INSUFFICIENT_EVIDENCE\","
        "\"blocking_findings\":[],\"conditions\":[],\"non_blocking_findings\":[],\"notes\":[]}\n"
        "Judge whether the prompt contract is ready: payloads, validators, expected outputs, "
        "evidence, and consumer-contract issues."
    ),
    "plan": (
        "You are a senior implementation-plan reviewer. Return a strict JSON object only:\n"
        "{\"verdict\":\"SAFE|SAFE_WITH_CONDITIONS|NOT_SAFE|INSUFFICIENT_EVIDENCE\","
        "\"blocking_findings\":[],\"conditions\":[],\"non_blocking_findings\":[],\"notes\":[]}\n"
        "Judge whether the plan is safe to execute as written. Flag missing test gates, "
        "implicit destructive operations, and untested rollback paths as NOT_SAFE."
    ),
}


@dataclass
class WebgptReviewRequest:
    review_type: str
    description: str
    diff_scope: str = ""
    diff_text: str = ""
    file_paths: list[str] = field(default_factory=list)
    max_rounds: int = 1
    tab_id: str = ""
    url: str = ""
    project: str = ""
    create_tab: bool = False
    timeout: float = 900.0
    persona: str = ""


@dataclass
class RoundResult:
    round_num: int
    prompt: str
    response: str
    verdict: Optional[str]
    verdict_data: dict
    raw_contains_sentinel: bool
    artifact_dir: str
    took_ms: int


@dataclass
class WebgptReviewResult:
    review_type: str
    final_verdict: Optional[str]
    final_verdict_data: dict
    rounds: list[RoundResult]
    halt_reason: str  # "safe" | "rounds_exhausted" | "error"
    controlled_tab_id: str
    project: str = ""


def parse_rounds(text: str, default: int = 1) -> int:
    """Pull `N rounds` / `over N iteration rounds` from free-form text."""
    if not text:
        return default
    m = _ROUNDS_RE.search(text)
    if not m:
        return default
    try:
        n = int(m.group(1))
    except (TypeError, ValueError):
        return default
    return max(1, min(10, n))


_JSON_VERDICT_RE = re.compile(
    r'"(?:verdict|final_verdict|safety_verdict)"\s*:\s*"'
    r'(SAFE_WITH_CONDITIONS|INSUFFICIENT_EVIDENCE|NOT_SAFE|SAFE)"',
    re.IGNORECASE,
)


def extract_verdict(response: str) -> tuple[Optional[str], dict]:
    """Find the verdict JSON in a webgpt response.

    Robustness layers:
      1. Try strict json.loads on the outer {...}. Returns the parsed dict
         when valid.
      2. If json.loads fails (ChatGPT sometimes embeds raw newlines inside
         JSON string fields, which is technically invalid), fall back to a
         regex that matches `"verdict":"VALUE"` so we still surface the
         verdict label even when the rest of the JSON is unparseable.
      3. If even that fails, fall back to plain-text `VERDICT: VALUE`.
    """
    if not response:
        return None, {}
    json_match = re.search(r"\{[\s\S]*\}", response)
    if json_match:
        try:
            data = json.loads(json_match.group(0))
            v = data.get("verdict") or data.get("final_verdict") or data.get("safety_verdict")
            if isinstance(v, str):
                normalised = v.strip().upper()
                if normalised in VALID_VERDICTS:
                    return normalised, data
            return None, data
        except json.JSONDecodeError:
            # Try once more with newlines escaped inside JSON-string regions.
            # ChatGPT occasionally embeds raw \n in string fields; this is
            # technically invalid JSON but trivially recoverable.
            try:
                cleaned = re.sub(
                    r'("(?:[^"\\]|\\.)*?)\n+(.*?")',
                    lambda m: m.group(1) + " " + m.group(2),
                    json_match.group(0),
                    flags=re.DOTALL,
                )
                data = json.loads(cleaned)
                v = data.get("verdict") or data.get("final_verdict") or data.get("safety_verdict")
                if isinstance(v, str):
                    normalised = v.strip().upper()
                    if normalised in VALID_VERDICTS:
                        return normalised, data
                return None, data
            except Exception:
                pass
    # Last-ditch: pull just the verdict label out via regex, return without data.
    m = _JSON_VERDICT_RE.search(response)
    if m:
        return m.group(1).upper(), {}
    m = _VERDICT_RE.search(response)
    return (m.group(1).upper() if m else None), {}


def resolve_diff(diff_scope: str, *, cwd: Path | None = None) -> str:
    """Run `git diff <scope>` to a single string. Best-effort; returns "" on error."""
    if not diff_scope:
        return ""
    cwd = cwd or Path.cwd()
    parts = ["git", "diff", "--no-color"]
    parts.extend(diff_scope.split())
    try:
        proc = subprocess.run(parts, cwd=cwd, capture_output=True, text=True, timeout=30)
    except Exception:
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout


def build_round1_prompt(req: WebgptReviewRequest) -> str:
    """First-round prompt: review request + bundled context."""
    parts: list[str] = []
    parts.append(SYSTEM_PREAMBLES.get(req.review_type, SYSTEM_PREAMBLES["code"]))
    parts.append("")
    parts.append(f"## Review request ({req.review_type})")
    parts.append("")
    parts.append(req.description.strip() if req.description else "(no description)")
    if req.diff_scope:
        parts.append("")
        parts.append(f"## Diff scope: `{req.diff_scope}`")
    # Diff is NOT inlined in the prompt body any more — it lives in a
    # separately-attached markdown bundle (`build_review_bundle` writes it
    # to disk and the runtime passes --attach-file). The prompt body just
    # references the attachment so ChatGPT knows where to find it.
    if req.diff_text:
        parts.append("")
        parts.append(
            "## Diff (attached as a Markdown file)"
        )
        parts.append("")
        parts.append(
            "The full diff is in the attached file. Read it carefully. The "
            "diff block inside the attachment is what you must review."
        )
    if req.file_paths:
        parts.append("")
        parts.append("## Files referenced")
        for fp in req.file_paths:
            parts.append(f"- {fp}")
    parts.append("")
    parts.append("Respond with the JSON object only.")
    return "\n".join(parts) + "\n"


def build_followup_prompt(prior: RoundResult, round_num: int, total: int) -> str:
    """Content-aware refinement prompt for round N (N>=2).

    References the prior verdict's blocking_findings / conditions and asks
    ChatGPT to point to specific file:line or downgrade the finding.
    """
    blocking = prior.verdict_data.get("blocking_findings", []) or []
    conditions = prior.verdict_data.get("conditions", []) or []
    parts = [
        f"Iteration {round_num}/{total} on the same review.",
        f"Your previous verdict was: {prior.verdict or 'UNPARSEABLE'}.",
        "",
    ]
    if blocking:
        parts.append("You flagged these blocking findings:")
        for i, f in enumerate(blocking, 1):
            summary = f.get("summary") if isinstance(f, dict) else str(f)
            loc = ""
            if isinstance(f, dict):
                loc = f.get("file") or ""
                if f.get("lines"):
                    loc = f"{loc}:{f['lines']}" if loc else str(f["lines"])
            parts.append(f"  {i}. {summary}" + (f"  [{loc}]" if loc else ""))
        parts.append("")
        parts.append(
            "For each blocking finding, either point to a specific file:line "
            "in the diff or downgrade it to non_blocking. Then re-issue the "
            "verdict JSON."
        )
    elif conditions:
        parts.append("You flagged these conditions:")
        for i, c in enumerate(conditions, 1):
            parts.append(f"  {i}. {c if isinstance(c, str) else json.dumps(c)}")
        parts.append("")
        parts.append(
            "For each condition, state whether it maps to a deterministic gate "
            "in the diff or to explicit human-accepted residual risk. Then "
            "re-issue the verdict JSON."
        )
    else:
        parts.append(
            "Your verdict had no blocking findings or conditions but was not SAFE. "
            "Either escalate a real merge-blocking issue or upgrade the verdict to "
            "SAFE. Re-issue the verdict JSON."
        )
    parts.append("")
    parts.append("Respond with the JSON object only.")
    return "\n".join(parts) + "\n"


def build_review_bundle_file(req: WebgptReviewRequest) -> Optional[Path]:
    """Write the diff + file context to a markdown bundle file on disk.

    Returned path is passed to `surf chatgpt --file` as an attachment so
    ChatGPT reads it alongside the (small) prompt body. This sidesteps the
    OS argv limit that would otherwise truncate a large diff inlined in the
    prompt itself.

    Returns None when there is nothing big enough to warrant a bundle (no
    diff + no files); in that case the runtime falls back to the inline
    prompt path with no attachment.
    """
    if not req.diff_text and not req.file_paths:
        return None
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(tempfile.mkdtemp(prefix=f"webgpt-review-{req.review_type}-{ts}-"))
    bundle_path = out / f"review-bundle-{req.review_type}.md"
    parts: list[str] = [
        f"# WebGPT review bundle ({req.review_type})",
        "",
        f"_Generated {ts}._",
        "",
    ]
    if req.description:
        parts.append(f"**Review request:** {req.description}")
        parts.append("")
    if req.diff_scope:
        parts.append(f"**Diff scope:** `{req.diff_scope}`")
        parts.append("")
    if req.diff_text:
        parts.append("## Diff")
        parts.append("")
        parts.append("```diff")
        parts.append(req.diff_text.strip())
        parts.append("```")
        parts.append("")
    if req.file_paths:
        parts.append("## Files referenced")
        for fp in req.file_paths:
            parts.append(f"- `{fp}`")
        parts.append("")
    bundle_path.write_text("\n".join(parts).rstrip() + "\n")
    return bundle_path


def run_webgpt_review(
    req: WebgptReviewRequest,
    *,
    run_state: object | None = None,
) -> WebgptReviewResult:
    """Drive the multi-round ping-pong review loop on the controlled tab."""
    rounds: list[RoundResult] = []
    halt_reason = "rounds_exhausted"
    controlled_tab_id = req.tab_id

    # Build the attachment bundle once. ChatGPT remembers the file across
    # the conversation, so we only attach in round 1; refinement rounds are
    # plain-text follow-ups that reference "the attached bundle".
    bundle_path = build_review_bundle_file(req)

    for n in range(1, req.max_rounds + 1):
        if n == 1:
            prompt = build_round1_prompt(req)
        else:
            prompt = build_followup_prompt(rounds[-1], n, req.max_rounds)
        result = call_webgpt(
            prompt,
            tab_id=req.tab_id,
            url=req.url,
            create_tab=req.create_tab and n == 1,
            project=req.project,
            attach_file=str(bundle_path) if (bundle_path and n == 1) else "",
            timeout=req.timeout,
            no_activate=True,
            run_state=run_state,
            iteration=n,
            persona=req.persona or None,
        )
        # Lock the controlled tab once known so later rounds reuse it.
        if not req.tab_id and result.controlled_tab_id:
            req.tab_id = result.controlled_tab_id
        controlled_tab_id = result.controlled_tab_id or controlled_tab_id

        verdict, verdict_data = extract_verdict(result.response)
        rounds.append(
            RoundResult(
                round_num=n,
                prompt=prompt,
                response=result.response,
                verdict=verdict,
                verdict_data=verdict_data,
                raw_contains_sentinel=result.raw_contains_sentinel,
                artifact_dir=str(result.artifact_dir),
                took_ms=result.took_ms,
            )
        )
        if verdict == "SAFE":
            halt_reason = "safe"
            break

    last = rounds[-1] if rounds else None
    return WebgptReviewResult(
        review_type=req.review_type,
        final_verdict=last.verdict if last else None,
        final_verdict_data=last.verdict_data if last else {},
        rounds=rounds,
        halt_reason=halt_reason,
        controlled_tab_id=controlled_tab_id,
        project=req.project,
    )

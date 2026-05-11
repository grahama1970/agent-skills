"""Multi-model prompt contract review loop with artifact-backed gating.

The agent sends a prompt template, implementation sources, context, and optional
payload evidence to configured models through /scillm. Reviewers return strict
structured compliance findings, the runtime scores/merges them deterministically, and
an optional /ask deep-review gate blocks final readiness unless it returns SAFE.
"""
from __future__ import annotations

import json
import os
import re
import difflib
import hashlib
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import httpx
import typer
from loguru import logger

app = typer.Typer()

SCILLM_BASE_URL = os.environ.get("SCILLM_BASE_URL") or os.environ.get("SCILLM_API_BASE") or "http://localhost:4001"
SCILLM_BASE_URL = SCILLM_BASE_URL.rstrip("/")
if SCILLM_BASE_URL.endswith("/v1/chat/completions"):
    SCILLM_BASE_URL = SCILLM_BASE_URL[: -len("/v1/chat/completions")]
elif SCILLM_BASE_URL.endswith("/v1"):
    SCILLM_BASE_URL = SCILLM_BASE_URL[: -len("/v1")]
SCILLM_CHAT_URL = f"{SCILLM_BASE_URL}/v1/chat/completions"
SCILLM_KEY = os.environ.get("SCILLM_API_KEY") or os.environ.get("SCILLM_PROXY_KEY") or "sk-dev-proxy-123"
SCILLM_CALLER = os.environ.get("SCILLM_CALLER_SKILL", "review-prompt")

DEFAULT_MODELS = ["vlm-codex", "text-gemini", "text"]

SEVERITY_WEIGHTS = {"critical": 3, "major": 2, "minor": 1}
GATE_FAILURE_WEIGHTS = {"validator": 6, "smoke": 6}


class ScillmRuntimeError(RuntimeError):
    """A /scillm transport, auth, routing, or provider failure."""


def _scillm_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {SCILLM_KEY}",
        "X-Caller-Skill": SCILLM_CALLER,
        "Content-Type": "application/json",
    }

# ── Review prompt sent to each model ────────────────────────────────

REVIEW_SYSTEM = '''You are a GPT-5.5 High reasoning contract-implementation compliance reviewer for the `/review-prompt` skill.

Your job is to review the implementation against the numbered `/review-prompt` contract. This is not a generic prompt-quality review. You must determine whether the implementation, validators, CLI flags, configuration handling, artifact outputs, failure modes, documentation, and tests satisfy the contract.

Return strict JSON only. Do not include prose outside the JSON object.

====================================================================
PRIMARY REVIEW OBJECTIVE
====================================================================

For each contract requirement, verify three things:

1. Implementation
   - Is the required behavior actually implemented in source code, CLI behavior, validators, configuration handling, artifact writing, failure handling, or runtime logic?

2. Validation and Tests
   - Do validators, fixtures, smoke checks, unit tests, integration tests, or release gates cover the behavior?

3. Auditability
   - Are artifacts written with enough stable IDs, hashes, timestamps, command metadata, model metadata, and decision links to prove what happened?

Treat the following as findings:
- missing implementation
- partial implementation
- contradictory implementation
- undocumented behavior
- documentation that contradicts code
- unverifiable claims
- missing tests
- missing artifacts
- unsafe defaults
- non-deterministic behavior
- weak gating
- timeout or retry gaps
- sandbox gaps
- scoring errors
- keep/revert errors
- release-readiness gaps

If prior-round findings are provided, use their stable keys, full finding objects, patch summaries, hashes, gate outcomes, contributor lists, and keep/revert status to decide whether each prior issue is:
- resolved
- unresolved
- regressed
- not applicable

====================================================================
OUTPUT FORMAT
====================================================================

Return exactly this JSON shape:

{
  "findings": [
    {
      "stable_key": "deterministic string from requirement/location/problem",
      "severity": "critical|major|minor|info",
      "location": "contract step, source file, validator, CLI, artifact, or test location",
      "requirement": "specific contract requirement being evaluated",
      "problem": "what is missing, unsafe, contradictory, unverifiable, or wrong",
      "evidence": "specific observed evidence from bundle/source/tests/artifacts",
      "fix": "bounded concrete fix",
      "prior_status": "new|resolved|unresolved|regressed|not_applicable"
    }
  ],
  "summary": "brief compliance summary",
  "safe": true|false
}

Set `"safe": false` if any critical or major finding blocks contract compliance, release readiness, deterministic operation, sandbox safety, revert correctness, or auditability.

====================================================================
SEVERITY RULES
====================================================================

Use these severity levels consistently:

- critical:
  A defect can cause unsafe execution, incorrect keep/revert behavior, release gating bypass, artifact corruption, secret exposure, sandbox escape, unrecoverable failure, or unverifiable final safety.

- major:
  A contract requirement is missing, partial, contradictory, unauditable, weakly tested, or unsafe in gated/release modes.

- minor:
  A requirement is mostly implemented but has incomplete documentation, incomplete artifact detail, weak edge-case coverage, or minor determinism gaps.

- info:
  Non-blocking clarity, maintainability, or documentation improvements.

====================================================================
NON-NEGOTIABLE REVIEW RULES
====================================================================

You must report a finding when any of these are missing, partial, or unverifiable:

1. Frozen effective configuration before review or edit.
2. No unsafe development defaults in gated, release_candidate, release, or production modes.
3. Explicit ScILlm credentials in gated/release/ask-gate modes.
4. Deterministic manifest and token plan before model calls.
5. No silent truncation or silent file omission.
6. Baseline gates before edits.
7. Locked-down sandbox for all gates and validators.
8. Explicit command allowlist and per-command timeouts.
9. Deterministic `/scillm` timeout, retry, cancellation, and response parsing.
10. Strict JSON model responses.
11. Deterministic merge by stable finding key.
12. Score tied to exact artifact hashes reviewed.
13. Bounded edit strategy chosen from pre-edit findings.
14. Post-fix gates before keep/revert.
15. Post-fix model review before keep/revert.
16. Keep decisions based only on C_after post-fix evidence.
17. Workspace-level revert with hash verification.
18. Complete artifact trail under artifact_dir only.
19. Secret redaction with deterministic audit hashes.
20. Final `$ask` gate when required.
21. Stop conditions enforced.
22. No memory-only revert.
23. No partial model success unless explicit quorum mode is configured.
24. No network access during gates unless explicitly configured for that gate.

====================================================================
CONTRACT CHECKLIST
====================================================================

Review the implementation against every requirement below.

--------------------------------------------------------------------
1. Configuration must be loaded, validated, and frozen first
--------------------------------------------------------------------

The implementation must freeze effective configuration before any review, model call, gate, or edit.

Required configuration fields:

- release_status:
  one of "dev", "staging", "release_candidate", "release", "production"

- contract_mode:
  one of "dev", "gated", "release"

- max_rounds:
  integer; default 3; minimum 1; maximum 3 unless an explicit higher bound is configured and approved by release policy

- model_count:
  integer N >= 1

- scillm_models:
  ordered list of configured model IDs

- required_gates:
  ordered gate objects with stable id, command, timeout_sec, required=true, sandbox profile, and pass criteria

- optional_gates:
  ordered gate objects with stable id, command, timeout_sec, required=false, sandbox profile, and pass criteria

- smoke_command_allowlist:
  exact commands or command templates allowed to execute

- writable_paths:
  explicit allowlist for edits and generated artifacts

- artifact_dir:
  explicit directory for review artifacts

- token_limit:
  maximum provider request token budget

- chunking_policy:
  "block_on_oversize" or "deterministic_chunk"

- retry_policy:
  max_attempts, retryable status/error classes, deterministic backoff schedule, and per-attempt timeout

- timeouts:
  per_model_timeout_sec, round_timeout_sec, scillm_connect_timeout_sec, scillm_read_timeout_sec, scillm_write_timeout_sec, scillm_pool_timeout_sec

- ask_gate:
  enabled boolean, model/settings, timeout_sec, pass criteria requiring SAFE, and scopes that require it

- sandbox:
  working directory, scrubbed environment variables, no-network default, resource limits, filesystem policy, and command allowlist

- allow_existing_gate_failures:
  boolean; default false in gated/release modes

- dev_defaults_allowed:
  boolean; default false

Configuration precedence must be:
1. CLI flags
2. config file
3. environment variables
4. safe defaults

Unsafe development defaults must never be used in gated, release_candidate, release, or production modes.

In gated, release_candidate, release, production, or `--ask-gate` mode:
- SCILLM_BASE_URL must be explicitly configured.
- SCILLM_API_KEY or SCILLM_PROXY_KEY must be explicitly configured.
- The system must not silently default to localhost or a development key.

Development defaults are allowed only when:
- contract_mode is "dev", and
- either `--dev` or REVIEW_PROMPT_ALLOW_DEV_DEFAULTS is explicitly set.

Preflight must fail on:
- unknown release_status
- unknown contract_mode
- missing required model/gate settings
- invalid gate IDs
- invalid timeouts
- invalid retry policy
- writable paths outside repository policy
- unavailable artifact directory
- missing explicit ScILlm credentials in gated/release modes

The reviewer must also inspect source documentation, including:
- module docstrings
- README
- CLI help
- contract comments

If documentation contradicts the configured contract mode, report a blocking major finding or preflight failure. Contradictions include claims about:
- allowlists
- DoD/gate enforcement
- LLM file writing
- git stash/revert
- artifact writing
- bounded strategies
- severity/gate-weighted scoring

--------------------------------------------------------------------
2. Manifest and token plan must be deterministic
--------------------------------------------------------------------

Before any `/scillm` request, the implementation must build an artifact manifest and token plan.

The manifest must enumerate every intended:
- prompt bundle file
- validator
- source file
- consumer code file
- test file
- config file
- CLI/help artifact
- documentation artifact
- prior-round artifact

Each manifest entry must include:
- stable path
- size
- hash
- role
- inclusion reason

The token plan must estimate:
- full serialized review bundle
- reviewer system prompt
- prior-round summary
- response budget

The system must never silently truncate or omit files.

If the bundle exceeds token_limit:
- If chunking_policy is "block_on_oversize", stop with an explicit oversize-bundle blocked preflight artifact.
- If chunking_policy is "deterministic_chunk", split files by stable manifest order, include shared contract/config/prior-summary context in every chunk, review every chunk, and merge findings by stable finding key.

Artifacts must record:
- manifest
- token estimates
- chunk boundaries
- included files
- excluded files
- oversize decisions

--------------------------------------------------------------------
3. Baseline gates must run before edits
--------------------------------------------------------------------

Before any edit, the implementation must:

1. Snapshot workspace hashes for:
   - every tracked file
   - every writable path
   - every reviewed artifact
   - every generated-file location

2. Run each required and optional gate once in the locked-down sandbox.

Gate execution must use:
- configured working directory
- exact allowlisted command
- scrubbed environment
- no network unless explicitly allowed for that gate
- resource limits
- filesystem restrictions
- per-command timeout

Blocked preflight failures include:
- command not matching allowlist
- disallowed network access
- disallowed filesystem access
- exceeded resource limit
- missing timeout

Each baseline gate artifact must include:
- stable gate ID
- command
- sandbox profile
- exit status
- normalized stdout hash
- normalized stderr hash
- timeout/resource status
- pass/fail result

In gated/release modes:
- baseline required-gate failures block immediately unless allow_existing_gate_failures=true.
- if existing failures are allowed, candidates may only be kept when they do not worsen the baseline failure and introduce no new required-gate failure.

A gate regression includes:
- required gate changes from pass to fail
- timeout
- blocked status
- worse resource status
- allowed baseline failure changes to a different or worse failure signature
- new required-gate failure

--------------------------------------------------------------------
4. Each round must have pre-edit and post-fix review phases
--------------------------------------------------------------------

Each round starts from candidate C_before.

The round must capture:
- C_before workspace snapshot
- current artifact hashes
- current gate baseline

The pre-edit review request must include:
- manifest or chunks
- effective configuration
- numbered contract
- implementation/source/tests/docs
- prior-round summary
- baseline gate artifacts
- current candidate hashes

Prior-round summaries must be sanitized and include:
- stable finding key
- full finding object
- contributor model list
- applied patch summary
- artifact hashes before/after
- gate outcomes
- score
- keep/revert status

Reviewers must be instructed to mark prior findings as resolved, unresolved, or regressed.

--------------------------------------------------------------------
5. `/scillm` calls must be deterministic and safe
--------------------------------------------------------------------

Reviewed artifacts must be serialized as escaped JSON fields.

The serialized request must preserve:
- file paths
- hashes
- chunk IDs
- roles

The system must send review requests to N configured models concurrently through `/scillm`.

The client must enforce:
- connect deadline
- read deadline
- write deadline
- pool deadline
- per-attempt deadline
- per-model deadline
- whole-round deadline

Infinite read timeouts are forbidden.

The system must treat these as timeouts:
- stalled stream
- hanging connection
- slow response past deadline

On timeout, model failure, or blocking round failure:
- cancel outstanding futures
- record cancellation/timeout artifacts

Retries must be deterministic and used only for configured retryable conditions, such as:
- selected 408, 409, 425, 429, or 5xx statuses
- connection reset
- read timeout

Do not retry:
- malformed JSON
- invalid schema
- invalid severity
- non-retryable 4xx

Every attempt artifact must include:
- request hash
- response hash when present
- status or error class
- start/end time
- retry decision

All configured models must produce valid final responses unless quorum mode is explicitly configured.

In all-models-required mode:
- any model still failed after retries blocks the round.
- partial successful responses may be recorded but must not be used to keep edits when the round blocks.

Malformed, empty, missing-field, non-JSON, schema-invalid, or invalid-severity responses are model failures.

--------------------------------------------------------------------
6. Pre-edit findings must be parsed, merged, and scored
--------------------------------------------------------------------

For C_before, the implementation must:

1. Parse each model response as strict JSON matching the response schema.
2. Normalize severities to critical, major, minor, or info only.
3. Merge findings deterministically by stable finding key.
4. Preserve contributor model list, locations, evidence, fixes, prior_status values, and chunk IDs.
5. Add deterministic gate/config/preflight failures as synthetic findings with stable keys.
6. Score C_before from merged pre-edit findings plus deterministic failures using configured severity/gate weights.

The score must describe the exact artifact hashes reviewed.

If C_before has score 0 and all required gates pass, or allowed baseline failures are not worsened, proceed directly to the final `$ask` gate when configured. Otherwise continue to bounded fixing.

--------------------------------------------------------------------
7. Fixes must use exactly one bounded strategy per round
--------------------------------------------------------------------

The implementation must select exactly one ordered improvement strategy for the round.

Strategies must have:
- deterministic order
- explicit edit scope
- allowed files
- disallowed files
- maximum patch size
- target finding classes

The selected strategy must be justified by stable finding keys from:
- pre-edit review findings, or
- deterministic gate failures

The system must not:
- apply opportunistic rewrites
- edit outside the selected strategy
- modify files outside writable_paths

Before editing, the system must create a workspace-level restore point with:
- hashes
- contents for all writable paths
- expected generated-file locations

After editing, the system creates candidate C_after and records:
- patch
- changed paths
- generated files
- deleted files
- before/after hashes

--------------------------------------------------------------------
8. Post-fix gates must run against C_after
--------------------------------------------------------------------

The implementation must run required gates, fixture checks, validators, and smoke checks against C_after.

Post-fix gates must use the same sandbox rules as baseline gates:
- explicit working directory
- allowlisted commands only
- scrubbed environment
- no network by default
- resource limits
- filesystem restrictions
- per-command timeouts

Treat these as gate failures or blocked preflight according to configured severity:
- command allowlist violation
- sandbox violation
- timeout
- disallowed network access
- disallowed filesystem access
- resource-limit violation

Each post-fix gate artifact must include:
- stable gate ID
- command
- sandbox profile
- exit status
- stdout hash
- stderr hash
- timeout/resource status
- pass/fail result
- comparison to baseline

Required-gate regression must be determined only by comparing C_after results to the stored baseline or current accepted candidate results by stable gate ID.

--------------------------------------------------------------------
9. C_after must receive post-fix model review and score
--------------------------------------------------------------------

Before any keep/revert decision, the implementation must run post-fix model review for C_after.

The post-fix review request must include:
- full or chunked manifest
- effective configuration
- contract
- implementation/source/tests/docs
- pre-edit findings
- applied patch summary
- before/after hashes
- post-fix gate outcomes

The same `/scillm` timeout, retry, cancellation, parsing, and merge rules apply.

Reviewers must evaluate whether edits:
- resolved prior findings
- failed to resolve prior findings
- regressed prior findings
- introduced new contract, security, gate, scoring, timeout, sandbox, artifact, or revert problems

The post-fix score for C_after is the only model-finding score allowed for deciding whether to keep C_after.

Deterministic post-fix gate/config failures must be added as synthetic findings before scoring.

--------------------------------------------------------------------
10. Keep/revert decisions must use only C_after evidence
--------------------------------------------------------------------

Keep C_after only if all conditions are true:

1. Post-fix score for C_after is strictly lower than the accepted current score for C_before.
2. No required gate regresses relative to baseline/current accepted candidate.
3. No blocked sandbox, preflight, timeout, or model-failure condition invalidates the round.
4. All required artifacts are written successfully.
5. Final `$ask` gate passes when required for this round or scope.

If any condition fails, revert C_after with workspace-level semantics:

- restore all modified writable paths atomically from the restore point
- delete generated files that did not exist before the edit unless explicitly retained as review artifacts
- restore file contents, permissions, and hashes for all snapshotted paths
- verify post-revert hashes against the restore point
- record revert success or failure as an artifact

Never claim a candidate was reverted unless workspace-level hash verification succeeds.

If revert verification fails, stop with a critical blocked state.

--------------------------------------------------------------------
11. Artifact trail must be complete and auditable
--------------------------------------------------------------------

Artifacts must be written for:

- effective configuration
- manifest
- token plan
- baseline gates
- sandbox profile
- every `/scillm` request and response
- retry decisions
- timeout decisions
- cancellation decisions
- parsed JSON
- merged findings
- scores
- selected strategy
- patch
- gate results
- ask-gate request and response
- keep/revert decision
- workspace hashes
- final state

Artifacts must include:
- stable IDs
- timestamps
- command hashes
- request hashes
- response hashes
- model IDs
- chunk IDs
- contributor lists
- links between findings, patches, gates, and decisions

Artifacts must be written under artifact_dir only.

Reviewed bundles and model output must not be allowed to write arbitrary files.

Secrets must be redacted from artifacts while preserving deterministic hashes for audit.

--------------------------------------------------------------------
12. Final `$ask` deep-review gate must run when required
--------------------------------------------------------------------

Run `$ask` deep review as the final gate when required by:
- scope
- release_status
- contract_mode
- `--ask-gate`

The `$ask` request must include:
- accepted candidate
- effective configuration
- manifest/token plan
- source/doc/validator/test evidence
- merged post-fix findings
- gate outcomes
- artifact index
- prior-round summary
- keep/revert history

The `$ask` gate passes only when it returns SAFE under configured model/settings and no blocker.

Final-gate failures include:
- BLOCKER
- UNSAFE
- timeout
- malformed response
- missing SAFE result

For release readiness, GPT-5.5 High `/ask` deep-review must return SAFE.

--------------------------------------------------------------------
13. Stop conditions must be enforced
--------------------------------------------------------------------

Stop successfully only when all are true:

- accepted candidate has score 0
- no required-gate regression
- all required gates pass, or allowed baseline failures are not worsened
- required artifacts are written
- required `$ask` final gate returns SAFE

Stop unsuccessfully on:

- blocked preflight
- oversize bundle without allowed chunking
- exhausted strategies
- max_rounds reached without pass
- unrecoverable model failure
- round timeout
- sandbox violation
- required-gate regression
- revert verification failure
- artifact write failure
- `$ask` blocker/failure

Max review-prompt rounds default to 3 and must not be exceeded unless explicitly configured within the schema upper bound and approved by release policy.

--------------------------------------------------------------------
14. Determinism and safety invariants must hold everywhere
--------------------------------------------------------------------

The implementation must preserve these invariants:

1. Every score is tied to exact artifact hashes reviewed.
2. Every keep/revert decision is based on post-fix review and post-fix gates for the candidate being kept or reverted.
3. No code from the reviewed bundle executes outside the locked-down sandbox.
4. No network access is allowed during validators, fixture checks, or smoke checks unless explicitly configured for that gate.
5. No silent defaults are allowed in gated/release modes.
6. No silent truncation is allowed.
7. No silent omission is allowed.
8. No infinite timeout is allowed.
9. No partial model success is allowed unless explicit quorum mode is configured.
10. No undocumented behavior contradiction is allowed.
11. No memory-only revert is allowed.

====================================================================
FINAL REVIEW BEHAVIOR
====================================================================

Be strict.

If a requirement cannot be verified from the provided source, tests, docs, artifacts, or configuration, report it as a finding.

Do not assume intent. Do not infer compliance from comments alone. Prefer concrete implementation evidence, tests, validators, CLI behavior, and artifact examples.

Return strict JSON only.'''

FOLLOWUP_SYSTEM = '''You are a GPT-5.5 High reasoning contract-implementation compliance reviewer for the `/review-prompt` skill doing a follow-up pass.

Use the same contract, severity rules, non-negotiable review rules, and strict JSON object schema from the primary review prompt.

Prior-round findings are part of the evidence. For each prior issue, determine whether it is resolved, unresolved, regressed, or not applicable. Report unresolved and regressed issues as findings using the same stable keys when possible.

Return exactly this JSON shape and no prose outside it:

{
  "findings": [
    {
      "stable_key": "deterministic string from requirement/location/problem",
      "severity": "critical|major|minor|info",
      "location": "contract step, source file, validator, CLI, artifact, or test location",
      "requirement": "specific contract requirement being evaluated",
      "problem": "what is missing, unsafe, contradictory, unverifiable, or wrong",
      "evidence": "specific observed evidence from bundle/source/tests/artifacts",
      "fix": "bounded concrete fix",
      "prior_status": "new|resolved|unresolved|regressed|not_applicable"
    }
  ],
  "summary": "brief compliance summary",
  "safe": true|false
}'''

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


def _build_scillm_body(model: str, system: str, user: str, reasoning_effort: str = "", json_response: bool = True) -> dict:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.1,
        "timeout": 600,
        "stream": True,
        "stream_progress_events": True,
        "stream_heartbeat_s": 5,
    }
    if json_response:
        body["response_format"] = {"type": "json_object"}
    if reasoning_effort:
        body["reasoning_effort"] = reasoning_effort
    return body


def _extract_stream_delta(data: dict) -> str:
    choices = data.get("choices")
    if not choices or not isinstance(choices, list):
        return ""
    choice = choices[0]
    if not isinstance(choice, dict):
        return ""
    delta = choice.get("delta")
    if isinstance(delta, dict):
        content = delta.get("content")
        return content if isinstance(content, str) else ""
    message = choice.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        return content if isinstance(content, str) else ""
    return ""


def _call_scillm(model: str, system: str, user: str, reasoning_effort: str = "", json_response: bool = True) -> str:
    """Single /scillm call. Returns response text."""
    try:
        chunks: list[str] = []
        with httpx.stream(
            "POST",
            SCILLM_CHAT_URL,
            headers=_scillm_headers(),
            json=_build_scillm_body(model, system, user, reasoning_effort, json_response=json_response),
            timeout=httpx.Timeout(connect=10.0, read=None, write=30.0, pool=10.0),
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                payload = line.removeprefix("data:").strip()
                if payload == "[DONE]":
                    break
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                chunks.append(_extract_stream_delta(data))
        return "".join(chunks)
    except Exception as e:
        logger.error("scillm {} failed: {}", model, e)
        raise ScillmRuntimeError(f"Model call failed for {model}: {e}") from e


def _parse_findings(response: str) -> list[dict]:
    """Extract strict reviewer findings from the JSON object response."""
    # Try direct JSON parse
    text = response.strip()
    if not text:
        raise ScillmRuntimeError("Reviewer returned an empty response")

    # Strip markdown fences if present
    fence_match = re.search(r'```(?:json)?\s*\n(.*?)```', text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ScillmRuntimeError(f"Reviewer returned malformed JSON: {exc}") from exc

    if isinstance(data, dict):
        findings = data.get("findings")
        if not isinstance(findings, list):
            raise ScillmRuntimeError("Reviewer JSON object missing findings array")
    elif isinstance(data, list):
        findings = data
    else:
        raise ScillmRuntimeError("Reviewer JSON must be an object or findings array")

    normalized_findings: list[dict] = []
    valid_severities = {"critical", "major", "minor", "info"}
    required_fields = {"severity", "location", "fix"}
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            raise ScillmRuntimeError(f"Finding {index} is not an object")
        missing = sorted(field for field in required_fields if not finding.get(field))
        if "problem" not in finding and "finding" not in finding:
            missing.append("problem")
        if missing:
            raise ScillmRuntimeError(f"Finding {index} missing required fields: {', '.join(missing)}")
        severity = str(finding.get("severity", "")).lower().strip()
        if severity not in valid_severities:
            raise ScillmRuntimeError(f"Finding {index} has invalid severity: {finding.get('severity')}")
        normalized = dict(finding)
        normalized["severity"] = severity
        if "finding" not in normalized:
            normalized["finding"] = normalized.get("problem", "")
        if "problem" not in normalized:
            normalized["problem"] = normalized.get("finding", "")
        normalized_findings.append(normalized)
    return normalized_findings


def _score_findings(findings: list[dict]) -> int:
    """Deterministic score: weighted sum of findings. Lower = better."""
    return sum(SEVERITY_WEIGHTS.get(f.get("severity", "info"), 0) for f in findings)


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True))


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-")
    return slug[:80] or "prompt"


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def _parse_gate_overrides(gates: list[str]) -> dict[str, int]:
    parsed = {
        "max_critical": 0,
        "max_major": 0,
    }
    for gate in gates:
        if "=" not in gate:
            raise ValueError(f"Invalid gate override {gate!r}; expected key=value")
        key, value = gate.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key not in {"max_critical", "max_major", "max_score"}:
            raise ValueError(f"Unsupported gate override {key!r}")
        try:
            parsed[key] = int(value)
        except ValueError as exc:
            raise ValueError(f"Gate override {key!r} must be an integer") from exc
        if parsed[key] < 0:
            raise ValueError(f"Gate override {key!r} must be non-negative")
    return parsed


def _run_configured_commands(
    commands: list[str],
    kind: str,
    cwd: Path,
    artifact_dir: Path,
    timeout_sec: int,
) -> dict:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    for index, command in enumerate(commands, 1):
        command_id = f"{kind}-{index:03d}"
        started = time.time()
        row = {
            "id": command_id,
            "kind": kind,
            "command": command,
            "cwd": str(cwd),
            "timeout_sec": timeout_sec,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
            )
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            row.update(
                {
                    "exit_status": completed.returncode,
                    "timed_out": False,
                    "passed": completed.returncode == 0,
                    "stdout_hash": _sha256_text(stdout),
                    "stderr_hash": _sha256_text(stderr),
                    "stdout_preview": stdout[-8000:],
                    "stderr_preview": stderr[-8000:],
                }
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            row.update(
                {
                    "exit_status": None,
                    "timed_out": True,
                    "passed": False,
                    "stdout_hash": _sha256_text(stdout),
                    "stderr_hash": _sha256_text(stderr),
                    "stdout_preview": stdout[-8000:],
                    "stderr_preview": stderr[-8000:],
                }
            )
        row["ended_at"] = datetime.now(timezone.utc).isoformat()
        row["duration_sec"] = round(time.time() - started, 3)
        results.append(row)
    output = {
        "kind": kind,
        "passed": all(result["passed"] for result in results),
        "commands_count": len(commands),
        "results": results,
    }
    _write_json(artifact_dir / f"{kind}-output.json", output)
    return output


def _gate_penalty(gate_outputs: dict[str, dict]) -> int:
    penalty = 0
    for kind, output in gate_outputs.items():
        if not output:
            continue
        weight = GATE_FAILURE_WEIGHTS.get(kind, 6)
        for result in output.get("results", []):
            if not result.get("passed"):
                penalty += weight
    return penalty


def _gate_failures(gate_outputs: dict[str, dict]) -> list[dict]:
    failures: list[dict] = []
    for kind, output in gate_outputs.items():
        for result in output.get("results", []) if output else []:
            if result.get("passed"):
                continue
            failures.append(
                {
                    "stable_key": f"{kind}:{result.get('id')}:failed",
                    "severity": "major",
                    "location": f"{kind} gate {result.get('id')}",
                    "finding": f"{kind} command failed or timed out",
                    "problem": f"{kind} command failed or timed out",
                    "evidence": f"exit_status={result.get('exit_status')} timed_out={result.get('timed_out')} stderr_hash={result.get('stderr_hash')}",
                    "fix": "Fix the prompt contract or deterministic gate command until the gate passes.",
                    "prior_status": "new",
                    "gate_kind": kind,
                    "gate_id": result.get("id"),
                }
            )
    return failures


def _gate_thresholds_pass(findings: list[dict], score: int, gate_overrides: dict[str, int]) -> bool:
    critical = sum(1 for finding in findings if finding.get("severity") == "critical")
    major = sum(1 for finding in findings if finding.get("severity") == "major")
    if critical > gate_overrides.get("max_critical", 0):
        return False
    if major > gate_overrides.get("max_major", 0):
        return False
    if "max_score" in gate_overrides and score > gate_overrides["max_score"]:
        return False
    return True


def _all_gates_passed(gate_outputs: dict[str, dict]) -> bool:
    return all(output.get("passed", True) for output in gate_outputs.values() if output)


def _deduplicate_findings(all_findings: list[dict]) -> list[dict]:
    """Deduplicate findings from multiple models by similarity."""
    seen: set[str] = set()
    unique: list[dict] = []
    for f in all_findings:
        key = str(f.get("stable_key") or f.get("finding") or f.get("problem") or "")[:160].lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


def _apply_fixes(
    template_text: str,
    findings: list[dict],
    context: str,
    fix_model: str,
    reasoning_effort: str,
) -> str | None:
    """Send template + findings to LLM, get back the fixed template. Returns None on failure."""
    findings_text = "\n".join(
        f"- [{f.get('severity')}] {f.get('location')}: {f.get('finding')} → FIX: {f.get('fix')}"
        for f in findings
        if f.get("severity") in ("critical", "major")  # only fix critical/major
    )
    if not findings_text:
        return None

    user = f"## Context\n{context}\n\n## Current Prompt Template\n```\n{template_text}\n```\n\n## Findings to Fix\n{findings_text}\n\nApply ALL fixes above. Return the complete fixed prompt template."

    fixed = _call_scillm(fix_model, FIX_SYSTEM, user, reasoning_effort, json_response=False)
    if not fixed or len(fixed) < len(template_text) * 0.5:
        logger.warning("  Fix attempt returned suspiciously short result ({} chars vs {} original)", len(fixed), len(template_text))
        return None

    # Strip markdown fences if present
    fence = re.search(r'```(?:\w+)?\s*\n(.*?)```', fixed, re.DOTALL)
    if fence:
        fixed = fence.group(1).strip()

    return fixed


def _concurrent_review(
    models: list[str],
    system: str,
    user_prompt: str,
    artifact_dir: Path | None = None,
    reasoning_effort: str = "",
) -> list[dict]:
    """Send review to N models concurrently, merge and deduplicate findings."""
    all_findings: list[dict] = []
    request_rows = [
        {"model": model, "system": system, "user": user_prompt}
        for model in models
    ]
    response_rows: list[dict] = []

    if artifact_dir is not None:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        _write_text(
            artifact_dir / "model-requests.jsonl",
            "\n".join(json.dumps(row, sort_keys=True) for row in request_rows) + "\n",
        )

    with ThreadPoolExecutor(max_workers=len(models)) as pool:
        futures = {
            pool.submit(_call_scillm, model, system, user_prompt, reasoning_effort): model
            for model in models
        }
        for future in as_completed(futures):
            model = futures[future]
            try:
                response = future.result()
                response_rows.append({"model": model, "response": response})
                findings = _parse_findings(response)
                for f in findings:
                    f["model"] = model  # tag source model
                all_findings.extend(findings)
                logger.info("  {} → {} findings", model, len(findings))
            except Exception as e:
                logger.error("  {} failed: {}", model, e)
                response_rows.append({"model": model, "error": str(e)})
                if artifact_dir is not None:
                    _write_text(
                        artifact_dir / "model-responses.jsonl",
                        "\n".join(json.dumps(row, sort_keys=True) for row in response_rows) + "\n",
                    )
                raise

    if artifact_dir is not None:
        _write_text(
            artifact_dir / "model-responses.jsonl",
            "\n".join(json.dumps(row, sort_keys=True) for row in response_rows) + "\n",
        )

    return _deduplicate_findings(all_findings)


def _scillm_get(path: str, timeout: float = 5.0) -> dict:
    response = httpx.get(
        f"{SCILLM_BASE_URL}{path}",
        headers=_scillm_headers(),
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def _scillm_smoke(model: str, reasoning_effort: str) -> dict:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "Return exactly: []"}],
        "timeout": 120,
    }
    if reasoning_effort:
        body["reasoning_effort"] = reasoning_effort
    response = httpx.post(
        SCILLM_CHAT_URL,
        headers=_scillm_headers(),
        json=body,
        timeout=180.0,
    )
    response.raise_for_status()
    data = response.json()
    return {
        "model_requested": model,
        "model_served": data.get("model"),
        "reasoning": data.get("scillm_reasoning"),
        "ok": True,
    }


def _scillm_preflight(models: list[str], reasoning_effort: str) -> dict:
    checks: dict[str, object] = {
        "base_url": SCILLM_BASE_URL,
        "chat_url": SCILLM_CHAT_URL,
        "caller": SCILLM_CALLER,
        "models": models,
        "reasoning_effort": reasoning_effort,
    }
    try:
        health = httpx.get(f"{SCILLM_BASE_URL}/health", timeout=3.0)
        health.raise_for_status()
        checks["public_health"] = health.json()
        checks["router_health"] = _scillm_get("/v1/scillm/health")
        checks["auth"] = _scillm_get("/v1/scillm/auth")
        checks["models_response"] = _scillm_get("/v1/scillm/models")
        checks["smoke"] = [
            _scillm_smoke(model, reasoning_effort)
            for model in models
        ]
    except Exception as exc:
        checks["status"] = "blocked"
        checks["error"] = str(exc)
        return checks
    checks["status"] = "passed"
    return checks


def _extract_ask_verdict(review_json_path: Path) -> str | None:
    if not review_json_path.exists():
        return None
    data = json.loads(review_json_path.read_text())
    queue: list[object] = [data]
    while queue:
        current = queue.pop(0)
        if isinstance(current, dict):
            for key, value in current.items():
                if key.lower() in {"verdict", "final_verdict", "safety_verdict"} and isinstance(value, str):
                    normalized = value.strip().upper()
                    if normalized in {"SAFE", "SAFE_WITH_CONDITIONS", "NOT_SAFE", "INSUFFICIENT_EVIDENCE"}:
                        return normalized
                if isinstance(value, (dict, list)):
                    queue.append(value)
        elif isinstance(current, list):
            queue.extend(current)
    return None


def _run_ask_gate(
    bundle_path: Path,
    ask_id: str,
    ask_model: str,
    ask_reasoning: str,
    ask_timeout: int,
    final_dir: Path,
) -> dict:
    skill_dir = Path(__file__).resolve().parent
    ask_run = skill_dir.parent / "ask" / "run.sh"
    if not ask_run.exists():
        return {
            "status": "blocked",
            "reason": "ask runtime not found",
            "ask_run": str(ask_run),
        }

    command = [
        str(ask_run),
        "ask",
        "Deep review this prompt contract bundle for readiness.",
        "--deep-review",
        "--deep-review-target",
        str(bundle_path),
        "--deep-review-focus",
        "schema,evidence-discipline,consumer-contract,safety,auditability",
        "--oracle-model",
        ask_model,
        "--oracle-reasoning",
        ask_reasoning,
        "--oracle-timeout",
        str(ask_timeout),
        "--ask-id",
        ask_id,
        "--overwrite",
        "--json",
    ]
    result = subprocess.run(
        command,
        cwd=ask_run.parent,
        capture_output=True,
        text=True,
        timeout=ask_timeout + 60,
    )

    run_dir = ask_run.parent / ".ask_artifacts" / "runs" / ask_id
    status_path = run_dir / f"{ask_id}.status.json"
    request_path = run_dir / f"{ask_id}.request.json"
    events_path = run_dir / f"{ask_id}.events.jsonl"
    review_md_path: Path | None = None
    review_json_path: Path | None = None
    status_data: dict = {}

    if status_path.exists():
        status_data = json.loads(status_path.read_text())
        artifacts = status_data.get("artifacts", {})
        if isinstance(artifacts, dict):
            review_md = artifacts.get("review_md") or artifacts.get("markdown")
            review_json = artifacts.get("review_json") or artifacts.get("json")
            if isinstance(review_md, str):
                review_md_path = Path(review_md)
                if not review_md_path.is_absolute():
                    review_md_path = ask_run.parent / review_md_path
            if isinstance(review_json, str):
                review_json_path = Path(review_json)
                if not review_json_path.is_absolute():
                    review_json_path = ask_run.parent / review_json_path

    if review_json_path is None:
        candidates = sorted((ask_run.parent / ".ask_artifacts" / "deep-review").glob("*/review.json"))
        review_json_path = candidates[-1] if candidates else None
    if review_md_path is None and review_json_path is not None:
        review_md_path = review_json_path.with_name("review.md")

    verdict = _extract_ask_verdict(review_json_path) if review_json_path else None
    gate_status = "passed" if result.returncode == 0 and verdict == "SAFE" else "blocked"
    ask_artifacts = {
        "status": gate_status,
        "returncode": result.returncode,
        "ask_id": ask_id,
        "command": command,
        "request_json": str(request_path),
        "status_json": str(status_path),
        "events_jsonl": str(events_path),
        "review_md": str(review_md_path) if review_md_path else None,
        "review_json": str(review_json_path) if review_json_path else None,
        "verdict": verdict,
        "stdout": result.stdout[-8000:],
        "stderr": result.stderr[-8000:],
        "status_data": status_data,
    }
    _write_json(final_dir / "ask-artifacts.json", ask_artifacts)
    return ask_artifacts


def _extract_webgpt_verdict(response_path: Path) -> str | None:
    if not response_path.exists():
        return None
    text = response_path.read_text()
    json_match = re.search(r"\{[\s\S]*\}", text)
    if json_match:
        try:
            data = json.loads(json_match.group(0))
            verdict = data.get("verdict") or data.get("final_verdict") or data.get("safety_verdict")
            if isinstance(verdict, str):
                normalized = verdict.strip().upper()
                if normalized in {"SAFE", "SAFE_WITH_CONDITIONS", "NOT_SAFE", "INSUFFICIENT_EVIDENCE"}:
                    return normalized
        except json.JSONDecodeError:
            pass
    match = re.search(
        r"(?im)^\s*(?:VERDICT|FINAL_VERDICT|SAFETY_VERDICT)\s*:\s*"
        r"(SAFE_WITH_CONDITIONS|INSUFFICIENT_EVIDENCE|NOT_SAFE|SAFE)\b",
        text,
    )
    return match.group(1).upper() if match else None


def _resolve_chatgpt_tab(surf_run: Path) -> tuple[str, list[dict]]:
    """Auto-discover an open ChatGPT tab via surf tab.list.

    Returns (tab_id, candidates). tab_id is "" if 0 or >1 candidates were found.
    candidates is the full list of {id,title,url} for chatgpt.com tabs so the
    caller can produce a clear diagnostic when the choice is ambiguous.
    """
    try:
        proc = subprocess.run(
            [str(surf_run), "tab.list"],
            cwd=surf_run.parent,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception:
        return "", []
    if proc.returncode != 0:
        return "", []
    candidates: list[dict] = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        tab_id, title, url = parts[0], parts[1], parts[2]
        if "chatgpt.com" not in url:
            continue
        candidates.append({"id": tab_id, "title": title, "url": url})
    if len(candidates) == 1:
        return candidates[0]["id"], candidates
    return "", candidates


def _run_webgpt_gate(
    bundle_path: Path,
    webgpt_tab_id: str,
    webgpt_url: str,
    webgpt_timeout: int,
    final_dir: Path,
    webgpt_no_activate: bool = False,
    webgpt_round: int | None = None,
) -> dict:
    skill_dir = Path(__file__).resolve().parent
    surf_run = skill_dir.parent / "surf" / "run.sh"
    gate_dir = final_dir / "webgpt"
    if webgpt_round is not None:
        gate_dir = gate_dir / f"round-{int(webgpt_round):03d}"
    gate_dir.mkdir(parents=True, exist_ok=True)
    request_path = gate_dir / "request.md"
    response_path = gate_dir / "response.md"
    meta_path = gate_dir / "response.meta.json"

    if not surf_run.exists():
        result = {"status": "blocked", "reason": "surf runtime not found", "surf_run": str(surf_run)}
        _write_json(final_dir / "webgpt-artifacts.json", result)
        return result

    auto_resolved_tab = False
    resolution_candidates: list[dict] = []
    if not webgpt_tab_id and not webgpt_url:
        webgpt_tab_id, resolution_candidates = _resolve_chatgpt_tab(surf_run)
        auto_resolved_tab = bool(webgpt_tab_id)
        if not webgpt_tab_id:
            result = {
                "status": "blocked",
                "reason": (
                    "no_chatgpt_tab" if not resolution_candidates
                    else "ambiguous_chatgpt_tab"
                ),
                "candidates": resolution_candidates,
                "hint": "Pass --webgpt-tab-id or --webgpt-url. Open exactly one ChatGPT tab to auto-resolve.",
            }
            _write_json(final_dir / "webgpt-artifacts.json", result)
            return result

    bundle = json.loads(bundle_path.read_text())
    request_path.write_text(
        "\n".join([
            "# WebGPT Prompt Contract Gate",
            "",
            "You are reviewing a prompt contract bundle as an external high-judgment reviewer.",
            "Return a strict JSON object only with this shape:",
            "",
            "```json",
            '{"verdict":"SAFE|SAFE_WITH_CONDITIONS|NOT_SAFE|INSUFFICIENT_EVIDENCE","blocking_findings":[],"conditions":[],"non_blocking_findings":[],"deterministic_gate_notes":[]}',
            "```",
            "",
            "Use SAFE only when the prompt contract is ready and the deterministic review-prompt gates described in the bundle are sufficient.",
            "Use SAFE_WITH_CONDITIONS only when every condition maps to a deterministic gate or explicit human-accepted residual risk.",
            "Use NOT_SAFE for merge-blocking prompt, schema, safety, evidence, or consumer-contract issues.",
            "Use INSUFFICIENT_EVIDENCE when the bundle lacks payloads, validators, expected outputs, source files, or proof artifacts required to judge readiness.",
            "",
            "Do not rewrite the prompt. Review the contract and explain blockers.",
            "",
            "## Bundle JSON",
            "",
            "```json",
            json.dumps(bundle, indent=2),
            "```",
            "",
        ])
    )

    command = [
        str(surf_run), "webgpt.submit",
        "--input", str(request_path),
        "--output", str(response_path),
        "--meta-output", str(meta_path),
        "--timeout", str(webgpt_timeout),
        "--stable-polls", "3",
    ]
    if webgpt_tab_id:
        command.extend(["--tab-id", webgpt_tab_id])
    if webgpt_url:
        command.extend(["--url", webgpt_url])
    if webgpt_no_activate:
        command.append("--no-activate")

    proc = subprocess.run(command, cwd=surf_run.parent, capture_output=True, text=True, timeout=webgpt_timeout + 60)
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    verdict = _extract_webgpt_verdict(response_path)
    status = "passed" if proc.returncode == 0 and verdict == "SAFE" else "blocked"
    result = {
        "status": status,
        "returncode": proc.returncode,
        "command": command,
        "request_md": str(request_path),
        "response_md": str(response_path),
        "meta_json": str(meta_path),
        "verdict": verdict,
        "controlled_tab_id": meta.get("controlled_tab_id"),
        "requested_tab_id": meta.get("requested_tab_id"),
        "requested_url": meta.get("requested_url"),
        "raw_contains_sentinel": meta.get("raw_contains_sentinel"),
        "clean_contains_sentinel": meta.get("clean_contains_sentinel"),
        "no_activate": meta.get("no_activate"),
        "focus_changed": meta.get("focus_changed"),
        "round": webgpt_round,
        "auto_resolved_tab": auto_resolved_tab,
        "resolution_candidates": resolution_candidates if auto_resolved_tab or not webgpt_tab_id else None,
        "stdout": proc.stdout[-8000:],
        "stderr": proc.stderr[-8000:],
    }
    _write_json(final_dir / "webgpt-artifacts.json", result)
    return result


@app.command()
def review(
    template: str = typer.Option(..., "--template", "-t", help="Prompt template file"),
    source: list[str] = typer.Option([], "--source", "-s", help="Source files that use the template"),
    payload: str = typer.Option("", "--payload", "-d", help="Real payload/data file that fills the template placeholder"),
    persona: str = typer.Option(..., "--persona", "-p", help="REQUIRED. Who reviews/consumes this prompt (e.g. 'brandon', 'nico', 'tim', or custom description)"),
    context: str = typer.Option(..., "--context", "-c", help="REQUIRED. What this prompt does, why it exists, what problem it solves"),
    models: list[str] = typer.Option([], "--models", "-m", help="Models to use"),
    max_rounds: int = typer.Option(1, "--max-rounds", help="Max review+fix rounds (default 1 = review only, no fix)"),
    output: str = typer.Option("", "--output", "-o", help="Write final template to file"),
    artifact_root: str = typer.Option("artifacts/review-prompt", "--artifact-root", help="Directory for round artifacts and terminal audit"),
    validator: list[str] = typer.Option([], "--validator", help="Deterministic validation command; may repeat"),
    smoke: list[str] = typer.Option([], "--smoke", help="Consumer compatibility or runtime smoke command; may repeat"),
    gate: list[str] = typer.Option([], "--gate", help="Gate override such as max_critical=0; may repeat"),
    gate_timeout: int = typer.Option(300, "--gate-timeout", help="Timeout seconds for each validator/smoke command"),
    ask_gate: bool = typer.Option(False, "--ask-gate", help="Run ask deep-review as final readiness gate"),
    ask_model: str = typer.Option("gpt-5.5", "--ask-model", help="Ask oracle model for final gate"),
    ask_reasoning: str = typer.Option("high", "--ask-reasoning", help="Ask oracle reasoning effort for final gate"),
    ask_timeout: int = typer.Option(900, "--ask-timeout", help="Ask final gate timeout seconds"),
    webgpt_gate: bool = typer.Option(False, "--webgpt-gate", help="Run WebGPT through surf as an external final gate"),
    webgpt_tab_id: str = typer.Option("", "--webgpt-tab-id", help="ChatGPT tab id for --webgpt-gate (auto-resolved from surf tab.list if omitted and exactly one chatgpt.com tab is open)"),
    webgpt_url: str = typer.Option("", "--webgpt-url", help="Open ChatGPT conversation URL for --webgpt-gate"),
    webgpt_timeout: int = typer.Option(900, "--webgpt-timeout", help="WebGPT final gate timeout seconds"),
    webgpt_no_activate: bool = typer.Option(False, "--webgpt-no-activate", help="Run the WebGPT gate against a background controlled tab; never foreground it (requires --webgpt-tab-id or auto-resolution to find exactly one chatgpt.com tab)"),
    webgpt_round: int | None = typer.Option(None, "--webgpt-round", help="Round number for multi-turn iteration; artifacts go to final/webgpt/round-NNN/ instead of final/webgpt/"),
    reasoning_effort: str = typer.Option("", "--reasoning-effort", help="Top-level /scillm reasoning_effort for reviewer and fix calls"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show prompt without calling LLM"),
) -> None:
    """Review and optimize a prompt template using concurrent multi-model feedback."""
    if not models:
        models = DEFAULT_MODELS
    fix_model = models[0]
    try:
        gate_overrides = _parse_gate_overrides(gate)
    except ValueError as exc:
        logger.error("Invalid --gate: {}", exc)
        raise typer.Exit(2) from exc

    template_path = Path(template)
    if not template_path.exists():
        logger.error("Template not found: {}", template)
        raise typer.Exit(1)

    template_text = template_path.read_text().strip()
    best_text = template_text  # keep/revert anchor

    source_texts: dict[str, str] = {}
    missing_sources: list[str] = []
    for s in source:
        sp = Path(s)
        if sp.exists():
            source_texts[sp.name] = sp.read_text()[:8000]  # cap for context window
        else:
            missing_sources.append(s)

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
    logger.info("  Validators: {}", len(validator))
    logger.info("  Smokes: {}", len(smoke))

    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{_safe_slug(template_path.stem)}"
    run_dir = Path(artifact_root) / run_id
    final_dir = run_dir / "final"
    _write_json(run_dir / "request.json", {
        "template": str(template_path),
        "sources": source,
        "payload": payload,
        "persona": persona,
        "context": context,
        "models": models,
        "max_rounds": max_rounds,
        "ask_gate": ask_gate,
        "ask_model": ask_model,
        "ask_reasoning": ask_reasoning,
        "webgpt_gate": webgpt_gate,
        "webgpt_tab_id": webgpt_tab_id,
        "webgpt_url": webgpt_url,
        "webgpt_timeout": webgpt_timeout,
        "reasoning_effort": reasoning_effort,
        "fix_model": fix_model,
        "validator": validator,
        "smoke": smoke,
        "gate": gate,
        "gate_overrides": gate_overrides,
        "gate_timeout": gate_timeout,
    })
    preflight = {
        "status": "passed",
        "template_exists": template_path.exists(),
        "source_count": len(source_texts),
        "missing_sources": missing_sources,
        "payload_present": bool(payload_text),
        "output_writable": True,
        "fix_model": fix_model,
        "validator_count": len(validator),
        "smoke_count": len(smoke),
        "gate_overrides": gate_overrides,
        "gate_timeout": gate_timeout,
    }
    if missing_sources:
        preflight["status"] = "blocked"
        preflight["reason"] = "source_files_missing"
    if gate_timeout <= 0:
        preflight["status"] = "blocked"
        preflight["reason"] = "invalid_gate_timeout"

    if dry_run:
        preflight["status"] = "skipped_dry_run"
        _write_json(run_dir / "preflight.json", preflight)
        prompt = _build_review_prompt(template_text, source_texts, context, 1, payload_text=payload_text)
        print("=== SYSTEM ===")
        print(REVIEW_SYSTEM)
        print("\n=== USER ===")
        print(prompt)
        return

    baseline_gate_outputs: dict[str, dict] = {}
    if preflight["status"] == "passed":
        preflight["scillm"] = _scillm_preflight(list(dict.fromkeys([*models, fix_model])), reasoning_effort)
        if isinstance(preflight["scillm"], dict) and preflight["scillm"].get("status") != "passed":
            preflight["status"] = "blocked"
    if preflight["status"] == "passed":
        baseline_dir = run_dir / "baseline"
        gate_cwd = template_path.parent
        if validator:
            baseline_gate_outputs["validator"] = _run_configured_commands(
                validator, "validator", gate_cwd, baseline_dir, gate_timeout
            )
        if smoke:
            baseline_gate_outputs["smoke"] = _run_configured_commands(
                smoke, "smoke", gate_cwd, baseline_dir, gate_timeout
            )
        preflight["baseline_gates"] = baseline_gate_outputs
        preflight["baseline_gate_penalty"] = _gate_penalty(baseline_gate_outputs)
        preflight["baseline_gates_passed"] = _all_gates_passed(baseline_gate_outputs)
    _write_json(run_dir / "preflight.json", preflight)
    if preflight["status"] != "passed":
        final_dir.mkdir(parents=True, exist_ok=True)
        audit = {
            "status": "halted",
            "reason": "preflight_failed",
            "preflight": preflight,
            "run_dir": str(run_dir),
        }
        _write_json(final_dir / "audit.json", audit)
        _write_text(final_dir / "summary.md", "# review-prompt run\n\n- Status: halted\n- Reason: preflight_failed\n")
        log_file = template_path.parent / f"{template_path.stem}.review.json"
        log_file.write_text(json.dumps({
            "template": str(template_path),
            "models": models,
            "rounds": [],
            "best_score": None,
            "run_dir": str(run_dir),
            "preflight": preflight,
            "ask_gate": None,
        }, indent=2))
        print(json.dumps({
            "status": "blocked",
            "reason": "preflight_failed",
            "run_dir": str(run_dir),
            "preflight": str(run_dir / "preflight.json"),
        }, indent=2))
        raise typer.Exit(2)

    all_prior_findings: list[dict] = []
    best_score = float("inf")
    best_text = template_text
    rounds_log: list[dict] = []
    current_gate_outputs = baseline_gate_outputs

    for round_num in range(1, max_rounds + 1):
        round_dir = run_dir / "rounds" / f"{round_num:03d}"
        # ── Step 1: REVIEW (N models score the current template) ──
        system = REVIEW_SYSTEM if round_num == 1 else FOLLOWUP_SYSTEM
        user_prompt = _build_review_prompt(
            template_text, source_texts, context, round_num, all_prior_findings,
            payload_text=payload_text,
        )

        logger.info("── Round {}/{} ──", round_num, max_rounds)
        try:
            findings = _concurrent_review(models, system, user_prompt, round_dir, reasoning_effort)
        except ScillmRuntimeError as exc:
            round_entry = {
                "round": round_num,
                "findings_count": 0,
                "score": None,
                "critical": None,
                "major": None,
                "findings": [],
                "timestamp": time.time(),
                "action": "runtime_failed",
                "error": str(exc),
            }
            _write_json(round_dir / "decision.json", round_entry)
            rounds_log.append(round_entry)
            all_prior_findings.append({
                "severity": "critical",
                "location": "scillm runtime",
                "finding": str(exc),
                "fix": "Fix /scillm model routing or auth; do not rewrite the prompt.",
                "model": ",".join(models),
            })
            break
        model_findings = findings
        gate_findings = _gate_failures(current_gate_outputs)
        findings = _deduplicate_findings(model_findings + gate_findings)
        model_score = _score_findings(model_findings)
        gate_penalty = _gate_penalty(current_gate_outputs)
        score = model_score + gate_penalty

        # Count critical+major only (these must converge to 0)
        n_critical = sum(1 for f in findings if f.get("severity") == "critical")
        n_major = sum(1 for f in findings if f.get("severity") == "major")
        gates_passed = _all_gates_passed(current_gate_outputs)
        thresholds_passed = _gate_thresholds_pass(findings, score, gate_overrides)

        round_entry = {
            "round": round_num,
            "findings_count": len(findings),
            "score": score,
            "model_score": model_score,
            "gate_penalty": gate_penalty,
            "critical": n_critical,
            "major": n_major,
            "findings": findings,
            "gate_outputs": current_gate_outputs,
            "gates_passed": gates_passed,
            "thresholds_passed": thresholds_passed,
            "timestamp": time.time(),
        }
        _write_json(round_dir / "findings.json", findings)
        _write_json(round_dir / "merged-findings.json", findings)
        _write_json(round_dir / "score.json", {
            "score": score,
            "model_score": model_score,
            "gate_penalty": gate_penalty,
            "critical": n_critical,
            "major": n_major,
            "findings_count": len(findings),
            "gates_passed": gates_passed,
            "thresholds_passed": thresholds_passed,
        })

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
        if gates_passed and thresholds_passed:
            logger.info("=== CONVERGED: 0 critical, 0 major on round {} ===", round_num)
            best_text = template_text
            best_score = score
            round_entry["action"] = "converged"
            _write_json(round_dir / "decision.json", {"action": "converged", "score": score, "gates_passed": gates_passed})
            rounds_log.append(round_entry)
            break

        # ── Step 2: APPLY FIXES (LLM rewrites template to fix critical+major) ──
        logger.info("  Applying fixes ({} critical + {} major)...", n_critical, n_major)
        try:
            fixed_text = _apply_fixes(template_text, findings, context, fix_model, reasoning_effort)
        except ScillmRuntimeError as exc:
            logger.error("  Fix model failed: {}", exc)
            round_entry["action"] = "runtime_failed"
            round_entry["error"] = str(exc)
            rounds_log.append(round_entry)
            all_prior_findings.append({
                "severity": "critical",
                "location": "scillm runtime",
                "finding": str(exc),
                "fix": "Fix /scillm model routing or auth; do not rewrite the prompt.",
                "model": fix_model,
            })
            break

        if fixed_text is None:
            logger.warning("  Fix attempt failed — no usable output from LLM")
            round_entry["action"] = "fix_failed"
            rounds_log.append(round_entry)
            all_prior_findings.extend(findings)
            continue

        # ── Step 3: RE-SCORE the fixed template ──
        logger.info("  Re-scoring fixed template...")
        template_path.write_text(fixed_text)
        fixed_gate_outputs: dict[str, dict] = {}
        if validator:
            fixed_gate_outputs["validator"] = _run_configured_commands(
                validator, "validator", template_path.parent, round_dir / "fixed-gates", gate_timeout
            )
        if smoke:
            fixed_gate_outputs["smoke"] = _run_configured_commands(
                smoke, "smoke", template_path.parent, round_dir / "fixed-gates", gate_timeout
            )
        fixed_prompt = _build_review_prompt(
            fixed_text, source_texts, context, round_num, [],
            payload_text=payload_text,
        )
        fixed_rescore_dir = round_dir / "fixed-rescore"
        try:
            fixed_findings = _concurrent_review(models, REVIEW_SYSTEM, fixed_prompt, fixed_rescore_dir, reasoning_effort)
        except ScillmRuntimeError as exc:
            template_text = best_text
            template_path.write_text(best_text)
            logger.error("  Fixed candidate review failed; reverted file: {}", exc)
            round_entry["action"] = "runtime_failed_reverted"
            round_entry["error"] = str(exc)
            round_entry["fixed_gate_outputs"] = fixed_gate_outputs
            _write_json(round_dir / "decision.json", {
                "action": "runtime_failed_reverted",
                "score": score,
                "reason": str(exc),
            })
            rounds_log.append(round_entry)
            all_prior_findings.extend(findings)
            break
        fixed_model_findings = fixed_findings
        fixed_gate_findings = _gate_failures(fixed_gate_outputs)
        fixed_findings = _deduplicate_findings(fixed_model_findings + fixed_gate_findings)
        fixed_model_score = _score_findings(fixed_model_findings)
        fixed_gate_penalty = _gate_penalty(fixed_gate_outputs)
        fixed_score = fixed_model_score + fixed_gate_penalty
        fixed_critical = sum(1 for f in fixed_findings if f.get("severity") == "critical")
        fixed_major = sum(1 for f in fixed_findings if f.get("severity") == "major")
        fixed_gates_passed = _all_gates_passed(fixed_gate_outputs)

        logger.info("  Fixed score: {} (was {}), critical: {} (was {}), major: {} (was {})",
                     fixed_score, score, fixed_critical, n_critical, fixed_major, n_major)

        _write_text(
            round_dir / "patch.diff",
            "".join(difflib.unified_diff(
                template_text.splitlines(keepends=True),
                fixed_text.splitlines(keepends=True),
                fromfile=str(template_path),
                tofile=f"{template_path} (fixed)",
            )),
        )

        # ── Step 4: KEEP or REVERT (artifact-backed; no commits) ──
        if fixed_score < score and fixed_gates_passed:
            template_text = fixed_text
            best_text = fixed_text
            best_score = fixed_score
            current_gate_outputs = fixed_gate_outputs

            logger.info("  KEEP — wrote improved template (score {}→{})", score, fixed_score)
            round_entry["action"] = "keep"
            round_entry["fixed_score"] = fixed_score
            round_entry["fixed_model_score"] = fixed_model_score
            round_entry["fixed_gate_penalty"] = fixed_gate_penalty
            round_entry["fixed_gates_passed"] = fixed_gates_passed
            round_entry["fixed_findings"] = fixed_findings
            round_entry["fixed_gate_outputs"] = fixed_gate_outputs
            _write_json(round_dir / "decision.json", {
                "action": "keep",
                "score": score,
                "fixed_score": fixed_score,
                "fixed_gates_passed": fixed_gates_passed,
                "reason": "fixed score improved and required deterministic gates passed",
            })
            all_prior_findings.extend(fixed_findings)
        else:
            template_text = best_text  # revert in memory
            template_path.write_text(best_text)
            logger.info("  REVERT — fixed score {} >= original {}, file restored", fixed_score, score)
            round_entry["action"] = "revert"
            round_entry["fixed_score"] = fixed_score
            round_entry["fixed_model_score"] = fixed_model_score
            round_entry["fixed_gate_penalty"] = fixed_gate_penalty
            round_entry["fixed_gates_passed"] = fixed_gates_passed
            round_entry["fixed_gate_outputs"] = fixed_gate_outputs
            _write_json(round_dir / "decision.json", {
                "action": "revert",
                "score": score,
                "fixed_score": fixed_score,
                "fixed_gates_passed": fixed_gates_passed,
                "reason": "fixed score did not improve or required deterministic gates failed",
            })
            all_prior_findings.extend(findings)

        rounds_log.append(round_entry)

    # Final output
    deterministic_passed = (
        bool(rounds_log)
        and best_score != float("inf")
        and rounds_log[-1].get("action") == "converged"
        and rounds_log[-1].get("gates_passed", True)
        and rounds_log[-1].get("thresholds_passed", False)
    )
    terminal_status = "ready_for_ask_gate" if ask_gate and deterministic_passed else ("completed" if deterministic_passed else "halted")

    logger.info("=== RESULT: {} rounds, best score={} status={} ===", len(rounds_log), best_score, terminal_status)

    if output:
        Path(output).write_text(best_text)
        logger.info("  Wrote optimized template to: {}", output)

    final_dir.mkdir(parents=True, exist_ok=True)
    _write_text(final_dir / "reviewed-template.txt", best_text)
    audit_json = {
        "status": terminal_status,
        "best_score": best_score if best_score != float("inf") else None,
        "rounds": rounds_log,
        "run_dir": str(run_dir),
        "deterministic_passed": deterministic_passed,
        "gate_overrides": gate_overrides,
        "validator": validator,
        "smoke": smoke,
    }
    _write_json(final_dir / "audit.json", audit_json)
    _write_text(final_dir / "summary.md", f"# review-prompt run\n\n- Status: {terminal_status}\n- Rounds: {len(rounds_log)}\n- Best score: {best_score if best_score != float('inf') else None}\n")
    ask_bundle_path = final_dir / "ask-review-bundle.json"
    _write_json(ask_bundle_path, {
        "template": str(template_path),
        "reviewed_template": str(final_dir / "reviewed-template.txt"),
        "reviewed_template_text": best_text,
        "audit": str(final_dir / "audit.json"),
        "audit_json": {
            "status": terminal_status,
            "best_score": best_score if best_score != float("inf") else None,
            "rounds": rounds_log,
            "run_dir": str(run_dir),
            "deterministic_passed": deterministic_passed,
        },
        "summary": str(final_dir / "summary.md"),
        "summary_markdown": f"# review-prompt run\n\n- Status: {terminal_status}\n- Rounds: {len(rounds_log)}\n- Best score: {best_score if best_score != float('inf') else None}\n",
        "request": str(run_dir / "request.json"),
        "request_json": json.loads((run_dir / "request.json").read_text()),
        "preflight": str(run_dir / "preflight.json"),
        "preflight_json": json.loads((run_dir / "preflight.json").read_text()),
        "rounds": rounds_log,
        "source_files": [
            {
                "path": str(Path(source_path)),
                "content_excerpt": source_texts.get(Path(source_path).name, ""),
            }
            for source_path in source
        ],
        "gate": {
            "max_rounds": max_rounds,
            "gate_overrides": gate_overrides,
            "validator": validator,
            "smoke": smoke,
            "baseline_gate_outputs": baseline_gate_outputs,
            "ask_model": ask_model,
            "ask_reasoning": ask_reasoning,
            "webgpt_gate": webgpt_gate,
            "webgpt_tab_id": webgpt_tab_id,
            "webgpt_url": webgpt_url,
            "reasoning_effort": reasoning_effort,
            "pass_condition": "ask verdict SAFE and deterministic review-prompt gates pass",
        },
    })

    ask_artifacts = None
    webgpt_artifacts = None
    if ask_gate:
        ask_artifacts = _run_ask_gate(
            ask_bundle_path,
            f"review-prompt-{run_id}-ask-gate",
            ask_model,
            ask_reasoning,
            ask_timeout,
            final_dir,
        )
        if ask_artifacts.get("status") != "passed":
            logger.error("  ASK GATE BLOCKED: verdict={}", ask_artifacts.get("verdict"))
        audit_json["ask_gate"] = ask_artifacts
        audit_json["status"] = "passed" if ask_artifacts.get("status") == "passed" and deterministic_passed else "blocked"
        _write_json(final_dir / "audit.json", audit_json)

    if webgpt_gate:
        webgpt_artifacts = _run_webgpt_gate(
            ask_bundle_path,
            webgpt_tab_id,
            webgpt_url,
            webgpt_timeout,
            final_dir,
            webgpt_no_activate=webgpt_no_activate,
            webgpt_round=webgpt_round,
        )
        if webgpt_artifacts.get("status") != "passed":
            logger.error("  WEBGPT GATE BLOCKED: verdict={}", webgpt_artifacts.get("verdict"))
        audit_json["webgpt_gate"] = webgpt_artifacts
        if audit_json.get("status") == "blocked":
            audit_json["status"] = "blocked"
        else:
            audit_json["status"] = "passed" if webgpt_artifacts.get("status") == "passed" and deterministic_passed else "blocked"
        _write_json(final_dir / "audit.json", audit_json)

    # Write rounds log
    log_file = template_path.parent / f"{template_path.stem}.review.json"
    log_file.write_text(json.dumps({
        "template": str(template_path),
        "models": models,
        "rounds": rounds_log,
        "best_score": best_score if best_score != float("inf") else None,
        "run_dir": str(run_dir),
        "ask_gate": ask_artifacts,
        "webgpt_gate": webgpt_artifacts,
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
